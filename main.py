import time

import numpy as np
import tensorflow as tf

batch_size = 128
N = 64

class FitzNag(tf.keras.layers.Layer):
    def __init__(self, units=32, **kwargs):
        super(FitzNag, self).__init__(**kwargs)
        self.units = units

    def build(self, input_shape):
        self.kernel = self.add_weight(
            'kernel',
            shape=[input_shape[-1], self.units],
            initializer='random_normal',
            dtype='float32',
            trainable=True)
        self.bias = self.add_weight(
            'bias',
            shape=[self.units, ],
            initializer='zeros',
            dtype='float32',
            trainable=True)
        a_init = tf.keras.initializers.RandomNormal(mean=1.25, stddev=0.75)
        self.a = self.add_weight(shape=(self.units,),
                                 initializer=a_init,
                                 dtype='float32',
                                 trainable=True)
        self.A = self.add_weight(shape=(self.units,), initializer="ones", dtype='float32', trainable=True)
        self.B = self.add_weight(shape=(self.units,),
                                 initializer=tf.keras.initializers.RandomNormal(mean=1., stddev=0.25),
                                 dtype='float32',
                                 trainable=True)
        self.C = self.add_weight(shape=(self.units,),
                                 initializer=tf.keras.initializers.RandomNormal(mean=2.0, stddev=0.5),
                                 dtype='float32',
                                 trainable=True)
        super(FitzNag, self).build(input_shape)

    def call(self, inputs):
        x = tf.add(tf.matmul(inputs, self.kernel), self.bias)
        return fitznag(self.a, self.A, self.B, self.C, x)

    def compute_output_shape(self, input_shape):
        return input_shape[0], self.units


@tf.custom_gradient
def fitznag(a, A, B, C, x):
    # Two exponentials in activation function (t = 1)
    e1 = tf.exp(x / 8. + (1. / 2. - a) * 1.)
    e2 = tf.exp(a * x / 8. + a * (a / 2. - 1.) * 1.)
    # print(e1)
    # print(e2)
    # Activation function - A solution of Fitzhugh-Nagumo equation
    fn = (A * e1 + a * B * e2) / (A * e1 + B * e2 + C)

    def grad(upstream):
        # Finding dfn_dx and grad_x
        diff_x1 = (A * e1 + (a ** 2) * B * e2) / (A * e1 + B * e2 + C)
        diff_x2 = ((A * e1 + a * B * e2) ** 2) / ((A * e1 + B * e2 + C) ** 2)
        dfn_dx = (diff_x1 - diff_x2) / 8.
        grad_x = upstream * dfn_dx

        grad_vars = []
        # Expressions used in dfn_da
        de1 = -1. * e1
        de2 = e2 * (x / 8. + (a - 1.) * 1.)
        # Finding dfn_da and grad_a
        diff_a1 = (A * de1 + B * (e2 + a * de2)) / (A * e1 + B * e2 + C)
        diff_a2 = ((A * e1 + a * B * e2) * (A * de1 + B * de2)) / ((A * e1 + B * e2 + C) ** 2)
        dfn_da = diff_a1 - diff_a2
        # grad_a = upstream * (diff_a1 - diff_a2)
        # Finding dfn_da and grad_A
        diff_A1 = e1 / (A * e1 + B * e2 + C)
        diff_A2 = ((A * e1 + a * B * e2) * e1) / ((A * e1 + B * e2 + C) ** 2)
        dfn_dA = diff_A1 - diff_A2
        # grad_A = upstream * (diff_A1 - diff_A2)
        # Finding dfn_da and grad_B
        diff_B1 = (a * e2) / (A * e1 + B * e2 + C)
        diff_B2 = ((A * e1 + a * B * e2) * e2) / ((A * e1 + B * e2 + C) ** 2)
        dfn_dB = diff_B1 - diff_B2
        # grad_B = upstream * (diff_B1 - diff_B2)
        # Finding dfn_da and grad_C
        diff_C1 = 0
        diff_C2 = (A * e1 + a * B * e2) / ((A * e1 + B * e2 + C) ** 2)
        dfn_dC = diff_C1 - diff_C2
        # grad_C = upstream * (diff_C1 - diff_C2)
        # grad_vars = upstream * tf.stack([dfn_da, dfn_dA, dfn_dB, dfn_dC, dfn_dw, dfn_db])
        grad_a = upstream * dfn_da
        grad_A = upstream * dfn_dA
        grad_B = upstream * dfn_dB
        grad_C = upstream * dfn_dC
        grad_vec = tf.stack([grad_a, grad_A, grad_B, grad_C])
        # print(grad_vec.shape)
        grad_vars.append(
            tf.reduce_sum(grad_vec, 1) / batch_size
        )
        grad_vars = tf.squeeze(grad_vars)
        # print(tf.shape(grad_vars))
        # Pull off the individual derivative vectors for each variable
        # Slice creates a 1xN vector and squeeze gets rid of the 1
        grad_a_new = tf.squeeze(tf.slice(grad_vars, [0, 0], [1, N]))
        grad_A_new = tf.squeeze(tf.slice(grad_vars, [1, 0], [1, N]))
        grad_B_new = tf.squeeze(tf.slice(grad_vars, [2, 0], [1, N]))
        grad_C_new = tf.squeeze(tf.slice(grad_vars, [3, 0], [1, N]))
        return grad_a_new, grad_A_new, grad_B_new, grad_C_new, grad_x  # , grad_w, grad_b

    return tf.identity(fn), grad


class ActivityRegularizationLayer(tf.keras.layers.Layer):
    def __init__(self, rate=1e-2):
        super(ActivityRegularizationLayer, self).__init__()
        self.rate = rate

    def call(self, inputs):
        self.add_loss(self.rate * tf.reduce_sum(inputs))
        return inputs


class OuterLayerWithKernelRegularizer(tf.keras.layers.Layer):
    def __init__(self):
        super(OuterLayerWithKernelRegularizer, self).__init__()
        self.dense = tf.keras.layers.Dense(
            32, kernel_regularizer=tf.keras.regularizers.l2(1e-3)
        )

    def call(self, inputs):
        return self.dense(inputs)


# model building
FN_model = tf.keras.Sequential([tf.keras.Input(shape=(28, 28, 1,), batch_size=batch_size),
                                tf.keras.layers.Conv2D(32, kernel_size=(3, 3),
                                                       activation='relu',
                                                       input_shape=(28, 28, 1)),
                                tf.keras.layers.BatchNormalization(),
                                tf.keras.layers.Conv2D(64, (3, 3), activation='relu'),
                                tf.keras.layers.BatchNormalization(),
                                tf.keras.layers.MaxPooling2D(pool_size=(2, 2)),
                                tf.keras.layers.Flatten(),
                                tf.keras.layers.BatchNormalization(),
                                FitzNag(N),
                                ActivityRegularizationLayer(),
                                # tf.keras.layers.Dense(32, activation='relu'),
                                tf.keras.layers.Dense(10, activation='softmax')])

FN_model.summary()

# Instantiate an optimizer.
# optimizer = tf.keras.optimizers.RMSprop(learning_rate=1e-4)
optimizer = tf.keras.optimizers.Adam(learning_rate=1e-3)
# Instantiate a loss function.
loss_fn = tf.keras.losses.CategoricalCrossentropy(from_logits=False)


def loss(model, x, y, training):
    # training=training is needed only if there are layers with different
    # behavior during training versus inference (e.g. Dropout).
    y_ = model(x, training=training)
    return loss_fn(y_true=y, y_pred=y_)


# def grad_loss(model, inputs, targets):
#    with tf.GradientTape() as tape:
#        loss_value = loss(model, inputs, targets, training=True)
#    return loss_value, tape.gradient(loss_value, model.trainable_variables)


# def train_step(x, y):
#    train_acc_metric = tf.keras.metrics.CategoricalAccuracy()
#    with tf.GradientTape() as tape:
#        logits = FN_model(x, training=True)
#        loss_value = loss_fn(y, logits)
#    grads_train = tape.gradient(loss_value, FN_model.trainable_variables)
#    optimizer.apply_gradients(zip(grads_train, FN_model.trainable_variables))
#    train_acc_metric.update_state(y, logits)
#    return loss_value


# def test_step(model, x, y):
#    val_acc_metric = tf.keras.metrics.CategoricalAccuracy()
#    val_logits = model(x, training=False)
#    val_acc_metric.update_state(y, val_logits)


mnist = tf.keras.datasets.mnist

(x_train, y_train), (x_test, y_test) = mnist.load_data()
x_train, x_test = x_train.astype('float32') / 255.0, x_test.astype('float32') / 255.0

# convert class vectors to binary class matrices
y_train = tf.keras.utils.to_categorical(y_train, num_classes=10)
y_test = tf.keras.utils.to_categorical(y_test, num_classes=10)

# Add a channels dimension
# x_train = x_train[..., np.newaxis].astype("float32")
# x_test = x_test[..., np.newaxis].astype("float32")

# Add batch axis
x_train = np.expand_dims(x_train, axis=-1)
x_test = np.expand_dims(x_test, axis=-1)

train_dataset = tf.data.Dataset.from_tensor_slices((x_train, y_train))
train_dataset = train_dataset.shuffle(batch_size * 50).batch(batch_size)

val_dataset = tf.data.Dataset.from_tensor_slices((x_test, y_test))
val_dataset = val_dataset.batch(batch_size)
# print(val_dataset)

epochs = 10
train_acc_metric = tf.keras.metrics.CategoricalAccuracy()
val_acc_metric = tf.keras.metrics.CategoricalAccuracy()

for epoch in range(epochs):

    print("\nStart of epoch %d" % (epoch,))
    start_time = time.time()

    epoch_loss_avg = tf.keras.metrics.Mean()
    epoch_accuracy = tf.keras.metrics.CategoricalAccuracy()

    # Iterate over the batches of the dataset.
    for step, (x_batch_train, y_batch_train) in enumerate(train_dataset):

        # loss_value = train_step(x_batch_train, y_batch_train)
        with tf.GradientTape() as tape:
            logits = FN_model(x_batch_train, training=True)
            loss_value = loss_fn(y_batch_train, logits)
            # print(loss_value)

        grads = tape.gradient(loss_value, FN_model.trainable_variables)
        # print(grads)
        optimizer.apply_gradients(zip(grads, FN_model.trainable_variables))

        if step % 100 == 0:
            print(
                "Training loss (for one batch) at step %d: %.4f"
                % (step, loss_value.numpy())
            )
            print("Seen so far: %s samples" % ((step + 1) * batch_size))

        train_acc_metric.update_state(y_batch_train, logits)

    train_acc = train_acc_metric.result()
    train_acc_metric.reset_states()
    print("Training accuracy over epoch: %.4f" % train_acc.numpy())

    # Display metrics at the end of each epoch.
    epoch_loss_avg.update_state(loss_value)  # print("Training acc over epoch: %.4f" % (float(train_acc),))

    # Reset training metrics at the end of each epoch
    epoch_accuracy.update_state(y_batch_train, FN_model(x_batch_train, training=True))

    # Run a validation loop at the end of each epoch.
    for x_batch_val, y_batch_val in val_dataset:
        val_acc_metric = tf.keras.metrics.CategoricalAccuracy()
        val_logits = FN_model(x_batch_val, training=False)
        # print(val_logits[0])
        val_acc_metric.update_state(y_batch_val, val_logits)

    val_acc = val_acc_metric.result()
    val_acc_metric.reset_states()
    print("Validation acc: %.4f" % val_acc.numpy())
    print("Time taken: %.2fs" % (time.time() - start_time))

# model.compile(optimizer='RMSprop',
#              loss='categorical_crossentropy',
#              metrics=['accuracy'])

# we'll go for 100 epochs
# history = model.fit(x_train,
#                      y_train,
#                      epochs=5,
#                      batch_size=512,
#                      validation_data=(x_test,y_test))
# history_dict = history.history
