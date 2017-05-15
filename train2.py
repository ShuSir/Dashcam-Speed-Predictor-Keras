import os
import numpy as np
import tensorflow as tf
import cv2
import argparse
from keras.applications import imagenet_utils
from keras.preprocessing.image import img_to_array, load_img, ImageDataGenerator
from keras.models import Sequential, Model
from keras.models import model_from_json
from keras.optimizers import RMSprop
from keras.layers.advanced_activations import LeakyReLU
from keras.layers.core import Reshape
from keras.layers import Dropout, Flatten, Dense, Conv2D, LSTM, Merge, Bidirectional, Activation, TimeDistributed, GRU, MaxPooling2D, Input, BatchNormalization, GlobalAveragePooling2D, SeparableConv2D, Cropping2D
from keras.callbacks import TensorBoard, EarlyStopping, ModelCheckpoint, History
from random import randint
from keras import backend as K


# fix random seed for reproducibility
np.random.seed(2000)
# dimensions of our images.
img_width, img_height = 150,150
nb_train_samples = 14280
nb_validation_samples = 6120
train_batch_size=10
validation_batch_size=10
val_steps=10
train_steps=10
nb_epoch=100
channels=3 #RGB
timesteps=3
nb_conv_layers=1
nb_rnn_layers = 1
frequency=60 #Gap between frames

global trainbag, validationbag
train_index_pointer = list(np.linspace(1,nb_train_samples-1, nb_train_samples, dtype=np.int64))
validation_index_pointer = list(np.linspace(1,nb_validation_samples-1, nb_validation_samples, dtype=np.int64))
trainbag=len(train_index_pointer)
validationbag=len(validation_index_pointer)

instance_flag=0 #0 for loading data from Local, 1 for FloydHub instance


if instance_flag==0:
    root_dir, _ = os.path.split(os.path.abspath(__file__))
    train_root_dir = root_dir + '/data/images/train'
    val_root_dir = root_dir + '/data/images/validation'
    speeds = np.loadtxt(root_dir + '/data/train.txt')
else:
    train_root_dir =  '/input/images/train'
    val_root_dir = '/input/images/validation'
    speeds = np.loadtxt('/input/train.txt')

def train():
    
    if instance_flag==0:
        checkpointer = ModelCheckpoint(filepath="./weights/dashcam_weights-{epoch:02d}-{val_mean_squared_error:.2f}.hdf5", verbose=1, save_best_only=True)
        tensorboard = TensorBoard(log_dir='./logs/', histogram_freq=0, write_graph=True, write_images=False)
        history = LossHistory()
    else:
        checkpointer = ModelCheckpoint(filepath="/output/weights/dashcam_weights-{epoch:02d}-{val_mean_squared_error:.2f}.hdf5", verbose=1, save_best_only=True)
        tensorboard = TensorBoard(log_dir='/output/logs', histogram_freq=0, write_graph=True, write_images=False)

    y_train= speeds[0:nb_train_samples]
    y_validation= speeds[nb_train_samples:len(speeds)]

    y_train=np.expand_dims(y_train, axis=-1)
    y_validation=np.expand_dims(y_train, axis=-1)

    print('Building Model...')

    model = buildmodel(summary=1)
    train_generator = generator(y_train, 0)
    validation_generator = generator(y_validation, 1)


    earlyStopping= EarlyStopping(monitor='val_mean_squared_error', patience=10, verbose=1, mode='auto')

    print('Training...')
    
    model.fit_generator(train_generator, steps_per_epoch=50, epochs=20, verbose=1, validation_data=validation_generator, validation_steps=10, callbacks=[tensorboard, earlyStopping, checkpointer])
    
        # serialize model to JSON
    model_json = model.to_json()
    with open("./model/speed-predictor-keras-model-{val_mean_squared_error:.2f}.json", "w") as json_file:
        json_file.write(model_json)
    # serialize weights to HDF5
    print("Saving Model to disk...")
    print('Saving History...')
    if instance_flag==0:
        loss_history = model.History()
        numpy_loss_history = np.array(loss_history)
        np.savetxt("./loss_history.txt", numpy_loss_history, delimiter=",")
    else:
        np.savetxt("/ouput/logs/loss_history.txt", numpy_loss_history, delimiter=",")
    return

def buildmodel(summary):

    #Define hyperparameters
    
    lr = 0.001
    weight_init='glorot_uniform'
    stateful=False
    Act =LeakyReLU(alpha=7.0)
    #l1_gru=0.1
    #l2_gru=0.5
    #l1_dense=0.1
    #l2_dense=0.5
    #l1_conv=0.1
    #l2_conv=0.5

    data= Input(shape=(None,img_width,img_height,channels))
    #Define Sequential Model
    convs= Sequential()
    convs.add(BatchNormalization(axis=3, input_shape=(img_width,img_height, channels)))
    convs.add(Cropping2D(cropping=((60,10),(10,10))))
    convs.add(Conv2D(8, (3, 3), kernel_initializer=weight_init, padding="same", bias=False, activation='relu'))
    convs.add(Conv2D(16, (3, 3), kernel_initializer=weight_init, padding="same", bias=False, activation='relu'))
    convs.add(Conv2D(32, (3, 3), kernel_initializer=weight_init, padding="same", bias=False, activation='relu'))
    convs.add(MaxPooling2D((2, 2), strides=(2, 2), padding='same'))
    convs.add(Conv2D(16, (3, 3), kernel_initializer=weight_init, padding="same", bias=False, activation='relu'))
    convs.add(Conv2D(32, (3, 3), kernel_initializer=weight_init, padding="same", bias=False, activation='relu'))
    convs.add(GlobalAveragePooling2D())
    
    x=TimeDistributed(convs)(data)

    x=Bidirectional(GRU(32, activation='relu', kernel_initializer=weight_init, recurrent_activation='hard_sigmoid',return_sequences=False, input_shape=(timesteps,None)))(x)
    #x=Bidirectional(GRU(16, activation='relu', kernel_initializer=weight_init, recurrent_activation='hard_sigmoid', return_sequences=False))(x)
    x = Dense(units=64, kernel_initializer=weight_init, bias=False)(x)
    x =Act(x)
    x=Dropout(0.2)(x)
    x = Dense(units=4, kernel_initializer=weight_init, bias=False)(x)
    x =Act(x)
    x=Dropout(0.2)(x)
    x=Dense(1, init=weight_init, activation='linear')(x)

    model=Model(inputs=data, outputs=x)

    #sgd = SGD(lr=lr, decay=1e-6, momentum=0.8, nesterov=True, clipnorm=0.3)
    optimize=RMSprop(lr=lr, decay=1e-6)
    print('Compiling Model...')
    model.compile(optimizer=optimize,
        loss=l1_smooth_loss,
        metrics=['mse'])
    
    if summary:
        print(model.summary())
        return model

def preprocess_img(img):
    #Histogram normalization in v channel
    # central square crop
    min_side = min(img.shape[:-1])
    centre = img.shape[0]//2, img.shape[1]//2
    img = img[centre[0]-min_side//2:centre[0]+min_side//2,
              centre[1]-min_side//2:centre[1]+min_side//2,
              :]
    # rescale to standard size
    img = cv2.resize(img,(img_width, img_height), interpolation = cv2.INTER_AREA)

    #img=np.array(img, dtype=np.uint8)
    #-----Converting image to LAB Color model----------------------------------- 
    lab= cv2.cvtColor(img, cv2.COLOR_BGR2LAB)

    #-----Splitting the LAB image to different channels-------------------------
    l, a, b = cv2.split(lab)

    #-----Applying CLAHE to L-channel-------------------------------------------
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
    cl = clahe.apply(l)

    #-----Merge the CLAHE enhanced L-channel with the a and b channel-----------
    limg = cv2.merge((cl,a,b))

    #-----Converting image from LAB Color model to RGB model--------------------
    
    img = cv2.cvtColor(limg, cv2.COLOR_LAB2BGR)
    img= np.array(img, dtype=np.float)
    img/= 255.0
    #img = np.swapaxes(img,0,1)
    img=np.expand_dims(img,axis=0)

    # roll color axis to axis 0
    #img = np.swapaxes(img,0,1)

    return img

#Define Smooth L1 Loss
def l1_smooth_loss(y_true, y_pred):
    abs_loss = tf.abs(y_true - y_pred)
    sq_loss = 0.5 * (y_true - y_pred)**2
    l1_loss = tf.where(tf.less(abs_loss, 1.0), sq_loss, abs_loss - 0.5)
    return tf.reduce_sum(l1_loss, -1)    

def generator(labels, flag):
    count=0
    dataX=[]
    dataY=[]
    batch_features=[]
    batch_labels=[]

    
    #print('Generator Active')
    
    while True:

        if flag == 0:
            batch_size=train_batch_size
            #trainbag=len(train_index_pointer)
            #if trainbag<timesteps:
                #print("Out of Novel Train Data")
                #break
            #else:
            ind = np.random.randint(1000,nb_train_samples-1000)
            
            index = '{:0>5}'.format(ind)
            dataX = cv2.imread(train_root_dir + '/frame-' + index + '.jpeg',3)
            dataX =  preprocess_img(dataX)
            dataY = labels[ind]
        else:
            batch_size=validation_batch_size
            #validationbag=len(validation_index_pointer)
            #if validationbag<timesteps:
                #print("Out of Validation Data")
                #break
            #else:
            ind = np.random.randint(1000,nb_validation_samples-1000)
            index = ind + nb_train_samples
            index='{:0>5}'.format(index)
            #dataX = imageio.imread(val_root_dir + '/frame-' + index + '.jpeg')
            dataX = cv2.imread(val_root_dir + '/frame-' + index + '.jpeg',3)
            dataX=preprocess_img(dataX)
            dataY = labels[ind]
            #print("initial datax shape=", dataX.shape)
            #print("Validation Dataset Size", validationbag)


        #Create One sample of (timesteps, features_size)
        for j in range(1,timesteps):
            
            pointer = ind-(j*frequency)
            if pointer<0:
               pointer = nb_train_samples + pointer
            
            #If using Validation, Reformat pointer according to filenames.
            if flag==1:
                pointer = pointer + nb_train_samples
                pointstr='{0:0>5}'.format(pointer)
                img = cv2.imread(val_root_dir + '/frame-' + pointstr + '.jpeg',3)
                #img = imageio.imread(val_root_dir + '/frame-' + pointstr + '.jpeg')
                img=preprocess_img(img)

            else:
                pointstr='{0:0>5}'.format(pointer)
                #img = imageio.imread(train_root_dir + '/frame-' + pointstr + '.jpeg')
                img = cv2.imread(train_root_dir + '/frame-' + pointstr + '.jpeg',3)
                img=preprocess_img(img)
            
            
            dataX=np.append(dataX, img, axis=0)
            #print("datax shape=" , dataX.shape)

        X_train=np.expand_dims(dataX, axis=0)
        #Stack samples to create batch
        if count==0:
            batch_features = X_train
            batch_labels=dataY
        else:
            batch_features=np.append(batch_features, X_train, axis=0)
            batch_labels = np.append(batch_labels, dataY, axis=0)
        
        #print("batchshape=" , batch_features.shape)
        count+=1
        if count == batch_size:
            count=0
            #TrainY =  np.transpose(batch_labels, (1, 0))
            yield batch_features, batch_labels

train()



