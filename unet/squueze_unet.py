# -*- coding: utf-8 -*-
"""squueze-unet

## Import Libraries
"""

from __future__ import print_function

import os
import skimage.io as io
import skimage.transform as trans
import shutil
import cv2
import matplotlib.pyplot as plt
import pickle
import time
import glob

import numpy as np
import keras
from keras.models import Model
from keras.layers import Input, merge, Convolution2D, MaxPooling2D, UpSampling2D
from keras.optimizers import Adam
from keras.optimizers import SGD
from keras.callbacks import ModelCheckpoint, LearningRateScheduler
from keras.layers import Conv2D, MaxPooling2D, UpSampling2D, Dropout
from keras.layers import concatenate, Conv2DTranspose, BatchNormalization
from keras import backend as K

from keras import backend as keras

from keras.layers import Dropout

from sklearn.externals import joblib
import argparse
from keras.callbacks import *
import sys
import theano
import theano.tensor as T
from keras import initializers
from keras.layers import BatchNormalization
import copy
import tensorflow as tf

from keras.models import *
from keras.layers import *
from keras.optimizers import *
from tensorflow.keras.models import load_model as load_initial_model
from keras.preprocessing.image import ImageDataGenerator
from keras.losses import binary_crossentropy

import gc

def dice_coef(y_true, y_pred):
  smooth = 0.0
  y_true_f = keras.flatten(y_true)
  y_pred_f = keras.flatten(y_pred)
  intersection = keras.sum(y_true_f * y_pred_f)
  return (2. * intersection + smooth) / (keras.sum(y_true_f) + keras.sum(y_pred_f) + smooth)

def jacard(y_true, y_pred):

  y_true_f = keras.flatten(y_true)
  y_pred_f = keras.flatten(y_pred)
  intersection = keras.sum ( y_true_f * y_pred_f)
  union = keras.sum ( y_true_f + y_pred_f - y_true_f * y_pred_f)

  return intersection/union

def dice_coef_loss(y_true, y_pred):
    return 1. - dice_coef(y_true, y_pred)

def cross_entropy(p, q):
	  return -sum([p[i]*log2(q[i]) for i in range(len(p))])

"""## Squeeze U-Net Model"""

def fire_module(x, fire_id, squeeze=16, expand=64):
    f_name = "fire{0}/{1}"
    channel_axis = 1 if K.image_data_format() == 'channels_first' else -1

    x = Conv2D(squeeze, (1, 1), activation='relu', padding='same', name=f_name.format(fire_id, "squeeze1x1"))(x)
    x = BatchNormalization(axis=channel_axis)(x)

    left = Conv2D(expand, (1, 1), activation='relu', padding='same', name=f_name.format(fire_id, "expand1x1"))(x)
    right = Conv2D(expand, (3, 3), activation='relu', padding='same', name=f_name.format(fire_id, "expand3x3"))(x)
    x = concatenate([left, right], axis=channel_axis, name=f_name.format(fire_id, "concat"))
    return x


def SqueezeUNet(inputs, num_classes=None, deconv_ksize=3, dropout=0.5, activation='sigmoid'):
    """SqueezeUNet is a implementation based in SqueezeNetv1.1 and unet for semantic segmentation
    :param inputs: input layer.
    :param num_classes: number of classes.
    :param deconv_ksize: (width and height) or integer of the 2D deconvolution window.
    :param dropout: dropout rate
    :param activation: type of activation at the top layer.
    :returns: SqueezeUNet model
    """
    channel_axis = 1 if K.image_data_format() == 'channels_first' else -1
    if num_classes is None:
        num_classes = K.int_shape(inputs)[channel_axis]

    x01 = Conv2D(64, (3, 3), strides=(2, 2), padding='same', activation='relu', name='conv1')(inputs)
    x02 = MaxPooling2D(pool_size=(3, 3), strides=(2, 2), name='pool1', padding='same')(x01)

    x03 = fire_module(x02, fire_id=2, squeeze=16, expand=64)
    x04 = fire_module(x03, fire_id=3, squeeze=16, expand=64)
    x05 = MaxPooling2D(pool_size=(3, 3), strides=(2, 2), name='pool3', padding="same")(x04)

    x06 = fire_module(x05, fire_id=4, squeeze=32, expand=128)
    x07 = fire_module(x06, fire_id=5, squeeze=32, expand=128)
    x08 = MaxPooling2D(pool_size=(3, 3), strides=(2, 2), name='pool5', padding="same")(x07)

    x09 = fire_module(x08, fire_id=6, squeeze=48, expand=192)
    x10 = fire_module(x09, fire_id=7, squeeze=48, expand=192)
    x11 = fire_module(x10, fire_id=8, squeeze=64, expand=256)
    x12 = fire_module(x11, fire_id=9, squeeze=64, expand=256)

    if dropout != 0.0:
        x12 = Dropout(dropout)(x12)

    up1 = concatenate([
        Conv2DTranspose(192, deconv_ksize, strides=(1, 1), padding='same')(x12),
        x10,
    ], axis=channel_axis)
    up1 = fire_module(up1, fire_id=10, squeeze=48, expand=192)

    up2 = concatenate([
        Conv2DTranspose(128, deconv_ksize, strides=(1, 1), padding='same')(up1),
        x08,
    ], axis=channel_axis)
    up2 = fire_module(up2, fire_id=11, squeeze=32, expand=128)

    up3 = concatenate([
        Conv2DTranspose(64, deconv_ksize, strides=(2, 2), padding='same')(up2),
        x05,
    ], axis=channel_axis)
    up3 = fire_module(up3, fire_id=12, squeeze=16, expand=64)

    up4 = concatenate([
        Conv2DTranspose(32, deconv_ksize, strides=(2, 2), padding='same')(up3),
        x02,
    ], axis=channel_axis)
    up4 = fire_module(up4, fire_id=13, squeeze=16, expand=32)
    up4 = UpSampling2D(size=(2, 2))(up4)

    x = concatenate([up4, x01], axis=channel_axis)
    x = Conv2D(64, (3, 3), strides=(1, 1), padding='same', activation='relu')(x)
    x = UpSampling2D(size=(2, 2))(x)
    x = Conv2D(num_classes, (1, 1), activation=activation)(x)
    model = Model(inputs, x)
    #model.summary()
    model.compile(optimizer=Adam(lr = 1e-4), loss=binary_crossentropy, metrics = ['accuracy',dice_coef,jacard,tf.keras.metrics.MeanIoU(num_classes=2),
                                                                                      tf.keras.metrics.Precision(), tf.keras.metrics.Recall()])
                                                                                      
    return model

