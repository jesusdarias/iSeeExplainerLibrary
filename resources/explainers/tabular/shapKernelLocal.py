from http.client import BAD_REQUEST
from flask_restful import Resource
import tensorflow as tf
import torch
import pandas as pd
import numpy as np
import joblib
import h5py
import json
import shap
from flask import request
import matplotlib.pyplot as plt
from PIL import Image
from io import BytesIO
from getmodelfiles import get_model_files
from utils import ontologyConstants
from utils.base64 import PIL_to_base64
from utils.dataframe_processing import normalize_dataframe
import requests
import traceback

class ShapKernelLocal(Resource):

    def __init__(self,model_folder,upload_folder):
        self.model_folder = model_folder
        self.upload_folder = upload_folder
        
    def post(self):
        try:
            params = request.json
            if params is None:
                return "The json body is missing."
        
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
        
        
            #getting model info, data, and file from local repository
            model_file, model_info_file, data_file = get_model_files(_id,self.model_folder)

            #loading data
            if data_file!=None:
                dataframe = joblib.load(data_file) ##error handling?
            else:
                return "The training data file was not provided.",BAD_REQUEST

            #getting params from info
            model_info=json.load(model_info_file)
            backend = model_info["backend"]
            target_name=model_info["attributes"]["target_names"][0]
            output_names=model_info["attributes"]["features"][target_name]["values_raw"]
            dataframe.drop([target_name], axis=1, inplace=True)
            feature_names=list(dataframe.columns)
            kwargsData = dict(feature_names=feature_names, output_names=output_names)
       
            #getting params from request
            index=0
            if "target_class" in params_json:
                target_class=str(params_json["target_class"])
                try:
                    index=output_names.index(target_class)
                except:
                    pass
            plot_type=None
            if "plot_type" in params_json:
                plot_type=params_json["plot_type"]

        
        
            ## getting predict function
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

            #normalize instance
            df_inst=pd.DataFrame([instance.values()],columns=instance.keys())
            if target_name in df_inst.columns:
                df_inst.drop([target_name], axis=1, inplace=True)
            df_inst=df_inst[feature_names]
            norm_instance=normalize_dataframe(df_inst,model_info).to_numpy()[0]

            # Create data
            explainer = shap.KernelExplainer(predic_func, dataframe,**{k: v for k, v in kwargsData.items()})
            shap_values = explainer.shap_values(np.expand_dims(norm_instance,axis=0))
        
            if(len(np.array(shap_values).shape)!=1):
                explainer.expected_value=explainer.expected_value[index]
                shap_values=shap_values[index]
            
            #plotting
            plt.switch_backend('agg')
            if plot_type=="bar":
                shap.plots._bar.bar_legacy(shap_values[0],features=np.array(list(df_inst.to_dict("records")[0].values())),feature_names=kwargsData["feature_names"],show=False)
            elif plot_type=="decision":
                shap.decision_plot(explainer.expected_value,shap_values=shap_values[0],features=np.array(list(df_inst.to_dict("records")[0].values())),feature_names=kwargsData["feature_names"])
            elif plot_type=="force":
                    shap.plots._force.force(explainer.expected_value,shap_values=shap_values[0],features=np.array(list(df_inst.to_dict("records")[0].values())),feature_names=kwargsData["feature_names"],out_names=target_name,matplotlib=True,show=False)
            else:
                if plot_type==None:
                    print("No plot type was specified. Defaulting to waterfall plot.")
                elif plot_type!="waterfall":
                    print("No plot with the specified name was found. Defaulting to waterfall plot.")
                shap.plots._waterfall.waterfall_legacy(explainer.expected_value,shap_values=shap_values[0],features=np.array(list(df_inst.to_dict("records")[0].values())),feature_names=kwargsData["feature_names"],show=False)
       
            #saving force plot to html (DEPRECATED)
            #additive_exp = shap.force_plot(explainer.expected_value, shap_values,features=np.array(instance),feature_names=kwargsData["feature_names"],out_names=out_names,show=False)
        
            #formatting json output
            #shap_values = [x.tolist() for x in shap_values]
            #ret=json.loads(json.dumps(shap_values))

            ##saving
            img_buf = BytesIO()
            plt.savefig(img_buf,bbox_inches="tight")
            im = Image.open(img_buf)
            b64Image=PIL_to_base64(im)
            plt.close()

            response={"type":"image","explanation":b64Image,"explanation_llm":json.loads(pd.DataFrame(shap_values, columns=feature_names).to_json(orient="index"))}

            return response
        except:
            return traceback.format_exc(), 500

    def get(self,id=None):
        
        base_dict={
        "_method_description": "This method displays the contribution of each attribute for an individual prediction based on Shapley values. This method accepts 4 arguments: " 
                           "the 'id', the 'instance', the 'url',  and the 'params' JSON with the configuration parameters of the method. "
                           "These arguments are described below.",
        "id": "Identifier of the ML model that was stored locally.",
        "instance": "Array with the feature values of an instance without including the target class.",
        "url": "External URL of the prediction function. Ignored if a model file was uploaded to the server. "
               "This url must be able to handle a POST request receiving a (multi-dimensional) array of N data points as inputs (instances represented as arrays). It must return a array of N outputs (predictions for each instance).",
        "params": { 
                "target_class": {
                    "description":"Name of the target class to be explained. Ignore for regression models. Defaults to the first class target class defined in the configuration file.",
                    "type":"string",
                    "default": None,
                    "range":None,
                    "required":False
                    },
                "plot_type": {
                    "description":"String with the name of the plot to be generated.",
                    "type":"string",
                    "default": "waterfall",
                    "range":['waterfall','decision','force','bar'],
                    "required":False
                    }
                },

        "output_description":{
                "waterfall_plot": "Waterfall plots are designed to display explanations for individual predictions, so they expect a single row of an Explanation object as input. "
                                    "The bottom of a waterfall plot starts as the expected value of the model output, and then each row shows how the positive (red) or negative (blue) contribution of "
                                    "each feature moves the value from the expected model output over the background dataset to the model output for this prediction.",
                "force_plot":"Displays the contribution of each attribute as a plot that confronts the features that contribute positively (left) and the ones that contribute negatively (right) to the predicted outcome. "
                             "The predicted outcome is displayed as a divisory line between the positive and negative contributions.",

                "decision_plot": "A decision plot shows how a complex model arrive at its predictions. "
                                "The decision plot displays the average of the model's base values and shifts the SHAP values accordingly to accurately reproduce the model's scores."
                                "The straight vertical line marks the model's base value. The colored line is the prediction. Feature values are printed next to the prediction line for reference."
                                "Starting at the bottom of the plot, the prediction line shows how the SHAP values (i.e., the feature effects) accumulate from the base value to arrive at the model's final score at the top of the plot. ",

                "bar_plot": "The bar plot is a local feature importance plot, where the bars are the SHAP values for each feature. Note that the feature values are shown in the left next to the feature names."
         },
        "meta":{
                "modelAccess":"Any",
                "supportsBWImage":False,
                "needsTrainingData": True
            }
        }

        if id is not None:
            #Getting model info, data, and file from local repository
            try:
                _, model_info_file, _ = get_model_files(id,self.model_folder)
                model_info=json.load(model_info_file)
            except:
                return base_dict

            target_name=model_info["attributes"]["target_names"][0]
            output_names=model_info["attributes"]["features"][target_name]["values_raw"]

            base_dict["params"]["target_class"]["range"]=output_names
            base_dict["params"]["target_class"]["default"]=output_names[1]

            return base_dict

        else:
            return base_dict
    

