import ast
import os
import re
import json

# from importlib_metadata import entry_points
from ConstructKB.Import_Level.core import *
from ConstructKB.Import_Level.core.source_visitor import SourceVisitor
# from wheel_inspect import inspect_wheel
import tarfile
from zipfile import ZipFile

import importlib
import inspect

function_body = {}
class Tree:
    def __init__(self, name):
        self.name = name
        self.children = []
        self.parent = None
        self.cargo = {}
        self.source = ''
        self.ast = None
    def __str__(self):
        return str(self.name)

def parse_import(tree):
    module_item_dict = {}
    try:
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom): 
                if node.module is None and node.level not in module_item_dict:
                    module_item_dict[node.level] = []
                elif node.module not in module_item_dict:
                   module_item_dict[node.module] = []
                items = [nn.__dict__ for nn in node.names]
              
                for d in items:
                    if d['name'] == 'compute':
                        print('point')
                    if node.module is None:
                        module_item_dict[node.level].append(d['name'])
                    else:
                        module_item_dict[node.module].append(d['name'])
        return module_item_dict
    except(AttributeError):
        return None
    
def parse_import_code(tree):
    """
    解析文件中的 import 语句，并返回导入的模块信息（源码形式）。
    """
    import_code = ""  # 存储导入的模块信息（源码格式）

    try:
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):  # 处理 'from ... import ...' 类型
                module = node.module if node.module is not None else "." * node.level  # 处理 from . import v1
                for alias in node.names:
                    if alias.asname:  # 处理别名
                        import_code += f"from {module} import {alias.name} as {alias.asname}\n"
                    else:
                        import_code += f"from {module} import {alias.name}\n"
            elif isinstance(node, ast.Import):  # 处理 'import ...' 类型
                for alias in node.names:
                    if alias.asname:
                        import_code += f"import {alias.name} as {alias.asname}\n"
                    else:
                        import_code += f"import {alias.name}\n"

        return import_code
    except AttributeError:
        return ""


 
def gen_AST(filename):
    try:
        source = open(filename).read()
        tree = ast.parse(source, mode='exec')
        return tree
    except (SyntaxError,UnicodeDecodeError,):  
        pass
        return None
def parse_pyx(filename):
    lines = open(filename).readlines()
    all_func_names = []
    for line in lines:
        names = re.findall('def ([\s\S]*?)\(', str(line))
        if len(names)>0:
            all_func_names.append(names[0])

def extract_class(filename):
    try:
        # print(filename)
        source = open(filename).read()
        tree = ast.parse(source, mode='exec')
        visitor = SourceVisitor()
        visitor.visit(tree)
        # print('testing')
        return visitor.result, tree
    except Exception as e:  # to avoid non-python code
        # fail passing python3 
        if filename[-3:] == 'pyx':
            parse_pyx(filename)
        return {}, None  # return empty 

def extract_class_from_source(source):
    try:
        tree = ast.parse(source, mode='exec')
        visitor = SourceVisitor()
        visitor.visit(tree)

        function_bodies = {}
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                start_line = node.lineno - 1  # Line number starts from 1 in AST
                if node.decorator_list:  # 检查是否有装饰器
                    start_line = node.decorator_list[0].lineno - 1  # 取第一个装饰器的行号
                end_line = node.end_lineno    # Available in Python 3.8+
                function_bodies[node.lineno] = "\n".join(source.splitlines()[start_line:end_line])

        return visitor.result, tree, function_bodies
    except Exception as e:
        print(e)
        return {}, None, {}  # Return empty in case of error
    
def extract_top_level_code(source):
    # 解析AST并建立父节点映射
    try:
        tree = ast.parse(source)
        
        class ParentCollector(ast.NodeVisitor):
            def __init__(self):
                self.parent_map = {}
            
            def visit(self, node):
                for child in ast.iter_child_nodes(node):
                    self.parent_map[child] = node
                    self.visit(child)
        
        collector = ParentCollector()
        collector.visit(tree)
        
        # 收集所有非函数/类内部的代码行
        code_lines = source.splitlines()
        valid_lines = set()
        
        for node in ast.walk(tree):
            # 排除模块节点本身
            if isinstance(node, ast.Module):
                continue
            if isinstance(node, ast.Import) or isinstance(node, ast.ImportFrom):
                continue
            
            # 检查是否在函数/类内部
            current = node
            in_function_or_class = False
            while current is not None:
                if isinstance(current, (ast.FunctionDef, ast.ClassDef)):
                    in_function_or_class = True
                    break
                current = collector.parent_map.get(current)
            
            if not in_function_or_class:
                # 获取节点行号范围（Python 3.8+）
                if hasattr(node, 'lineno') and hasattr(node, 'end_lineno'):
                    start = node.lineno - 1  # 转换为0-based
                    end = node.end_lineno    # end_lineno是包含的
                    valid_lines.update(range(start, end))
        
        # 按行号顺序生成代码
        return '\n'.join(
            line for i, line in enumerate(code_lines)
            if i in valid_lines
        )
    except:
        pass

def build_dir_tree(node):
    if node.name in ['test', 'tests', 'testing','setup.py']:
        return 
    if os.path.isdir(node.name):
        os.chdir(node.name)
        items  = os.listdir('.')
        for item in items:
            child_node = Tree(item)
            child_node.parent =  node
            build_dir_tree(child_node)
            if child_node.name.endswith('.py') or os.path.isdir(child_node.name): 
                node.cargo[os.path.splitext(child_node.name)[0]] = ('*','*','*','*')  
                node.children.append(child_node)  
        os.chdir('..')
    else:
        if node.name.endswith('.py'):
            source = open(node.name, 'rb').read()
            node.source = source.decode("utf-8", errors="ignore")
            res, tree, function_bodies = extract_class_from_source(node.source)
            top_level_code = extract_top_level_code(node.source)
            res_new = {}
            tmp_API_prefix = leaf2root(node) 
            res_new['self_init'] = ('*','*','*',tmp_API_prefix,top_level_code)
            for k,v in res.items():
                if isinstance(v,tuple):
                    arg_names, len_defaults,node_lineno = v
                    res_new[k] = (arg_names, len_defaults, node_lineno, tmp_API_prefix, function_bodies.get(node_lineno, ""))
                elif isinstance(v, dict):
                    new_d = {}
                    for t1, t2 in v.items():
                        arg_names, len_defaults, node_lineno = t2
                        new_d[t1] = (arg_names, len_defaults, node_lineno, tmp_API_prefix, function_bodies.get(node_lineno, ""))
                    res_new[k] = new_d
                else:
                    print('wrong')
            node.cargo = res_new
            node.ast = tree
            node.origin = True

        

def leaf2root(node):
    tmp_node = node
    path_to_root = []
    while tmp_node is not None:
        path_to_root.append(tmp_node.name)
        tmp_node = tmp_node.parent
    if node.name == '__init__.py':
        path_to_root = path_to_root[1:]
        path_name = ".".join(reversed(path_to_root))
        return path_name
    else:
        path_name = ".".join(reversed(path_to_root[1:]))
        path_name = "{}.{}".format(path_name, node.name.split('.')[0])
        return path_name

 
def find_child_by_name(node, name):
    for ch in node.children:
        if ch.name == name:
            return ch
    return None
def find_node_by_name(nodes, name):
    for node in nodes:
        if node.name == name or os.path.splitext(node.name)[0]== name:
            return node
    return None
def go_to_that_node(root, cur_node, visit_path):
    route_node_names = visit_path.split('.')  
    route_length = len(route_node_names)
    tmp_node = None
    tmp_node =  find_node_by_name(cur_node.parent.children, route_node_names[0])
    if tmp_node is not None:
        for i in range(1,route_length):
            tmp_node =  find_node_by_name(tmp_node.children, route_node_names[i])
            if tmp_node is None:
                break
    elif route_node_names[0] == root.name:
        tmp_node = root
        for i in range(1,route_length):
            tmp_node =  find_node_by_name(tmp_node.children, route_node_names[i])
            if tmp_node is None:
                break
        return tmp_node
    elif route_node_names[0] == cur_node.parent.name:
        tmp_node = cur_node.parent
        for i in range(1,route_length):
            tmp_node =  find_node_by_name(tmp_node.children, route_node_names[i])
            if tmp_node is None:
                break

    if tmp_node is not None and tmp_node.name.endswith('.py') is not True:
       tmp_node =  find_node_by_name(tmp_node.children, '__init__.py')

    return tmp_node

def tree_infer_levels(root_node):
    API_name_lst = []
    leaf_stack = []
    working_queue = []
    working_queue.append(root_node)
    files_map = {}

    while len(working_queue)>0:
        tmp_node = working_queue.pop(0)
        if tmp_node.name.endswith('.py') == True:
            leaf_stack.append(tmp_node)
        working_queue.extend(tmp_node.children)

   
    for node in leaf_stack[::-1]:
        module_item_dict = parse_import(node.ast)
        if module_item_dict is None:
            continue
        #print(module_item_dict)    
        for k, v in module_item_dict.items():
            if k is None or isinstance(k, int):
                continue
            dst_node = go_to_that_node(root_node, node, k)
            
            if dst_node is not None:
                if v[0] =='*':
                  for k_ch, v_ch in dst_node.cargo.items():
                      node.cargo[k_ch] = v_ch
                  k_ch_all = list(dst_node.cargo.keys())
                else:
                    
                    for api in v:
                        if api in dst_node.cargo:
                            node.cargo[api]= dst_node.cargo[api]  
            else:
                pass

    import_info = {}
    for node in leaf_stack:
        API_prefix = leaf2root(node) 
        API_prefix = API_prefix.strip('.')
        module_list = parse_import_code(node.ast)
        import_info[API_prefix] = module_list
        node_API_lst = make_API_full_name(node.cargo, API_prefix)
        API_name_lst.extend(node_API_lst)

    return API_name_lst,import_info

class function_node(object):
    def __init__(self,API_name,loc_name,args,args_default,filepath='*',lineno='*',namespace='*'):
        self.API_name = API_name  
        self.loc_name = loc_name  
        self.args = args
        self.args_default = args_default
        self.filepath = filepath
        self.lineno = lineno
        self.namespace = namespace

def make_API_full_name(meta_data, API_prefix):
    API_lst = []
    for k, v in meta_data.items():
        if isinstance(v, tuple): 
            if len(v) < 4:
                continue
            API_name = function_node(
                f'{API_prefix}.{k}',
                '.'.join([v[3], k]),
                ";".join(v[0]),
                v[1],
                v[3],
                v[2],
                '*',
            )
            if len(v) > 4 :
                API_name.body = v[4]  # Add function body here
                function_body[API_name.loc_name] = API_name.body

            API_lst.append(API_name.__dict__)
        elif isinstance(v, dict):
            if '__init__' in v:
                args = v['__init__']
                if len(args) < 4:
                    continue
                API_name = function_node(
                    f'{API_prefix}.{k}',
                    '.'.join([args[3], k]),
                    ";".join(args[0]),
                    args[1],
                    args[3],
                    args[2],
                    '*',
                )
                if len(args) >4 :
                    API_name.body = args[4]  # Add constructor body
                    function_body[API_name.loc_name] = API_name.body
             
                API_lst.append(API_name.__dict__)
            for f_name, args in v.items():
                if len(args) < 4:
                    continue
                API_name = function_node(
                    f'{API_prefix}.{k}.{f_name}',
                    '.'.join([args[3], k, f_name]),
                    ";".join(args[0]),
                    args[1],
                    args[3],
                    args[2],
                    k,
                )
                if len(args) > 4:
                    API_name.body = args[4]  # Add function body here
                    function_body[API_name.loc_name] = API_name.body
        
                API_lst.append(API_name.__dict__)
    return API_lst

def search_targets(root_dir, targets):
     entry_points = []
     for root, dirs, files in os.walk(root_dir):
        n_found = 0
        for t in targets:
            if t in dirs :
                entry_points.append(os.path.join(root, t))
                n_found += 1
            elif t+'.py' in files:
                entry_points.append(os.path.join(root, t+'.py'))
                n_found += 1
            
        if n_found == len(targets):
            return entry_points
     return None




def process_single_module(module_path):
    API_name_lst = []
    import_info = {}
    if os.path.isfile(module_path):
        name_segments =  os.path.splitext(os.path.basename(module_path))[1] == '.py' 
        res, tree = extract_class(module_path)
        # with open('1.txt', 'a',encoding='utf-8') as f:
        #     f.write("1:")
        #     f.write(str(name_segments))
        #     f.write("\n")
        #     f.write(str(res))
        #     f.write("\n\n\n\n")
        node_API_lst = make_API_full_name(res, name_segments)
        API_name_lst.extend(node_API_lst)
    else:
        first_name = os.path.basename(module_path)
        working_dir = os.path.dirname(module_path)
        path = []
        cwd = os.getcwd() 
        os.chdir(working_dir)
        root_node = Tree(first_name)
        build_dir_tree(root_node) 
        API_name_lst,import_info = tree_infer_levels(root_node)
        os.chdir(cwd) # go back cwd
    return API_name_lst,import_info

def process_single_module_code(module_path):
    """
    处理单个模块，并收集其中的 import 信息（源码形式）。
    """
    import_info = {}  # 用于存储模块的 import 信息（源码格式）

    if os.path.isfile(module_path):
        # 如果是单个文件
        source = open(module_path).read()
        tree = ast.parse(source, mode='exec')  # 解析源代码生成 AST
        import_code = parse_import(tree, module_path)  # 获取该模块的 import 源码信息
        import_info[module_path] = import_code  # 保存为源码形式
    else:
        # 如果是文件夹，递归处理其中的文件
        first_name = os.path.basename(module_path)
        working_dir = os.path.dirname(module_path)
        path = []
        cwd = os.getcwd()
        os.chdir(working_dir)
        
        root_node = Tree(first_name)
        build_dir_tree(root_node)
        for child in root_node.children:
            if child.name.endswith('.py'):
                file_path = os.path.join(module_path, child.name)
                if os.path.isfile(file_path):  # 检查文件是否存在
                    source = open(file_path).read()
                    tree = ast.parse(source, mode='exec')
                    import_code = parse_import_code(tree)  # 获取该模块的 import 源码信息
                    import_info[child.name] = import_code  # 保存为源码形式
                else:
                    print(f"Warning: {file_path} not found!")
        
        os.chdir(cwd)  # 恢复原目录

    return import_info


def construct_pre_annonation(client,client_path,libs,lib_path=None):

    annotations = {}
    import_info = {}  # 用于存储所有模块的 import 信息（源码形式）
    for lib_name in libs +[client]:
        if lib_name == client:
            lib_dir = client_path
        else:
            lib_dir = os.path.join(lib_path,lib_name)
        versions = ['Latest']
        API_data = {"module":[], "API":{}, "version":[]}
        entry_points = [lib_dir]
        if entry_points is not None:
            API_data['module'] = entry_points
            API_data['API'] = []
            for ep in entry_points:
                print(ep)
                API_name_lst,module_import_info = process_single_module(ep)  
                #module_import_info = process_single_module_code(ep)
                if len(API_name_lst) == 0 :
                    print(str(ep) + " is empty")
                    continue
                # if str(ep) == r"E:\001_some_AI_code\003_AutoExtension\STAR\repo\tmp_env\argparse":
                #     print(API_name_lst)
                API_data['API'].extend(API_name_lst)
                if lib_name == client:
                    import_info.update(module_import_info)  # 将该模块的 import 信息更新到总字典中
        
        
        for line in API_data['API']:
            if line['API_name'].split('.')[-1] == 'self_init':
                line['API_name'] = line['API_name'].replace('.self_init','')
                line['loc_name'] = line['loc_name'].replace('.self_init','')
            if lib_name == client:
                line['name_type'] = "local_name"
                if line['API_name'] == line['loc_name']:
                    annotations[line['API_name']] = line
            else : #对于所有的都让API_name=loc_name 
                line['name_type'] = "third library"
                if line['API_name'] == line['loc_name']:
                    annotations[line['API_name']] = line

        if lib_name == client:
            stdlib_dir = os.path.join(lib_path,"stdlib")
            os.makedirs(stdlib_dir, exist_ok=True)

            Standard_Libs = set()
            with open('stdlib.txt','r',encoding='utf-8') as f:
                Standard_Libs = set(f.read().split('\n'))

            result_list = []
            for _,module_name in module_import_info.items():
                if module_name != "":
                    result_list.extend(module_name.strip().split('\n'))
            result_list = list(set(result_list))

            # 匹配 "import xx"
            pattern1 = r"^import\s+(\S+)$"
            # 匹配 "from yy import xx"
            pattern2 = r"^from\s+(\S+)\s+import\s+(\S+)$"
            # 匹配 "from yy import xx as zz"
            pattern3 = r"^from\s+(\S+)\s+import\s+(\S+)\s+as\s+(\S+)$"
            # 匹配 "import xx as zz"
            pattern4 = r"^import\s+(\S+)\s+as\s+(\S+)$"
            
            module_path_list = []
            for s in result_list:
                match1 = re.match(pattern1, s)
                match2 = re.match(pattern2, s)
                match3 = re.match(pattern3, s)
                match4 = re.match(pattern4, s)
                #print(s)
                if match1:
                    module_name = match1.group(1)
                elif match2:
                    module_name = match2.group(1)
                    name = match2.group(2)
                elif match3:
                    module_name = match3.group(1)
                    name = match3.group(2)
                    asname = match3.group(3)
                elif match4:
                    module_name = match4.group(1)
                    asname = match4.group(2)
                else:
                    print("error__!!")
                try :
                    import shutil
                    module_name = module_name.split('.')[0] # 可能有urllib.error   只取urllib
                    if module_name in Standard_Libs:
                        module = importlib.import_module(module_name)
                        module_file = inspect.getfile(module)
                        last_part = os.path.basename(module_file)
                        if last_part == "__init__.py": #复制文件夹
                            module_dir = os.path.dirname(module_file)
                            destination_path = os.path.join(stdlib_dir,module_name)
                            try:
                                shutil.copytree(module_dir, destination_path)
                            except Exception as e:
                                pass
                                #print(module)
                                #print(f"发生了一个错误: {e}")

                        else :
                            destination_path = os.path.join(stdlib_dir,module_name + ".py")
                            try:
                                shutil.copy(module_file, destination_path)
                            except Exception as e:
                                pass
                                #print(module)
                                #print(f"发生了一个错误: {e}")
                        # source_code = inspect.getsource(module)
                        # module_path = os.path.join(stdlib_dir,module_name + ".py")
                        # with open(module_path, 'w', encoding='utf-8') as f:
                        #     f.write(source_code)

                except Exception as e:
                    #print(module_name)
                    pass
                    #import traceback
                    #traceback.print_exc()
                    #print(f"Failed to load or inspect {module_name}: {e}\n")
            #print(stdlib_dir)
            API_data['API'] = []
            API_name_lst,module_import_info = process_single_module(stdlib_dir)  
            if len(API_name_lst) != 0 :
                API_data['API'].extend(API_name_lst)
                #import_info.update(module_import_info)  # 将该模块的 import 信息更新到总字典中
            else :
                print(stdlib_dir + " is empty")
            for line in API_data['API']:
                if line['API_name'].split('.')[-1] == 'self_init':
                    line['API_name'] = line['API_name'].replace('.self_init','')
                    line['loc_name'] = line['loc_name'].replace('.self_init','')
                if line['API_name'].split('.')[0] == 'stdlib':
                    line['API_name'] = line['API_name'].replace('stdlib.','')
                    line['loc_name'] = line['loc_name'].replace('stdlib.','')
                if line['filepath'].split('.')[0] == 'stdlib':
                    line['filepath'] = line['filepath'].replace('stdlib.','')
                line['name_type'] = "stdlib"
                if line['API_name'] == line['loc_name']:
                    annotations[line['API_name']] = line
    # # 在生成 JSON 文件之前处理 annotations
    # updated_annotations = {}
    # for api_key, api_value in annotations.items():
    #     # 使用 loc_name 替换原来的 key
    #     new_key = api_value['loc_name']
    #     # 删除 API_name 字段
    #     del api_value['API_name']
    #     updated_annotations[new_key] = api_value

    # annotations = updated_annotations
    # def remove_comments(code: str) -> str:
    #     # 移除单行注释
    #     code = re.sub(r'#.*', '', code)
    #     # 移除多行注释（单引号和双引号）
    #     code = re.sub(r'"""(.*?)"""', '', code, flags=re.DOTALL)
    #     code = re.sub(r"'''(.*?)'''", '', code, flags=re.DOTALL)
    #     return code
    # for api_key, api_value in annotations.items():
    #     api_value['body'] = remove_comments(api_value['body'])
    
    location = os.getcwd()

    if not os.path.exists(os.path.join(location,'pre_knowledge')):
        os.mkdir(os.path.join(location,'pre_knowledge'))
    
    with open(os.path.join(location,'pre_knowledge') +'/'+f'{client}_pre_annotations.json','w') as f:
        json.dump(annotations,f,indent=4)
    with open(os.path.join(location, 'pre_knowledge') + f'/{client}_import_info.json', 'w') as f:
        json.dump(import_info, f, indent=4)