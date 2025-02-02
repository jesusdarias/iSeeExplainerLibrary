from http.client import BAD_REQUEST
from flask_restful import Resource
import json
import pandas as pd
from getmodelfiles import get_model_files
import joblib
from pertCF.PertCF import PertCF
from flask import request
from utils import ontologyConstants
from utils.dataframe_processing import normalize_dataframe, denormalize_dataframe
import traceback

class Pertcf(Resource):

    def __init__(self,model_folder,upload_folder):
        self.model_folder = model_folder
        self.upload_folder = upload_folder

    def post(self):
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
        params_json={}
        if "params" in params:
            params_json=params["params"]

        #getting model info, data, and file from local repository
        model_file, model_info_file, data_file = get_model_files(_id, self.model_folder)


        ## params from model info
        model_info=json.load(model_info_file)
        backend = model_info["backend"]

        #loading data
        if data_file!=None:
            data = joblib.load(data_file) 
        else:
            return "The training data file was not provided.",BAD_REQUEST

        ## loading model
        model=None
        if model_file!=None:
            if backend in ontologyConstants.SKLEARN_URIS:
                model = joblib.load(model_file)
            else:
                return "This method currently supports scikit-learn classification models only.",BAD_REQUEST
        else:
            return "The model file was not uploaded.",BAD_REQUEST

        return self.explain(model, model_info, data, params_json, instance)

    def explain(self,model, model_info, data=None, params_json=None, instance=None):

        try:
            #params from model info
            features=model_info["attributes"]["features"]
            target_name=model_info["attributes"]["target_names"][0]
            output_names=features[target_name]["values_raw"]
            label=target_name
            feature_names=list(data.columns)
            feature_names.remove(label)

            feature_groups={'categorical': None, 'numeric': None, 'ordinal': None}

            #params from json
            encode_cat='OrdinalEncoder'
            if 'encode_cat' in params_json:
                encode_cat = str(params_json['encode_cat'])
            global_sim='euclidean'
            if 'global_sim' in params_json:
                global_sim = str(params_json['global_sim'])
            local_sim='auto'
            if 'local_sim' in params_json:
                local_sim = str(params_json['local_sim'])
            sample_shap=50
            if 'shap_sample' in params_json:
                sample_shap=int(params_json['shap_sample'])
            candidate_threshold=0.5
            if 'candidate_threshold' in params_json:
                candidate_threshold=float(candidate_threshold)
            candidate_max_iter=20
            if 'candidate_max_iter' in params_json:
                candidate_max_iter=int(candidate_max_iter)


            model.feature_names_in_=feature_names
            explainer = PertCF(dataset = data,
                               label = label,
                               model = model,
                               feature_names = feature_groups, ###
                               encode_cat = encode_cat,
                               global_sim = global_sim,
                               local_sim = local_sim,
                               shap_param = {'sample':sample_shap,'Visualize': False, 'Normalize': False},
                               candidate_param = {'thresh':candidate_threshold,'max_iter':candidate_max_iter})


            #normalize instance
            df_inst=pd.DataFrame([instance.values()],columns=instance.keys())
            if target_name in df_inst.columns:
                df_inst.drop([target_name], axis=1, inplace=True)
            df_inst=df_inst[feature_names]
            norm_instance=normalize_dataframe(df_inst,model_info)

            test_label = model.predict(norm_instance.to_numpy())[0]
            norm_instance[label]=test_label

            norm_explanation = explainer.explain(norm_instance.iloc[0])
            denorm_explanation=denormalize_dataframe(norm_explanation,model_info)
            denorm_explanation.index.name=None

            ret={"type":"html", "explanation":denorm_explanation.to_html(),"explanation_llm":json.loads(denorm_explanation.to_json(orient="index"))}
            return ret

        except:
            return traceback.format_exc(), 500
    
    def get(self,id=None):
        
        base_dict={
        "_method_description": "PertCF is a perturbation-based counterfactual generation method \
                              that benefits from the feature attributions generated by the SHAP. \
                              PertCF combines the strengths of perturbation-based counterfactual \
                              generation and feature attribution to generate high-quality, stable, \
                              and interpretable counterfactuals. This method accepts 3 arguments: \
                              'id', 'instance', and the execution 'params'.",


        "id": "Identifier of the ML model that was stored locally.",
        "instance": "Dictionary representing the instance to be explained.",
        "params": {

            "encode_cat": {
                "description": "Encoding technique for categorical features. Prefer the same technique that is used for the model for reliable results.",
                "type": "string",
                "range": ['auto', 'manual', 'BackwardDifferenceEncoder', 'BaseNEncoder', 'BinaryEncoder',
                          'CatBoostEncoder', 'CountEncoder', 'GLMMEncoder', 'GrayEncoder', 'HelmertEncoder',
                          'JamesSteinEncoder', 'LeaveOneOutEncoder', 'MEstimateEncoder', 'OneHotEncoder',
                          'OrdinalEncoder', 'PolynomialEncoder', 'QuantileEncoder', 'RankHotEncoder',
                          'SumEncoder', 'TargetEncoder', 'WOEEncoder'],
                "default": 'OrdinalEncoder',
                "required": False
            },

            "global_sim": {
                "description": "Global similarity technique.",
                "type": "string",
                "range": ['ManualEuclidean', 'ShapEuclidean', 'braycurtis', 'canberra', 'chebyshev', 'jaccard',
                          'hamming', 'cosine', 'sqeuclidean', 'cityblock', 'minkowski', 'euclidean'],
                "default": 'euclidean',
                "required": False
            },

            "local_sim": {
                "description": "Local similarity technique.",
                "type": "string",
                "range": ['manual', 'auto'],
                "default": 'auto',
                "required": False
            },

            "shap_sample": {
                "description": "Number of samples to use for calculating the SHAP values faster.",
                "type": "int",
                "default": 50,
                "required": False
            },

            "candidate_threshold": {
                "description": "Step size threshold between CF candidates.",
                "type": "float",
                "range":[0,1],
                "default": 0.5,
                "required": False
            },

            "candidate_max_iter": {
                "description": "Maximum number of iterations to generate CF.",
                "type": "int",
                "default": 20,
                "required": False
            }
        },

        "output_description":{
                "html_table": "An html page containing a table with the generated couterfactuals."
               },
        "meta":{
                "modelAccess":"File",
                "supportsBWImage":False,
                "needsTrainingData": True
        }
    }

        if id is not None:
            #Getting model info, data, and file from local repository
            try:
                _, model_info_file, data_file = get_model_files(id,self.model_folder)
            except:
                return base_dict


            dataframe = joblib.load(data_file)
            model_info=json.load(model_info_file)
            target_name=model_info["attributes"]["target_names"][0]
            feature_names=list(dataframe.columns)
            feature_names.remove(target_name)

            base_dict["params"]["shap_sample"]["range"]=[1,dataframe.shape[0]]
            base_dict["params"]["shap_sample"]["default"]=int(dataframe.shape[0]/10)
        
            return base_dict
        else:
            return base_dict
