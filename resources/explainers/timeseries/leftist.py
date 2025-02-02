from http.client import BAD_REQUEST
from flask_restful import Resource
from flask import request
import tensorflow as tf
import torch
import pandas as pd
import numpy as np
import h5py
import json
import joblib
import requests
import matplotlib.pyplot as plt
from io import BytesIO
from PIL import Image
from getmodelfiles import get_model_files
from utils import ontologyConstants
from utils.base64 import PIL_to_base64
import traceback


from LIMESegment.LIMESegmentExplainers import Explainer



class Leftist(Resource):

    def __init__(self,model_folder,upload_folder):
        self.model_folder = model_folder
        self.upload_folder = upload_folder 
        
    def post(self):
        try:
            params = request.json
            if params is None:
                return "The json body is missing.",BAD_REQUEST
        
            #Check params
            if("id" not in params):
                return "The model id was not specified in the params.",BAD_REQUEST
            if("type" not in params):
                return "The instance type was not specified in the params.",BAD_REQUEST
            if("instance" not in params):
                return "The instance was not specified in the params.",BAD_REQUEST

            _id =params["id"]
            if("type"  in params):
                inst_type=params["type"]
            instance=params["instance"]
            url=None
            if "url" in params:
                url=params["url"]
            params_json={}
            if "params" in params:
                params_json=params["params"]
        
        
            #Getting model info, data, and file from local repository
            model_file, model_info_file, data_file = get_model_files(_id,self.model_folder)

            #loading data
            if data_file!=None:
                dataframe = pd.read_csv(data_file,header=0)
            else:
                raise Exception("The training data file was not provided.")

            ##getting params from info
            model_info=json.load(model_info_file)
            backend = model_info["backend"] 
            target_names=model_info["attributes"]["target_names"]
            features=list(model_info["attributes"]["features"].keys())
            for target in target_names:
                features.remove(target)
            dataframe.drop(target_names,axis=1,inplace=True)
            feature=features[0]
            tslen=len(dataframe.columns)


            #check univariate
            if(1):
                pass
            else:
                return "This method only supports univariate timeseries datasets.",BAD_REQUEST

            #check binary class
            if(1):
                pass
            else:
                return "This method only supports binary classification tasks.",BAD_REQUEST

            ## getting predict function
            model_type="proba"
            predic_func=None
            if model_file!=None:
                if backend in ontologyConstants.TENSORFLOW_URIS:
                    model=h5py.File(model_file, 'w')
                    mlp = tf.keras.models.load_model(model)
                    predic_func=mlp
                elif backend in ontologyConstants.SKLEARN_URIS:
                    mlp = joblib.load(model_file)
                    try:
                        predic_func=mlp.predict_proba
                    except:
                        predic_func=mlp.predict
                        model_type="class"
                elif backend in ontologyConstants.PYTORCH_URIS:
                    mlp = torch.load(model_file)
                    predic_func=mlp.predict
                else:
                    try:
                        mlp = joblib.load(model_file)
                        predic_func=mlp.predict
                    except Exception as e:
                        return "Could not extract prediction function from model: " + str(e),BAD_REQUEST
            elif url!=None:
                def predict(X):
                    return np.array(json.loads(requests.post(url, data=dict(inputs=str(X.tolist()))).text))
                predic_func=predict
            else:
                return "Either a stored model or a valid URL for the prediction function must be provided.",BAD_REQUEST

            class ModelWrapper:
                def predict(self,x):
                    return predic_func(x)

            model=ModelWrapper()

            #reshaping instance
            instance=np.array(instance)
            instance=instance.reshape(model_info["attributes"]["features"][feature]["shape"])

            #explanation
            explainer = Explainer()
            explanation = explainer.explain (
                             example = instance, 
                             model = model,
                             model_type=model_type,
                             X_background=np.expand_dims(dataframe.to_numpy(),axis=-1),
                             explainer="LEFTIST"
                             )
            explainer.plot_explanation(instance, 
                                       explanation,
                                       title="Attributions for Class " + str(model_info["attributes"]["features"][target_names[0]]["values_raw"][1]),
                                       y_label=feature
                                       )
            #saving
            img_buf = BytesIO()
            plt.savefig(img_buf,bbox_inches="tight")
            im = Image.open(img_buf)
            b64Image=PIL_to_base64(im)
            plt.close()

            json_exp={}
            for i in range(len(explanation[1])-1):
                json_exp[str(explanation[1][i])+"_"+str(explanation[1][i+1])]=explanation[0][i]
            json_exp[str(explanation[1][i])+"_"+str(model_info["attributes"]["features"][feature]["shape"][-1])]=explanation[0][-1]
            segments={"segments":json_exp}

            response={"type":"image","explanation":b64Image,"explanation_llm":segments}
            return response
        except:
            return traceback.format_exc(), 500        

    def get(self,id=None):
        base_dict={
        "_method_description": "LEFTIST is the proposed adaptation of LIME to time series data of Guilleme et al. This method accepts 3 arguments: " 
                           "the 'id', the 'instance', and the 'url'. "
                           "These arguments are described below.",
        "id": "Identifier of the ML model that was stored locally.",
        "url": "External URL of the prediction function. Ignored if a model file was uploaded to the server. "
                   "This url must be able to handle a POST request receiving a (multi-dimensional) array of N data points as inputs (instances represented as arrays). It must return a array of N outputs (predictions for each instance).",
        "instance": "Array containing the values for each time point.",
        "output_description":{
                "timeseries_attributions": "Show the attributions of the individual segments of the timeseries to the positive class."
        },
        "meta":{
                "modelAccess":"Any",
                "supportsBWImage":False,
                "needsTrainingData": False
            }

        }
        
        return base_dict

        
