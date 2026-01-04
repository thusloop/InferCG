

import os
import ast
import sys
import json
from invoke_local import get_local_name,get_annotation,type_button
from pointer.classm import ClassNode,ClassManager
from pointer.function import FuncNode,FunctionManager
from pointer.importm import VarNode,VarManager,ImportManager
from base import PointNode
        


class ForwardVisitor(ast.NodeVisitor):
    def __init__(self,root_path,arg3=None,benchmark = 'dynamic'):
        self.scopes = []
        self.self_class = []
        self.global_values = {}  
        self.global_functions = {}
        self.classes_manager = ClassManager()
        self.funcs_manager = FunctionManager()
        self.vars_manager = VarManager()
        self.imports_mangager = ImportManager()
        self.definitions = {}
        self.project = arg3
        self.annotations = get_annotation(self.project)
        if benchmark == 'micro':
            self.project = self.project.split('#')[1]  #only micro
        self.processOne(root_path)

    def processOne(self,root_path): 
        '''
        visit all import statements
        '''    
        current_project = os.path.basename(root_path)
    
        walk = os.walk(root_path, followlinks=True)
        ignore_dirs = [".hg", ".svn", ".git", ".tox", "__pycache__", "env", "venv"]
        
        self.scopes.append(current_project)
        self.self_class.append(current_project)
        for root, dirs, files in walk:
            dirs[:] = [d for d in dirs if d not in ignore_dirs]
            files = [fn for fn in files if os.path.splitext(fn)[1] == ".py" ]
            for file in files:
                file_name = os.path.join(root, file)
                if 'test_' in file:
                    continue
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
                    self.callparent_signs = {}
                    self.special_items = []
                    self.dataflow_attribute = {}
                    ast_ = ast.parse(content)
                    self.visit(ast_)
                    current_context = self.get_current_context()
                    
                    self.global_values[current_context] = {}
                    for module_context in self.used_ModuleNames:
                        if module_context == current_context:
                            self.global_values[module_context] = self.used_ModuleNames[module_context]
                            for item,point in self.used_ModuleNames[module_context].items():
                                self.imports_mangager.add(item,current_context,point)

                    for name,item in self.classes_manager.names.items():
                        attrs = item.properties
                        if name not in self.dataflow_attribute:
                            continue
                        for attr in attrs:
                            if attr in self.dataflow_attribute[name]:  
                                attrs[attr].add_point(self.dataflow_attribute[name][attr])

                        interface_name = name.replace(current_context,'').strip('.')
                        if name in self.dataflow_attribute:
                            for attr,attr_value in self.dataflow_attribute[name].items():
                                self.global_values[current_context][interface_name+'.'+attr] = attr_value
                                self.vars_manager.add(interface_name+'.'+attr,current_context,attr_value)
                        
                        self.global_values[current_context][interface_name] = item

                    for name,item in self.funcs_manager.names.items():
                        interface_name = name.replace(current_context,'').strip('.')
                        self.global_values[current_context][interface_name] = item
                    
                except SyntaxError as e:  
                    print(e)

                self.scopes = [self.scopes[0]]  
                self.self_class = [self.self_class[0]] 

        self.scopes.pop()
        self.self_class.pop()

    def only_inlude(self,sub,complete):
        if '.'+sub + '.' in '.'+complete + '.' and complete.startswith(sub):
            return True
        else:
            return False

    def add_points(self,name,context,new_point):  
        if isinstance(new_point,list):
            return
        if context not in self.used_ModuleNames:
            self.used_ModuleNames[context] = {}
        if name not in self.used_ModuleNames[context]:
            self.used_ModuleNames[context][name] = [] 
        
        if new_point not in self.used_ModuleNames[context][name]:
            
            self.used_ModuleNames[context][name].append(new_point)

    def add_attr(self,name,context,new_point):  
       
        
        if context not in self.dataflow_attribute:
            self.dataflow_attribute[context] = {}
        if name not in self.dataflow_attribute[context]:
            self.dataflow_attribute[context][name] = [] 
        
        if new_point not in self.dataflow_attribute[context][name]:
            
            self.dataflow_attribute[context][name].append(new_point)

    def if_inclass(self):
        current_file = self.current_rel_filename.replace('.__init__','',1)
        if (self.self_class[-1] == self.scopes[-1]) and self.get_current_context() != current_file and self.get_current_class() != current_file :
            return True
        return False

    def _patch_with_scope(self,target_nodes,current_context,point_target):
        for target_value in target_nodes:
            target_name = self.get_node_name(target_value)
            if target_name:
                if 'self.' in target_name: 
                    
                    current_cls_name = self.self_class[-1]
                    tmp = current_context[0:current_context.rindex(current_cls_name)+len(current_cls_name)]
                    self.add_points(target_name,tmp,point_target) 
                    self.add_attr(target_name.replace('self.','',1),tmp,point_target)
                else: 
                    if self.if_inclass():  
                        current_cls_name = self.self_class[-1]
                        tmp = current_context[0:current_context.rindex(current_cls_name)+len(current_cls_name)]
                        if tmp == current_context:
                            self.add_points('self.'+target_name,tmp,point_target)
                            self.add_attr(target_name,tmp,point_target)
                            
                    self.add_points(target_name,current_context,point_target)
                

    def analyze_within(self,full_name,current_context,args,callsite = None):
        callee_functions  = []
        max_match_within_function = None
        
        if 'self.' in full_name:
            current_cls = self.self_class[-1]
            current_self = current_context[0:current_context.rindex(current_cls)+len(current_cls)]
            max_match_within_function = current_self + full_name.replace('self','',1)


        else:
          
            if len(full_name.split('.')) > 1:  
                possible_class = full_name.split('.')[0]
              
                for within_class in self.classes_manager.names:
                    if possible_class == within_class.split('.')[-1]:  
                        max_match_within_function = within_class + full_name.replace(possible_class,'',1)
                
                    
        if max_match_within_function:
            callee_functions.append(max_match_within_function)
            
        else:
            for within_class in self.classes_manager.names:
                if within_class.startswith(self.current_rel_filename.replace('.__init__','')):  
                    if full_name == within_class.replace(self.current_rel_filename.replace('.__init__',''),'').strip('.'): 
                        callee_functions.append(within_class)


            max_length = 0
            max_match_within_function = None
            for within_function in self.funcs_manager.names: 
                node_name = within_function.replace(self.current_rel_filename.replace('.__init__',''),'').strip('.')  
                if node_name.split('.')[-1] == full_name.split('.')[-1]:  
                    
                    candidates_edge =  node_name.strip()           
                    common_length = set(candidates_edge.split('.')) & set(full_name.split('.'))
                    if len(common_length) > max_length:
                        max_match_within_function = within_function.strip()
                        max_length = len(common_length)


            if max_match_within_function:
                callee_functions.append(max_match_within_function)
        
            
        return callee_functions

    def deal_with_call(self,call_node):
    
        full_name = self.get_node_name(call_node.func)
      
        all_call_names = None
        current_context = self.get_current_context()

        if full_name == None: 
            return []
        if all_call_names == None:
            all_call_names = [full_name]

    
        dispatch_objects = []
        # 
        for full_name in all_call_names:
            for module_context in self.used_ModuleNames:
                if module_context not in current_context:  
                    continue
                all_used_modules = self.used_ModuleNames[module_context]
                for module_name in all_used_modules:
                    if self.only_inlude(module_name,full_name):  
                        for pointTo_ in all_used_modules[module_name]:
                            API_name = pointTo_ + full_name.replace(module_name,'',1)  
                            dispatch_objects.append(API_name)

        call_functions = self.analyze_within(full_name,current_context,{'args':len(call_node.args)+len(call_node.keywords)})  
        dispatch_objects += call_functions 
        dispatch_objects = set(dispatch_objects)
        
        return_objects = []
        for f_ in dispatch_objects:
            if f_:
                an_f_ ,flag = get_local_name(f_,{'args':len(call_node.args)+len(call_node.keywords)},self.annotations)
                if flag:
                    if an_f_ in self.global_functions:
                        if self.global_functions[an_f_].returns:
                            return_objects += self.global_functions[an_f_].returns  
                        else:
                            return_objects.append(an_f_)
                    else:  
                        return_objects.append(an_f_)
        return return_objects

    def deal_with_assign(self,source_node,target_nodes):
   

        if source_node == None:
            return
       
        current_context = self.get_current_context()  
        source_name = None
        if isinstance(source_node,str):
            source_name = source_node.strip()
        elif isinstance(source_node,ast.Str):
            self._patch_with_scope(target_nodes,current_context,'Constant#Str')  
        elif isinstance(source_node,ast.Num):
            self._patch_with_scope(target_nodes,current_context,'Constant#Num')  
        elif isinstance(source_node,ast.Constant):
            self._patch_with_scope(target_nodes,current_context,'Constant#NC')  
        elif isinstance(source_node,ast.Name): 
            source_name = self.get_node_name(source_node) 
        elif isinstance(source_node,ast.Attribute):
          
            source_name = self.get_node_name(source_node)  
            
        elif isinstance(source_node,ast.Call):  
             
            return_values = self.deal_with_call(source_node) 
            if len(return_values) == 0: 
                source_name = self.get_node_name(source_node.func) 
            else:
                for sn in return_values:    
                    self._patch_with_scope(target_nodes,current_context,sn)
            
        
        elif isinstance(source_node,ast.BoolOp): 
            for v in source_node.values:
                self.deal_with_assign(v,target_nodes)

        elif isinstance(source_node,ast.BinOp):
            self.deal_with_assign(source_node.left,target_nodes)
            self.deal_with_assign(source_node.right,target_nodes)
        elif isinstance(source_node,ast.Dict): 
            if len(source_node.values) == 0: 
                
                self._patch_with_scope(target_nodes,current_context,'Constant#Dict')
            else:
                for dict_value in source_node.values:
                    self.deal_with_assign(dict_value,target_nodes)
        elif isinstance(source_node,ast.List): 
            if len(source_node.elts) == 0: 
                self._patch_with_scope(target_nodes,current_context,'Constant#List')
            else:
                for list_value in source_node.elts:
                    self.deal_with_assign(list_value,target_nodes)
        elif isinstance(source_node,ast.Set): #
            if len(source_node.elts) == 0:
                self._patch_with_scope(target_nodes,current_context,'Constant#Set')
            else:
                for list_value in source_node.elts:
                    self.deal_with_assign(list_value,target_nodes)

        elif isinstance(source_node,ast.Tuple): #
            if len(source_node.elts) == 0: 
                self._patch_with_scope(target_nodes,current_context,'Constant#Tuple')
            else:
                for tuple_value in source_node.elts:
                    self.deal_with_assign(tuple_value,target_nodes)
        elif isinstance(source_node,ast.Subscript): #A[]
            self.deal_with_assign(source_node.value,target_nodes)
        elif isinstance(source_node,ast.Starred):
            self.deal_with_assign(source_node.value,target_nodes)
        elif isinstance(source_node,ast.IfExp):
            self.deal_with_assign(source_node.body,target_nodes)
            self.deal_with_assign(source_node.orelse,target_nodes)
        if source_name:
            
            current_context = self.get_current_context()
            for module_context in self.used_ModuleNames:
                if module_context not in current_context:  
                    continue
                import copy
                all_used_modules = copy.deepcopy(self.used_ModuleNames[module_context])
                for module_name in all_used_modules:
                    if module_name == 'self' and source_name != 'self':  
                        continue
                    if self.only_inlude(module_name,source_name):
                        points = copy.deepcopy(all_used_modules[module_name])  
                        for pointTo_ in points:
                            self._patch_with_scope(target_nodes,current_context,pointTo_ + source_name.replace(module_name,'',1))
                        break

            call_functions = self.analyze_within(source_name,current_context,None)  
            if len(call_functions) > 0:
                for pointTo_ in call_functions:
                    if pointTo_:
                        self._patch_with_scope(target_nodes,current_context,pointTo_)

    def visit_Return(self, node):
        current_function = self.get_current_context() 
        self.deal_with_assign(node.value,[current_function+'<return>'])
        self.generic_visit(node)

    def visit_Assign(self, node):
       
        current_context = self.get_current_context()
        for t in node.targets:
            target_name = self.get_node_name(t)
            if target_name:
                if 'self.' in target_name: #self
                    current_cls_name = self.self_class[-1]
                    tmp = current_context[0:current_context.rindex(current_cls_name)+len(current_cls_name)]
                    if tmp in self.classes_manager.names:
                        var = VarNode(target_name.replace('self.','',1),self.current_rel_filename)
                        self.classes_manager.get(tmp).add_property(var)  
                else: 
                    if self.if_inclass():  
                        current_cls_name = self.self_class[-1]
                        tmp = current_context[0:current_context.rindex(current_cls_name)+len(current_cls_name)]
                        if tmp == current_context:
                           
                                var = VarNode(target_name,self.current_rel_filename)
                                self.classes_manager.get(tmp).add_property(var) 
                           

        self.deal_with_assign(node.value,node.targets)
        self.generic_visit(node)  

    
    def visit_AugAssign(self, node):        
        self.deal_with_assign(node.value,[node.target])
        self.generic_visit(node)  
    
    def visit_AnnAssign(self, node):
        
        self.deal_with_annonations(node.annotation,[node.target])
        self.deal_with_assign(node.value,[node.target])

        self.generic_visit(node)   

    def visit_Import(self,node):
        '''
        import A.a.b  is parsed A.a.b
        '''
        current_context = self.get_current_context() 
        for subnode in node.names:
            if subnode.name:
                alias_name = subnode.asname if subnode.asname else subnode.name 
                true_point = subnode.name
                # else:
                current_path = self.current_rel_filename
                refer_path = '.'.join(current_path.split('.')[0:len(current_path.split('.'))-1])
                pkg = '.'.join([refer_path,subnode.name])
                if pkg in self.global_values:  
                    import_type = 'Module'
                    true_point = pkg.strip()

                self.add_points(alias_name,current_context,true_point)
                    
                    
                    
            

    def visit_ImportFrom(self,node):
        '''
        remove the import statement: from . import A
        from A import a.b is parsed as A, a.b

        '''
        
        current_context = self.get_current_context() 
        if node.level == 0:
            pkg = node.module
            modules = node.names
            if 1:
                for subnode in modules:  
                    alias_name = subnode.asname if subnode.asname else subnode.name 
                    if alias_name == '*':
                        if pkg in self.global_values:
                            for simple_name,full_quality_name in self.global_values[pkg].items():
                                self.add_points(simple_name,current_context,full_quality_name.ns)
                        else:
                            current_path = self.current_rel_filename
                            refer_path = '.'.join(current_path.split('.')[0:len(current_path.split('.'))-1])
                            tmp_pkg = '.'.join([refer_path,pkg])
                            if tmp_pkg in self.global_values:  
                                for simple_name,full_quality_name in self.global_values[tmp_pkg].items():
                                    self.add_points(simple_name,current_context,full_quality_name.ns)
                    else:
                        current_path = self.current_rel_filename
                        refer_path = '.'.join(current_path.split('.')[0:len(current_path.split('.'))-1])
                        tmp_pkg = '.'.join([refer_path,pkg])
                        if tmp_pkg in self.global_values:
                            pkg = tmp_pkg.strip()

                        self.add_points(alias_name,current_context,'.'.join([pkg,subnode.name]))
                    

        else:
            current_path = self.current_rel_filename
            refer_path = '.'.join(current_path.split('.')[0:len(current_path.split('.'))-node.level])

            if node.module == None:
                pkg = refer_path  #from . import A
            else:
                pkg = '.'.join([refer_path,node.module])
            modules = node.names
            for subnode in modules:
                alias_name = subnode.asname if subnode.asname else subnode.name 
                self.add_points(alias_name,current_context,'.'.join([pkg,subnode.name]))

    

    def get_current_context(self):
        return '.'.join(self.scopes)
    def get_current_class(self):
        return '.'.join(self.self_class)
        
    def deal_with_annonations(self,source_node,target_nodes):
        if type_button == False:
            return  
        if source_node == None:
            return
        

        current_context = self.get_current_context()  
        source_name = None
        if isinstance(source_node,str):
            source_name = [source_node.strip(),'Var']
        elif isinstance(source_node,ast.Str):
            source_name = [source_node.s,'Var'] 
        elif isinstance(source_node,ast.Num) or isinstance(source_node,ast.NameConstant):
            self._patch_with_scope(target_nodes,current_context,'Constant#Num')
        elif isinstance(source_node,ast.Name): 
            source_name = [source_node.id,'Var'] 
        elif isinstance(source_node,ast.Constant):
            self.deal_with_annonations(source_node.value,target_nodes)
            
        elif isinstance(source_node,ast.Attribute):
            source_name = [self.get_node_name(source_node),'Attr']  
        elif isinstance(source_node,ast.Call):  
            return_values = self.deal_with_call(source_node) 
            if len(return_values) == 0:
                source_name = [self.get_node_name(source_node.func),'Call'] 
            else:
                for sn in return_values:                   
                    self._patch_with_scope(target_nodes,current_context,sn)

        elif isinstance(source_node,ast.Subscript): #Optional[a,b]
            self.deal_with_annonations(source_node.value,target_nodes)
            self.deal_with_annonations(source_node.slice,target_nodes)
        elif isinstance(source_node,ast.Dict): #
            if len(source_node.values) == 0: 
                
                self._patch_with_scope(target_nodes,current_context,'Constant#Dict')
            else:
                for dict_value in source_node.values:
                    self.deal_with_annonations(dict_value,target_nodes)
        elif isinstance(source_node,ast.List): #
            if len(source_node.elts) == 0: 
                self._patch_with_scope(target_nodes,current_context,'Constant#List')
            else:
                for list_value in source_node.elts:
                    self.deal_with_annonations(list_value,target_nodes)
        elif isinstance(source_node,ast.Set): 
            if len(source_node.elts) == 0: 
                self._patch_with_scope(target_nodes,current_context,'Constant#Set')
            else:
                for list_value in source_node.elts:
                    self.deal_with_annonations(list_value,target_nodes)

        elif isinstance(source_node,ast.Tuple):
            if len(source_node.elts) == 0: 
                self._patch_with_scope(target_nodes,current_context,'Constant#Tuple')
            else:
                for tuple_value in source_node.elts:
                    self.deal_with_annonations(tuple_value,target_nodes)

        elif isinstance(source_node,ast.Starred): 
            self.deal_with_annonations(source_node.value,target_nodes)
        if source_name: 
            source_name = source_name[0]
            flag_find = False
            current_context = self.get_current_context()
            for module_context in self.used_ModuleNames:
                if module_context not in current_context:  
                    continue
                import copy
                all_used_modules = copy.deepcopy(self.used_ModuleNames[module_context])
                for module_name in all_used_modules:
                    if module_name == 'self' and source_name != 'self':  
                        continue
                    if self.only_inlude(module_name,source_name):
                        points = copy.deepcopy(all_used_modules[module_name])  
                        for pointTo_ in points:
                            self._patch_with_scope(target_nodes,current_context,pointTo_ + source_name.replace(module_name,'',1))
                        
                        flag_find = True
                        break

            call_functions = self.analyze_within(source_name,current_context,None)   
            if len(call_functions) > 0:
                for pointTo_ in call_functions:
                    if pointTo_:
                        self._patch_with_scope(target_nodes,current_context,pointTo_)
            else:
                if flag_find == False:
                    if source_name[0] in ['list','dict','set','defaultdict','str']:  
                        self._patch_with_scope(target_nodes,current_context,'Constant#'+source_name[0])         
                   
        else:
            pass
    def visit_FunctionDef(self,node):
        self.scopes.append(node.name)
        current_func = self.get_current_context()     
     
        self.used_ModuleNames[current_func] = {}
        self.funcs_manager.add(current_func,self.current_rel_filename.replace('.__init__',''),node.lineno,None)

        for arg in node.args.args:
            if arg.annotation:  
                self.deal_with_annonations(arg.annotation,[arg.arg])    

        if hasattr(node,'returns'):
            self.deal_with_annonations(node.returns,[current_func+'<return>'])

        parameter_results = {}
        parameter_ = 0
        
        for arg in node.args.args:
                self.add_points(arg.arg,current_func,current_func + '.arg_#'+str(parameter_)+'#'+arg.arg)
                new_point = PointNode(current_func + '.arg_#'+str(parameter_)+'#'+arg.arg,'','Unknown#P')
                parameter_results[parameter_] = new_point
                parameter_ += 1
            
        for arg,value in zip(node.args.kwonlyargs,node.args.kw_defaults):
            if arg.arg == 'self' and parameter_ == 0:  
                pass
            else:
                self.deal_with_assign(value,[arg.arg])  

                new_point = PointNode(current_func + '.arg_#'+str(parameter_)+'#'+arg.arg,'','Unknown#P')
              
                parameter_results[parameter_] = new_point

                parameter_ += 1   
                
        for deco in node.decorator_list:
            if isinstance(deco,ast.Name) and deco.id == 'property':
                self.funcs_manager.names[current_func].property = True

        self.funcs_manager.names[current_func].params = parameter_results
        self.generic_visit(node)

        if current_func+'<return>' in self.used_ModuleNames[current_func]:
            self.funcs_manager.names[current_func].returns = self.used_ModuleNames[current_func][current_func+'<return>']

        self.used_ModuleNames.pop(current_func)
        self.scopes.pop()

        if self.if_inclass():
            current_cls = self.classes_manager.get(self.get_current_context())
            current_cls.add_method(self.funcs_manager.get(current_func))
            


    def visit_AsyncFunctionDef(self, node):
        self.visit_FunctionDef(node)


    def visit_ClassDef(self, node):
        self.scopes.append(node.name)
        self.self_class.append(node.name)
        self.inherited_classes[node.name] = []
        for cls_name in node.bases:
            parsed_name =  self.get_node_name(cls_name)
            if parsed_name:
                self.inherited_classes[node.name].append(parsed_name)
        

        current_context = self.get_current_context()
        self.classes_manager.add(current_context,self.current_rel_filename)
        cur_cls = self.classes_manager.get(current_context)
        for cls_name in node.bases:
            parsed_name =  self.get_node_name(cls_name)
            if parsed_name:
                if parsed_name == 'object':
                    continue
                self.inherited_classes[node.name].append(parsed_name)

        self.dataflow_attribute[current_context] = {}
        self.used_ModuleNames[current_context] = {}
        self.generic_visit(node)
        self.used_ModuleNames.pop(current_context)
        self.scopes.pop()
        self.self_class.pop()
    
            
    def get_node_name(self,ast_node):
        if isinstance(ast_node,ast.Str):
            return ast_node.s
        if isinstance(ast_node,str):
            return ast_node
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

