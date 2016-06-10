import matplotlib.pyplot as plt
import os
import numpy as np
import pandas as pd
import tensorflow as tf
import random

os.chdir('/media/OS/Users/Nash Taylor/Documents/My Documents/School/Machine Learning Nanodegree/Capstone')

# get data
df = pd.read_csv('featuresets/features-Rt.csv', nrows=220000)

# standardize and remove outliers


# shuffle data to eliminate dependencies or relationships in minibatches
df = df.iloc[np.random.permutation(len(df))]
df = df.reset_index(drop=True)

# convert label to int
le = ['fold','call','raise0.0','raise0.25','raise0.5','raise0.75','raise1.0','raise2.0']

# split data
X = df.ix[:, ~(df.columns.isin(['Action','Player']))]
y = df.Action.apply(lambda x: le.index(x))

dfSizes = {'train': 10./11, 'test': 1./22, 'valid': 1./22}
dfSizes = {k: int(v*df.shape[0]) for k,v in dfSizes.iteritems()}

X_train = X[:dfSizes['train']].as_matrix().astype(np.float32)
y_train = y[:dfSizes['train']].as_matrix()
X_valid = X[dfSizes['train']:(dfSizes['train']+dfSizes['valid'])].as_matrix().astype(np.float32)
y_valid = y[dfSizes['train']:(dfSizes['train']+dfSizes['valid'])].as_matrix()
X_test = X[dfSizes['valid']:(dfSizes['valid']+dfSizes['test'])].as_matrix().astype(np.float32)
y_test = y[dfSizes['valid']:(dfSizes['valid']+dfSizes['test'])].as_matrix()

y_train = np.array([random.choice(range(8)) for i in xrange(len(y_train))])
y_valid = np.array([random.choice(range(8)) for i in xrange(len(y_train))])
y_test = np.array([random.choice(range(8)) for i in xrange(len(y_train))])

print X_train.shape[0], X_valid.shape[0], X_test.shape[0]

# change all labels to one-hot vectors
n_labels = len(df.Action.unique())
y_train = (np.arange(n_labels) == y_train[:,None]).astype(np.float32)
y_valid = (np.arange(n_labels) == y_valid[:,None]).astype(np.float32)
y_test = (np.arange(n_labels) == y_test[:,None]).astype(np.float32)

# hyperparameters
h1units = 30
h2units = 10

batch_size = 200
sd = 0.1
avg = 0.01
nl = tf.nn.relu

# to be used for results
def accuracy(predictions, labels):
    return (100.0 * np.sum(np.argmax(predictions, 1) == np.argmax(labels, 1))
          / predictions.shape[0])

# Set up computation graph
graph = tf.Graph()

with graph.as_default():
    # data placeholders
    X_trainPH = tf.placeholder(tf.float32, shape=(batch_size, X_train.shape[1]))
    y_trainPH = tf.placeholder(tf.float32, shape=(batch_size, n_labels))
    X_validPH = tf.constant(X_valid)
    X_testPH = tf.constant(X_test)
    
    # hidden layer 1
    weights1 = tf.Variable(tf.truncated_normal([X_train.shape[1], h1units], stddev=sd, mean=avg))
    biases1 = tf.Variable(tf.zeros([h1units]))
    logits1 = nl(tf.add(tf.matmul(X_trainPH, weights1), biases1))
    
    # dropout layer 1
    #logits1 = tf.nn.dropout(logits1, keep_prob)
    
    # hidden layer 2
    weights2 = tf.Variable(tf.truncated_normal([h1units, h2units], stddev=sd, mean=avg))
    biases2 = tf.Variable(tf.zeros([h2units]))
    logits2 = nl(tf.add(tf.matmul(logits1, weights2), biases2))
    
    # dropout layer 2
    #logits2 = tf.nn.dropout(logits2, keep_prob)
        
    # final layer
    weightsF = tf.Variable(tf.truncated_normal([h2units, n_labels], stddev=sd, mean=avg))
    biasesF = tf.Variable(tf.zeros([n_labels]))
    
    # make logits
    logitsF = tf.add(tf.matmul(logits2, weightsF), biasesF)
    
    # compute loss
    loss = tf.reduce_mean(tf.nn.softmax_cross_entropy_with_logits(logitsF, y_trainPH))
    
    # optimize
    optimizer = tf.train.GradientDescentOptimizer(0.5).minimize(loss)
    
    # create train predictions
    trainPrediction = tf.nn.softmax(logitsF)
    
    # create validation predictions
    validLogits1 = tf.nn.relu(tf.add(tf.matmul(X_valid, weights1), biases1))
    validLogits2 = tf.nn.relu(tf.add(tf.matmul(validLogits1, weights2), biases2))
    validLogitsF = tf.add(tf.matmul(validLogits2, weightsF), biasesF)
    validPrediction = tf.nn.softmax(validLogitsF)
    
    # create test predictions
    testLogits1 = tf.nn.relu(tf.add(tf.matmul(X_test, weights1), biases1))
    testLogits2 = tf.nn.relu(tf.add(tf.matmul(testLogits1, weights2), biases2))
    testLogitsF = tf.add(tf.matmul(testLogits2, weightsF), biasesF)
    testPrediction = tf.nn.softmax(testLogitsF)


# Run computation graph
num_steps = 3001
#lastValidationAccuracy = -0.01
with tf.Session(graph=graph) as session:
    tf.initialize_all_variables().run()
    print("Initialized")
    for step in range(num_steps):
        # generate minibatch
        offset = (step * batch_size) % (y_train.shape[0] - batch_size)
        batch_data = X_train[offset:(offset + batch_size), :]
        batch_labels = y_train[offset:(offset + batch_size), :]
        
        # data to feed graph
        feed_dict = {X_trainPH : batch_data, y_trainPH : batch_labels}
        
        # results from running graph on this minibatch
        _, l, predictions = session.run(
            [optimizer, loss, trainPrediction], feed_dict=feed_dict)
            
        # status print
        if (step % 500 == 0):
            vAccuracy = accuracy(validPrediction.eval(), y_valid)
            print "Minibatch loss at step %d: %f" % (step, l)
            print "Minibatch accuracy: %.1f%%" % accuracy(predictions, batch_labels)
            print "Validation accuracy: %.1f%%" % vAccuracy
                
            #if lastValidationAccuracy - vAccuracy > 0.001:
                #break
            
            #lastValidationAccuracy = vAccuracy
    
    # test accuracy
    print "Test accuracy: %.1f%%" % accuracy(testPrediction.eval(), y_test)