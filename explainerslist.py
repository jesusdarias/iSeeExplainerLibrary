﻿from flask_restful import Resource

class Explainers(Resource):
    def get(self):
        return [ '/Images/Anchors',
                 #'/Images/Counterfactuals',
                 '/Images/ClassificationReport',
                 '/Images/ConfusionMatrix',
                 '/Images/GradCam',
                 '/Images/IntegratedGradients',
                 '/Images/LIME',
                 '/Images/NearestNeighbours',
                 '/Images/SSIMCounterfactuals',
                 '/Images/SSIMNearestNeighbours',
                 '/Tabular/ALE',
                 '/Tabular/Anchors',
                 '/Tabular/ConfusionMatrix',
                 '/Tabular/CumulativePrecision',
                 '/Tabular/DeepSHAPGlobal',
                 '/Tabular/DeepSHAPLocal',
                 '/Tabular/DicePrivate',
                 '/Tabular/DicePublic',
                 '/Tabular/DisCERN',
                 '/Tabular/ICE',
                 '/Tabular/IREX',
                 '/Tabular/Importance',
                 '/Tabular/KernelSHAPGlobal',
                 '/Tabular/KernelSHAPLocal',
                 '/Tabular/LiftCurve',
                 '/Tabular/LIME',
                 '/Tabular/NICE',  
                 '/Tabular/PDP',
                 '/Tabular/PertCF',
                 '/Tabular/PrecisionGraph',
                 '/Tabular/PR-AUC',
                 '/Tabular/RegressionPredictedVsActual',
                 '/Tabular/RegressionResiduals',
                 '/Tabular/ROC-AUC',
                 '/Tabular/SHAPDependence',
                 '/Tabular/SHAPInteraction',
                 '/Tabular/SHAPSummary',
                 '/Tabular/SummaryMetrics', 
                 '/Tabular/TreeSHAPGlobal',
                 '/Tabular/TreeSHAPLocal',
                 '/Text/LIME',
                 '/Text/NLPClassifier',
                 '/Timeseries/CBRFox',
                 '/Timeseries/ConfusionMatrix',
                 '/Timeseries/iGenCBR',
                 '/Timeseries/LEFTIST',
                 '/Timeseries/LIMESegment',
                 '/Timeseries/NativeGuides',
                 '/Timeseries/NearestNeighbours',
                 '/Timeseries/NEVES',
                 '/Timeseries/SummaryMetrics',
                 '/Misc/AIModelPerformance']
