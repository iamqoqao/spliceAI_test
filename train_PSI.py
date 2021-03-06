from model import *
from utils import *

from sklearn.model_selection import train_test_split

import tensorflow as tf

import keras
from keras.optimizers import Adam
from keras.callbacks import LearningRateScheduler

import math
import numpy as np
import time

print('eagerly?', tf.executing_eagerly())

# TRAINING PARAMETERS
batch_size = 128
num_classes = 1
epochs = 1

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

start_time = time.time()

# importing the data
transcripts = np.loadtxt('./data/transcripts_HEX_chr21', dtype='str', delimiter='\t')
labels = np.loadtxt('./data/labels_HEX_chr21', dtype='str', delimiter='\t')

# one-hot-encoding
transcripts_ = []
labels_ = []

for i in range(len(transcripts)):
    # hot-encode seq
    transcripts_.append([np.array(hot_encode_seq(let)) for let in transcripts[i]])
    labels_.append([float(x) for x in labels[i]])

transcripts = np.array(transcripts_)
labels = np.array(labels_)

(x_train, x_test, y_train, y_test) = train_test_split(transcripts,
                                                      labels, test_size=0.2)

input_shape = x_train.shape[1:]

print('x_train shape:', x_train.shape)
print(x_train.shape[0], 'train samples')
print(x_test.shape[0], 'test samples')
print('y_train shape:', y_train.shape)

print("Data prep: {} seconds".format(time.time() - start_time))

lr_scheduler = LearningRateScheduler(lr_schedule)

model = spliceAI_model(input_shape=input_shape, num_classes=num_classes)

model.compile(loss=MSE_masked,
              optimizer=Adam(learning_rate=lr_schedule(0)),
              metrics=tf.keras.metrics.MeanSquaredError())

print(model.summary())

start_time = time.time()
training_generator = DataGenerator(x_train, y_train, batch_size)

for e in range(1, 5):
    model.fit(training_generator, epochs=e+1, initial_epoch=e, callbacks=[lr_scheduler], shuffle=True)
    model.save('./data/model_regression_HEX_chr21')

print("Fitting: {} seconds".format(time.time() - start_time))

scores = model.evaluate(x_test, y_test, verbose=1)
print('Test loss:', scores[0])
print('Test accuracy:', scores[1])
