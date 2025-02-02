from http.client import BAD_REQUEST
from flask_restful import Resource
from flask import request
from PIL import Image
import os
import numpy as np
import tensorflow as tf
import torch
import h5py
import json
from io import BytesIO
import matplotlib.pyplot as plt
import pandas as pd
from sklearn.metrics import ConfusionMatrixDisplay
from getmodelfiles import get_model_files
from utils import ontologyConstants
from utils.base64 import PIL_to_base64
from utils.img_processing import normalise_image_batch
from utils.validation import validate_params
import traceback

class ConfusionMatrixImages(Resource):

    def __init__(self,model_folder,upload_folder):
        self.model_folder = model_folder
        self.upload_folder = upload_folder
        
    def get_preds(self, model_info, predic_func, data_file,output_names,sample=None):
        train_data = []
        actual=[]
        
        if type(data_file)==str and os.path.isdir(data_file):
            # classification image dataset in zipped folder
            _folders = [_f for _f in os.listdir(data_file)]
            if len(_folders)<1:
                raise Exception("No data found.")

            for folder in _folders:
                _folder_path = os.path.join(data_file, folder)
                _files = [os.path.join(_folder_path, f) for f in os.listdir(_folder_path)]
                train_data=train_data+[np.array(Image.open(f)) for f in _files]
                actual=actual+([output_names.index(folder)]*len(_files))
        
            train_data=np.asarray(train_data)
            actual=np.asarray(actual)
            if sample!=None:
                sample_idx=np.random.randint(train_data.shape[0], size=sample)
                train_data=train_data[sample_idx,:]
                actual=actual[sample_idx]
            train_data = normalise_image_batch(train_data, model_info)
            #instead of batch to avoid potential OOM errors
            preds=[]
            for instance in train_data:
                pred=predic_func(np.expand_dims(instance,axis=0))[0]
                preds.append(pred)
            preds=np.array(preds)

            return preds, actual
           
        else:
            header = next(data_file).split(',')
            header = [elem.strip() for elem in header]

            while True:
                try:
                    s_instance = next(data_file)
                    s_instance = s_instance.replace('\n', '')
                    s_array = s_instance.split(',')
                    actual.append(float(s_array[-1]))
                    s_array = [float(s) for s in s_array][:-1]
                    train_data.append(s_array)
                except Exception as e: #end of rows
                    train_data=np.asarray(train_data)
                    actual=np.asarray(actual)
                    if sample!=None:
                        sample_idx=np.random.randint(train_data.shape[0], size=sample)
                        train_data=train_data[sample_idx,:]
                        actual=actual[sample_idx]
                    train_data = train_data.reshape((train_data.shape[0],)+tuple(model_info["attributes"]["features"]["image"]["shape"]))
                    #instead of batch to avoid potential OOM errors
                    preds=[]
                    for instance in train_data:
                        pred=predic_func(np.expand_dims(instance,axis=0))[0]
                        preds.append(pred)
                    preds=np.array(preds)

                    return preds, actual                 
                   
 
    def post(self):
        params = request.json
        if params is None:
            return "The params are missing",BAD_REQUEST

        #check params
        if("id" not in params):
            return "The model id was not specified in the params.",BAD_REQUEST
        if("type" not in params):
            return "The instance type was not specified in the params.",BAD_REQUEST
        if("instance" not in params):
            return "The instance was not specified in the params.",BAD_REQUEST
        
        _id =params["id"]
        instance = params["instance"]
        params_json={}
        if "params" in params:
            params_json=params["params"]

        params_json=validate_params(params_json,self.get(_id)["params"])

        return self.explain(_id, instance, params_json)
    
    def explain(self, model_id, instance, params_json):
        try:

            #Getting model info, data, and file from local repository
            model_file, model_info_file, data_file = get_model_files(model_id,self.model_folder)

            ## params from info
            model_info=json.load(model_info_file)
            backend = model_info["backend"]  ##error handling?
            output_names=model_info["attributes"]["features"][model_info["attributes"]["target_names"][0]]["values_raw"]

            predic_func=None

            if model_file!=None:
                if backend in ontologyConstants.TENSORFLOW_URIS:
                    model = h5py.File(model_file, 'w')
                    model = tf.keras.models.load_model(model)
                    predic_func=model   
                elif backend in ontologyConstants.PYTORCH_URIS:
                    model = torch.load(model_file)
                    predic_func=model.predict
                else:
                    return "Only Tensorflow and PyTorch backends are supported.",BAD_REQUEST
            else:
                return "A ML model must be provided.",BAD_REQUEST
        
            sample=params_json["samples"]
 
                

            preds, actual = self.get_preds(model_info, predic_func, data_file,output_names,sample=sample)

            if(len(preds.shape)==2):
                preds = np.squeeze(np.argmax(preds,axis=-1))

            print(preds.shape)
            print(actual.shape)
            plot=ConfusionMatrixDisplay.from_predictions(actual, preds,display_labels=output_names)

            print()
    
            #saving
            img_buf = BytesIO()
            plt.savefig(img_buf,bbox_inches='tight')
            im = Image.open(img_buf)
            b64Image=PIL_to_base64(im)

            def parse_dict(x):
                if hasattr(x, "tolist"): 
                    return x.tolist()
                raise TypeError(x)

            response={"type":"image","explanation":b64Image,"explanation_llm":json.loads(pd.DataFrame(plot.confusion_matrix, columns=["Predicted " + s for s in output_names], index=["Actual " + s for s in output_names]).to_json(orient="index"))}
            return response
        except:
            return traceback.format_exc(), 500

    def get(self,id=None):
        return {
        "_method_description": "Finds the nearest neighbours to a data instances based on minimum euclidean distance",
        "id": "Identifier of the ML model that was stored locally.",
        "instance": "Image to be explained in BASE64 format",
        "params": { 
                "samples":{
                    "description": "Number of samples to use from the background data. A hundred samples are used by default.",
                    "type":"int",
                    "default": 100,
                    "range":None,
                    "required":False
                    }
                },
        "output_description":{
                "0":"This explanation displays the confusion matrix of the model on the provided dataset."
            },

        "meta":{
                "modelAccess":"File",
                "supportsBWImage":True,
                "needsTrainingData": True


        }
    }
