

# coding: utf-8
# from __future__ import annotations
from collections import defaultdict
import ast
# from http import client
import os
import sys
import json

# from numpy import argsort
import shutil


class DefNode(object):
    def __init__(self,name,args,defaults,function_property,lineno,filepath):
        self.name = name
        self.args = args
        self.len_defaults = defaults
        self.property = function_property
        self.site = lineno
        self.filepath = filepath
        
    def __str__(self):
        return '\n'.join([str(self.name),str(self.lineno),str(self.filepath),str(self.namespace)])


def get_keywords(node,f_):
    args = node.args
    arg_names = []
    defaults = args.defaults
    for arg in args.args:
        arg_names += [arg.arg]
    function_property = False
    for deco in node.decorator_list:
        if isinstance(deco,ast.Name):
            if deco.id == 'property':
                function_property = True
                break
    # tmp = function_node(node.name,arg_names,len(defaults),filepath,node.lineno,'.'.join(scope)) 

    return (node.name,arg_names,len(defaults),function_property,node.lineno,f_)

class APIvisitor(ast.NodeVisitor):
    def __init__(self,project_name,source_path):
        self.Third_parties = defaultdict(list)
        # self.Import_APIs = defaultdict(list)
        self.edges = {}
        self.name_imports = []
        self.candidates = []
        self.abs_imports = set() 
        self.scopes = []
        self.self_class = []
        self.funcs = []  #funcs的名称集
        self.inherited_maps = {}    
        self.processOne(source_path)

   

    def add_edge(self,caller,callee,site):
        if caller not in self.edges:
            self.edges[caller] = {}
        self.edges[caller]['site'] = site
        if 'inherited' not in self.edges[caller]:
            self.edges[caller]['inherited'] = []
        if isinstance(callee,str):
            self.edges[caller]['inherited'].append(callee)
        self.edges[caller]['method'] = []


   
    def processOne(self,root_path): 
        '''
        visit all import statements
        '''    
        current_project = os.path.basename(root_path)

        walk = os.walk(root_path, followlinks=True)
        ignore_dirs = [".hg", ".svn", ".git", ".tox", "__pycache__", "env", "venv",'tmp_env']
       
        self.scopes.append(current_project)
        self.self_class.append(current_project)
        for root, dirs, files in walk:
            dirs[:] = [d for d in dirs if d not in ignore_dirs]
            files = [fn for fn in files if os.path.splitext(fn)[1] == ".py" ]
            
            for file in files:
                file_name = os.path.join(root, file)
               
                if sys.platform =='win32': 
                    rel_path = os.path.splitext(file_name)[0].replace(root_path,'').strip('\\').replace('\\','.')
                else:
                    rel_path = os.path.splitext(file_name)[0].replace(root_path,'').strip('/').replace('/','.')
                    
                self.current_rel_filename = '.'.join([current_project,rel_path])
                if file == '__init__.py':
                    rel_path = rel_path.replace('__init__','',1).strip('.')
                
                if len(rel_path.strip()) > 0:
                    self.scopes.append(rel_path)
                    self.self_class.append(rel_path)

                self.filepath = file_name                    
                try:
                # if 1:
                    content = ''
                    if sys.version_info[0] > 2:
                        with open(file_name,'r',encoding='utf-8') as f:
                            content = f.read()
                    else:
                        with open(file_name,'r') as f:
                            content = f.read()
                    self.used_ModuleNames = {}
                    self.used_ModuleNames[self.get_current_context()] = {}
                    self.inherited_classes = {}
                    
                    ast_ = ast.parse(content)
                    self.visit(ast_)
                except (SyntaxError,UnicodeDecodeError) as e:  
                    print(e)

                
            
                self.scopes = [self.scopes[0]] 
                self.self_class = [self.self_class[0]] 

        self.scopes.pop()
        self.self_class.pop()


   
    def visit_Import(self,node):
        '''
        import A.a.b  is parsed A.a.b
        '''
        current_context = self.get_current_context() 
      
        for subnode in node.names:
            if subnode.name:
                if 1:                    
                    alias_name = subnode.asname if subnode.asname else subnode.name 
                    self.used_ModuleNames[current_context][alias_name] = subnode.name

    def visit_ImportFrom(self,node):
        '''
        remove the import statement: from . import A
        from A import a.b is parsed as A, a.b

        '''
        if node.module:
            current_context = self.get_current_context() 
            if node.level == 0:
                pkg = node.module
                modules = node.names
                if 1:
                    for subnode in modules:  
                        alias_name = subnode.asname if subnode.asname else subnode.name 
                        self.used_ModuleNames[current_context][alias_name] = '.'.join([pkg,subnode.name])
            
            else:
                current_path = self.current_rel_filename
                refer_path = '.'.join(current_path.split('.')[0:len(current_path.split('.'))-node.level])
                # print(refer_path)
                pkg = '.'.join([refer_path,node.module])
                # print(pkg)
                modules = node.names
                for subnode in modules:
                    alias_name = subnode.asname if subnode.asname else subnode.name 
                    self.used_ModuleNames[current_context][alias_name] = '.'.join([pkg,subnode.name])


    def get_current_context(self):
        return '.'.join(self.scopes)
    def get_current_class(self):
        return '.'.join(self.self_class)
    
    def if_inclass(self):
        current_file = self.current_rel_filename.replace('.__init__','',1)
        if (self.self_class[-1] == self.scopes[-1]) and self.get_current_context() != current_file and self.get_current_class() != current_file :
            return True
        return False

    def visit_FunctionDef(self,node):
        current_context = self.get_current_context()
        
        new_funtion = DefNode(*get_keywords(node,self.filepath)).__dict__
        
        if self.if_inclass(): 
                self.edges[current_context]['method'].append(new_funtion) 
            
        
        self.scopes.append(node.name)
        current_context = self.get_current_context()
        self.used_ModuleNames[current_context] = {}
        self.generic_visit(node)
        
        self.used_ModuleNames.pop(current_context)
        self.scopes.pop()



    def visit_AsyncFunctionDef(self, node):
        self.visit_FunctionDef(node)


    def visit_ClassDef(self, node):
        cur_cls = node.name

        current_context = self.get_current_context()
        if self.if_inclass() and current_context not in self.funcs:  
            invoke_cls_name = []
            for sc in reversed(self.self_class):
                if sc in self.inherited_classes:
                    invoke_cls_name.append(sc)
                else:
                    break 
            self.inherited_classes['.'.join(list(reversed(invoke_cls_name))) + '.'+ cur_cls] = []

        
        
        
       
        self.self_class.append(cur_cls)
        self.inherited_classes[cur_cls] = []
       
        lineno = node.lineno
        
        self.add_edge(current_context+'.'+cur_cls,[],lineno) 
        for cls_name in node.bases:
            parsed_name =  self.get_node_name(cls_name)
            if parsed_name:
                if parsed_name == 'object':
                    continue
                if parsed_name  in  self.inherited_classes:  
                    self.inherited_classes[cur_cls].append(current_context+'.'+parsed_name)  
                    self.add_edge(current_context+'.'+cur_cls,current_context+'.'+parsed_name,lineno)
                else: 
                    for module_context in self.used_ModuleNames:
                        if module_context not in current_context:  
                            continue
                        all_used_modules = self.used_ModuleNames[module_context]
                        for module_name in all_used_modules:
                            if len(parsed_name.split('.')) < len(module_name.split('.')):
                                continue
                            for i in range(len(module_name.split('.'))):
                                if parsed_name.split('.')[i] != module_name.split('.')[i]:
                                    break  
                            else:  
                                API_name = all_used_modules[module_name] + parsed_name.replace(module_name,'')  
                                self.add_edge(current_context+'.'+cur_cls,API_name,lineno)
                                self.inherited_classes[cur_cls].append(API_name)   
                                
        
        self.scopes.append(node.name)
        self.used_ModuleNames[self.get_current_context()] = {}
        self.generic_visit(node)

        self.scopes.pop()
        self.self_class.pop()
    
    
            
    def get_node_name(self,ast_node):
        if isinstance(ast_node,ast.Attribute):
            full_attrName = [ast_node.attr]
            now_attrName = ast_node.value
            while isinstance(now_attrName,ast.Attribute):
                full_attrName.append(now_attrName.attr)
                now_attrName = now_attrName.value
            if isinstance(now_attrName,ast.Name):
                full_attrName.append(now_attrName.id)
            full_attrName = reversed(full_attrName)
            return '.'.join(full_attrName)
        if isinstance(ast_node,ast.Name):
            return ast_node.id

        if isinstance(ast_node,ast.Subscript):
            if isinstance(ast_node.value,ast.Name):
                return ast_node.value.id
        return None


def construct_class_base(client_,client_path,deps_name,lib_path):
    all_inherited = {}
    for lib_name in  [client_] + deps_name:
        if lib_name == client_:
            pro_path = client_path
        else:
            pro_path = f'{lib_path}/{lib_name}'
        APIs = APIvisitor(lib_name, pro_path)
        inherited_info = APIs.edges
        
        
        for k,v in inherited_info.items():
            if k in all_inherited:
                all_inherited[k] = dict(list(all_inherited[k].items()) + list(inherited_info[k].items()))
            else:
                all_inherited[k] = inherited_info[k]

    location = os.getcwd() 
     
    with open(f'{location}/pre_knowledge/{client_}_pre_inherited.json','w') as f:
            json.dump(all_inherited,f,indent=4)   

  
    

def load_pkg_deps(pkg,propath):
    import pandas as pd
    if not os.path.exists('depData/{}.csv'.format(pkg)):
        from ConstructKB.Dependency_Level.GetDep_ast import main
        to_file = 'depData/{}.csv'.format(pkg)
        main(propath,to_file)
        
    try:
        data = pd.read_csv('depData/{}.csv'.format(pkg))
        
        norm_deps = set()
        deps_name = set()
        for i in range(data.shape[0]):
            if data['version'][i] == '==*':
                norm_deps.add(data['dep'][i].lower())
            else:
                norm_deps.add(data['dep'][i].lower()+data['version'][i].lower())
            deps_name.add(data['dep'][i].lower())
        return list(norm_deps),list(deps_name)
    except Exception as e:
        return []

def get_knowledge(client_,client_path,top_path=None,benchmark='dynamic'):
    
    cwd = os.getcwd()
    environment_path = os.path.dirname(client_path) 

    if benchmark == 'dynamic':
 
        if top_path == None:
            deps,deps_name = None,None
        else:
            deps,deps_name = load_pkg_deps(client_,top_path)  
        try:
            if os.path.exists(os.path.join(environment_path,'tmp_env')):
                shutil.rmtree(os.path.join(environment_path,'tmp_env'))
            #if not os.path.exists(os.path.join(environment_path,'tmp_env')):
            os.mkdir(os.path.join(environment_path,'tmp_env'))
            
            SC_location = os.path.join(environment_path,'tmp_env')
            os.chdir(os.path.join(SC_location))
            deps = ['"{}"'.format(dep) for dep in deps]
            os.system('pip3 download -i https://mirrors.aliyun.com/pypi/simple/ {}'.format(' '.join(deps)))

            os.chdir(cwd)
            
            import zipfile
            for sourceCode in os.listdir(SC_location):
                
                if sourceCode.endswith('.whl'):
                    f = zipfile.ZipFile(os.path.join(SC_location,sourceCode),'r') 
                    for file in f.namelist():
                        f.extract(file,SC_location+'/') 
                    f.close()
                if os.path.isfile(os.path.join(SC_location,sourceCode)):
                    os.remove(os.path.join(SC_location,sourceCode))
        except:
            pass
    else:
        SC_location = environment_path
        deps_name = []
    #  contruct module summary and API 
    # print(deps_name)
    from ConstructKB.Import_Level.get_import_map import construct_pre_annonation
    construct_pre_annonation(client_,client_path,deps_name,SC_location)
    construct_class_base(client_,client_path,deps_name,SC_location)