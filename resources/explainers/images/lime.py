from flask_restful import Resource
from flask import request
from lime.wrappers.scikit_image import SegmentationAlgorithm
from skimage.segmentation import mark_boundaries
from PIL import Image
import numpy as np
import tensorflow as tf
import torch
import h5py
import joblib
import json
import math
import werkzeug
import matplotlib.pyplot as plt
from lime import lime_image
from saveinfo import save_file_info
from getmodelfiles import get_model_files
import requests
from io import BytesIO
from utils import ontologyConstants
from utils.base64 import base64_to_vector,PIL_to_base64
from utils.img_processing import normalize_img

class LimeImage(Resource):

    def __init__(self,model_folder,upload_folder):
        self.model_folder = model_folder
        self.upload_folder = upload_folder
        
    def post(self):
        params = request.json
        if params is None:
            return "The params are missing"

        #Check params
        if("id" not in params):
            return "The model id was not specified in the params."
        if("type" not in params):
            return "The instance type was not specified in the params."
        if("instance" not in params):
            return "The instance was not specified in the params."

        _id =params["id"]
        instance = params["instance"]
        inst_type=params["type"]
        url=None
        if "url" in params:
            url=params["url"]
        params_json={}
        if "params" in params:
            params_json=params["params"]
       
        #Getting model info, data, and file from local repository
        model_file, model_info_file, _ = get_model_files(_id,self.model_folder)

        ## params from info
        model_info=json.load(model_info_file)
        backend = model_info["backend"] 
        output_names=model_info["attributes"]["features"][model_info["attributes"]["target_names"][0]]["values_raw"]
        predic_func=None

        if model_file!=None:
            if backend in ontologyConstants.TENSORFLOW_URIS:
                model=h5py.File(model_file, 'w')
                mlp = tf.keras.models.load_model(model)
                predic_func=mlp.predict
            elif backend in ontologyConstants.SKLEARN_URIS:
                mlp = joblib.load(model_file)
                predic_func=mlp.predict_proba
            elif backend in ontologyConstants.PYTORCH_URIS:
                mlp = torch.load(model_file)
                predic_func=mlp.predict
            else:
                mlp = joblib.load(model_file)
                predic_func=mlp.predict
        elif url!=None:
            def predict(X):
                return np.array(json.loads(requests.post(url, data=dict(inputs=str(X.tolist()))).text))
            predic_func=predict
        else:
            raise Exception("Either a locally stored model or a URL for the prediction function of the model must be provided.")
        
        
       #converting to vector
        try:
            instance=base64_to_vector(instance)
        except Exception as e:  
            return "Could not convert base64 Image to vector: " + str(e)

        #normalizing
        try:
            instance=normalize_img(instance,model_info)
        except Exception as e:
                return  "Could not normalize instance: " + str(e)

        if len(model_info["attributes"]["features"]["image"]["shape_raw"])==2 or model_info["attributes"]["features"]["image"]["shape_raw"][-1]==1:
           return "LIME only supports RGB images."

        kwargsData = dict(top_labels=1,segmentation_fn=None)
        if "top_classes" in params_json:
            kwargsData["top_labels"] = int(params_json["top_classes"])   #top labels
        if "segmentation_fn" in params_json:
            kwargsData["segmentation_fn"] = SegmentationAlgorithm(params_json["segmentation_fn"])

        size=(12, 12)
        if "png_height" in params_json and "png_width" in params_json:
            try:
                size=(int(params_json["png_width"])/100.0,int(params_json["png_height"])/100.0)
            except:
                print("Could not convert dimensions for .PNG output file. Using default dimensions.")
        
        explainer = lime_image.LimeImageExplainer()
        explanation = explainer.explain_instance(instance[0], classifier_fn=predic_func,**{k: v for k, v in kwargsData.items() if v is not None})

        fig, axes = plt.subplots(1,len(explanation.top_labels), figsize = size)
        i=0
        for cat in explanation.top_labels:
            temp, mask = explanation.get_image_and_mask(cat, positive_only=False,hide_rest=False)
            axes[i].imshow(mark_boundaries(temp, mask))
            if output_names != None:
                cat = output_names[cat]
            axes[i].set_title('Positive/Negative Regions for {}'.format(cat))
            i=i+1
        fig.tight_layout()
        ##formatting json explanation
        dict_exp={}
        for key in explanation.local_exp:
            dict_exp[int(key)]=[[float(y) for y in x ] for x in explanation.local_exp[key]]
        
        #saving
        img_buf = BytesIO()
        fig.savefig(img_buf)
        im = Image.open(img_buf)
        b64Image=PIL_to_base64(im)

        response={"type":"image","explanation":b64Image}#,"explanation":dict_exp}
        return response

    def get(self):
        return {
        "_method_description": "Uses LIME to identify the group of pixels that contribute the most to the predicted class."
                           "This method accepts 5 arguments: " 
                           "the 'id', the 'url' (optional),  the 'params' dictionary (optional) with the configuration parameters of the method, the 'instance' containing the image that will be explained as a matrix, or the 'image' file instead. "
                           "These arguments are described below.",
        "id": "Identifier of the ML model that was stored locally.",
        "url": "External URL of the prediction function. This url must be able to handle a POST request receiving a (multi-dimensional) array of N data points as inputs (images represented as arrays). It must return N outputs (predictions for each image).",
        "instance": "Matrix representing the image to be explained.",
        "image": "Image file to be explained. Ignored if 'instance' was specified in the request. Passing a file is only recommended when the model works with black and white images, or color images that are RGB-encoded using integers ranging from 0 to 255.",
        "params": { 
                "top_classes":{
                        "description": "Integer representing the number of classes with the highest prediction probability to be explained. Overrides 'output_classes' if provided.",
                        "type":"int",
                        "default": 1,
                        "range":None,
                        "required":False
                    },
                "segmentation_fn": {
                    "description":"A string with an image segmentation algorithm from the following:'quickshift', 'slic', or 'felzenszwalb'.",
                    "type":"string",
                    "default": "quickshift",
                    "range":['quickshift','slic','felzenszwalb'],
                    "required":False
                    },
                "png_width":{
                    "description": "Width (in pixels) of the png image containing the explanation.",
                    "type":"int",
                    "default": 1200,
                    "range":None,
                    "required":False
                    },
                "png_height": {
                    "description": "Height (in pixels) of the png image containing the explanation.",
                    "type":"int",
                    "default": 1200,
                    "range":None,
                    "required":False
                    }
                },
        "output_description":{
                "lime_image":"Displays the group of pixels that contribute positively (in green) and negatively (in red) to the prediction of the image class. More than one class may be displayed."
            },

        "meta":{
                "supportsAPI":True,
                "supportsB&WImage":False,
                "needsData": False,
                "requiresAttributes":[]

            }
        }