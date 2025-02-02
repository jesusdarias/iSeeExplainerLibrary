from http.client import BAD_REQUEST
from flask_restful import Resource
from flask import request
from PIL import Image
import tensorflow as tf
import h5py
import json
import math
import matplotlib.pyplot as plt
import numpy as np
from xplique.attributions import HsicAttributionMethod
from xplique.attributions.global_sensitivity_analysis import LatinHypercube
from xplique.plots import plot_attributions
from io import BytesIO
from getmodelfiles import get_model_files
from utils import ontologyConstants
from utils.base64 import base64_to_vector,PIL_to_base64
from utils.img_processing import normalize_img
from utils.validation import validate_params
import traceback



class HsicAttributionMethodExp(Resource):

    def __init__(self,model_folder,upload_folder):
        self.model_folder = model_folder
        self.upload_folder = upload_folder

    def post(self):
        try:
            params = request.json
            if params is None:
                return "The params are missing",BAD_REQUEST

            #Check params
            if("id" not in params):
                return "The model id was not specified in the params.",BAD_REQUEST
            if("type" not in params):
                return "The instance type was not specified in the params.",BAD_REQUEST
            if("instance" not in params):
                return "The instance was not specified in the params.",BAD_REQUEST

            _id =params["id"]
            instance = params["instance"]
            inst_type=params["type"]
            params_json={}
            if "params" in params:
                params_json=params["params"]
            params_json=validate_params(params_json,self.get(_id)["params"])

            #Getting model info, data, and file from local repository
            model_file, model_info_file, _ = get_model_files(_id,self.model_folder)

            ## params from info
            model_info=json.load(model_info_file)
            backend = model_info["backend"]  
            output_names=model_info["attributes"]["features"][model_info["attributes"]["target_names"][0]]["values_raw"]

            if model_file!=None:
                if backend in ontologyConstants.TENSORFLOW_URIS:
                    model=h5py.File(model_file, 'w')
                    mlp = tf.keras.models.load_model(model)
                else:
                    return "This method only supports Tensorflow/Keras models.",BAD_REQUEST
            else:
                return "This method requires a model file.",BAD_REQUEST

            #converting to vector
            try:
                instance=base64_to_vector(instance)
            except Exception as e:  
                return "Could not convert base64 Image to vector: " + str(e),BAD_REQUEST

            im=instance #Raw format needed for explanation

            #normalizing
            try:
                instance=normalize_img(instance,model_info)
            except Exception as e:
                    return  "Could not normalize instance: " + str(e),BAD_REQUEST

            prediction=mlp(instance)[0].numpy()
            target_class=int(prediction.argmax())

           
            if "target_class" in params_json:
                if(params_json["target_class"]!="Highest Pred."):
                    target_class = output_names.index(params_json["target_class"])

            grid_size=params_json["grid_size"] 
            nb_design=params_json["nb_design"]

            ## Generating explanation
            try:
                mlp.layers[-1].activation = tf.keras.activations.linear
            except:
                pass
            try:
                explainer=HsicAttributionMethod(mlp,grid_size=grid_size, nb_design=nb_design, sampler = LatinHypercube(binary=True),batch_size=64)
                explanations = explainer(instance, tf.one_hot(np.array([target_class]), depth=len(output_names), axis=-1))
            except Exception as e:
                return  "Could not generate explanation: " + str(e),BAD_REQUEST

            plot_attributions(explanations, np.expand_dims(im,axis=0), img_size=2., cmap='jet', alpha=0.4,absolute_value=True, clip_percentile=0.5)

            #saving
            img_buf = BytesIO()
            plt.savefig(img_buf,bbox_inches='tight',pad_inches = 0)
            im = Image.open(img_buf)
            b64Image=PIL_to_base64(im)

            response={"type":"image","explanation":b64Image,"explanation_llm":explanations.tolist()}
            return response
        except:
            return traceback.format_exc(), 500

    def get(self,id=None):
        base_dict={
        "_method_description": "The HSIC attribution method from Novello, Fel, Vigouroux explains a neural network's prediction for a given input image by assessing the dependence between the output and patches of the input. Thanks to the sample efficiency of HSIC Estimator, this black box method requires fewer forward passes to produce relevant explanations.",
        "id": "Identifier of the ML model that was stored locally. If provided, then 'url' is ignored.",
        "instance": "Matrix representing the image to be explained.",
        "params": { 
                "target_class":{
                    "description": "String denoting the desired class for the computation of the attributions. Ignore for regression models. Defaults to the predicted class of the instance.",
                    "type":"string",
                    "default": None,
                    "range":None,
                    "required":False
                    },         
                "grid_size":{
                    "description": "Divides the image in a grid of (grid_size, grid_size) to estimate an indice per cell. Defaults to 8.",
                    "type":"int",
                    "default": 8,
                    "range":None,
                    "required":False
                    },         
                "nb_design":{
                    "description": "Number of design for the sampler. Defaults to 500.",
                    "type":"int",
                    "default": 500,
                    "range":None,
                    "required":False
                    }      
                },
        "output_description":{
                "saliency_map":"Displays an image that highlights the most relevant pixels to the target class. Red pixels indicate greater importance."
            },

        "meta":{
                "modelAccess":"File",
                "supportsBWImage":True,
                "needsTrainingData": False

        }

        }

        if id is not None:
            #Getting model info, data, and file from local repository
            try:
                _, model_info_file, _ = get_model_files(id,self.model_folder)
            except:
                return base_dict

            model_info=json.load(model_info_file)
            target_name=model_info["attributes"]["target_names"][0]


            if model_info["attributes"]["features"][target_name]["data_type"]=="categorical":

                output_names=model_info["attributes"]["features"][target_name]["values_raw"]

                base_dict["params"]["target_class"]["default"]="Highest Pred."
                base_dict["params"]["target_class"]["range"]=["Highest Pred."] + output_names

                return base_dict

            else:
                base_dict["params"].pop("target_class")
                return base_dict

        else:
            return base_dict
