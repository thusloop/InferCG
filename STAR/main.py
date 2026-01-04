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

    # pro_name = sys.argv[1]
    # pro_path = sys.argv[2]
    # if len(sys.argv) > 3:
    #     depconfig_path = sys.argv[3]

    pro_name_list = ['asciinema','autojump','fabric','face_classification','Sublist3r','bpytop','furl','rich_cli','sqlparse','sshtunnel','textrank4zh']
    # pro_name = 'asciinema'
    # pro_name = 'autojump'
    # pro_name = 'fabric'
    # pro_name = 'face_classification'
    # pro_name = 'Sublist3r'
    #pro_name = 'flask'
    
    # project_list_id = [
    #     1,3,4,6,7,8,9,11,12,13,14,15,16,17,18,19,20,22,23,24,25,28,29,31,32,33,35,36,37,38,45,46,48,50,52,53,56,57,58
    # ]
    # for i in project_list_id:
    #     pro_name = "project{}".format(i)
    #     pro_path = r'E:\001_some_AI_code\003_AutoExtension\STAR\repo\{}'.format(pro_name)
    #     depconfig_path = r'E:\001_some_AI_code\003_AutoExtension\STAR\repo\{}'.format(pro_name)
    #     get_knowledge(pro_name,pro_path,depconfig_path)

    # for pro_name in pro_name_list:
    #     # if pro_name != "face_classification":
    #     #     continue
    #     #pro_name = 'textrank4zh'
    #     pro_path = r'E:\001_some_AI_code\003_AutoExtension\STAR\repo\{}'.format(pro_name)
    #     depconfig_path = r'E:\001_some_AI_code\003_AutoExtension\STAR\repo\{}'.format(pro_name)
    #     if pro_name == "asciinema":
    #         pro_path = os.path.join(pro_path,'asciinema') 
    #     if pro_name == "autojump":
    #         pro_path = os.path.join(pro_path,'bin') 
    #     if pro_name == "face_classification":
    #         pro_path = os.path.join(pro_path,'src') 
    #         #depconfig_path = os.path.join(depconfig_path,'requirements.txt') 
    #     if pro_name == "furl":
    #         pro_path = os.path.join(pro_path,'furl')
    #     if pro_name == "rich_cli":
    #         pro_path = os.path.join(pro_path,'src')    
    #     if pro_name == "sqlparse":
    #         pro_path = os.path.join(pro_path,'sqlparse') 
    #     if pro_name == "textrank4zh":
    #         pro_path = os.path.join(pro_path,'textrank4zh')   
    #     #print(pro_path)
    #     get_knowledge(pro_name,pro_path,depconfig_path)
    # get_knowledge('flask' ,'repo/flask/src/flask','repo/flask') #

    # pro_name = "micro-benchmark"
    # pro_path = r"E:\001_some_AI_code\003_AutoExtension\STAR\repo\micro-benchmark"
    # depconfig_path = r"E:\001_some_AI_code\003_AutoExtension\STAR\repo\micro-benchmark"
    # get_knowledge(pro_name,pro_path,depconfig_path)
    def list_fx_dirs(root_dir):
        result = []
        for pro in os.listdir(root_dir):
            pro_path = os.path.join(root_dir, pro)
            if not os.path.isdir(pro_path):
                continue
            for fx in os.listdir(pro_path):
                fx_path = os.path.join(pro_path, fx)
                if os.path.isdir(fx_path):
                    # 只记录 fX 层，不再深入
                    result.append(os.path.abspath(fx_path))
        return result
    def list_files_in_directory(dir_path):
        """列出指定目录中的所有文件"""
        files = set()
        for item in os.listdir(dir_path):
            item_path = os.path.join(dir_path, item)
            if os.path.isfile(item_path):  # 判断是否为文件
                original_str = item
                #print(original_str)
                suffix_to_remove = "_pre_annotations.json"
                if original_str.endswith(suffix_to_remove):
                    cleaned_str = original_str[:-len(suffix_to_remove)]
                    files.add(cleaned_str)
                else:
                    pass
                
        return files
    project_vul_lst = list_fx_dirs(r"E:\001_some_AI_code\003_AutoExtension\STAR\vulnerable_fun")
    
    #print(has_pro)
    while True:
        flag_finished = 1
        has_pro = list_files_in_directory(r"E:\001_some_AI_code\003_AutoExtension\STAR\pre_knowledge")
        for project_vul_path in project_vul_lst:
            pro_name = os.path.basename(os.path.normpath(project_vul_path))
            print(f"处理项目: {pro_name}")
            if pro_name in has_pro:
                print(f"项目 {pro_name} 已存在预知识，跳过。")
                continue
            flag_finished = 0
            pro_path = project_vul_path
            depconfig_path = os.path.join(project_vul_path,'requirements.txt')
            try:
                get_knowledge(pro_name,pro_path,depconfig_path)
            except :
                print(f"项目 {pro_name} 处理失败，跳过。")
                pass
        if flag_finished == 1:
            print("所有项目均已处理完成，程序结束。")
            break 
        print("睡着中......")
        #time.sleep(300*2) 
        print("睡醒了!!!")

    ###以下为测试单个项目用法
    # pro_name = "django"
    # pro_path = r"E:\001_some_AI_code\003_AutoExtension\STAR\repo\django"
    # depconfig_path = r"E:\001_some_AI_code\003_AutoExtension\STAR\repo\django"
    # get_knowledge(pro_name,pro_path,depconfig_path)


    ###以下不用管，原始代码
    # forwardprocessor = ForwardVisitor(pro_path,pro_name)
    # add_annotation(pro_name,forwardprocessor)
    # backprocessor = BackwardVisitor(pro_path,forwardprocessor.global_values,forwardprocessor.funcs_manager,pro_name,forwardprocessor.classes_manager)
    # annotations = get_annotation(pro_name)
    # inference(pro_name,backprocessor,annotations,f'result/{pro_name}.json')
    