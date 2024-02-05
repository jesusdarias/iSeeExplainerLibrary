from http.client import BAD_REQUEST
from flask_restful import Resource
from flask import request
from PIL import Image
import tensorflow as tf
import h5py
import json
import matplotlib.pyplot as plt
import numpy as np
from xplique.attributions import Rise
from xplique.plots import plot_attributions
from io import BytesIO
from getmodelfiles import get_model_files
from utils import ontologyConstants
from utils.base64 import base64_to_vector,PIL_to_base64
from utils.img_processing import normalize_img
from utils.validation import validate_params
import traceback



class RiseExp(Resource):

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

            nb_samples=params_json["nb_samples"]
            grid_size=params_json["grid_size"]


            ## Generating explanation
            try:
                mlp.layers[-1].activation = tf.keras.activations.linear
            except:
                pass
            explainer=Rise(mlp,nb_samples=nb_samples, grid_size=grid_size)
            explanations = explainer(instance, tf.one_hot(np.array([target_class]), depth=len(output_names), axis=-1))

            plot_attributions(explanations, instance, img_size=2., cmap='jet', alpha=0.4,absolute_value=True, clip_percentile=0.5)

            #saving
            img_buf = BytesIO()
            plt.savefig(img_buf,bbox_inches='tight',pad_inches = 0)
            im = Image.open(img_buf)
            b64Image=PIL_to_base64(im)

            response={"type":"image","explanation":b64Image}#,"explanation":json.loads(explanation.to_json())}
            return response
        except:
            return traceback.format_exc(), 500

    def get(self,id=None):
        base_dict={
        "_method_description": "The RISE method consist of probing the model with randomly masked versions of the input image and obtaining the corresponding outputs to deduce critical areas.",


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
                "nb_samples":{
                    "description": "Number of masks generated for Monte Carlo sampling. A small number of samples will not provide a precise enough estimator, thus leading to noisy explanations. A large number of sample can only have a good impact on the explanation, however it will impact the computation time linearly. The number of samples should be increased when using setting greater grid sizes. Defaults to 4000.",
                    "type":"int",
                    "default": 4000,
                    "range":None,
                    "required":False
                    },
                "grid_size":{
                    "description": "Size of the grid used to generate the scaled-down masks. Masks are then rescale to and cropped to input_size. Small grid sizes will create large group of pixels resulting in low-precision explanations. Large grid sizes will drastically increase the number of pixel groups. Therefore, the number of sample necessary for the method to converge will be much higher. If you do not know which order of value to try, you should try 7, the square root of your image size and some other in the same order of magnitude. But remember to increase your nb_samples for larger values of grid_size. Defaults to 7.",
                    "type":"int",
                    "default": 7,
                    "range":None,
                    "required":False
                    },
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