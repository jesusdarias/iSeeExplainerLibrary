from flask_restful import Resource,reqparse
from flask import request
from PIL import Image
import numpy as np
import torch
import json
import werkzeug
import numpy as np
from pytorch_grad_cam.utils.image import show_cam_on_image,preprocess_image
from pytorch_grad_cam.utils.model_targets import ClassifierOutputTarget
from pytorch_grad_cam import GradCAM
from saveinfo import save_file_info
from getmodelfiles import get_model_files

class GradCamTorch(Resource):

    def __init__(self,model_folder,upload_folder):
        self.model_folder = model_folder
        self.upload_folder = upload_folder
        
    def post(self):
        parser = reqparse.RequestParser()
        parser.add_argument("id", required=True)
        parser.add_argument('instance')  
        parser.add_argument("image", type=werkzeug.datastructures.FileStorage, location='files')
        parser.add_argument('params')
        args = parser.parse_args()
        
        _id = args.get("id")
        instance=args.get("instance")
        image = args.get("image")
        params=args.get("params")
        params_json={}
        if(params !=None):
            params_json = json.loads(params)

        #Getting model info, data, and file from local repository
        model_file, model_info_file, _ = get_model_files(_id,self.model_folder)

        #loading model
        if model_file!=None:
            mlp = torch.load(model_file)
            mlp.eval()
        else:
            raise Exception("This method requires a PyTorch model to be uploaded.")

        ## params from info
        target_layers=None
        mean=[0.5,0.5,0.5]
        std=[0.5,0.5,0.5]
        model_info=json.load(model_info_file)
        backend = model_info["backend"]  
        if backend!="PYT":
            raise Exception("Only PyTorch models are compatible with this explanation method.")
        if "mean" in model_info:
            mean=model_info["mean"]
        if "std" in model_info:
            std=model_info["std"]
        if "target_layer" in model_info:
            if hasattr(mlp,model_info["target_layer"]):
                target_layers = [getattr(mlp,model_info["target_layer"])]
            else:
                raise Exception("The specified target layer" + str(model_info["target_layer"]) + "does not exist.")
        else:
            raise Exception("This method requires the name of target layer to be provided as a string. This is the layer that you want to compute the visualization for."\
                " Usually this will be the last convolutional layer in the model. It is also possible to specify internal components of this layer by passing the"\
                " target_layer_index parameter in params. To get the target layer, this method executes 'model.<target_layer>[<target_layer_index>]'"\
                " Some common examples of these parameters for well-known models:"\
                " Resnet18 and 50: model.layer4 -> 'target_layer':'layer4'"\
                " VGG, densenet161: model.features[-1] -> 'target_layer':'features', 'target_layer_index':-1"\
                " mnasnet1_0: model.layers[-1] -> 'target_layer':'layers', 'target_layer_index':-1")


        rgb_img=None        
        if instance!=None:
            try:
                rgb_img = np.array(json.loads(instance))
            except:
                raise Exception("Could not read instance from JSON.")
        elif image!=None:
             try:
                rgb_img  = np.asarray(Image.open(image))
             except:
                 raise Exception("Could not load image from file.")
        else:
            raise Exception("Either an image file or a matrix representative of the image must be provided.")
        if len(rgb_img.shape)<3:
            raise Exception("The provided image must be RGB-encoded.")
        rgb_img = np.float32(rgb_img) / 255
        input_tensor = preprocess_image(rgb_img,
                                mean=mean,
                                std=std)

        if "target_layer_index" in params_json:
            try:
                target_layers=[target_layers[0][int(params_json["target_layer_index"])]]
            except:
                raise Exception("The specified index could not be accessed in the target_layer.")

        target=None
        if "target_class" in params_json:
            target = [ClassifierOutputTarget(int(params_json["target_class"]))]

        aug_smooth=True
        if "aug_smooth" in params_json:
            aug_smooth= bool(params_json["aug_smooth"])

        cam  = GradCAM(model=mlp,
                   target_layers=target_layers, use_cuda=torch.cuda.is_available())
        grayscale_cam = cam(input_tensor=input_tensor, targets=target,aug_smooth=aug_smooth,eigen_smooth=True)
        grayscale_cam = grayscale_cam[0, :]
        cam_image = show_cam_on_image(rgb_img, grayscale_cam, use_rgb=True)
  
        #saving
        upload_folder, filename, getcall = save_file_info(request.path,self.upload_folder)
        cam_image = Image.fromarray(cam_image)
        cam_image.save(upload_folder+filename+'.png')

        response={"plot_png":getcall+".png"}
        return response

    def get(self):
        return {
        "_method_description": "Gradient-weighted Class Activation Mapping (Grad-CAM), uses the gradients of any target concept, flowing into the final convolutional layer to produce a coarse localization map highlighting important regions in the image for predicting the concept."
                           "This method accepts 4 arguments: " 
                           "the 'id', the 'params' dictionary (optional) with the configuration parameters of the method, the 'instance' containing the image that will be explained as a matrix, or the 'image' file instead. "
                           "These arguments are described below.",

        "id": "Identifier of the ML model that was stored locally.",
        "instance": "Matrix representing the image to be explained.",
        "image": "Image file to be explained. Ignored if 'instance' was specified in the request. Passing a file is only recommended when the model works with black and white images, or color images that are RGB-encoded using integers ranging from 0 to 255.",
        "params": { 
                "target_layer_index": "(Optional) index of the target layer to be accessed. Provide it when you want to focus on a specific component of the target layer."
                                      "If not provided, the whole layer specified as target when uploading the model will be used.",
                "target_class": "(Optional) Integer representing the index of the target class to generate the explanation. If not provided, defaults to the class with the highest predicted probability.",
                "aug_smooth": "(Optional) Boolean indicating whether to apply augmentation smoothing (defaults to True). This has the effect of better centering the CAM around the objects. However, it increases the run time by x6."
                },
        "output_description":{
                "saliency_map":"Displays an image that highlights the region that contributes the most to the target class."
            }

        }