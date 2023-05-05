from flask_restful import Resource
from flask import request
from PIL import Image
import numpy as np
import tensorflow as tf
import h5py
import json
import matplotlib.pyplot as plt
import matplotlib.cm as cm
from alibi.explainers import IntegratedGradients
from io import BytesIO
from getmodelfiles import get_model_files
from utils import ontologyConstants
from utils.base64 import base64_to_vector,PIL_to_base64
from utils.img_processing import normalize_img



class IntegratedGradientsImage(Resource):

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
        params_json={}
        if "params" in params:
            params_json=params["params"]

        #Getting model info, data, and file from local repository
        model_file, model_info_file, _ = get_model_files(_id,self.model_folder)

        ## params from info
        model_info=json.load(model_info_file)
        backend = model_info["backend"]  
        output_names=None
        try:
            output_names=model_info["attributes"]["features"][model_info["attributes"]["target_names"][0]]["values_raw"]
        except:
            pass

        if model_file!=None:
            if backend in ontologyConstants.TENSORFLOW_URIS:
                model=h5py.File(model_file, 'w')
                mlp = tf.keras.models.load_model(model)
            else:
                raise Exception("This method only supports Tensorflow/Keras models.")
        else:
            raise Exception("This method requires a model file.")

        #converting to vector
        try:
            instance=base64_to_vector(instance)
        except Exception as e:  
            return "Could not convert base64 Image to vector: " + str(e)

        im=instance #Raw format needed for explanation

        #normalizing
        try:
            instance=normalize_img(instance,model_info)
        except Exception as e:
                return  "Could not normalize instance: " + str(e)
        ## params from request
        n_steps = 10
        if "n_steps" in params_json:
            n_steps = params_json["n_steps"]

        method = "gausslegendre"
        if "method" in params_json:
            method = params_json["method"]

        internal_batch_size=100
        if "internal_batch_size" in params_json:
            internal_batch_size = params_json["internal_batch_size"]

        prediction=mlp(instance)[0].numpy()
        target_class=int(prediction.argmax())

        is_class=True
        if(prediction.shape[-1]==1): ## it's regression
            is_class=False

        if(is_class):
            if "target_class" in params_json:
                    target_class = params_json["target_class"]

        size=(12, 6)
        if "png_height" in params_json and "png_width" in params_json:
            try:
                size=(int(params_json["png_width"])/100.0,int(params_json["png_height"])/100.0)
            except:
                print("Could not convert dimensions for .PNG output file. Using default dimensions.")

        plot_type="heatmap"
        if "plot_type" in params_json:
            if str(params_json["plot_type"])=="attributions":
                plot_type="attributions"

        ## Generating explanation
        ig  = IntegratedGradients(mlp,
                                  n_steps=n_steps,
                                  method=method,
                                  internal_batch_size=internal_batch_size)

        explanation = ig.explain(instance, target=target_class)
        attrs = explanation.attributions[0]
        attr = attrs[0]

        # fig, (a0,a1,a2,a3,a4) = plt.subplots(nrows=1, ncols=5, figsize=size,gridspec_kw={'width_ratios':[3,3,3,3,1]})

        # a0.imshow(im)
        # a0.set_title("Original Image")

        if(plot_type=="attributions"):
            fig, (a0,a1,a2, a3, a4) = plt.subplots(nrows=1, ncols=5, figsize=size,gridspec_kw={'width_ratios':[3,3,3,3,1]})

            a0.imshow(im)
            a0.set_title("Original Image")

            cmap_bound = np.abs(attrs).max()

            # attributions
            im = a1.imshow(attr.squeeze(), vmin=-cmap_bound, vmax=cmap_bound, cmap='PiYG')

            # positive attributions
            attr_pos = attr.clip(0, 1)
            im_pos = a2.imshow(attr_pos.squeeze(), vmin=-cmap_bound, vmax=cmap_bound, cmap='PiYG')

            # negative attributions
            attr_neg = attr.clip(-1, 0)
            im_neg = a3.imshow(attr_neg.squeeze(), vmin=-cmap_bound, vmax=cmap_bound, cmap='PiYG')

            if(is_class):
                a1.set_title('Attributions for Class: ' + output_names[target_class])
            else:
               a1.set_title("Attributions for Pred: " + str(np.squeeze(prediction).round(4)))
            a2.set_title('Positive attributions');
            a3.set_title('Negative attributions');

            for ax in fig.axes:
                ax.axis('off')
   
            fig.colorbar(im)
            fig.tight_layout()

        elif(plot_type=="heatmap"):
            fig, (a0,a1,a2) = plt.subplots(nrows=1, ncols=3, figsize=size,gridspec_kw={'width_ratios':[3,3,1]})

            a0.imshow(im)
            a0.set_title("Original Image")
            # attributions
            attr_all=np.abs(attr.squeeze())
            heatmap=((attr_all-np.min(attr_all)) / (np.max(attr_all) - np.min(attr_all))).astype("float32")
            heatmap = np.uint8(255 * heatmap)

            jet = cm.get_cmap("jet")
            jet_colors = jet(np.arange(256))[:, :3]
            jet_heatmap = jet_colors[heatmap]
            jet_heatmap=np.uint8(255 * jet_heatmap)
            if len(im.shape)==2:
                im=im.reshape(im.shape+(1,))
            print(jet_heatmap.shape)
            print(np.max(jet_heatmap))
            print(im.shape)
            print(np.max(im))
            superimposed_img = (jet_heatmap * 0.4 + im).astype("uint8")
            img=Image.fromarray(superimposed_img)
            im1 = a1.imshow(img)

            if(is_class):
                a1.set_title('Attributions for Class: ' + output_names[target_class])
            else:
               a1.set_title("Attributions for Pred: " + str(np.squeeze(prediction).round(4)))
            
            for ax in fig.axes:
                ax.axis('off')
   
            fig.colorbar(im1)
            fig.tight_layout()     
            
        #saving
        img_buf = BytesIO()
        fig.savefig(img_buf,bbox_inches='tight',pad_inches = 0)
        im = Image.open(img_buf)
        b64Image=PIL_to_base64(im)

        response={"type":"image","explanation":b64Image}#,"explanation":json.loads(explanation.to_json())}
        return response

    def get(self):
        return {
        "_method_description": "Defines an attribution value for each pixel in the image provided based on the Integration Gradients method. It only works with Tensorflow/Keras models."
                            "This method accepts 4 arguments: " 
                           "the 'id', the 'params' dictionary (optional) with the configuration parameters of the method, the 'instance' containing the image that will be explained as a matrix, or the 'image' file that can be passed instead of the instance. "
                           "These arguments are described below.",

        "id": "Identifier of the ML model that was stored locally. If provided, then 'url' is ignored.",
        "instance": "Matrix representing the image to be explained.",
        "image": "Image file to be explained. Ignored if 'instance' was specified in the request. Passing a file is only recommended when the model works with black and white images, or color images that are RGB-encoded using integers ranging from 0 to 255.",
        "params": { 
                "target_class":{
                    "description": "Integer denoting the desired class for the computation of the attributions. Ignore for regression models. Defaults to the predicted class of the instance.",
                    "type":"int",
                    "default": None,
                    "range":None,
                    "required":False
                    }, 
                "method": {
                    "description":"Method for the integral approximation. The methods available are: 'riemann_left', 'riemann_right', 'riemann_middle', 'riemann_trapezoid', 'gausslegendre'. Defaults to 'gausslegendre'.",
                    "type":"string",
                    "default": "gausslegendre",
                    "range":['gausslegendre','riemann_left','riemann_right','riemann_middle','riemann_trapezoid',],
                    "required":False
                    },
                "n_steps": {
                    "description":  "Number of step in the path integral approximation from the baseline to the input instance. Defaults to 10.",
                    "type":"int",
                    "default": 10,
                    "range":None,
                    "required":False
                    },
                "internal_batch_size": {
                    "description":  "Batch size for the internal batching. Defaults to 100.",
                    "type":"int",
                    "default": 100,
                    "range":None,
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
                    "default": 600,
                    "range":None,
                    "required":False
                    }
                },
        "output_description":{
                "attribution_plot":"Subplot with two columns. The first column shows the original image and its prediction. The second column shows the values of the attributions for the target class."
            },

        "meta":{
                "supportsAPI":False,
                "supportsB&WImage":True,
                "needsData": False,
                "requiresAttributes":[]
            }

        }
