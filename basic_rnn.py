# -*- coding:utf-8 -*-

from __future__ import print_function
import numpy as np
import tensorflow as tf
import collections
import MeCab
import sys
import random
import os.path as path
import shutil
import pickle

reload(sys)
sys.setdefaultencoding("utf-8")


## read and parse train data
vocab_size = 10000
raw_words = []
words = []

m = MeCab.Tagger()
with open('train.txt') as f:
  for line in f:
    for l in m.parse(line).splitlines():
      w = l.split()[0]
      raw_words.append(w)


## picked up most common vocab_size(=50000) words
index_of = {}
word_of = {}
count = [['UNK', -1]]

if path.exists('dictionary.pickle'):
  with open('dictionary.pickle', mode='rb') as f:
    [index_of, word_of] = pickle.load(f)
    vocab_size = len(word_of)
else: 
  count.extend(collections.Counter(raw_words).most_common(vocab_size - 1))
  index_of['UNK'] = 0
  word_of[0] = 'UNK'
  for word, _ in count:
    i = len(index_of)
    index_of[word] = i 
    word_of[i] = word
  with open('dictionary.pickle', mode='wb') as f:
    pickle.dump([index_of, word_of], f)
  vocab_size = len(word_of)

print('vocabraty size: %d' % vocab_size)


for w in raw_words:
  words.append(index_of[w])

##  trans word to sampled index 
def word_to_array(word):
  data = np.zeros(shape=(vocab_size), dtype=np.float32)

  if index_of[word] > 0:
    # known word
    data[index_of[word]] = 1
  else:
    # unknown word
    data[0] = 1

  return data

def index_to_array(i):
  data = np.zeros(shape=(vocab_size), dtype=np.float32)
  data[i] = 1
  return data

## word_from_prob
def word_from_prob(prob):
  for i in np.argmax(prob, 1):
    if i < len(word_of):
      return [word_of[i]]
    else:
      # unknown word
      return [word_of[0]]
  #return [word_of[i] for i in np.argmax(prob, 1)]

## sampling word from prediction
def sample_distribution(distribution):
  r = random.uniform(0, 1)
  s = 0
  for i in range(len(distribution)):
    s += distribution[i]
    if s >= r:
      return i
  return len(distribution) - 1

def sample(prediction):
  p = np.zeros(shape=[1, vocab_size], dtype=np.float)
  p[0, sample_distribution(prediction[0])] = 1.0
  return p

## rnn model
num_unrollings = 10
batch_size = 128 
embed_size = 64 
num_nodes = 64

graph = tf.Graph()
with graph.as_default():
  train_dataset = list()
  for i in range(num_unrollings): 
    train_dataset.append(tf.placeholder(tf.float32, shape=[batch_size, vocab_size]))

  train_labels = list()
  for i in range(num_unrollings):
    train_labels.append(tf.placeholder(tf.float32, shape=[batch_size, vocab_size]))

  # variable
  #embeddings = tf.Variable(tf.random_uniform([vocab_size, embed_size], -1.0, 1.0))
  weight = tf.Variable(tf.truncated_normal([num_nodes, vocab_size], -0.1, 0.1))
  bias = tf.Variable(tf.zeros([vocab_size]))

  # model
  lstm = tf.nn.rnn_cell.BasicLSTMCell(num_nodes)
  saved_state = tf.Variable(tf.zeros([batch_size, lstm.state_size]), trainable=False)
  
  # unrolled lstm loop
  loss = 0.0
  outputs = list()
  with tf.variable_scope("rnn") as scope:
    state = saved_state
    for current_word in train_dataset:
      embed = current_word
      #embed = tf.nn.embedding_lookup(embeddings, current_word)
      if len(outputs) > 0:
        scope.reuse_variables()
      output, state = lstm(embed, state)
      outputs.append(output) 

  with tf.control_dependencies([saved_state.assign(state)]):
    logits = tf.matmul(tf.concat(0, outputs), weight) + bias
    loss = tf.reduce_mean(tf.nn.softmax_cross_entropy_with_logits(logits, tf.concat(0, train_labels)))

  ## optimizer
  optimizer = tf.train.GradientDescentOptimizer(0.7).minimize(loss)


  ## prediction
  test_input = tf.placeholder(tf.float32, shape=[1, vocab_size])
  test_embed = test_input
  with tf.variable_scope("rnn") as scope:
    scope.reuse_variables()
    #test_embed = tf.nn.embedding_lookup(embeddings, test_input)
    saved_test_state = tf.Variable(tf.zeros([1, lstm.state_size]))
    test_output, test_state = lstm(test_embed, saved_test_state)
  with tf.control_dependencies([saved_test_state.assign(test_state)]):
    test_prediction = tf.nn.softmax(tf.matmul(test_output, weight) + bias) 



## training
skip = len(words) / batch_size
n_epochs = 5001 
with tf.Session(graph=graph) as session:
  # initialize
  tf.initialize_all_variables().run()
  saver = tf.train.Saver()
  feed_dict = dict()

  # restore model
  if path.exists("model.saved"):
    saver.restore(session, "model.saved")

  # train
  for epoch in range(n_epochs):
    for i in range(num_unrollings):
      dataset = []
      labels = []
      # labels_i = []

      for j in range(batch_size): 
        # dataset.append(words[(j * skip + i) % len(words)])
        dataset.append(index_to_array(words[(j * skip + i) % len(words)]))
        labels.append(index_to_array(words[(j * skip + i + 1) % len(words)]))
        # labels_i.append(words[(j * skip + i + 1) % len(words)])
      
      feed_dict[train_dataset[i]] = dataset
      feed_dict[train_labels[i]] = labels
      # print('num_unrolling: %d' % i)
      # print(dataset)
      # print(labels_i)
      # for l in labels:
      #   print(len(l))
      #   for m in range(len(l)):
      #     if l[m] == 1:
      #       print(m)

    #print(feed_dict[train_dataset[0]])
    _, l = session.run([optimizer, loss], feed_dict=feed_dict)

    # print loss
    if(epoch % 100 == 0):
      print('Loss at epoch %d: %f' % (epoch, l))

    # sample prediction
    if(epoch % 500 == 0):
      print("Sample Prediction:")
      for _ in range(1):
        test_data = [random.choice(index_of.values())]
        sentence = word_of[test_data[0]]
        test_data = [index_to_array(test_data[0])]
        for _ in range(100):
          prediction = test_prediction.eval({test_input: test_data})
          w = word_from_prob(sample(prediction))[0]
          sentence += w
          #sentence += " "
          test_data = [index_to_array(index_of[w])]
        print(sentence)

    # save trained model by epoch
    #shutil.copyfile("model.saved", "model.saved.bak")
  saver.save(session, "model.saved")

