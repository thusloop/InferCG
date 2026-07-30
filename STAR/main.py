# coding: utf-8

import sys
import time
import json
from forwardprocess import ForwardVisitor
from backwardprocess import BackwardVisitor
from log import logger
import logging
from invoke_local import get_annotation
from inference import inference

import os

from ConstructKB.get_pre_sta import get_knowledge
def add_annotation(name,forwardprocessor):
    annotations = get_annotation(name)
    for item in forwardprocessor.funcs_manager.names:
        if item not in annotations[name]:
            annotations[name][item] = {'API_name':item,'loc_name':item}
    for item in forwardprocessor.classes_manager.names:
        if item not in annotations[name]:
            annotations[name][item] = {'API_name':item,'loc_name':item}
    with open(f'pre_knowledge/{name}_pre_annotations.json','w') as f:
        json.dump(annotations,f,indent=4)

if __name__ == '__main__':


    ###以下为测试单个项目用法
    pro_name = "django"
    pro_path = r"E:\001_some_AI_code\003_AutoExtension\STAR\repo\django"
    depconfig_path = r"E:\001_some_AI_code\003_AutoExtension\STAR\repo\django"
    get_knowledge(pro_name,pro_path,depconfig_path)


