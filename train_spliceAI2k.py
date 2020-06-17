from __future__ import print_function
import keras
from keras.layers import Dense, Conv1D, BatchNormalization, Activation, Dropout
from keras.layers import AveragePooling2D, Input, Flatten, MaxPooling2D, Cropping1D
from keras.optimizers import Adam
from keras.callbacks import LearningRateScheduler
from keras import backend as K
from keras.models import Model, Sequential
from keras import optimizers
from keras import metrics
import keras.backend as K

import math

import tensorflow as tf
print('eagerly?', tf.executing_eagerly())

from sklearn.model_selection import train_test_split
from sklearn.metrics import confusion_matrix, classification_report

import numpy as np

def hot_encode_seq(let):
    if let=='A':
        return([1,0,0,0])
    elif let=='T':
        return([0,1,0,0])
    elif let=='C':
        return([0,0,1,0])
    elif let=='G':
        return([0,0,0,1])
    elif let=='O':
        return([0,0,0,0])

def hot_encode_label(let):
    if let=='p':
        return([0,0,0])
    elif let=='b':
        return([1,0,0])
    elif let=='a':
        return([0,1,0])
    elif let=='d':
        return([0,0,1])

def dehot_encode_label(let):
    if (let==[0,0,0]).all():
        return('p')
    elif (let==[1,0,0]).all():
        return('b')
    elif (let==[0,1,0]).all():
        return('a')
    elif (let==[0,0,1]).all():
        return('d')

def dehot_encode_pred(let):
    if np.argmax(let)==0:
        return('b')
    elif np.argmax(let)==1:
        return('a')
    elif np.argmax(let)==2:
        return('d')

def transform_input(transcripts_, labels_):
    transcripts = []
    labels = []
    # hot-encode
    for i in range(len(transcripts_)):
        # hot-encode seq
        transcripts.append([np.array(hot_encode_seq(let)) for let in transcripts_[i]])
        # hot-encode labels
        labels.append([np.array(hot_encode_label(x)) for x in labels_[i]])
    return transcripts, labels

def transform_output(y_test, y_pred):
    y_test_, y_pred_ = [], []
    for vector in y_test:
        y_test_.append([dehot_encode_label(x) for x in vector])
    for vector in y_pred:
        y_pred_.append([dehot_encode_pred(x) for x in vector])
    return y_test_, y_pred_

def lr_schedule(epoch):
    lr = 0.001
    if epoch == 7:
        lr *= 0.5
    elif epoch == 8:
        lr *= (0.5)**2
    elif epoch == 9:
        lr *= (0.5)**3
    elif epoch == 10:
        lr *= (0.5)**4
    print('Learning rate: ', lr)
    return lr


# TRAINING PARAMETERS
batch_size = 128
num_classes = 3
epochs = 10


class DataGenerator(keras.utils.Sequence):
    
    def __init__(self, x_set, y_set, batch_size):
        self.x, self.y = x_set, y_set
        self.batch_size = batch_size

    def __len__(self):
        return math.ceil(len(self.x) / self.batch_size)

    def __getitem__(self, idx):
        batch_x = self.x[idx * self.batch_size:(idx + 1) *
        self.batch_size]
        batch_y = self.y[idx * self.batch_size:(idx + 1) *
        self.batch_size]

        return np.array(batch_x), np.array(batch_y)

#@tf.function 
def custom_crossentropy_loss(y_true, y_pred):
    
    # clip the predicted values so we never have to calc log of 0
    # norm the probas so the sum of all probas for one observation is 1
    y_pred /= tf.expand_dims(tf.reduce_sum(y_pred, axis=-1), -1)
    y_pred = tf.keras.backend.clip(y_pred, 1e-15, 1-1e-15)
    
    # mask for blank, donor, acceptor sites 
    mask_b = np.array([True, False, False])
    mask_a = np.array([False, True, False])
    mask_d = np.array([False, False, True])
    
    # normalize the labels by the number of samples of each class
    labels_b = tf.squeeze(tf.boolean_mask(y_true, mask_b, axis=2))
    labels_b /= tf.add(tf.expand_dims(tf.reduce_sum(labels_b, axis=-1), -1), tf.constant(1e-15))
    
    labels_a = tf.squeeze(tf.boolean_mask(y_true, mask_a, axis=2))
    labels_a /= tf.add(tf.expand_dims(tf.reduce_sum(labels_a, axis=-1), -1), tf.constant(1e-15))
    
    labels_d = tf.squeeze(tf.boolean_mask(y_true, mask_d, axis=2))
    labels_d /= tf.add(tf.expand_dims(tf.reduce_sum(labels_d, axis=-1), -1), tf.constant(1e-15))
    
    # stack everything back normalized
    labels_norm = tf.stack([labels_b, labels_a, labels_d], axis=-1)
    
    return -tf.reduce_sum(labels_norm*tf.keras.backend.log(y_pred))


def RB_block(inputs,
             num_filters=32,
             kernel_size=11,
             strides=1,
             activation='relu',
             dilation_rate=1):
    """1D Convolution-Batch Normalization-Activation stack builder

    # Arguments
        inputs (tensor): input tensor from input image or previous layer
        num_filters (int): Conv2D number of filters
        kernel_size (int): Conv2D square kernel dimensions
        strides (int): Conv2D square stride dimensions
        activation (string): activation name
        dilation rate (int): dilation rate

    # Returns
        x (tensor): tensor as input to the next layer
    """
    conv = Conv1D(num_filters,
                  kernel_size=kernel_size,
                  strides=strides,
                  padding='same',
                  dilation_rate=dilation_rate)

    x = inputs

    for layer in range(2):
        x = BatchNormalization()(x)
        x = Activation(activation)(x)
        x = conv(x)

    return x


def spliceAI_model(input_shape, num_classes=3):
    """Model builder

    Shortcut layers after every 4 RB blocks.

    # Arguments
        input_shape (tensor): shape of input image tensor
        num_classes (int): number of classes

    # Returns
        model (Model): Keras model instance
    """
    inputs = Input(shape=input_shape)

    # initiate 
    x = Conv1D(32, kernel_size=1, strides=1, padding='same', dilation_rate=1)(inputs)

    # another Conv on x before splitting
    y = Conv1D(32, kernel_size=1, strides=1, padding='same', dilation_rate=1)(x)

    # RB 1: 32 11 1
    for stack in range(4):
        x = RB_block(x, num_filters=32, kernel_size=11, strides=1, activation='relu', dilation_rate=1)

    y = keras.layers.add([Conv1D(32, kernel_size=1, strides=1, padding='same', dilation_rate=1)(x), y])

    # RB 2: 32 11 4
    for stack in range(4):
        x = RB_block(x, num_filters=32, kernel_size=11, strides=1, activation='relu', dilation_rate=4)

    y = keras.layers.add([Conv1D(32, kernel_size=1, strides=1, padding='same', dilation_rate=1)(x), y])  
    # RB 3: 32 21 10
    for stack in range(4):
        x = RB_block(x, num_filters=32, kernel_size=21, strides=1, activation='relu', dilation_rate=10)

    x = Conv1D(32, kernel_size=1, strides=1, padding='same', dilation_rate=1)(x)

    # adding up with what was shortcut from the prev layers
    x = keras.layers.add([x, y]) 

    x = Conv1D(3, kernel_size=1, strides=1, padding='same', dilation_rate=1)(x)

    x = Dense(num_classes, activation='softmax')(x)

    # crop to fit the labels (7k to 5k)
    outputs = Cropping1D(cropping=(1000, 1000))(x)

    model = Model(inputs=inputs, outputs=outputs)

    return model


# importing the data
transcripts = np.loadtxt('./data/transcripts_chr21', dtype='str', delimiter='\t')
labels = np.loadtxt('./data/labels_chr21', dtype='str', delimiter='\t')

# one-hot-encoding
transcripts, labels = transform_input(transcripts, labels)

transcripts = np.array(transcripts)
labels = np.array(labels)

(x_train, x_test, y_train, y_test) = train_test_split(transcripts,
    labels, test_size=0.2)

input_shape = x_train.shape[1:]

print('x_train shape:', x_train.shape)
print(x_train.shape[0], 'train samples')
print(x_test.shape[0], 'test samples')
print('y_train shape:', y_train.shape)

lr_scheduler = LearningRateScheduler(lr_schedule)

model = spliceAI_model(input_shape=input_shape)

model.compile(loss=custom_crossentropy_loss,
              optimizer=Adam(learning_rate=lr_schedule(0)),
              metrics=['accuracy'])

print(model.summary())

training_generator = DataGenerator(x_train, y_train, batch_size)

#model.fit(x_train, y_train, batch_size=batch_size, epochs=epochs, callbacks=[lr_scheduler], validation_split=0.1, shuffle=True)
model.fit(training_generator, epochs=epochs, callbacks=[lr_scheduler], shuffle=True)

model.save('./data/model_spliceAI2k')

scores = model.evaluate(x_test, y_test, verbose=1)
print('Test loss:', scores[0])
print('Test accuracy:', scores[1])

y_pred = model.predict(x_test)

y_test, y_pred = transform_output(y_test, y_pred)

donor_t_p, acceptor_t_p, blank_t_p = 0, 0, 0
donor, acceptor, blank = 0, 0, 0 

for i in range(len(y_test)):
    for j in range(len(y_test[0])):
        if y_test[i][j]==y_pred[i][j] and y_test[i][j]=='d':
            donor += 1
            donor_t_p += 1
        elif y_test[i][j]==y_pred[i][j] and y_test[i][j]=='a':
            acceptor += 1
            acceptor_t_p += 1
        elif y_test[i][j]==y_pred[i][j] and y_test[i][j]=='b':
            blank += 1
            blank_t_p += 1
        elif y_test[i][j]=='d':
            donor += 1
        elif y_test[i][j]=='a':
            acceptor += 1
        elif y_test[i][j]=='b':
            blank += 1
            
print("Out of {} blank {} TP, out of {} donor {} TP, out of {} acceptor {} TP".format(blank, blank_t_p, donor, donor_t_p, acceptor, acceptor_t_p))