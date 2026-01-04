from time import time
import os
from openai import OpenAI

from transformers import AutoTokenizer
import json
import ast
import sys
#import ollama
import textwrap
import asyncio
import shutil
from utilts import find_identifiers_scope,find_builtin_func,extract_standard_calls,get_non_standard_calls,ImportCollector,generate_call_graph
from prompt import system_prompt_comm,user_prompt_comm_step1,user_prompt_comm_step2,system_prompt_builtin,user_prompt_builtin_step1,user_prompt_builtin_step2,system_prompt_stdlib_and_thirdlib,user_prompt_stdlib_and_thirdlib_step1,user_prompt_stdlib_and_thirdlib_step2

import csv
import re
from tqdm import tqdm

# 加载 JSON 文件
def load_json(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)

# 构建调用关系字典
def build_call_dict_and_reverse(project_data):
    """
    构建调用关系字典 (caller -> callee) 和反向字典 (callee -> callerD)
    """
    call_dict = {}
    callee_to_callers_dict = {}

    # 假设 project_data 是一个字典，包含了所有的调用关系数据
    for caller, callees in project_data.items():
        if caller not in call_dict:
            call_dict[caller] = []
        
        # 构建 caller -> callee 的字典
        for callee in callees:
            call_dict[caller].append(callee)
            
            # 构建 callee -> callers 的反向字典
            if callee not in callee_to_callers_dict:
                callee_to_callers_dict[callee] = []
            callee_to_callers_dict[callee].append(caller)

    return call_dict, callee_to_callers_dict


# 构建函数信息字典
def build_func_info_dict(pre_annotations_data):
    func_info_dict = {}
    for func_name, func_info in pre_annotations_data.items():
        func_info_dict[func_name] = func_info
    return func_info_dict

def is_magic_method(method_name: str) -> bool:
    # 判断字符串是否以双下划线开头和结尾
    return method_name.startswith('__') and method_name.endswith('__')

def remove_comments(code: str) -> str:
    if code :
        # 移除单行注释
        code = re.sub(r'#.*', '', code)
        # 移除多行注释（单引号和双引号）
        code = re.sub(r'"""(.*?)"""', '', code, flags=re.DOTALL)
        code = re.sub(r"'''(.*?)'''", '', code, flags=re.DOTALL)
        # code = re.sub(r"'(.*?)'", '', code, flags=re.DOTALL)
        # code = re.sub(r'"(.*?)"', '', code, flags=re.DOTALL)
        return code
    else :
        return ""

def contains_in_code(caller_code: str, class_name: str) -> bool:
    if caller_code == None:
        return False
    if class_name not in caller_code:
        return False
    pattern = rf"(?<![a-zA-Z0-9]){re.escape(class_name)}(?![a-zA-Z0-9])"
    return re.search(pattern, caller_code) is not None

# 获取候选被调函数
def get_candidate_callees(name, call_dict, func_info_dict, import_info,all_or_EA):
    candidate_callees = {}
    candidate_callees_builtin = {}
    candidate_callees_stdlib = {}
    candidate_callees_non_stdlib = {}
    candidate_callees_stdlib_and_thirdlib = {}
    for caller in func_info_dict:
        # if caller in func_info_dict and caller == func_info_dict[caller]["filepath"]:
        #     continue
        #print(caller)
        if caller not in func_info_dict or func_info_dict[caller]["name_type"] != "local_name":#只选取local_name作为调用函数
            continue
        caller_code = func_info_dict[caller]["body"]
        caller_name = caller.split('.')[-1]
        import_module = import_info[func_info_dict[caller]["filepath"]]
        global_fg = 0
        if caller == func_info_dict[caller]["filepath"]:#调用者是global的情况 
            global_fg = 1
        had_fun = []
        # if caller in call_dict:
        #     had_fun = call_dict[caller]
        if caller_code != "":  
            candidate_callees_builtin[caller] = find_builtin_func(caller_code,caller_name,had_fun,global_fg)
            #candidate_callees_stdlib[caller] = extract_standard_calls(import_module.rstrip() + "\n\n" + textwrap.dedent(caller_code))
            #candidate_callees_non_stdlib[caller] = get_non_standard_calls(import_module.rstrip() + "\n\n" + textwrap.dedent(caller_code))
            try :
                candidate_callees_stdlib_and_thirdlib[caller] = generate_call_graph(import_module.rstrip() + "\n\n" + textwrap.dedent(caller_code))
            except:
                pass

        candidates = []
        for callee in func_info_dict:
            if name == "micro-benchmark":
                if ".".join(caller.split(".")[:3]) != ".".join(callee.split(".")[:3]):#处理micro
                    continue
                if caller == callee:
                    continue
                candidates.append(callee)  
                continue
            if all_or_EA == 0:#只选取local_name的情况
                if callee not in func_info_dict or func_info_dict[callee]["name_type"] != "local_name":
                    continue
            # if (caller in call_dict and callee in call_dict[caller]) or caller == callee:
            #     continue
            if callee not in func_info_dict or func_info_dict[callee]["name_type"] == "stdlib":#stdlib不用处理
                continue

            if callee == func_info_dict[callee]["filepath"]:#被调用者是global的情况
                continue
            # if callee in func_info_dict and func_info_dict[callee]["body"] == "":
            #     continue
            if callee.split('.')[-1] == "__init__":#调用类放在下面处理
                continue
            # if func_info_dict[callee]["name_type"] != "local_name": #被调用者不是local_name的情况(可能是标准库和第三方库)
            #     scopes = find_identifiers_scope(caller_code)
            #     if callee.split('.')[-1].startswith("__") and callee.split('.')[-1].endswith("__"):
            #         check_list = callee.split('.')[:-1]
            #     else :
            #         check_list = callee.split('.')
            #     flag = 1
            #     for i in check_list:
            #         if contains_in_code(import_module,i) == False and contains_in_code(caller_code,i) == False:
            #             flag = 0
            #     if flag == 1:
            #         candidates.append(callee)
            # else :
            
            tree = ast.parse(import_module)
            import_collector = ImportCollector()
            import_collector.visit(tree)
            init_module = "\n"
            for module in import_collector.module_list:
                if module and '.' not in module and module in import_info:
                    init_module += import_info[module]
  

            if func_info_dict[callee]["namespace"] == callee.split('.')[-1]:
                #是类的情况
                class_name = func_info_dict[callee]["namespace"]
                module_name = func_info_dict[callee]["filepath"].split('.')[-1]
                if contains_in_code(import_module + init_module,module_name) == False and contains_in_code(import_module,class_name)==False and func_info_dict[callee]["filepath"] != func_info_dict[caller]["filepath"]: #如果是相同文件下
                    continue
                # if caller.split('.')[-1] == "__init__" and func_info_dict[caller]["namespace"] == caller.split('.')[-2]:#调用者和被调用者都是__init__(类)的情况下,避免的只存在赋值，而没有初始化的情况
                #     continue

                if contains_in_code(caller_code ,class_name) == False:
                    if class_name not in import_collector.symbols:
                        continue
                    if class_name in import_collector.symbols and contains_in_code(caller_code,import_collector.symbols[class_name]) == False: # or callee + ".__init__"  not in func_info_dict:#必须存在__init_方法????
                        continue
 
                scopes = find_identifiers_scope(caller_code)  
                # if caller_name in scopes and class_name not in scopes[caller_name]["variable"] :
                #     continue    
                if caller_name in scopes:
                    if any(contains_in_code(callee, except_name) for except_name in scopes[caller_name]['exceptions']):
                        continue
                

                candidates.append(callee)
                
            elif callee.split('.')[-1].startswith("__") and callee.split('.')[-1].endswith("__"):
                # if callee.split('.')[-1] != "__init__" or callee.split('.')[-1] != "__enter__" or callee.split('.')[-1] != "__exit__":
                #     continue
                # 魔术方法
                module_name = func_info_dict[callee]["filepath"].split('.')[-1]
                class_name = func_info_dict[callee]["namespace"] 
                if class_name != "*" and contains_in_code(caller_code,class_name) and (contains_in_code(import_module + init_module,module_name) or func_info_dict[caller]["filepath"] == func_info_dict[callee]["filepath"]):
                    candidates.append(callee)
            elif contains_in_code(caller_code,callee.split('.')[-1]):
                #主要处理嵌套函数的情况，只有callee在当前caller主函数中有时才放入
                scopes = find_identifiers_scope(caller_code)
                module_name = func_info_dict[callee]["filepath"].split('.')[-1]
                class_name = func_info_dict[callee]["namespace"] 
                callee_name = callee.split('.')[-1]
                if caller == func_info_dict[caller]["filepath"]:
                    tmp_name = 'global'
                else :
                    tmp_name = caller_name

                if tmp_name in scopes:
                    if tmp_name in scopes and callee_name in scopes[tmp_name]['variable'] and (contains_in_code(caller_code,class_name) or (class_name in import_collector.symbols and contains_in_code(caller_code,import_collector.symbols[class_name]))  or class_name == func_info_dict[caller]["namespace"] or class_name == "*" ) and (contains_in_code(import_module + init_module,module_name) or func_info_dict[caller]["filepath"] == func_info_dict[callee]["filepath"]):
                        candidates.append(callee)
                    else :
                        callee_arg_count = None
                        callee_args = func_info_dict.get(callee, {}).get("args", "")
                        if callee_args and callee_args != "*":
                            arg_list = [arg for arg in callee_args.split(';') if arg]
                            if arg_list and arg_list[0] in ("self","cls"):
                                arg_list = arg_list[1:]
                            callee_arg_count = len(arg_list)

                        call_arg_matched = False
                        if callee_arg_count is not None and caller_code:
                            try:
                                call_tree = ast.parse(caller_code)
                                for node in ast.walk(call_tree):
                                    if isinstance(node, ast.Call):
                                        func_name = None
                                        if isinstance(node.func, ast.Name):
                                            func_name = node.func.id
                                        elif isinstance(node.func, ast.Attribute):
                                            func_name = node.func.attr
                                        if func_name == callee_name:
                                            call_args_count = len(node.args) + len([kw for kw in node.keywords if kw.arg is not None])
                                            if call_args_count == callee_arg_count:
                                                call_arg_matched = True
                                                break
                            except SyntaxError:
                                pass

                        if call_arg_matched:
                            candidates.append(callee)
                        elif "_" in callee_name and callee_name in scopes[tmp_name]['variable']:
                            candidates.append(callee) 
                        else :
                            for tmp in scopes[tmp_name]['variable']:
                                if tmp.split('.')[0] == 'self' and tmp.split('.')[-1] == callee_name:
                                    candidates.append(callee)           
        candidate_callees[caller] = candidates
    return candidate_callees,candidate_callees_builtin,candidate_callees_stdlib,candidate_callees_non_stdlib,candidate_callees_stdlib_and_thirdlib




def solve(name = "asciinema", all_or_EA=1,static_method="pycg"):

    if static_method == "pycg":
        project_json_path = "../PyCG_data/{}.json".format(name)
    elif static_method == "depends":
        project_json_path = "../Depends_data/{}.json".format(name)
    else :
        print("no static_method")
        return 
    pre_annotations_path = "../STAR/pre_knowledge/{}_pre_annotations.json".format(name)
    import_info_path = "../STAR/pre_knowledge/{}_import_info.json".format(name)
    inherited_info_path = "../STAR/pre_knowledge/{}_pre_inherited.json".format(name)

    choice = "api"
    #choice = "ollama"

    # 加载数据
    # project_data = load_json(project_json_path)
    pre_annotations_data = load_json(pre_annotations_path)
    import_info = load_json(import_info_path)
    inherited_info = load_json(inherited_info_path)

    # 构建调用关系字典
    # call_dict, callee_to_callers_dict = build_call_dict_and_reverse(project_data)
    call_dict = {}
    # 构建函数信息字典
    func_info_dict = build_func_info_dict(pre_annotations_data)

    # 获取候选被调函数
    candidate_callees, candidate_callees_builtin, candidate_callees_stdlib, candidate_callees_non_stdlib, candidate_callees_stdlib_and_thirdlib = get_candidate_callees(name, call_dict, func_info_dict,import_info,all_or_EA)

    # Sample prompts.
    # 提示示例
    generating_prompts = []
    caller_candidates = []

    class call_info:
        def get(self,x):
            pass
        def __init__(self,caller,caller_code="",caller_init="",caller_import_info="",caller_file_path="",callee="",callee_code="",callee_init="",callee_import_info="",callee_file_path="",global_info="",system_prompt="",prompt_step1="",prompt_step2=""):
            self.caller = caller
            self.caller_code = caller_code
            self.caller_init = caller_init
            self.caller_import_info = caller_import_info
            self.caller_file_path = caller_file_path
            self.callee = callee
            self.callee_code = callee_code
            self.callee_init = callee_init
            self.callee_import_info = callee_import_info
            self.callee_file_path = callee_file_path
            self.global_info = global_info
            self.system_prompt = system_prompt
            self.prompt_step1 = prompt_step1
            self.prompt_step2 = prompt_step2
            #pass

    #内置函数
    call_info_list = []
    for caller, candidates in candidate_callees.items():
        global_info = ""
        grandcaller = ""
        # if caller in callee_to_callers_dict:
        #     for grandcaller_ in callee_to_callers_dict[caller]:
        #         if grandcaller_ in func_info_dict and func_info_dict[grandcaller_]["body"] != "":
        #             global_info = func_info_dict[grandcaller_]["body"]
        #             grandcaller = grandcaller_
        #             break
        # if global_info != "" and grandcaller in func_info_dict and func_info_dict[grandcaller]["filepath"] in import_info:
        #     global_info = import_info[func_info_dict[grandcaller]["filepath"]] + global_info
            
        for candidate in candidates:
            caller_code = ""
            candidate_code = ""
            #查找caller和candidate的代码
            caller_callee = call_info(caller)
            if caller in func_info_dict:
                caller_code = func_info_dict[caller]["body"]
                caller_code = remove_comments(caller_code)
                caller_callee.caller_code = caller_code
                caller_callee.caller_file_path = func_info_dict[caller]["filepath"]
                if func_info_dict[caller]["namespace"] != "*":
                    caller_class = ".".join(caller.rsplit(".", 1)[:-1])
                    caller_init = caller_class + ".__init__"
                    if caller_init in func_info_dict and caller_init != caller:
                        caller_init_code = func_info_dict[caller_init]["body"]
                        caller_init_code = remove_comments(caller_init_code)

                        #消融 wo-global
                        #caller_init_code = ""

                        if caller_class in inherited_info and inherited_info[caller_class]["inherited"]:  #有继承
                            #caller_code = "class "+ func_info_dict[caller]["namespace"] + "(" + inherited_info[caller_class]["inherited"][0] + ")" + ":\n" + caller_init_code + "\n" + caller_code
                            caller_callee.caller_code = "class "+ func_info_dict[caller]["namespace"] + "(" + inherited_info[caller_class]["inherited"][0] + ")" + ":\n" + caller_init_code + "\n" + caller_code
                            caller_callee.caller_init = caller_init_code
                        else :
                            #caller_code = "class "+ func_info_dict[caller]["namespace"] + ":\n" + caller_init_code + "\n" + caller_code
                            caller_callee.caller_code = "class "+ func_info_dict[caller]["namespace"] + ":\n" + caller_init_code + "\n" + caller_code
                            caller_callee.caller_init = caller_init_code
                    else :
                
                        if caller_class in inherited_info and inherited_info[caller_class]["inherited"]:
                            #caller_code = "class "+ func_info_dict[caller]["namespace"] + "(" + inherited_info[caller_class]["inherited"][0] + ")" + ":\n" + caller_code
                            caller_callee.caller_code = "class "+ func_info_dict[caller]["namespace"] + "(" + inherited_info[caller_class]["inherited"][0] + ")" + ":\n" + caller_code
                        else :
                            #caller_code = "class "+ func_info_dict[caller]["namespace"] + ":\n" + caller_code
                            caller_callee.caller_code = "class "+ func_info_dict[caller]["namespace"] + ":\n" + caller_code 

            if candidate in func_info_dict:
                caller_callee.callee = candidate
                candidate_code = func_info_dict[candidate]["body"]
                candidate_code = remove_comments(candidate_code)
                caller_callee.callee_code = candidate_code
                caller_callee.callee_file_path = func_info_dict[candidate]["filepath"]
                if func_info_dict[candidate]["namespace"] != "*":
                    candidate_class = ".".join(candidate.rsplit(".", 1)[:-1])
                    candidate_init = candidate_class + ".__init__"
                    if candidate_init in func_info_dict and candidate_init != candidate:
                        candidate_init_code = func_info_dict[candidate_init]["body"]
                        candidate_init_code = remove_comments(candidate_init_code)

                        #消融 wo-global
                        #candidate_init_code = ""

                        if candidate_class in inherited_info and inherited_info[candidate_class]["inherited"]:
                            #candidate_code = "class "+ func_info_dict[candidate]["namespace"] + "(" + inherited_info[candidate_class]["inherited"][0] + ")" + ":\n" + candidate_init_code + "\n" +  candidate_code
                            caller_callee.callee_code = "class "+ func_info_dict[candidate]["namespace"] + "(" + inherited_info[candidate_class]["inherited"][0] + ")" + ":\n" + candidate_init_code + "\n" +  candidate_code
                            caller_callee.callee_init = candidate_init_code
                        else: 
                            #candidate_code = "class "+ func_info_dict[candidate]["namespace"] + ":\n" + candidate_init_code + "\n" +  candidate_code
                            caller_callee.callee_code = "class "+ func_info_dict[candidate]["namespace"] + ":\n" + candidate_init_code + "\n" +  candidate_code
                            caller_callee.callee_init = candidate_init_code
                    else :
                        if candidate_class in inherited_info and inherited_info[candidate_class]["inherited"]:
                            #candidate_code = "class "+ func_info_dict[candidate]["namespace"] + "(" + inherited_info[candidate_class]["inherited"][0] + ")" + ":\n" + candidate_code
                            caller_callee.callee_code = "class "+ func_info_dict[candidate]["namespace"] + "(" + inherited_info[candidate_class]["inherited"][0] + ")" + ":\n" + candidate_code
                        else :
                            #candidate_code = "class "+ func_info_dict[candidate]["namespace"] + ":\n" + candidate_code
                            caller_callee.callee_code = "class "+ func_info_dict[candidate]["namespace"] + ":\n" + candidate_code
                       
            # if caller_code != "":
            #     caller_candidates.append({"caller":caller,"candidate":candidate})
            # 代码上加上import信息
            if caller in func_info_dict and func_info_dict[caller]["filepath"] in import_info:
                #caller_code = import_info[func_info_dict[caller]["filepath"]] + caller_code
                caller_callee.caller_import_info = import_info[func_info_dict[caller]["filepath"]]
            if candidate in func_info_dict and func_info_dict[candidate]["filepath"] in import_info:
                #candidate_code = import_info[func_info_dict[candidate]["filepath"]] + candidate_code   
                caller_callee.callee_import_info = import_info[func_info_dict[candidate]["filepath"]]  
            caller_callee.global_info = global_info

            caller_all_code=""
            callee_all_code=""
            if name == "micro-benchmark":
                try:
                    file_path = "../STAR/repo/{}.py".format('/'.join(caller_callee.caller_file_path.split('.')))
                    with open(file_path, "r", encoding="utf-8") as f:
                        caller_all_code = f.read()
                except:
                    file_path = "../STAR/repo/{}/__init__.py".format('/'.join(caller_callee.caller_file_path.split('.')))
                    with open(file_path, "r", encoding="utf-8") as f:
                        caller_all_code = f.read()
                try:
                    file_path = "../STAR/repo/{}.py".format('/'.join(caller_callee.callee_file_path.split('.')))
                    with open(file_path, "r", encoding="utf-8") as f:
                        callee_all_code = f.read()   
                except:
                    file_path = "../STAR/repo/{}/__init__.py".format('/'.join(caller_callee.callee_file_path.split('.')))
                    with open(file_path, "r", encoding="utf-8") as f:
                        callee_all_code = f.read()                       
            #prompts_info = "\n调用者名称:"+ caller + "\n调用者代码:\n" + caller_code+ "\n被调用者名称: " + candidate + "\n被调用者代码:\n" + candidate_code + "\n全局信息的代码:\n" + global_info
            caller_callee.system_prompt = system_prompt_comm

            #消融实验，缺失被调用者代码
            # caller_callee.callee_code = ""
            # caller_callee.caller_import_info = ""
            # caller_callee.callee_import_info =""
            # caller_callee.caller_file_path=""
            # caller_callee.callee_file_path=""

            caller_callee.prompt_step1 = user_prompt_comm_step1.format(
                caller = caller_callee.caller,
                caller_code = caller_callee.caller_code,
                callee = caller_callee.callee,
                callee_code = caller_callee.callee_code,
                global_info = caller_callee.global_info,
                caller_import_info = caller_callee.caller_import_info,
                callee_import_info = caller_callee.callee_import_info,
                caller_file_path = caller_callee.caller_file_path,
                callee_file_path = caller_callee.callee_file_path,
                caller_all_code = caller_all_code,
                callee_all_code = callee_all_code
            )
            caller_callee.prompt_step2 = user_prompt_comm_step2.format(
                caller = caller_callee.caller,
                callee = caller_callee.callee
            )
            #generating_prompts.append(prompts_info)
            call_info_list.append(caller_callee)

    for caller, candidates in candidate_callees_builtin.items():
        caller_code = ""
        for candidate in candidates:
            if caller in func_info_dict:
                caller_callee = call_info(caller)
                caller_callee.callee = candidate
                caller_code = func_info_dict[caller]["body"]
                caller_code = remove_comments(caller_code)
                caller_callee.caller_code = caller_code
                if func_info_dict[caller]["namespace"] != "*":
                    caller_class = ".".join(caller.rsplit(".", 1)[:-1])
                    caller_init = caller_class + ".__init__"
                    if caller_init in func_info_dict and caller_init != caller:
                        caller_init_code = func_info_dict[caller_init]["body"]
                        caller_init_code = remove_comments(caller_init_code)

                        #消融 wo-global
                        #caller_init_code = ""
                        
                        if caller_class in inherited_info and inherited_info[caller_class]["inherited"]:  #有继承
                            #caller_code = "class "+ func_info_dict[caller]["namespace"] + "(" + inherited_info[caller_class]["inherited"][0] + ")" + ":\n" + caller_init_code + "\n" + caller_code
                            caller_callee.caller_code = "class "+ func_info_dict[caller]["namespace"] + "(" + inherited_info[caller_class]["inherited"][0] + ")" + ":\n" + caller_init_code + "\n" + caller_code
                            caller_callee.caller_init = caller_init_code
                        else :
                            #caller_code = "class "+ func_info_dict[caller]["namespace"] + ":\n" + caller_init_code + "\n" + caller_code
                            caller_callee.caller_code = "class "+ func_info_dict[caller]["namespace"] + ":\n" + caller_init_code + "\n" + caller_code
                            caller_callee.caller_init = caller_init_code
                    else :
                        if caller_class in inherited_info and inherited_info[caller_class]["inherited"]:
                            #caller_code = "class "+ func_info_dict[caller]["namespace"] + "(" + inherited_info[caller_class]["inherited"][0] + ")" + ":\n" + caller_code
                            caller_callee.caller_code = "class "+ func_info_dict[caller]["namespace"] + "(" + inherited_info[caller_class]["inherited"][0] + ")" + ":\n" + caller_code
                        else :
                            #caller_code = "class "+ func_info_dict[caller]["namespace"] + ":\n" + caller_code
                            caller_callee.caller_code = "class "+ func_info_dict[caller]["namespace"] + ":\n" + caller_code

            caller_callee.global_info = global_info[:4000]
            # if caller_code != "":
            #     caller_candidates.append({"caller":caller,"candidate":candidate})

            #prompts_info = "\n调用者名称:"+ caller + "\n调用者代码:\n" + caller_code+ "\n被调用者名称: " + candidate
            callee_obj = ""
            if caller_callee.callee.split('.')[0] == "<**PyStr**>":
                callee_obj = "The string (str) object calls"
            elif caller_callee.callee.split('.')[0] == "<**PyList**>":
                callee_obj = "The list object calls"
            elif caller_callee.callee.split('.')[0] == "<**PyDict**>":
                callee_obj = "The dictionary (dict) object calls"
            elif caller_callee.callee.split('.')[0] == "<**PySet**>":
                callee_obj = "The set object calls"
            elif caller_callee.callee.split('.')[0] == "<**PyTuple**>":
                callee_obj = "The tuple object calls"
            elif caller_callee.callee.split('.')[0] == "<**PyNum**>":
                callee_obj = "The numeric (int type) object called"
            elif caller_callee.callee.split('.')[0] == "<**PyFile**>":
                callee_obj = "The file object calls"
            elif caller_callee.callee.split('.')[0] == "<builtin>":
                callee_obj = "Python built-in functions"

            caller_callee.caller_code = caller_callee.caller_code[:10000]
            caller_callee.callee_code = caller_callee.callee_code[:2000]
            caller_callee.system_prompt = system_prompt_builtin
            caller_callee.prompt_step1 = user_prompt_builtin_step1.format(
                caller = caller_callee.caller,
                caller_code = caller_callee.caller_code,
                callee = caller_callee.callee,
                callee_code = caller_callee.callee_code,
                global_info = caller_callee.global_info,
                caller_import_info = caller_callee.caller_import_info,
                callee_name = caller_callee.callee.split('.')[-1]
            )

            caller_callee.prompt_step2 = user_prompt_builtin_step2.format(
                caller = caller_callee.caller,
                callee = caller_callee.callee,
                callee_name = caller_callee.callee.split('.')[-1],
                callee_obj = callee_obj
            )
            #generating_prompts.append(prompts_info)
            call_info_list.append(caller_callee)

    for key in candidate_callees_stdlib_and_thirdlib:#删除local_name
        candidate_callees_stdlib_and_thirdlib[key] = [
            s for s in candidate_callees_stdlib_and_thirdlib[key] 
            if not any((s == k or s in k) and func_info_dict.get(k, {}).get("name_type") == "local_name" 
                    for k in func_info_dict)
        ]
    for key in candidate_callees_stdlib_and_thirdlib:#删除name
        candidate_callees_stdlib_and_thirdlib[key] = [
            s for s in candidate_callees_stdlib_and_thirdlib[key] 
            if name not in s
        ]
    if all_or_EA == 0:
        candidate_callees_stdlib_and_thirdlib = {}
        # for key in candidate_callees_stdlib_and_thirdlib:#删除thirdlib
        #     candidate_callees_stdlib_and_thirdlib[key] = [
        #         s for s in candidate_callees_stdlib_and_thirdlib[key] 
        #         if not any((s == k or s in k or k.split('.')[0] in s) and func_info_dict.get(k, {}).get("name_type") == "third library" 
        #             for k in func_info_dict)
        #     ]


    for caller,candidates in candidate_callees_stdlib_and_thirdlib.items():
        caller_code = ""
        for candidate in candidates:
            if caller in func_info_dict:
                caller_callee = call_info(caller)
                caller_callee.callee = candidate
                caller_code = func_info_dict[caller]["body"]
                caller_code = remove_comments(caller_code)
                caller_callee.caller_code = caller_code
                if func_info_dict[caller]["namespace"] != "*":
                    caller_class = ".".join(caller.rsplit(".", 1)[:-1])
                    caller_init = caller_class + ".__init__"
                    if caller_init in func_info_dict and caller_init != caller:
                        caller_init_code = func_info_dict[caller_init]["body"]
                        caller_init_code = remove_comments(caller_init_code)

                        #消融 wo-global
                        #caller_init_code = ""
                        
                        if caller_class in inherited_info and inherited_info[caller_class]["inherited"]:  #有继承
                            #caller_code = "class "+ func_info_dict[caller]["namespace"] + "(" + inherited_info[caller_class]["inherited"][0] + ")" + ":\n" + caller_init_code + "\n" + caller_code
                            caller_callee.caller_code = "class "+ func_info_dict[caller]["namespace"] + "(" + inherited_info[caller_class]["inherited"][0] + ")" + ":\n" + caller_init_code + "\n" + caller_code
                            caller_callee.caller_init = caller_init_code
                        else :
                            #caller_code = "class "+ func_info_dict[caller]["namespace"] + ":\n" + caller_init_code + "\n" + caller_code
                            caller_callee.caller_code = "class "+ func_info_dict[caller]["namespace"] + ":\n" + caller_init_code + "\n" + caller_code
                            caller_callee.caller_init = caller_init_code
                    else :
                        if caller_class in inherited_info and inherited_info[caller_class]["inherited"]:
                            #caller_code = "class "+ func_info_dict[caller]["namespace"] + "(" + inherited_info[caller_class]["inherited"][0] + ")" + ":\n" + caller_code
                            caller_callee.caller_code = "class "+ func_info_dict[caller]["namespace"] + "(" + inherited_info[caller_class]["inherited"][0] + ")" + ":\n" + caller_code
                        else :
                            #caller_code = "class "+ func_info_dict[caller]["namespace"] + ":\n" + caller_code
                            caller_callee.caller_code = "class "+ func_info_dict[caller]["namespace"] + ":\n" + caller_code

            caller_callee.caller_code = caller_callee.caller_code[:10000]
            caller_callee.callee_code = caller_callee.callee_code[:2000]

            #消融实验，缺失被调用者代码
            #caller_callee.callee_code = ""

            caller_callee.system_prompt = system_prompt_stdlib_and_thirdlib
            caller_callee.prompt_step1 = user_prompt_stdlib_and_thirdlib_step1.format(
                caller = caller_callee.caller,
                caller_code = caller_callee.caller_code,
                callee = caller_callee.callee,
                callee_code = caller_callee.callee_code,
                global_info = caller_callee.global_info,
                caller_import_info = caller_callee.caller_import_info,
                callee_name = caller_callee.callee.split('.')[-1]
            )

            caller_callee.prompt_step2 = user_prompt_stdlib_and_thirdlib_step2.format(
                caller = caller_callee.caller,
                callee = caller_callee.callee,
                callee_name = caller_callee.callee.split('.')[-1],
                callee_obj = callee_obj
            )
            #generating_prompts.append(prompts_info)
            call_info_list.append(caller_callee)
            



    # with open("./prompt/{}_prompt_update.txt".format(name),"w",encoding="utf-8") as f:
    #     for call in call_info_list:
    #         f.write(str(call.system_prompt[:9000]))
    #         f.write(str(call.prompt_step1[:10000]))
    #         f.write(str(call.prompt_step2[:9000]))
    #         f.write("\n\n\n")
    print("{:<20} total prompts:".format(name),end="")
    print(len(call_info_list))
    custom_id = 0
    start_id = custom_id
    with open('./data/{}_data.csv'.format(name), mode='w', newline='', encoding='utf-8') as file:
        writer = csv.writer(file)
        for call in call_info_list:
            writer.writerow([custom_id, call.system_prompt[:9000], call.prompt_step1[:10000] + call.prompt_step2[:9000], call.caller,call.callee,name])
            custom_id += 1

    project_data = {}
    file2class = {}
    for i, call in enumerate(call_info_list):  
        caller, candidate = call.caller, call.callee
        if caller in project_data:
            project_data[caller].append(candidate)  # 将 candidate 添加到原列表
            # 去重
            project_data[caller] = list(set(project_data[caller]))
        else:
            project_data[caller] = []
            project_data[caller].append(candidate)  # 如果 caller 不存在，直接插入        
    filename_with_extension = project_json_path.split('/')[-1]
    if all_or_EA == 0 and name != "micro-benchmark":
        for caller in func_info_dict:
            if func_info_dict[caller]["namespace"] == caller.split('.')[-1]:
                if func_info_dict[caller]["filepath"] in file2class:
                    file2class[func_info_dict[caller]["filepath"]].append(caller)
                    file2class[func_info_dict[caller]["filepath"]] = list(set(file2class[func_info_dict[caller]["filepath"]]))
                else:
                    file2class[func_info_dict[caller]["filepath"]] = []
                    file2class[func_info_dict[caller]["filepath"]].append(caller)
                if func_info_dict[caller]["filepath"] in project_data:
                    project_data[func_info_dict[caller]["filepath"]].append(caller)
                    project_data[func_info_dict[caller]["filepath"]] = list(set(project_data[func_info_dict[caller]["filepath"]]))
                else:
                    project_data[func_info_dict[caller]["filepath"]] = []
                    project_data[func_info_dict[caller]["filepath"]].append(caller)
        for caller in import_info:
            tree = ast.parse(import_info[caller])
            import_collector = ImportCollector()
            import_collector.visit(tree)
            for callee,_ in import_collector.symbols.items():
                if name not in callee or '*' in callee:
                    continue
                callee = str(callee)
                if caller in file2class:
                    file2class[caller].append(callee)
                    file2class[caller] = list(set(file2class[caller]))
                else:
                    file2class[caller] = []
                    file2class[caller].append(callee)
                if caller in project_data:
                    project_data[caller].append(callee)
                    project_data[caller] = list(set(project_data[caller]))
                else:
                    project_data[caller] = []
                    project_data[caller].append(callee)


    for caller,candidate in candidate_callees_stdlib_and_thirdlib.items():
        if caller in project_data:
            project_data[caller].extend(candidate)
        else :
            project_data[caller]=candidate
    # for caller,candidate in call_dict.items():
    #     if caller in project_data:
    #         project_data[caller].extend(candidate)
    #     else :
    #         project_data[caller]=candidate        
    with open("../Ae_data/{}".format(filename_with_extension), "w", encoding="utf-8") as file:
        json.dump(project_data, file, indent=4, ensure_ascii=False)
    with open("../file2class_data/{}".format(filename_with_extension), "w", encoding="utf-8") as file:
        json.dump(file2class, file, indent=4, ensure_ascii=False)
    with open("../stdlib_and_thirdlib_data/{}".format(filename_with_extension), "w", encoding="utf-8") as file:
        json.dump(candidate_callees_stdlib_and_thirdlib, file, indent=4, ensure_ascii=False)
    return  

    

if __name__ == "__main__":
    project_name_list_1 = ["asciinema","autojump","fabric","face_classification","Sublist3r"]
    project_name_list_2 = ['bpytop','furl','rich_cli','sqlparse','sshtunnel','textrank4zh']
    #project_name_list_1 = ["asciinema","autojump"] #测试集
    #project_name_list_2 = ['sqlparse','sshtunnel','textrank4zh'] #测试集
    project_list_id = [
        1,3,4,6,7,8,9,11,12,13,14,15,16,17,18,19,20,22,23,24,25,28,29,31,32,33,35,36,37,38,45,46,48,50,52,53,56,57,58
    ]
    # for i in project_list_id:
    #     project_name = "project{}".format(i)
    #     project_path = './data/{}_data.csv'.format(project_name)
    #     if os.path.exists(project_path):
    #         print("{} pass~".format(project_name))
    #         continue
    #     solve(project_name,1,static_method="pycg")
    # # if os.path.exists("./data.csv"):
    # #     os.remove("./data.csv") 

    for project_name in project_name_list_1:
        solve(project_name,1,static_method="pycg")
    for project_name in project_name_list_2:
        solve(project_name,0,static_method="pycg")

    ###单文件演示 static_method没用 0,1只会影响是否存在文件对类定义的调用
    #solve('asciinema',1,static_method="pycg")

    
