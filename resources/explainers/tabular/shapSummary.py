from http.client import BAD_REQUEST
from flask_restful import Resource
import joblib
import json
from explainerdashboard import ClassifierExplainer, RegressionExplainer
from explainerdashboard.dashboard_components.shap_components import ShapSummaryComponent
from flask import request
from getmodelfiles import get_model_files
from utils import ontologyConstants
import traceback


class ShapSummary(Resource):

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

        _id =params["id"]

        return self.explain(_id)


    def explain(self,_id):
        try:
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
            model_task = model_info["model_task"]  

            #loading model (.pkl file)
            if model_file!=None:
                if backend in ontologyConstants.SKLEARN_URIS:
                    model = joblib.load(model_file)
                elif backend in ontologyConstants.XGBOOST_URIS:
                    model = joblib.load(model_file)
                elif backend in ontologyConstants.LIGHTGBM_URIS:
                    model = joblib.load(model_file)
                else:
                    return "This explainer only supports scikit-learn-based models",BAD_REQUEST
            else:
                return "Model file was not uploaded.",BAD_REQUEST

            if model_task in ontologyConstants.CLASSIFICATION_URIS:
                explainer = ClassifierExplainer(model, dataframe.drop([target_name], axis=1, inplace=False), dataframe[target_name])
            elif model_task in ontologyConstants.REGRESSION_URIS:
                explainer = RegressionExplainer(model, dataframe.drop([target_name], axis=1, inplace=False), dataframe[target_name])
            else:
                return "AI task not supported. This expliners only supports scikit-learn-based classifiers or regressors.",BAD_REQUEST

            exp=ShapSummaryComponent(explainer)

            exp_html=exp.to_html().replace('\n', ' ').replace("\"","'")

            response={"type":"html","explanation":exp_html,"explanation_llm":exp_html}
        except:
            return traceback.format_exc(), 500

    def get(self,id=None):
        return {
        "_method_description": "Displays de average SHAP values for the top features of the model. Only supports scikit-learn-based models. This method accepts only 1 argument: " 
                           "the model 'id'",
        "id": "Identifier of the ML model that was stored locally.",
        "output_description":{
                "bar_plot": "The bar plot displays the average SHAP values for each feature."
         },
        "meta":{
                "modelAccess":"File",
                "supportsBWImage":False,
                "needsTrainingData": True
            }
  
        }
    

