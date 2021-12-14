import torch
import torch.nn as nn
import torch.optim as optim
import numpy as np
import os
import pickle
import datetime
from torch.optim.lr_scheduler import StepLR
def calculate_loss(model, data, label, batch_size, computing_device, criterion):
    n_samples = data.shape[0]
    n_minibatch = int((n_samples+batch_size-1)/batch_size)
    loss = 0
    I = np.arange(n_samples)
    for i in range(n_minibatch):
        idx = I[batch_size*i:min(batch_size*(i+1), n_samples)]
        dt = data[idx].to(computing_device)
        lbl = label[idx].to(computing_device)
        outputs = model(dt)
        l = criterion(outputs, lbl.long())
        loss += l.item()
    return loss/n_minibatch
        
def calculate_accuracy(model, data, label, batch_size, computing_device):
    n_samples = data.shape[0]
    n_minibatch = int((n_samples+batch_size-1)/batch_size)
    accuracy = 0
    I = np.arange(n_samples)
    for i in range(n_minibatch):
        idx = I[batch_size*i:min(batch_size*(i+1), n_samples)]
        dt = data[idx].to(computing_device)
        lbl = label[idx].numpy()
        #output = model(dt).detach() ## detach code was written by Jahya.. not sure why this is there.. maybe as an alternate  
        #to torch.no_grad() ?
        ## Likely that is the case since, when I called this without
        output = model(dt)
        output = output.cpu().numpy()
        output = np.argmax(output,axis=1)
        accuracy += np.sum(output == lbl)
    return accuracy/n_samples

def train_model(model, model_file, train_set, val_set,TrainParams):
    # num_epochs, batch_size, learning_rate, criterion, computing_device,optimizer_type,n_epochs_earlystop, clip
    # Convert model to computing device
    num_epochs = TrainParams['num_epochs']
    batch_size = TrainParams['BS']
    learning_rate = TrainParams['LR']
    criterion = TrainParams['criterion']
    computing_device = TrainParams['computing_device']
    optimizer_type = TrainParams['optimizer_type']
    n_epochs_earlystop = TrainParams['n_epochs_earlystop']
    clip = TrainParams['clip']
    model = model.to(computing_device)
    print("Model on CUDA?", next(model.parameters()).is_cuda)
    print("Optimizer type inputted: ",optimizer_type)
    # Instantiate the gradient descent optimizer - use Adam optimizer with default parameters
    if optimizer_type =='Adam':
        print("Optimizer type: ",optimizer_type )
        optimizer = optim.Adam(model.parameters(), lr=learning_rate, weight_decay=TrainParams['weight_decay'])
        print("Optimizer used params: ", optimizer)
    elif optimizer_type == 'SGD':
        print("Optimizer type: ",optimizer_type )
        optimizer = optim.SGD(model.parameters(), lr=learning_rate)
    elif optimizer_type == 'RMSprop':
        print("Optimizer type: ",optimizer_type )
        optimizer = optim.RMSprop(model.parameters(), lr=learning_rate)
    
    scheduler = StepLR(optimizer,step_size=TrainParams['LRScheduler_stepsize'],gamma=TrainParams['LRSchedulerGamma'])
    batch_size_for_loss_calculation = TrainParams['test_bactchsize']

    # Prepare Data
    train_data, train_labels = train_set['data'], train_set['labels']
    val_data, val_labels = val_set['data'], val_set['labels']
    n_samples = train_data.shape[0]
    n_minibatch = int((n_samples+batch_size-1)/batch_size)
    
    
    # Check for existing model
    loss_file = model_file.strip('.pt') + '_loss.pkl'
    accuracy_file = model_file.strip('.pt') + '_accuracy.pkl'
    if os.path.isfile(model_file):
        model.load_state_dict(torch.load(model_file))
        print('Existing model loaded.')
        # Load Loss and Accuracy
        with open(loss_file, 'rb') as handle:
            Loss = pickle.load(handle)
        with open(accuracy_file, 'rb') as handle:
            Accuracy = pickle.load(handle)
        n_prev_epochs = len(Loss['train'])
        print("n_prev_epochs is: ",n_prev_epochs)
        n_prev_epochs = n_prev_epochs + 1 # Since we are already done with n_previous_epochs, we are starting with the next one.
        model.eval()
        #h0 = model.init_hidden(batch_size)
        #If the model exists apriori, we shall calcuate the loss and assign to prev_loss. 
        #Else we assing previous to Inf in the else loop - see below.
        # We set it to Inf so that always the first epoch loss is lower and saved by defaukt as the prev_loss.
        #Note that prev_loss is a misnomer and we save the best loss.
        with torch.no_grad():
            prev_val = calculate_loss(model, val_data, val_labels, \
                                      batch_size_for_loss_calculation, computing_device, criterion)
    else:
        prev_val = float('Inf')
        n_prev_epochs = 1
        Loss = {}
        Accuracy = {}
        Loss['train'] = []
        Loss['valid'] = []
        Accuracy['train'] = []
        Accuracy['valid'] = []
    
    
    # Prepare early stopping
    
    # earlier we had a value of 1000. Sometimes, the GPU resoruce may be limited. it is good to not have such large batch size, rather have it same as batch_size used for training, otherwise there may a sudden spike in GPU usage and that can stop tests due to memory error.
    
    # Also added model.eval and torch.no_grad for this loss calculation. This loss is used to compute the loss of the saved model taht can be used to compare if the loss of the next epoch drops or not (for early exit criterion check.)

    print("Clipping removed")
    stop_con = 0
    #epoch = n_prev_epochs
    # Begin training procedure
    epoch = n_prev_epochs
    for epoch in range(n_prev_epochs, num_epochs+1):
        print('Epoch:', epoch,'LR:', scheduler.get_lr())
        # Shuffle indices
        shuffled_idx = np.random.permutation(range(n_samples))
        model.train()
        train_loss = 0
        print('Epoch number: ', epoch, ' starting')
        print(datetime.datetime.now())
        
        #h0 = model.init_hidden(batch_size)
        for i in range(n_minibatch):
            idx = shuffled_idx[batch_size*i:min(batch_size*(i+1), n_samples)]
            data = train_data[idx].to(computing_device)
            labels = train_labels[idx].to(computing_device)
            
            # Zero out the stored gradient (buffer) from the previous iteration
            optimizer.zero_grad()
            # Creating new variables for the hidden state, otherwise
            # we'd backprop through the entire training history
            
            #h0 = tuple([each.data for each in h0])
            # Perform the forward pass through the network and compute the loss
            outputs = model(data)
            loss = criterion(outputs, labels.long())
            #loss = criterion(outputs, labels.float())
            
            # Compute the gradients and backpropagate the loss through the network
            loss.backward()
            
            #torch.nn.utils.clip_grad_norm_(model.parameters(), clip)
            # Update the weights
            optimizer.step()
            
            train_loss += loss.item()
            torch.cuda.empty_cache()
            if ((i%1000) == 0)&(i>0):
                print('Epoch Number: ', epoch, ' and Batch number: ', i, ' complete')
                print(datetime.datetime.now())
        
        model.eval()
        
        with torch.no_grad():
            train_loss = calculate_loss(model, train_data, train_labels, batch_size_for_loss_calculation\
                                        , computing_device, criterion)
            val_loss = calculate_loss(model, val_data, val_labels, batch_size_for_loss_calculation, \
                                      computing_device, criterion)
            Loss['train'].append(train_loss)
            Loss['valid'].append(val_loss)
            train_acc = calculate_accuracy(model, train_data, train_labels, batch_size_for_loss_calculation, computing_device)
            val_acc = calculate_accuracy(model, val_data, val_labels, batch_size_for_loss_calculation, computing_device)
            print("Train accuracy: ", train_acc)
            print("Validation accuracy: ", val_acc)
            Accuracy['train'].append(train_acc)
            Accuracy['valid'].append(val_acc)
        
        # Save loss and accuracy
        with open(loss_file, 'wb') as handle:
            pickle.dump(Loss, handle, protocol=pickle.HIGHEST_PROTOCOL)
        with open(accuracy_file, 'wb') as handle:
            pickle.dump(Accuracy, handle, protocol=pickle.HIGHEST_PROTOCOL)
        
        # Save model
        if (prev_val > val_loss):
            print("Previous best and current validation losses are: ", prev_val,val_loss)
            torch.save(model.state_dict(), model_file)
            prev_val = val_loss
            stop_con = 0
        elif epoch> 1: # make sure that we are not in the first epoch. 
            print("Validation loss increased from %f to %f." %(prev_val, val_loss))
            model.load_state_dict(torch.load(model_file))
            #prev_val = val_loss
            stop_con += 1
            if (stop_con >= n_epochs_earlystop):
                break
        else:
            print("Validation loss increased from %f to %f." %(prev_val, val_loss))
            #model.load_state_dict(torch.load(model_file))
            #prev_val = val_loss
            stop_con += 1
            #if (stop_con >= 3):
             #   break
            
      
                
        
            
        print("Epoch %d : Training Loss = %f,  Validation Loss = %f" % (epoch, train_loss, val_loss))
        scheduler.step()
    print("Training complete after", epoch, "epochs")
    torch.save(model.state_dict(), model_file)
    
    return model, Loss, Accuracy

