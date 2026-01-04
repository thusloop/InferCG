

import ast
import os
import sys


from invoke_local import get_local_name,get_cls_method,get_all_parent_class,get_implementation_class,get_annotation,type_button
from pointer.function import FuncNode,FunctionManager
from pointer.classm import ClassNode,ClassManager
from base import *
from invoke_local import BUILT_IN_FUNCTIONS,Standard_Libs,Standard_DataType,BUILT_IN_Returns,DT_Returns
from inference import get_closure
from type_analysis import *

from log import logger

from stdtypes import *
import copy

logger.name = __name__



def nameTostr(node):
    if isinstance(node, ast.Attribute):
        return nameTostr(node.value) + "." + node.attr   
    elif isinstance(node, ast.Name):
        return node.id
    elif isinstance(node, ast.Constant):
        return transferConstant(node).type
    elif isinstance(node,ast.Call):
        return nameTostr(node.func) + "()"
    else:
        return "<Other>"



class BackwardVisitor(ast.NodeVisitor):
    def __init__(self,root_path,global_values,global_functions,pro,classes_manager,benchmark='dynamic'):
        self.global_values = global_values
        self.edges = {}
        self.name_imports = []
        self.candidates = []
        self.abs_imports = set()
        self.funcs_manager = global_functions
        self.global_dataflows = {} 
        self.calls_manager = CallManager()
        self.attr_manager = AttrManager()
        self.scopes = []
        self.benchmark = benchmark
        self.self_class = []
        self.reachable_edges = {}
        self.classes_manager = classes_manager
        self.project = pro
        self.unknown_points = {}
        self.Data_Subs = {}
        self.inherited_map,self.cls_has_method = get_cls_method(pro)
        self.annotations = get_annotation(self.project)

        if self.project == 'micro':
            self.project = pro.split('#')[1] #only micro
        self.data_flows = {}
        self.decorator_relation = {}
        self.need_iterate_values = {}

        self.instances = [] 

        self.types = {} 
        self.processOne(root_path) 
        self.pass_decorator() 
        self.pass_parameter()        
               
    
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
                if 'test_' in file:
                    continue
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
                    content = ''
                    if sys.version_info[0] > 2:
                        with open(file_name,'r',encoding='utf-8') as f:
                            content = f.read()
                    else:
                        with open(file_name,'r') as f:
                            content = f.read()
                    
                    self.used_ModuleNames = {}  
                    self.used_ModuleNames[self.get_current_context()] = {}
                    self.lambda_names ={}
                    self.lambda_names[self.get_current_context()] = []
                    self.lambdas = []  

                    self.Import_points = {}  
                    self.import_map = {}
                    self.inherited_classes = {}
                    self.need_dispatch_name = []  
                    self.special_items = []
                    self.special_fors = []
                    self.current_cls = None
                    
                    ast_ = ast.parse(content)
                    self.visit(ast_)
                except SyntaxError as e:  
                    print(e)

                self.scopes = [self.scopes[0]]  
                self.self_class = [self.self_class[0]] 

        self.scopes.pop()
        self.self_class.pop()


    
    def pass_decorator(self): 
        
        
        old_reachable_edges = copy.deepcopy(self.reachable_edges)  
        for caller,calls in old_reachable_edges.items():
            for callee in calls:
                callee_func = self.funcs_manager.get(callee)
                if callee_func:  
                    callee_decos = callee_func.decos 
                    if len(callee_decos) > 0:
                        # logger.info('remove '+caller+' '+callee)
                        self.reachable_edges[caller].remove(callee)    
                        if callee_decos[0] not in self.reachable_edges:
                            self.reachable_edges[callee_decos[0]] = set()  

                        # logger.info('add: '+callee_decos[0]+' '+callee)          
                        for ad in [callee_decos[-1]]:
                            if ad in self.funcs_manager.names:
                                ad_func = self.funcs_manager.names[ad]
                                if ad_func.returns:
                                    for res in ad_func.returns: 
                                        if isinstance(res,dict):  
                                            o = res[tuple(res)[0]]
                                            if '.arg_#' in o.point_name:
                                                patch_func_name,param_num = o.point_name.split('.arg_#') 
                                                if len(param_num.split('.')) == 1:
                                                    method_name = '' 
                                                else: 
                                                    method_name = param_num.split('.',1)[1]
                                                param_num = param_num.split('#')[0]
                                                
                                                flag_find = False
                                                patch_func = self.funcs_manager.names[patch_func_name]
                                                if patch_func_name + '.arg_#0#None' in self.data_flows:
                                                    for ps in  self.data_flows[patch_func_name + '.arg_#0#'+'None']: 
                                                        if ps.scope == callee:
                                                            new_edge_name = ps.ns.strip()
                                                            if len(method_name) > 0:
                                                                new_edge_name = '.'.join([new_edge_name,method_name])
                                                            logger.info('add deco: '+caller+' '+new_edge_name)
                                                            self.add_edge(caller,PointNode(new_edge_name,new_edge_name,'Known'),0,56,'call',must=True) 
                                                            ps.scope = caller.strip()
                                                            flag_find = True
                                                if flag_find == False:
                                                    logger.info('add deco: '+caller+' '+o.point_name)
                                                    self.add_edge(caller,o,0,56,'call',must=True) 

                                            else:    # 

                                                logger.info('add deco: '+caller+' '+o.point_name)
                                                self.add_edge(caller,o,0,56,'call',must=True) 
                                        else:
                                            if res in self.classes_manager.names:  
                                                self.add_edge(caller,PointNode(res,res,'Cls'),0,56) 
                                           
                                           
                                else:
                                    self.reachable_edges[caller].add(ad)  
                            elif ad in self.classes_manager.names:
                                pass
                            else:
                                self.reachable_edges[caller].add(callee)

    def search_for_params(self,arg_num,arg_name,disp_func,scope):  
        if arg_name:
            for k,param in disp_func.params.items():
                if 'arg_#' not in param.point_name: 
                    continue
                param_name = param.point_name.rsplit('#',2)[2] 
                if param_name == arg_name:
                    return param
        else:
            if arg_num in disp_func.params:
                return disp_func.params[arg_num]
        
        return None

    def search_for_special(self,search_name):
        if search_name in self.need_iterate_values:
            for c in self.need_iterate_values[search_name]:
                if c.point_.context == 'iter':
                    return True
        return False

    def search_ralated_self(self,search_context):

        cls_name = None
        for i in range(len(search_context.split('.'))):
            tmp_cls = '.'.join(search_context.split('.')[0:len(search_context.split('.'))-i])
            if tmp_cls in self.classes_manager.names:
                cls_name = tmp_cls
                break  

        if cls_name == None:
            return []

        child_classes = get_implementation_class(cls_name,self.inherited_map)
        related_clses = []

        for child_c in child_classes:
            if child_c in self.instances:
                related_clses.append(child_c)
        
        return related_clses

    def map_current_self(self,current_self,full_name,caller,site):        
        new_points = []
        max_match_within_function = None
        if current_self + full_name.replace('self','',1) in self.funcs_manager.names:
            # herited
            max_match_within_function = [current_self + full_name.replace('self','',1),'Method']  
        else:
            inherited_ =  self.get_inherited_(current_self,full_name.replace('self','',1))
            if len(inherited_) > 0:
                if len(inherited_) == 1:  
                    max_match_within_function = [list(inherited_)[0],'Method']
                else:
                    max_match_within_function = [current_self + full_name.replace('self','',1),'Unknown'] 
            else:
                method_name = full_name.replace('self.','',1)
                for cls_name in [current_self]:
                    the_cls = self.classes_manager.names.get(cls_name)
                    if the_cls and method_name in the_cls.properties:
                        points_ = the_cls.properties[method_name].points
                        if points_:  
                            for po in points_:
                                if 'Constant#' in po:
                                    po = po.replace('Constant#','')
                                    new_points.append(PointNode(po,po,'DT'))  
                                else:
                                    new_points.append(PointNode(po,po,'Unknown'))  
                        break 
               


        if max_match_within_function:
            new_point = PointNode(max_match_within_function[0],max_match_within_function[0],max_match_within_function[1])._set('context','Self')
            new_points.append(new_point)
       

        if len(new_points) > 0:            
            for new_point in new_points:
                self.add_edge(caller,new_point,None,site,'Call',True) 


    def pass_parameter(self):
        # pass the argument to parameter
        iteration_num = 0
        while (iteration_num < 10):
            old_dataflows = copy.deepcopy(self.data_flows)  
            old_call_manager = copy.deepcopy(self.calls_manager.names)
            for _,calls in old_call_manager.items():
                for call in calls:
                    if len(call.point_to) == 0 and 'self.' in call.ns.replace(call.scope,''):  
                        candidate_clses = self.search_ralated_self(call.scope)
                        for c_c in candidate_clses:
                            self.map_current_self(c_c,call.ns.replace(call.scope,'').strip('.'),call.scope,call.lineno)
                            

                    for point_val in call.point_to: 
                        if point_val[1] == 1:
                            if isinstance(point_val[0],str) or isinstance(point_val[0],FuncNode):  
                                func_name = point_val[0] if isinstance(point_val[0],str) else point_val[0].ns
                                disp_func = self.funcs_manager.get(func_name) 
                                if disp_func == None:
                                    continue
                                arg_num = 0
                                for arg in call.args.values():   
                                    param = self.search_for_params(arg_num,arg[1],disp_func,call.scope)
                                    if param == None:
                                        break
                              
                                    arg_name = param.point_name.replace(f'arg_#{arg_num}#','')
                                    if param.point_name not in self.data_flows:
                                        self.data_flows[param.point_name] = set()

                                    for point_arg in arg[0]:
                                        if self.search_for_special(param.point_name):
                                            point_arg.context = 'iter'
                                        self.data_flows[param.point_name].add(CallContext(point_arg.point_name,point_arg,call.scope))  
                                    
                                    arg_num += 1
                                        
                            if isinstance(point_val[0],ClassNode): 
                                disp_func = self.funcs_manager.get(point_val[0].ns+'.__init__')
                                if disp_func:
                                    arg_num = 0
                                    for arg in call.args.values():   
                                        param = self.search_for_params(arg_num,arg[1],disp_func,call.scope)
                                        if param == None:
                                            break
                                       
                                        arg_name = param.point_name.replace(f'arg_#{arg_num}#','')
                                        if param.point_name not in self.data_flows:
                                            self.data_flows[param.point_name] = set()
                                        for point_arg in arg[0]:
                                            if self.search_for_special(param.point_name):
                                                point_arg.context = 'iter'
                                            self.data_flows[param.point_name].add(CallContext(point_arg.point_name,point_arg,call.scope))  
                                        
                                        arg_num += 1

                            elif isinstance(point_val[0],UnknownNode):
                               
                                if point_val[0].type == 'Call':
                                    unknown_func = point_val[0]
                                  
                                    args = call.args  
                                    if unknown_func.ns in self.data_flows:
                                        kword = unknown_func.ns
                                        tmp_l = []
                                        for tmp in self.data_flows[kword]:   
                                            ar = tmp.ns
                                            if ar in self.funcs_manager.names:
                                                tmp_l.append((ar,tmp.scope)) 
                                            elif ar in self.classes_manager.names:
                                                ar = ar+ '.__init__'
                                                tmp_l.append((ar,tmp.scope))     
                                        if len(tmp_l) > 0:
                                            unknown_func = tmp_l
                                        if isinstance(unknown_func,UnknownNode):
                                           continue
                                        for v in unknown_func:
                                            if isinstance(v[0],UnknownNode):
                                                continue
                                            if 'Unknown@IntraLevel@'+ point_val[0].ns in self.reachable_edges[call.scope]:
                                                self.reachable_edges[call.scope].remove('Unknown@IntraLevel@'+ point_val[0].ns)
                                            self.reachable_edges[call.scope].add(v[0])

                                            disp_func = self.funcs_manager.get(v[0])
                                            if disp_func == None:
                                                continue
                                            for ki,kv in disp_func.params.items(): 
                                                para_ = kv.point_name

                                                if para_ not in self.data_flows:
                                                    self.data_flows[para_] = set()
                                                if ki in args:
                                                    for current_arg in args[ki][0]:
                                                        if isinstance(current_arg,PointNode):
                                                            if self.search_for_special(para_):
                                                                current_arg.context = 'iter'
                                                            self.data_flows[para_].add(CallContext(current_arg.point_name,current_arg,call.scope))  
                                                        if isinstance(current_arg,list):
                                                            for cur_point in current_arg:
                                                                self.data_flows[para_].add(CallContext(cur_point.point_name,None,call.scope)) 
                
            if old_dataflows == self.data_flows:  
                break                                                                           
            iteration_num += 1

    
    
    def if_inlude(self,sub,complete):
        if len(sub.split('.')) > len(complete.split('.')):
            return False
        for sub_i, complete_i in zip(sub.split('.'),complete.split('.')):
            if sub_i != complete_i:
                return False
        return True
    
    def only_inlude(self,sub,complete):
        
        if sub == None or complete == None:
            return False
        if '.'+sub + '.' in '.'+complete + '.' and complete.startswith(sub):
            return True
        else:
            return False
    
    def map_within_file(self,current_edge,keyword):
        max_match_within_function = None
        match_type = 'Partial'
        current_context = self.get_current_context()
        funcs = self.funcs_manager.get_all_funcs(module=keyword)

        nested_funcs = {}
        for fc in funcs:
            if current_context in fc and current_context != fc:
                nested_funcs[fc] = funcs[fc]

        upper_func = '.'.join(current_context.split('.')[0:-1])
        if upper_func in self.funcs_manager.names and current_context in self.funcs_manager.names[upper_func].nested and '.'.join([upper_func,current_edge]) in self.funcs_manager.names[upper_func].nested:
            return '.'.join([upper_func,current_edge]),'Exact'

        if '.'.join([current_context,current_edge]) in nested_funcs:
            return  '.'.join([current_context,current_edge]),'Exact'

        for simple_name,full_quality_name in self.global_values[keyword].items():  
            find_flag = (False,None)
            if self.only_inlude(simple_name,current_edge):   
                find_flag = (True,current_edge)    

            if find_flag[0]:
                if isinstance(full_quality_name,(FuncNode,ClassNode)):
                    candidates_edge = full_quality_name.ns+ find_flag[1][find_flag[1].index(simple_name)+len(simple_name):]
            
                else:
                    
                    candidates_edge = []
                    for obj in full_quality_name:  
                        if isinstance(obj,dict):
                            o = obj[tuple(obj)[0]]
                            candidates_edge.append(o.point_name+find_flag[1][find_flag[1].index(simple_name)+len(simple_name):])
                        else:
                            o = obj
                            candidates_edge.append(o+find_flag[1][find_flag[1].index(simple_name)+len(simple_name):])

                if simple_name == find_flag[1]:  
                    return  candidates_edge,'Exact'               
              

        return max_match_within_function,match_type   

    def map_a_b(self,current_edge,keyword=False):
     
        def get_candidate_edge(simple_name,full_quality_names,edge):
            now_remain_first = edge[edge.index(simple_name)+len(simple_name):]  
            now_remain_last = edge[edge.rindex(simple_name)+len(simple_name):]
            if isinstance(full_quality_names,(FuncNode,ClassNode)):
                candidates_edge = [full_quality_names.ns+now_remain_first,full_quality_names.ns+now_remain_last,len(simple_name)] 
                
            else:
                if isinstance(full_quality_name[0],dict):
                    o = full_quality_names[0][tuple(full_quality_names[0])[0]]
                    candidates_edge = [o.point_name+now_remain_first,o.point_name+now_remain_last,len(simple_name)] 
                else:
                    o = None
                    for tmp in full_quality_names:
                        if tmp.endswith('.Any'):
                            continue
                        o = tmp.strip()
                        break
                    if o:
                        candidates_edge = [o+now_remain_first,o+now_remain_last,len(simple_name)]
                    else:
                        return None   

            return candidates_edge                       

        finally_edges = []
        for file_context in self.global_values:  
            if file_context == current_edge: 
                return ['Module#'+file_context]
            if (file_context == keyword) or (file_context in current_edge):   
                for simple_name,full_quality_name in self.global_values[file_context].items():
                    if self.only_inlude(file_context+'.'+simple_name,current_edge):  
                        need_parse = get_candidate_edge(simple_name,full_quality_name,current_edge.replace(file_context,'',1))
                        if need_parse == None or need_parse[0] in finally_edges:
                            continue  #

                        finally_edges.append(need_parse[0]) 

        return set(finally_edges)  
    



    def add_construct_edge(self,caller,cls_name,add_set,scope=None):
        flag = False
        all_parent_cls_ = get_all_parent_class(cls_name,self.inherited_map,self.annotations)
        for add_cls in [cls_name] + list(all_parent_cls_):
            if add_cls in self.cls_has_method:
                for inner_function in ['__init__','__new__']:
                    if inner_function in self.cls_has_method[add_cls]: 
                        construct_edge = add_cls+'.'+inner_function
                        if construct_edge not in add_set[caller]:
                            if scope:
                                add_set[caller].add(CallContext(construct_edge,None,scope))
                            else: 
                                add_set[caller].add(construct_edge)
                            flag = True
                      
                if flag == True:
                    break
    
    def check_function_signature(self,args,signature):
        return True
        must_args = signature['args'].remove('self')
        if args['args'] >= len(must_args) and args['args'] <= len(must_args) + signature['len_defaults']: #call == signature['name'] and 
            return True
        return False

    def add_new_class(self,cls_name):
        the_class = ClassNode(cls_name)
        all_parent_cls_ = get_all_parent_class(cls_name,self.inherited_map,self.annotations)
        implement_cls =  get_implementation_class(cls_name,self.inherited_map)
        the_class.mro = [cls_name] + all_parent_cls_
        the_class.reverse_mro = implement_cls
        the_class.methods = self.cls_has_method[cls_name]  
        return the_class


    

    def invalid_property_function(self,possible_edge,scene):
         if possible_edge.split('.')[-1] in (('__init__','__new__','__call__')):
             return False
         if possible_edge.split('.')[0] != self.project:  
             return False
         if scene == 'attribute' and self.funcs_manager.get(possible_edge):
             if self.funcs_manager.get(possible_edge).property == False:
                return True
         return False

    def is_standard_lib(self,name):
        for sub in Standard_Libs:
            if self.only_inlude(sub,name):
                return True
        return False
    def add_edge(self,caller,callee,args,site,scene='normal',must=False):
        if site == None:
            return []
        
        if self.benchmark == 'macro':
            if callee.point_type == 'UnknownFuncReturn' and len(callee.point_name.split('.')) > 2 and callee.point_name.split('.')[-2][0].islower(): 
                return [False]
            
            if callee.origin_from == 'Attribute':
                return [False]


        if scene == 'valueflow':
            add_set = self.data_flows
        else:
            add_set = self.reachable_edges
    
        if caller not in add_set:
            add_set[caller] = set()

        
            

        if self.benchmark == 'macro':
            if callee.point_name.split('.')[-1] in ['__enter__','__exit__']:  
                if callee.point_name.split('.')[0] != self.project:
                    return [False]  
 
        if callee.point_type == 'DT':
            if 'Constant#' in callee.point_name:
                callee.point_name = callee.point_name.replace('Constant#','')
            if callee.point_name.split('.')[0] in Standard_DataType:
                predix = Standard_DataType[callee.point_name.split('.')[0]]
                if len(callee.point_name.split('.')) > 1:
                    if '.'.join(callee.point_name.split('.')[1:]) in DT_Returns[callee.point_name.split('.')[0]]:
                        if self.benchmark == 'micro':
                         
                            add_callee =  self.project + '.'+predix + '.'+'.'.join(callee.point_name.split('.')[1:])
                        else:
                            add_callee = predix + '.'+ '.'.join(callee.point_name.split('.')[1:])
                        if add_callee not in add_set[caller]:  
                            add_set[caller].add(add_callee)

            return ['DT']

        if callee.point_type == 'builtin':
            add_callee = callee.point_name
            if add_callee not in add_set[caller]:
                add_set[caller].add(add_callee)

            return ['builtin']
        
        if self.is_standard_lib(callee.point_name):
            return ['stlib']

        
        def add_inherited_edges(edg,flag,scene='normal'):
            
            add_inherited = set()
            add_implementations= set()
            if flag == True:
                return add_inherited
            
            cls_names = []
            for i in range(len(edg.split('.'))):
                tmp_cls = '.'.join(edg.split('.')[0:len(edg.split('.'))-i])
                if tmp_cls in self.inherited_map:
                    cls_names.append((tmp_cls,edg.replace(tmp_cls,'',1)))

            for cls_name,method_remain_first in cls_names:
                    
                   
                implementation_class = []

                implementation_class= get_implementation_class(cls_name,self.inherited_map) 
                all_parent_cls_ = get_all_parent_class(cls_name,self.inherited_map,self.annotations)

                if len(method_remain_first) == 0:
                    continue
                method_name = method_remain_first.strip('.')
                for add_par_cls in all_parent_cls_:
                    if add_par_cls in self.cls_has_method and method_name in self.cls_has_method[add_par_cls]:
                        if self.check_function_signature(args,self.cls_has_method[add_par_cls][method_name]):
                            inherited_edge = add_par_cls+method_remain_first
                            add_flag = True
                           
                            if add_flag == True:
                                #if self.invalid_property_function(inherited_edge,scene):  
                                 #   print('filter',inherited_edge)
                                #else:
                                    add_inherited.add(inherited_edge)
                                    if inherited_edge not in add_set[caller] :
                                        # self.edges[caller].append([site,inherited_edge])
                                        add_set[caller].add(inherited_edge)
                               
                            break
            
                for add_implemente_cls in implementation_class:
                   
                    if add_implemente_cls in self.cls_has_method and method_name in self.cls_has_method[add_implemente_cls]:
                        implement_edge = add_implemente_cls+method_remain_first
                        #if self.invalid_property_function(implement_edge,scene):  
                        #    print('filter',implement_edge)
                        #else:
                        if 1:
                            add_implementations.add(implement_edge)
                        

            if len(add_inherited) > 0:
                    return add_inherited
            else:
                if len(add_implementations)> 0:
                    return add_implementations
                else:
                    return []
                        

        
        return_disp = []

        if  'arg_#' in callee.point_name: 
            edge = callee.point_name
            flag = False
        else:
            mp_edge,flag = get_local_name(callee.point_name,args,self.annotations,self.import_map,'Call') 
            

            if callee.point_name in self.funcs_manager.names:
                return_disp.append([self.funcs_manager.get(callee.point_name),1])
                edge = callee.point_name
                flag = True
            elif callee.point_name in self.classes_manager.names:
                return_disp.append([self.classes_manager.get(callee.point_name),1])
                edge = callee.point_name
                flag = True
        
            else:
                edge = mp_edge.strip()

    
        if callee.origin_from == 'Attribute' and ((edge in self.cls_has_method) or (flag == False)):
            return [False]
    

        if callee.context == 'Super':
            add_inherited = add_inherited_edges(edge,False,scene) 
            for inherited_edge in add_inherited:
                return_disp.append([inherited_edge,1/len(add_inherited)])

            return return_disp

        if edge in self.cls_has_method: 
            if scene != 'attribute':  #
                self.add_construct_edge(caller,edge,add_set)


        if flag==False:                        
            if  'arg_#' in callee.point_name:  
                callee.origin_from == 'DependLevel'  #
              
                return_disp.append([UnknownNode(callee.point_name,self.get_current_context()),1])   
                if caller != callee.point_name:  
                    if 'Unknown@'+callee.origin_from+'@'+callee.point_name not in add_set[caller]:
                        add_set[caller].add('Unknown@'+callee.origin_from+'@'+callee.point_name) 
                
                return return_disp

            guess_cls = '.'.join(edge.split('.')[0:-1])
            if guess_cls in self.cls_has_method:
                the_cls = self.classes_manager.names.get(guess_cls)
                if the_cls and edge.split('.')[-1] in the_cls.properties:
                    if must == True: 
                        disp_funcs = []
                        if the_cls.properties[edge.split('.')[-1]].points:
                            for obj in the_cls.properties[edge.split('.')[-1]].points: 
                                add_c = PointNode(obj,obj,'func')
                                disp_funcs += self.add_edge(caller,add_c,args,site,scene,must)
                        return disp_funcs
                    else:
                        return return_disp
                
            

            # check inherited class
            add_inherited = add_inherited_edges(edge,flag,scene)  
            if len(add_inherited) > 0:
                    for cls in add_inherited:
                        the_class = self.funcs_manager.get(cls)
                        
                        return_disp.append([the_class,1/len(add_inherited)]) 
                    
                    return return_disp
                
            else:
                
                unknown_node = UnknownNode(edge,self.get_current_context())
                unknown_node.type = 'inconstent'
                return_disp.append([unknown_node,1])

                if scene == 'valueflow':
                    pass
                else:
                    if 'Unknown@'+callee.origin_from+'@'+edge not in add_set[caller]:
                        add_set[caller].add('Unknown@'+callee.origin_from+'@'+edge)
                
                if callee.origin_from == 'IntraLevel':
                    return return_disp


            if callee.origin_from == 'ImportLevel':
               
                if edge.split('.')[0] != self.project: 
                    unknown_node = UnknownNode(edge,self.get_current_context())
                    unknown_node.type = 'importerror'
                    return_disp.append([unknown_node,1])
                    if scene == 'valueflow':
                        pass
                    else:
                        if 'Unknown@'+callee.origin_from+'@'+edge not in add_set[caller]:
                            add_set[caller].add('Unknown@'+callee.origin_from+'@'+edge)

                    return return_disp

                edges = self.map_a_b(edge)  

                if len(edges) == 1 and 'Module#' in list(edges)[0]:
                    return return_disp
                if edge in edges:
                    pass  
                else:
                    edges.add(edge)
                    for map_edg_ in edges: 
                        if  map_edg_ in BUILT_IN_FUNCTIONS:  
                            self.reachable_edges[caller].add(caller.split('.')[0]+'.<builtin>.' + map_edg_)
                            continue
                        map_edg,flag = get_local_name(map_edg_,args,self.annotations) 
                        return_disp += self.add_edge(caller,PointNode(map_edg,map_edg,'Unknown'),args,site)   
        
        else:
            if self.invalid_property_function(edge,scene) and scene != 'valueflow':  
                pass
            else:
                if '<lambda' in caller and caller == edge:
                    return []  

                if caller in self.funcs_manager.names and self.funcs_manager.get(caller).start_line > site: 
                    upper_caller = '.'.join(caller.split('.')[0:-1])
                    
                    if upper_caller not in add_set:
                        add_set[upper_caller] = set()

                    if edge not in add_set[upper_caller]:  
                        add_set[upper_caller].add(edge)
                else:
                    if edge not in add_set[caller]:  
                        add_set[caller].add(edge)

                
                if edge in self.cls_has_method:
                    if edge not in self.classes_manager.names:
                        
                        self.classes_manager.names[edge] = self.add_new_class(edge)

                    self.instances.append(edge)    

                    return_disp.append([self.classes_manager.get(edge),1]) 
                    # call.defined = True
                
                else:
                    if edge not in self.funcs_manager.names:
                        the_function = FuncNode(edge)
                    else:
                        the_function = self.funcs_manager.get(edge)
                    
                    return_disp.append([the_function,1]) 

           
        
            
            if (len(self.special_fors) > 0 and self.special_fors[-1] == 'For') or callee.context == 'iter' :  #0525
                if edge in self.cls_has_method:
                    
                    if '__next__' in self.cls_has_method[edge]:
                        add_set[caller].add(edge +'.__next__')
                        return_disp.append([self.funcs_manager.get(edge +'.__next__'),1])

                    if '__iter__' in self.cls_has_method[edge]:
                        add_set[caller].add(edge +'.__iter__')
                        return_disp.append([self.funcs_manager.get(edge +'.__iter__'),1])
        return return_disp
        
    
    def add_dataflow(self,caller,callee,scope=None,scene='normal',must=False):
        if scope == None:
            scope = caller.strip()
        
        add_set = self.data_flows
       
    
        if caller not in add_set:
            add_set[caller] = set()
      
        if callee.point_type == 'DT':
            if 'Constant#' in callee.point_name:
                callee.point_name = callee.point_name.replace('Constant#','')
            if callee.point_name.split('.')[0] in Standard_DataType:
                predix = Standard_DataType[callee.point_name.split('.')[0]]
                if len(callee.point_name.split('.')) > 1:
                    if '.'.join(callee.point_name.split('.')[1:]) in DT_Returns[callee.point_name.split('.')[0]]:
                        add_callee = predix + '.'+'.'.join(callee.point_name.split('.')[1:])
                        add_set[caller].add(CallContext(add_callee,None,scope))

            return ['DT']

        if callee.point_type == 'builtin':
            add_callee = callee.point_name
            add_set[caller].add(CallContext(add_callee,None,scope))

            return ['builtin']
        

        if self.is_standard_lib(callee.point_name):
            return ['stlib']

        
        def add_inherited_edges(edg,flag,scene='normal'):
            
            add_inherited = set()
            add_implementations= set()
            if flag == True:
                return add_inherited
            
            cls_names = []
            for i in range(len(edg.split('.'))):
                tmp_cls = '.'.join(edg.split('.')[0:len(edg.split('.'))-i])
                if tmp_cls in self.inherited_map:
                    cls_names.append((tmp_cls,edg.replace(tmp_cls,'',1)))

            for cls_name,method_remain_first in cls_names:           
                
                implementation_class = []

              
                implementation_class= get_implementation_class(cls_name,self.inherited_map) 
                all_parent_cls_ = get_all_parent_class(cls_name,self.inherited_map,self.annotations)

                if len(method_remain_first) == 0:
                    continue
                method_name = method_remain_first.strip('.')
                for add_par_cls in all_parent_cls_:
                    if add_par_cls in self.cls_has_method and method_name in self.cls_has_method[add_par_cls]:
                            inherited_edge = add_par_cls+method_remain_first
                            add_flag = True
                           
                            if add_flag == True:
                                #if self.invalid_property_function(inherited_edge,scene): 
                                 #   print('filter',inherited_edge)
                                #else:
                                    add_inherited.add(inherited_edge)
                                    if inherited_edge not in add_set[caller] :
                                        # self.edges[caller].append([site,inherited_edge])
                                        add_set[caller].add(inherited_edge)
                               
                            break
            
                for add_implemente_cls in implementation_class:
                   
                    if add_implemente_cls in self.cls_has_method and method_name in self.cls_has_method[add_implemente_cls]:
                        implement_edge = add_implemente_cls+method_remain_first
                        #if self.invalid_property_function(implement_edge,scene):  
                        #    print('filter',implement_edge)
                        #else:
                        if 1:
                            add_implementations.add(implement_edge)
                    

            if len(add_inherited) > 0:
                    return add_inherited
            else:
                if len(add_implementations)> 0:
                    return add_implementations
                else:
                    return []
                    

        
        return_disp = []
        mp_edge,flag = get_local_name(callee.point_name,0,self.annotations,self.import_map)  #
        if callee.point_name in self.funcs_manager.names:
            return_disp.append([self.funcs_manager.get(callee.point_name),1])
            edge = callee.point_name
            flag = True
        elif callee.point_name in self.classes_manager.names:
            return_disp.append([self.classes_manager.get(callee.point_name),1])
            edge = callee.point_name
            flag = True
       
        else:
            edge = mp_edge.strip()

        if callee.origin_from == 'Attribute' and edge in self.cls_has_method:
            return [False]
        if callee.origin_from == 'Attribute' and flag == False:  
            return [False]

        if callee.context == 'Super':
            add_inherited = add_inherited_edges(edge,False,scene) 
            for inherited_edge in add_inherited:
                return_disp.append([inherited_edge,1/len(add_inherited)])

            return return_disp
        if edge in self.cls_has_method: 
            if scene == 'attribute':  #
                pass
            else:
                self.add_construct_edge(caller,edge,add_set,scope)

      
        if flag==False:            
            if  'arg_#' in edge:  
                callee.origin_from == 'DependLevel'
                
                return_disp.append([UnknownNode(edge,self.get_current_context()),1])  
                if caller != edge:  
                    if 'Unknown@'+callee.origin_from+'@'+edge not in add_set[caller]:
                        add_set[caller].add(CallContext('Unknown@'+callee.origin_from+'@'+edge,callee,scope))  

                    add_set[caller].add(CallContext(edge,callee,scope))

                return return_disp
            

            guess_cls = '.'.join(edge.split('.')[0:-1])
            if guess_cls in self.cls_has_method:
                the_cls = self.classes_manager.names.get(guess_cls)
                if the_cls and edge.split('.')[-1] in the_cls.properties:
                    if must == True: 
                        disp_funcs = []
                        if the_cls.properties[edge.split('.')[-1]].points:
                            for obj in the_cls.properties[edge.split('.')[-1]].points: 
                                add_c = PointNode(obj,obj,'func')
                                disp_funcs += self.add_dataflow(caller,add_c,scope,scene,must)
                        return disp_funcs
                    else:
                        return return_disp
                
            

            if 1:
                add_inherited = add_inherited_edges(edge,flag,scene)  
                if len(add_inherited) > 0:
                        for cls in add_inherited:
                            the_class = self.funcs_manager.get(cls)
                            
                            return_disp.append([the_class,1/len(add_inherited)]) 
               
                else:
                    unknown_node = UnknownNode(edge,self.get_current_context())
                    unknown_node.type = 'inconstent'
                    return_disp.append([unknown_node,1])

                    add_set[caller].add(CallContext(edge,callee,scope))

            if callee.origin_from == 'ImportLevel':
                if edge.split('.')[0] != self.project: 
                    return return_disp

                edges = self.map_a_b(edge)  

                if len(edges) == 1 and 'Module#' in list(edges)[0]:
                    return add_set[caller].add(CallContext(list(edges)[0],callee,scope))
                if edge in edges:
                    pass  
                else:
                    edges.add(edge)
                    for map_edg_ in edges: 
                        if  map_edg_ in BUILT_IN_FUNCTIONS:  
                            self.reachable_edges[caller].add(caller.split('.')[0]+'.<builtin>.' + map_edg_)
                            continue
                        map_edg,flag = get_local_name(map_edg_,0,self.annotations) 
                        return_disp += self.add_dataflow(caller,PointNode(map_edg,map_edg,'Unknown'),scope)   
        
        else:
            add_set[caller].add(CallContext(edge,callee,scope))
           
        return return_disp
    

    def search_for_definition(self,full_name,current_context):
        if not isinstance(full_name,list):
            print('error')
            import sys
            sys.exit(1)
        
        if full_name[0] == 'self':  
            return [PointNode('self','self','Unknown')._set('origin_from','Unknown')]  

        if  full_name[0] in ['list','dict','set','defaultdict','str','num','tuple']:
            return [PointNode(full_name[0],full_name[0],'DT')._set('match','Exact')]
        elif full_name[0] in BUILT_IN_FUNCTIONS:
            return [PointNode(full_name[0],full_name[0],'builtin')._set('match','Exact')] 
        else:
            all_find_edge,_ = self.add_external_edges(full_name,current_context,{'args':0},None)
            if len(all_find_edge) == 0:
                all_find_edge,_ = self.analyze_within(full_name,current_context,{'args':0},None) 

        return all_find_edge

    def get_return_value(self,dispatch_objects, args,args_kw,lineno,value_context='Normal'):
        

        return_objects = []
        for pointTo_ in dispatch_objects:
            
            if pointTo_.point_type in ('DT','builtin'):  
                if pointTo_.point_name in BUILT_IN_Returns:
                    return_objects.append(PointNode(BUILT_IN_Returns[pointTo_.point_name],BUILT_IN_Returns[pointTo_.point_name],'DT',pointTo_))
                elif pointTo_.point_name in Standard_DataType:
                    return_objects.append(PointNode(pointTo_.point_name,pointTo_.point_name,'DT',pointTo_))
                elif pointTo_.point_name.split('.')[0] in DT_Returns: 
                    if '.'.join(pointTo_.point_name.split('.')[1:]) in DT_Returns[pointTo_.point_name.split('.')[0]]:
                        return_type = DT_Returns[pointTo_.point_name.split('.')[0]]['.'.join(pointTo_.point_name.split('.')[1:])]
                        if return_type != 'none':
                            return_objects.append(PointNode(return_type,return_type,'DT',pointTo_))
                continue

            elif pointTo_.point_name in self.funcs_manager.names:
                an_f_ = pointTo_.point_name
                flag = True
            elif pointTo_.point_name in self.classes_manager.names:
                an_f_ = pointTo_.point_name
                flag = True
            else:
                an_f_ ,flag = get_local_name(pointTo_.point_name,{'args':len(args)+len(args_kw)},self.annotations,self.import_map,'Return')
           

            if flag:

                if an_f_ in self.funcs_manager.names:
                    if self.funcs_manager.names[an_f_].returns:
                        for res in self.funcs_manager.names[an_f_].returns:  

                            if isinstance(res,dict):  #
                                o = res[tuple(res)[0]]  
                                return_objects.append(o)
                            else:
                                if res in self.cls_has_method:  
                                    return_objects.append(PointNode(res,res,'ClsReturn',pointTo_))
                                elif 'Constant#' in res:
                                    return_objects.append(PointNode(res.replace('Constant#',''),res.replace('Constant#',''),'DT',pointTo_))
                                else:
                                    return_objects.append(PointNode(res,res,'FuncReturn',pointTo_)) 
                    else:
                        return_objects.append(PointNode(an_f_,an_f_,'UnknownFuncReturn',pointTo_))  
                        
                else:  
                    if an_f_.split('.')[0] ==  self.project:

                        return_objects.append(PointNode(an_f_,an_f_,'ClsReturn',pointTo_))
                    else:
                         return_objects.append(PointNode(an_f_,an_f_,'CrossProReturn',pointTo_))


                    if value_context == 'iter':
                        if an_f_ + '.__next__' in self.funcs_manager.names:
                            iter_func = an_f_ + '.__next__'
                            return_objects += self.get_return_value([PointNode(iter_func,iter_func,'Func',pointTo_)],{},{},None) 
                        if an_f_ + '.__iter__' in self.funcs_manager.names:
                            iter_func = an_f_ + '.__iter__'
                            return_objects += self.get_return_value([PointNode(iter_func,iter_func,'Func',pointTo_)],{},{},None)  
            else:  

                return_objects.append(PointNode(an_f_,an_f_,"UnknownFuncReturn",pointTo_))  

        return return_objects

    def deal_with_call(self,call_node,value_context='Normal'):

       
        if call_node == None:
            return []
        current_context = self.get_current_context()
        i = 0

        
        find_objects = []
        '''
        f()
        A.f()
        A[0]()
        A()()
        '''
        if isinstance(call_node.func,ast.Attribute):  #
            find_objects = self.deal_with_attribute(call_node.func)
            
        elif isinstance(call_node.func,ast.Name):
            find_objects = [self.get_node_name(call_node.func)]
        elif isinstance(call_node.func,ast.Subscript):
            find_objects = [self.get_node_name(call_node.func)]
        elif isinstance(call_node.func,ast.Call):
            find_objects = self.deal_with_call(call_node.func)
           


        all_call_names = []
        for o in find_objects:
            if o == None:
                continue

            all_call_names.append(o)


        dispatch_objects = []
        
        for full_name in all_call_names:
            
            if isinstance(full_name,PointNode):
                if full_name.origin_from == 'Unknown': 
                    full_name = full_name.point_name
                else:
                    
                    dispatch_objects.append(full_name)
                    continue
            
            if full_name == 'super':
                #
                current_cls_name = self.self_class[-1]
                cls_name = current_context[0:current_context.rindex(current_cls_name)+len(current_cls_name)]  
                dispatch_objects.append(PointNode(cls_name,cls_name,'Cls')._set('context','Super'))
            
           
            elif full_name.split('.')[0] in ['list','dict','set','defaultdict','str']:  #
                new_point = PointNode(full_name,full_name,'DT')
                dispatch_objects.append(new_point)
            elif full_name.split('.')[0] in BUILT_IN_FUNCTIONS:
                
                dispatch_objects.append(PointNode(full_name,full_name,'builtin'))
            else:
                find_objects = self.search_for_definition([full_name,'Call'],current_context)
                dispatch_objects += list(find_objects)

        args = call_node.args
        args_kw = call_node.keywords

        return_objects = self.get_return_value(dispatch_objects,args,args_kw,call_node.lineno,value_context)
        return return_objects



    def add_points(self,name,context,new_point):  

        if new_point.origin_from == 'IntraLevel':
            PointsLevel = self.used_ModuleNames
        if new_point.origin_from == 'ImportLevel':  
            PointsLevel = self.Import_points
        if new_point.origin_from == 'Unknown': 
            PointsLevel = self.unknown_points

        if context not in PointsLevel:
            PointsLevel[context] = {}
        if name not in PointsLevel[context]:
            PointsLevel[context][name] = []        

        point_name = new_point.point_name
        
        if point_name not in PointsLevel[context][name]:
           
            new_point.control = '.'.join(self.special_items)
            news = []
            
            for o in PointsLevel[context][name]:
                if o[tuple(o)[0]].point_name == point_name:
                    continue
                if o[tuple(o)[0]].point_name in point_name: 
                    for special_i in self.special_items:
                        if 'If#' in special_i or 'Else#' in special_i:      
                            break
                    else:
                        
                        continue
                
                news.append(o)

            news.append({point_name:new_point})
            PointsLevel[context][name] = news

            if new_point.context != 'Normal':  
                if point_name not in self.need_iterate_values:
                    self.need_iterate_values[point_name] = []
                
                self.need_iterate_values[point_name].append(CallContext(point_name,new_point,context))  
           
    
    def if_inclass(self):
        current_file = self.current_rel_filename.replace('.__init__','',1)
        if (self.self_class[-1] == self.scopes[-1]) and self.get_current_context() != current_file and self.get_current_class() != current_file :
            return True
        return False

            

    def _patch_with_scope(self,target_nodes,current_context,point_target):
        
        if len(target_nodes) == 1 and isinstance(target_nodes[0],ast.Name):
            target_name = target_nodes[0].id
            if  self.if_inclass():  
                current_cls_name = self.self_class[-1]
                tmp = current_context[0:current_context.rindex(current_cls_name)+len(current_cls_name)]
                if tmp == current_context:
                    self.add_points('self.'+target_name,tmp,point_target)
                            
            self.add_points(target_name,current_context,point_target)
        elif len(target_nodes) == 1 and isinstance(target_nodes[0],str):
            target_name = target_nodes[0]
            if  self.if_inclass():  
                current_cls_name = self.self_class[-1]
                tmp = current_context[0:current_context.rindex(current_cls_name)+len(current_cls_name)]
                if tmp == current_context:
                    self.add_points('self.'+target_name,tmp,point_target)
                            
            self.add_points(target_name,current_context,point_target)

        elif len(target_nodes) == 1 and isinstance(target_nodes[0],ast.Attribute):
            target_name = self.get_node_name(target_nodes[0]) 
            if target_name:
                if 'self.' in target_name: #self.parent
                       
                    current_cls_name = self.self_class[-1]  
                    tmp = current_context[0:current_context.rindex(current_cls_name)+len(current_cls_name)]  
                    self.add_points(target_name,tmp,point_target)
                else:          
                    self.add_points(target_name,current_context,point_target)

        else:
            for target_value in target_nodes:
                target_name = self.get_node_name(target_value) 
                if target_name:
                    if 'self.' in target_name: #self                           
                        current_cls_name = self.self_class[-1]  
                        tmp = current_context[0:current_context.rindex(current_cls_name)+len(current_cls_name)]  
                        self.add_points(target_name,tmp,point_target)
                    else: 
                        if  self.if_inclass():  
                            current_cls_name = self.self_class[-1]
                            tmp = current_context[0:current_context.rindex(current_cls_name)+len(current_cls_name)]
                            if tmp == current_context:
                                self.add_points('self.'+target_name,tmp,point_target)
                                
                        self.add_points(target_name,current_context,point_target)
                
    def deal_with_star(self,source_node,target_nodes):
        star_range = [0,0]
        for tar in target_nodes[0].elts:
            if isinstance(tar,ast.Starred):  
                star_range[1] = star_range[0] + 1
            else:
                if star_range[1] > star_range[0]:
                    star_range[1] += 1
                else:
                    star_range[0] += 1
        
        for tar,sre in zip(target_nodes[0].elts[0:star_range[0]],source_node.elts):
            
            self.deal_with_assign(sre,[tar])
        
        if star_range[1] > star_range[0]:

            tar = target_nodes[0].elts[star_range[0]].value 
            for sre in source_node.elts[star_range[0]:star_range[1]]:
                self.deal_with_assign(sre,[tar])

        for tar,sre in zip(target_nodes[0].elts[star_range[0]+1:],source_node.elts[star_range[1]:]):
            self.deal_with_assign(sre,[tar])

    
    def deal_with_assign(self,source_node,target_nodes,num=1):
        '''

        '''
        search_context = 'Normal'
        if self.is_special_for():
            search_context = 'iter'

        
        if source_node == None:
            return

        current_context = self.get_current_context()  
        
        source_name = None
        if isinstance(source_node,str):
            source_name = [source_node.strip(),'Var']
            self._patch_with_scope(target_nodes,current_context,PointNode('str','str','DT'))
        elif isinstance(source_node,ast.Str):
            self._patch_with_scope(target_nodes,current_context,PointNode('str','str','DT'))
        elif isinstance(source_node,ast.Num):
            self._patch_with_scope(target_nodes,current_context,PointNode('num','num','DT'))

        elif isinstance(source_node,ast.Constant):
            if transferConstant(source_node):
                ty = transferConstant(source_node)
                self._patch_with_scope(target_nodes,current_context,PointNode(ty.type,ty.type,'DT')) 
        elif isinstance(source_node,ast.Name): 
            source_name = [source_node.id,'Var'] 
        elif isinstance(source_node,ast.Attribute):  

            find_objects = self.deal_with_attribute(source_node)
            attributes_results = []
            for o in find_objects:
                

                if o.origin_from== 'Unknown':
                    if  'self.' in o.point_name:  
                        source_name = [o.point_name,'Attr']
                else:
                    if o.point_name.split('.')[0] != self.project:  #failed to catch this attribute
                        pass
                    else:
                        self._patch_with_scope(target_nodes,current_context,o)  
            
        elif isinstance(source_node,ast.Call):  
            
            if self.get_node_name(source_node.func) in ['list','dict','set','defaultdict','tuple']:
               
                if len(source_node.args) == 0 and len(source_node.keywords) == 0: 
                    new_point = PointNode(self.get_node_name(source_node.func),self.get_node_name(source_node.func),'DT')
                    self._patch_with_scope(target_nodes,current_context,new_point)
                else:
                    new_point = PointNode(self.get_node_name(source_node.func),self.get_node_name(source_node.func),'DT')
                    self._patch_with_scope(target_nodes,current_context,new_point) 
                    

                    for dict_value in source_node.args: 
                        self.deal_with_assign(dict_value,target_nodes,num)
                    for dict_value in source_node.keywords:
                        self.deal_with_assign(dict_value,target_nodes,num)

            elif isinstance(source_node.func,ast.Attribute) and source_node.func.attr == 'copy' and source_node.args == [] and source_node.keywords == []:

              
                self.deal_with_assign(source_node.func.value,target_nodes)

            else:
                
                return_values = self.deal_with_call(source_node,search_context)  #
                
                for sn in return_values:                   
                    self._patch_with_scope(target_nodes,current_context,sn)
             
            
        
        elif isinstance(source_node,ast.BoolOp): 
            
            for v in source_node.values:
                self.deal_with_assign(v,target_nodes,num)

        elif isinstance(source_node,ast.BinOp):
            
            self.deal_with_assign(source_node.left,target_nodes,num)
            self.deal_with_assign(source_node.right,target_nodes,num)

        elif isinstance(source_node,ast.Dict): #


            if len(source_node.values) == 0: 
                self._patch_with_scope(target_nodes,current_context,PointNode('dict','dict','DT'))

            else:
                self._patch_with_scope(target_nodes,current_context,PointNode('dict','dict','DT'))
                for dict_value in source_node.values:
                    self.deal_with_assign(dict_value,target_nodes,num)
                
                                
        elif isinstance(source_node,ast.Set): 
            if len(source_node.elts) == 0: 
                self._patch_with_scope(target_nodes,current_context,PointNode('set','set','DT'))
            else:
               
                if len(target_nodes) == 1 and isinstance(target_nodes[0],ast.Set):
                    self.deal_with_star(source_node,target_nodes)
                elif len(target_nodes) == len(source_node.elts):
                    for tar,sre in zip(target_nodes,source_node.elts):
                        self.deal_with_assign(sre,[tar])
                else:
                    self._patch_with_scope(target_nodes,current_context,PointNode('set','set','DT'))
                    for list_value in source_node.elts:
                        self.deal_with_assign(list_value,target_nodes,num)

        elif isinstance(source_node,(ast.List,ast.Tuple)): #b = (O1,O2,O3)  
            current_name = 'tuple'
            if isinstance(source_node,ast.List):
                current_name = 'list'
            if len(source_node.elts) == 0: 
                self._patch_with_scope(target_nodes,current_context,PointNode(current_name,current_name,'DT'))
            else:
               
                if len(target_nodes) == 1 and isinstance(target_nodes[0],ast.Tuple):
                    self.deal_with_star(source_node,target_nodes)
                elif len(target_nodes) == len(source_node.elts):
                    for tar,sre in zip(target_nodes,source_node.elts):
                        self.deal_with_assign(sre,[tar])
                else:
                    self._patch_with_scope(target_nodes,current_context,PointNode(current_name,current_name,'DT'))
                    for tuple_value in source_node.elts:
                        self.deal_with_assign(tuple_value,target_nodes,num)
        elif isinstance(source_node,ast.Subscript): 
            self.deal_with_assign(source_node.value,target_nodes)


        elif isinstance(source_node,ast.Starred):
            self.deal_with_assign(source_node.value,target_nodes)
        elif isinstance(source_node,ast.IfExp): #
            self.deal_with_assign(source_node.body,target_nodes,num)
            self.deal_with_assign(source_node.orelse,target_nodes,num)
        elif isinstance(source_node,ast.Lambda):  # 
            
            return_lambdas = self.deal_with_lambda(source_node)
            for v in return_lambdas:
                self._patch_with_scope(target_nodes,current_context,v)
            

        if source_name:
            
            if source_name[0] == None:
               
                return

            flag_find = False

            need_add_points,_ = self.add_external_edges(source_name,current_context,0,None)
          
            for add_point in need_add_points:
                add_point.context = search_context  
                self._patch_with_scope(target_nodes,current_context,add_point)
                flag_find = True

          
            if flag_find == False:
                call_functions,_ = self.analyze_within(source_name,current_context,None)  
                if len(call_functions) > 0:
                    for pointTo_ in call_functions:
                        pointTo_.context = search_context
                        self._patch_with_scope(target_nodes,current_context,pointTo_)

    def deal_with_lambda(self,node):

        self.visit(node)  
        current_context = self.get_current_context() 
        current_lambda = LambdaNode(None,current_context)  
        current_lambda.setPos(node.lineno,node.end_lineno,node.col_offset,node.end_col_offset)

        
        for last_lambda in self.lambdas:
            if last_lambda == current_lambda:
                lambda_name = last_lambda.scope + '.' + last_lambda.ns  #
                break

        lambda_ndoe = PointNode(lambda_name,lambda_name,'lambda')
        return [lambda_ndoe]  


    def visit_Lambda(self,node):  
        current_context = self.get_current_context() 
        lambda_name = '<lambda' + str(len(self.lambda_names[current_context])+1) + '>'
        current_lambda = LambdaNode(lambda_name,current_context) 
        current_lambda.setPos(node.lineno,node.end_lineno,node.col_offset,node.end_col_offset)


        for last_lambda in self.lambdas:
            if last_lambda == current_lambda:
                lambda_name = last_lambda.ns  
                break
        else:
            self.lambdas.append(current_lambda)
            self.lambda_names[current_context].append(lambda_name)  

        self.scopes.append(lambda_name)
        current_func = self.get_current_context()
        self.funcs_manager.add(current_func,self.current_rel_filename.replace('.__init__',''),node.lineno,None)    
        self.visit_FunctionDef(node)


    def visit_Assign(self, node):
        
        for t in node.targets:
            if isinstance(t,ast.Attribute):
                self.add_noncall_edges([t],node.lineno) #
       
        self.add_noncall_edges([node.value],node.lineno) #
        self.deal_with_assign(node.value,node.targets)
        self.generic_visit(node)  


    def visit_AugAssign(self, node): 
        #  a += 1
        self.add_noncall_edges([node.target],node.lineno)
        self.add_noncall_edges([node.value],node.lineno)  
        self.deal_with_assign(node.value,[node.target])
        self.generic_visit(node)   
    
    def visit_AnnAssign(self, node):
        # https://docs.python.org/3/library/ast.html
        self.add_noncall_edges([node.value],node.lineno) 
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
                if subnode.name in ['typing','collections'] or subnode.name.startswith('typing.') or subnode.name.startswith('collections.'):
                   
                    import_type = 'builtin'
                else:
                    if subnode.name in BUILT_IN_FUNCTIONS or subnode.name in Standard_Libs:
                        import_type = 'builtin'
                    else:
                        import_type = 'import'
                        current_path = self.current_rel_filename
                        refer_path = '.'.join(current_path.split('.')[0:len(current_path.split('.'))-1])
                        pkg = '.'.join([refer_path,subnode.name])
                        if pkg in self.global_values:
                            import_type = 'Module'
                            true_point = pkg.strip()

                        if subnode.name != true_point:
                            self.import_map[subnode.name] = true_point       
                new_point = PointNode(true_point,true_point,import_type)
                new_point.origin_from = 'ImportLevel' 
                self.add_points(alias_name,current_context,new_point)
            

    def visit_ImportFrom(self,node):
        '''
        remove the import statement: from . import A
        from A import a.b is parsed as A, a.b

        '''
        
        current_context = self.get_current_context() 
        if node.level == 0:
            pkg = node.module
            if pkg in BUILT_IN_FUNCTIONS or pkg in Standard_Libs or pkg in ['typing','collections'] or pkg.startswith('typing.') or pkg.startswith('collections.'):
                import_type = 'builtin'
            else:
                import_type = 'import'
            modules = node.names
            if 1:
                for subnode in modules:  
                    alias_name = subnode.asname if subnode.asname else subnode.name 
                    
                    tmp_n =  '.'.join([pkg,subnode.name])
                    if tmp_n == ['typing','collections'] or tmp_n.startswith('typing.') or tmp_n.startswith('collections.'):
                        if current_context not in self.types:
                            self.types[current_context] = {}
                        if alias_name not in self.types[current_context]:
                            self.types[current_context][alias_name] =  tmp_n

                    
                  
                  
                    if alias_name == '*':
                         # import all

                        if pkg in self.global_values:
                            for simple_name,full_quality_name in self.global_values[pkg].items():
                                new_point = PointNode(full_quality_name.ns,full_quality_name.ns,full_quality_name.type)
                                new_point.origin_from = 'ImportLevel'  
                                self.add_points(simple_name,current_context,new_point)
                        else:
                            current_path = self.current_rel_filename
                            refer_path = '.'.join(current_path.split('.')[0:len(current_path.split('.'))-1])
                            tmp_pkg = '.'.join([refer_path,pkg])
                            if tmp_pkg in self.global_values:  
                                for simple_name,full_quality_name in self.global_values[tmp_pkg].items():
                                    new_point = PointNode(full_quality_name.ns,full_quality_name.ns,full_quality_name.type)
                                    new_point.origin_from = 'ImportLevel'  
                                    self.add_points(simple_name,current_context,new_point)
                    else:
                        if import_type != 'builtin':
                            current_path = self.current_rel_filename
                            refer_path = '.'.join(current_path.split('.')[0:len(current_path.split('.'))-1])
                            tmp_pkg = '.'.join([refer_path,pkg])
                            if tmp_pkg in self.global_values:
                                pkg = tmp_pkg.strip()
                            
                            if node.module != pkg:
                                self.import_map[node.module] = pkg

                        name = '.'.join([pkg,subnode.name])
                        new_point = PointNode(name,name,import_type)
                        new_point.origin_from = 'ImportLevel'
                        self.add_points(alias_name,current_context,new_point)
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
                edge,flag = get_local_name('.'.join([pkg,subnode.name]),0,self.annotations)  #
                import_type = 'import'
                if flag:

                    self.need_dispatch_name.append(alias_name)
                    if edge in self.cls_has_method:
                        import_type = 'Cls'
                    else:
                        import_type = 'importFunc'
                elif edge in self.global_values:  
                        import_type = 'Module'
                
                name = '.'.join([pkg,subnode.name])
                new_point = PointNode(name,name,'import')
                new_point.origin_from = 'ImportLevel' 
                self.add_points(alias_name,current_context,new_point)


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
        
        
        analysis_ty = annonationObject(source_node,self.Import_points,current_context)
        for t in analysis_ty.types:
            self._patch_with_scope(target_nodes,current_context,PointNode(t.type,t.type,'DT'))
            logger.info('[DT]'+t.type)

        for source_name in analysis_ty.names:
            flag_find = False
            if source_name[0] in builtins:
                self._patch_with_scope(target_nodes,current_context,PointNode(source_name[0],source_name[0],'DT'))
                logger.info('[DT]'+source_name[0])
            else:
                need_add_points,_ = self.add_external_edges(source_name,current_context,0,None)
                        
                for add_point in need_add_points:
                    flag_find = True
                    if add_point.point_name.startswith('typing') or add_point.point_name.startswith('collections'):
                        if add_point.point_name in simplified_types:
                            self._patch_with_scope(target_nodes,current_context,PointNode(simplified_types[add_point.point_name].lower(),simplified_types[add_point.point_name].lower(),'DT'))
                            logger.info('[DT]'+simplified_types[add_point.point_name].lower())
                    elif add_point.point_name.endswith('.Any') or add_point.point_name.endswith('.Callable'): 
                        pass
                    else:
                        self._patch_with_scope(target_nodes,current_context,add_point)
                        logger.info('[NoDT]'+add_point.point_name)
                        

                if flag_find == False:
                    call_functions,_ = self.analyze_within(source_name,current_context,None)   
                    if len(call_functions) > 0:
                        for pointTo_ in call_functions:
                            self._patch_with_scope(target_nodes,current_context,pointTo_)
                            logger.info('[NoDT_withIN]'+pointTo_.point_name)
                
                       
    def deal_with_decorator_call(self,params,dispatch_objects,lineno):
        return_objects = []
        for pointTo_ in dispatch_objects:
            if pointTo_.point_type in ('DT','builtin'): 
                if pointTo_.point_name in BUILT_IN_Returns:
                    return_objects.append(PointNode(BUILT_IN_Returns[pointTo_.point_name],BUILT_IN_Returns[pointTo_.point_name],'DT',pointTo_))
                    # continue
                elif pointTo_.point_name in Standard_DataType:
                    return_objects.append(PointNode(pointTo_.point_name,pointTo_.point_name,'DT',pointTo_))
                    # continue
                elif pointTo_.point_name.split('.')[0] in DT_Returns: 
                    if '.'.join(pointTo_.point_name.split('.')[1:]) in DT_Returns[pointTo_.point_name.split('.')[0]]:
                        return_type = DT_Returns[pointTo_.point_name.split('.')[0]]['.'.join(pointTo_.point_name.split('.')[1:])]
                        # print()
                        if return_type != 'none':
                            return_objects.append(PointNode(return_type,return_type,'DT',pointTo_))
                continue
            elif pointTo_.point_name in self.funcs_manager.names:
                an_f_ = pointTo_.point_name
                flag = True
            elif pointTo_.point_name in self.classes_manager.names:
                an_f_ = pointTo_.point_name
                flag = True
            else:
                an_f_ ,flag = get_local_name(pointTo_.point_name,0,self.annotations,self.import_map,'Return')
           

            if flag:

                if an_f_ in self.funcs_manager.names:
                    for para_object in params:
                        dispatch_parameter = an_f_+ '.arg_#0#'+'None'  
                        self.add_dataflow(dispatch_parameter,para_object,para_object.point_name,'valueflow') 

                    if self.funcs_manager.names[an_f_].returns:
                        for res in self.funcs_manager.names[an_f_].returns:  

                            if isinstance(res,dict):  #
                                o = res[tuple(res)[0]]
                                return_objects.append(o)
                            else:
                                if res in self.cls_has_method:  
                                    return_objects.append(PointNode(res,res,'ClsReturn',pointTo_))
                                elif 'Constant#' in res:
                                    return_objects.append(PointNode(res.replace('Constant#',''),res.replace('Constant#',''),'DT',pointTo_))
                                else:
                                    return_objects.append(PointNode(res,res,'FuncReturn',pointTo_)) 
                    else:
                        return_objects.append(PointNode(an_f_,an_f_,'UnknownFuncReturn',pointTo_))  
                
                else:  
                  
                    if an_f_ in self.classes_manager.names:
                        return_objects.append(PointNode(an_f_,an_f_,'ClsReturn',pointTo_))
                    else:
                        return_objects.append(PointNode(an_f_,an_f_,"CrossClsReturn",pointTo_))
                     
            else:  
                return_objects.append(PointNode(an_f_,an_f_,pointTo_.point_type,pointTo_))

        return return_objects
        
    def deal_with_decorators(self,decorator_list,current_context,decorate_site):
     
        params = [PointNode(current_context,current_context,'func')]
        for deco in reversed(decorator_list):            
            if isinstance(deco,ast.Name) and deco.id in ['property','staticmethod','classmethod']:
                continue
            find_objects= self.deal_with_dispatch(deco) 
                
            for o in find_objects:
                if o.origin_from != 'Unknown':
                    if current_context not in self.decorator_relation:
                        self.decorator_relation[current_context] = []
                    self.decorator_relation[current_context].append(o.point_name)
                
                    self.funcs_manager.names[current_context].decos.append(o.point_name)  
            
            params = self.deal_with_decorator_call(params,find_objects,decorate_site) 
    
    
    def visit_FunctionDef(self,node):

        if isinstance(node,ast.Lambda):
            pass  
        else:
            self.scopes.append(node.name)
        
        current_func = self.get_current_context() 
        self.used_ModuleNames[current_func] = {}
        self.Import_points[current_func] = {}
        self.lambda_names[current_func] = []

        parameter_results = {}
        parameter_ = 0

        
        upper_full_name = '.'.join(current_func.split('.')[0:-1])
        for i  in range(len(node.args.args) - len(node.args.defaults)):
            arg = node.args.args[i]
            if arg.annotation:
                self.deal_with_annonations(arg.annotation,[arg.arg])

           
            if arg.arg == 'self' and parameter_ == 0 and self.classes_manager.get(upper_full_name):  #
                pass
            else:
                new_point = PointNode(current_func + '.arg_#'+str(parameter_)+'#'+arg.arg,'','Unknown#P')
                if arg.arg == 'cls' and parameter_ == 0:    #
                    current_cls = '.'.join(current_func.split('.')[0:-1])
                    new_point = PointNode(current_cls,current_cls,'Cls')  #
                
                self.add_points(arg.arg,current_func,new_point)  
                parameter_results[parameter_] = new_point
 
                parameter_ += 1
        
        has_default_num = int(parameter_)
        for arg,value in zip(node.args.args[has_default_num:],node.args.defaults):
            if arg.annotation:
                self.deal_with_annonations(arg.annotation,[arg.arg])
            if arg.arg == 'self' and parameter_ == 0 and self.classes_manager.get(upper_full_name):  #
                pass
            else:
               
                self.deal_with_assign(value,[arg.arg],num=2)  
                
                new_point = PointNode(current_func + '.arg_#'+str(parameter_)+'#'+arg.arg,'','Unknown#P')
                if arg.arg == 'cls' and parameter_ == 0:    #
                    current_cls = '.'.join(current_func.split('.')[0:-1])
                    new_point = PointNode(current_cls,current_cls,'Cls')  #
                
                self.add_points(arg.arg,current_func,new_point)  
                
                parameter_results[parameter_] = new_point
 
                parameter_ += 1

       



        for arg,value in zip(node.args.kwonlyargs,node.args.kw_defaults):

            if arg.arg == 'self' and parameter_ == 0:  
                pass
            else:
                self.deal_with_assign(value,[arg.arg],num=2)  

                new_point = PointNode(current_func + '.arg_#'+str(parameter_)+'#'+arg.arg,'','Unknown#P')
                self.add_points(arg.arg,current_func,new_point)  
                parameter_results[parameter_] = new_point

                parameter_ += 1   

        upper_full_name = '.'.join(current_func.split('.')[0:-1])

        if isinstance(node,ast.Lambda):  
            pass
        else: 
            if upper_full_name in self.funcs_manager.names:
                self.funcs_manager.names[current_func].type = 'nested_func'
                self.funcs_manager.names[upper_full_name].nested.append(current_func)

            self.add_noncall_edges(node.decorator_list,node.lineno,upper_full_name,scene='Call')        
            
            self.deal_with_decorators(node.decorator_list,current_func,node.lineno)  #,'decorator'
        

        self.funcs_manager.names[current_func].params = parameter_results
        self.generic_visit(node)

        if hasattr(node,'returns'):
            
            self.deal_with_annonations(node.returns,[current_func+'<return>'])
    

        if current_func+'<return>' in self.used_ModuleNames[current_func]:
            self.funcs_manager.names[current_func].returns = self.used_ModuleNames[current_func][current_func+'<return>']  
        if current_func+'<return>' in self.Import_points[current_func]:
            self.funcs_manager.names[current_func].returns += self.Import_points[current_func][current_func+'<return>']  
        
        self.global_dataflows[current_func] = self.used_ModuleNames[current_func]
        self.used_ModuleNames.pop(current_func)
        self.Import_points.pop(current_func)
        self.scopes.pop()


    def visit_Return(self, node):

        current_function = self.get_current_context()
        self.add_noncall_edges([node.value],node.lineno) 
        self.deal_with_assign(node.value,[current_function+'<return>'])
        self.generic_visit(node)
    
    def visit_Yield(self,node):
        current_function = self.get_current_context()
        self.add_noncall_edges([node.value],node.lineno)
        self.deal_with_assign(node.value,[current_function+'<return>'])
        self.generic_visit(node)

    def visit_YieldFrom(self,node):
        self.visit_Yield(node)

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

        self.used_ModuleNames[current_context] = {}
        self.Import_points[current_context] = {}
        self.lambda_names[current_context] = []

        self.generic_visit(node)

        self.global_dataflows[current_context] = self.used_ModuleNames[current_context]
        
        
        self.used_ModuleNames.pop(current_context)
        self.Import_points.pop(current_context)
        self.scopes.pop()
        self.self_class.pop()
    
            
    def get_node_name(self,ast_node):
        if isinstance(ast_node,ast.Str):
            return ast_node.s
        elif isinstance(ast_node,str):
            return ast_node
        elif isinstance(ast_node,ast.Attribute):
            return self.get_node_name(ast_node.value) + '.' + ast_node.attr
        elif isinstance(ast_node,ast.Name):
            return ast_node.id

        elif isinstance(ast_node,ast.Subscript):
            return self.get_node_name(ast_node.value)
        else:
            return '<Other>'
    
    
    def add_external_edges(self,full_name_l,current_context,args,site=None,must=False):
        
        def check_same_control_level(control_l1,control_l2):
           
            min_level = min(len(control_l1),len(control_l2))
            control_l1 = control_l1[0:min_level]
            control_l2 = control_l2[0:min_level]

          
            if '.'.join(control_l1[0:-1]) == '.'.join(control_l2[0:-1]): 
                if 'With' in control_l1[-1] or 'With' in control_l2[-1]:
                    pass
                else:
                    current_special_item,current_line = control_l1[-1].split('#')
                    point_special_item,point_line = control_l2[-1].split('#')
                    if current_line == point_line:
                        if (current_special_item == 'If' and point_special_item == 'Else') or (current_special_item == 'Else' and point_special_item == 'If'):
                           
                            return True
            return False
      

        if isinstance(full_name_l,CallNode):
            full_name = full_name_l.ns.replace(full_name_l.scope+'.','')
            sym_type = 'Call'
        else:
            full_name,sym_type = full_name_l
        if full_name == 'self':
            return [],[]
        search_targets = [[self.used_ModuleNames,'IntraLevel'],[self.Import_points,'ImportLevel']]
        all_find_edge = []
        return_disps = []
     
        for [search_scope,scope_level] in search_targets:      
            for module_context in search_scope:
                if module_context not in current_context:  
                    continue
                all_used_modules = search_scope[module_context]
                for module_name in all_used_modules:
                    if self.only_inlude(module_name,full_name):  
                        
                        call_function = full_name.replace(module_name,'',1)
                        for pointTo_ in all_used_modules[module_name]:
                            API_name =tuple(pointTo_)[0] + call_function
                            node_old = pointTo_[tuple(pointTo_)[0]]
                            point_control = node_old.control
                            if len(self.special_items) > 0 and len(point_control) > 0:
                                point_control = point_control.split('.')
                                if check_same_control_level(self.special_items,point_control):
                                    continue
                          
                           
                            point_type = node_old.point_type  
                            match_type = 'Partial'
                            if module_name == full_name:
                                match_type = 'Exact'
                            
                            new_point = PointNode(API_name,API_name,point_type,node_old)

                            new_point.origin_from = scope_level
                            new_point.match=match_type

                            all_find_edge.append(new_point)
                            return_disps += self.add_edge(current_context,new_point,args,site,sym_type,must=must) 
                                                        
                            if len(self.special_items) > 0 and 'With' in self.special_items:
                                for methodname in ("__enter__", "__exit__"):
                                    name = API_name+'.{}'.format(methodname)
                                    new_point_ = PointNode(name,name,point_type)
                                    new_point.origin_from = scope_level
                                    self.add_edge(current_context,new_point_,args,site)
                           
                        
                      
                        if module_name == full_name: 
                            break
        
        return all_find_edge,return_disps

    def adds(self,data_origin,current_context,scene):
        if isinstance(data_origin,ast.Call) and scene == 'attribute':  
            return
        
        find_objects = self.deal_with_dispatch(data_origin)
        for o in find_objects:
            if o.origin_from != 'Unknown':
                if o.point_type in ['builtin','DT']:
                    continue    
                if 'arg_#' in o.point_name and scene not in  ['Call','Iter']:   
                    continue                
                self.add_edge(current_context,o,0,data_origin.lineno,scene)  
                if len(self.special_items) > 0 and 'With' in self.special_items:
                    for methodname in ("__enter__", "__exit__"):
                        new_point = PointNode(o.point_name + '.{}'.format(methodname),o.point_name + '.{}'.format(methodname),'Method')
                        self.add_edge(current_context,new_point,0,data_origin.lineno,scene)
               

    def add_noncall_edges(self,nodes,site,current_context=None,scene='attribute'):
        
        if scene not in  ['Call','Iter']  and self.benchmark != 'dynamic':
            return
        #
        if current_context == None:
            current_context = self.get_current_context()
        for no in nodes:
            # if isinstance
            if isinstance(no,ast.Name):
                if no.id in ['staticmethod','classmethod']: 
                    pass
                elif no.id in ['abstractmethod']:
                    # 抽象基类
                    cls_full_name = '.'.join(current_context.split('.')[0:-1])
                    if cls_full_name in self.inherited_map:
                        self.inherited_map[cls_full_name].append('abc.ABC')  
                elif scene in ['Call','Iter']:
                    self.adds(no,current_context,scene) 
            else:
                if isinstance(no,ast.keyword):
                    self.adds(no.value,current_context,scene)  #
                if isinstance(no,ast.Dict): #
                    for dict_value in no.values:
                        self.adds(dict_value,current_context,scene)
                    for dict_keys in no.keys:
                        self.adds(dict_keys,current_context,scene)
                elif isinstance(no,ast.List): #
                    for list_value in no.elts:
                        self.adds(list_value,current_context,scene)
                elif isinstance(no,ast.Set): #
                    for list_value in no.elts:
                        self.adds(list_value,current_context,scene)
                elif isinstance(no,ast.ListComp) or isinstance(no,ast.SetComp) or isinstance(no,ast.GeneratorExp): #
                    self.adds(no.elt,current_context,scene)
                elif isinstance(no,ast.DictComp):
                    self.adds(no.key,current_context,scene)
                    self.adds(no.value,current_context,scene)
                elif isinstance(no,ast.Tuple): #
                    for tuple_value in no.elts:
                        self.adds(tuple_value,current_context,scene)
                elif isinstance(no,ast.BoolOp): 
                    for v in no.values:
                        self.adds(v,current_context,scene)
                elif isinstance(no,ast.BinOp):
                    self.adds(no.left,current_context,scene)
                    self.adds(no.right,current_context,scene)
                elif isinstance(no,ast.Compare):
                    self.adds(no.left,current_context,scene)
                elif isinstance(no,ast.IfExp):
                    self.adds(no.test,current_context,scene)
                    self.adds(no.body,current_context,scene)
                    self.adds(no.orelse,current_context,scene)
                elif isinstance(no,ast.Subscript): 
                    self.adds(no.value,current_context,scene)
                    self.adds(no.slice,current_context,scene)
                elif isinstance(no,ast.ExceptHandler):
                    self.adds(no.type,current_context,scene)
                else:
                    self.adds(no,current_context,scene)

    def get_all_parent_class(self,all_start_class):  
        all_parent_names = []
        for sc in all_start_class:
            if sc in self.inherited_classes:
                all_parent_names = self.inherited_classes[sc]   
                full_names = self.inherited_classes[sc]
                while len(full_names) > 0:
                    new_parent_names = []
                    for parent in full_names:
                        if parent in self.inherited_classes:
                            new_parent_names += self.inherited_classes[parent] 
                    full_names = new_parent_names 
                    all_parent_names += new_parent_names
        return all_parent_names
    
    def visit_AsyncWith(self,node):
        self.visit_With(node)

    def visit_While(self, node) :
        self.generic_visit(node)

    def visit_For(self,node):
    
        self.special_fors.append('For')     
        self.deal_with_assign(node.iter,[node.target],num=3)  
        self.add_noncall_edges([node.iter],node.lineno,None,'Iter') 
        self.visit(node.iter) 
        self.special_fors.pop()
        self.visit(node.target)
        for smt in node.body:
            self.visit(smt)
        
    
    def visit_AsyncFor(self,node):
        self.visit_For(node)

    def extractCondition(self,node,inverse=1):
    
        # type(x) == y
        if (type(node) == ast.Compare and type(node.left) == ast.Call and type(node.left.func) == ast.Name 
            and node.left.func.id == "type" and len(node.left.args) == 1 and len(node.ops) == 1 and type(node.ops[0]) in [ast.Eq, ast.NotEq]
            and len(node.comparators) == 1 and type(node.comparators[0]) in [ast.Name, ast.Attribute]):
  
            typestr = nameTostr(node.comparators[0])
            if typestr in stdtypes["overall"]:
                typeobject = typeObject(inputtypemap[typestr.lower()], True)
            else:
                typeobject = typeObject(typestr, 2)
            if type(node.ops[0]) == ast.NotEq:
                inverse = inverse * -1  
            if inverse == 1:
                if typeobject.type != 'None':
                    # map typestr to the actual object
                    currenct_c = self.get_current_context()
                    return_cs = self.search_for_definition([typeobject.type,'Var'],currenct_c)
                    for p in return_cs:
                        self._patch_with_scope([node.left.args[0]],currenct_c,p)

        
        # x is y
        elif (type(node) == ast.Compare and (type(node.left) == ast.Name or type(node.left) == ast.Attribute) and len(node.ops) == 1
            and type(node.ops[0]) in [ast.Is, ast.IsNot] and len(node.comparators) == 1 and type(node.comparators[0]) in [ast.Name, ast.Attribute, ast.Constant]):
            
            if type(node.comparators[0]) == ast.Constant:
                typeobject = transferConstant(node.comparators[0])
            else:
                typestr = nameTostr(node.comparators[0])
                if typestr in stdtypes["overall"]:
                    typeobject = typeObject(inputtypemap[typestr.lower()], True,'DT') 
                else:
                    typeobject = typeObject(typestr, False)
            if type(node.ops[0]) == ast.IsNot:
                inverse = inverse * -1
            if inverse == 1:
                if typeobject.type != 'None':
                    # map typestr to the actual object
                    currenct_c = self.get_current_context()
                    return_cs = self.search_for_definition([typeobject.type,'Var'],currenct_c)
                    for p in return_cs:
                        self._patch_with_scope([node.left],currenct_c,p)

            
            
        # isinstance(x,y)
        elif (type(node) == ast.Call and type(node.func) == ast.Name and node.func.id == "isinstance"
            and len(node.args) == 2 and type(node.args[1]) in [ast.Name, ast.Attribute]):
        
            typestr = nameTostr(node.args[1])
            if typestr in stdtypes["overall"]:
                typeobject = typeObject(inputtypemap[typestr.lower()], True,'DT')
            else:
                typeobject = typeObject(typestr, 2)
            if inverse == 1:
                if typeobject.type != 'None':
                    currenct_c = self.get_current_context()
                    return_cs = self.search_for_definition([typeobject.type,'Var'],currenct_c)
                    for p in return_cs:
                        self._patch_with_scope([node.args[0]],currenct_c,p)


  
    def visit_If(self,node):
        

        self.special_items.append('If#'+str(node.lineno))
        self.extractCondition(node.test)
        self.add_noncall_edges([node.test],None)  
        self.visit(node.test)

        for stmt in node.body:
            if isinstance(stmt,(ast.ClassDef,ast.FunctionDef,ast.If)):
                self.visit(stmt) 
            else:
                self.visit(stmt) 
                self.generic_visit(stmt) 
        self.special_items.pop()
        self.special_items.append('Else#'+str(node.lineno))
        for stmt in node.orelse:
            if isinstance(stmt,(ast.ClassDef,ast.FunctionDef,ast.If)):
                self.visit(stmt) 
            else:
                self.visit(stmt) 
                self.generic_visit(stmt) 
 
        self.special_items.pop()

    def visit_Raise(self,node):
    
        self.add_noncall_edges([node.exc,node.cause],None,scene='Call')  

        self.generic_visit(node)

    def visit_Try(self,node):

        for handler in node.handlers:
            self.deal_with_assign(handler.type,[handler.name])
        self.generic_visit(node)
      
    def visit_Global(self,node):
        self.generic_visit(node)
    def visit_Nonlocal(self, node):
        self.generic_visit(node)
    def visit_Expr(self, node):
        self.generic_visit(node)

    def visit_Assert(self,node):
        self.add_noncall_edges([node.test,node.msg],None,scene='Call')
        self.generic_visit(node)
     
    def visit_With(self, node):
     

        self.special_items.append('With')
        for withitem in node.items:
            expr = withitem.context_expr
            vars = withitem.optional_vars
            # TODO:
            #
            if isinstance(expr,ast.Name): 
                self.adds(expr,self.get_current_context(),'Call') 
            else:
                self.add_noncall_edges([expr],None,scene='Call')  


            self.visit(expr)
            if vars is not None:
                if isinstance(vars, ast.Name):
                    self.deal_with_assign(expr,[vars])  
                else:
                    self.visit(vars) 
        self.special_items.pop()  
        for stmt in node.body:
            self.visit(stmt)

    
    def get_inherited_(self,cls_name,method_remain_first):

        add_inherited = set()
        implementation_class = []
        add_implementations = set()
       
        implementation_class= get_implementation_class(cls_name,self.inherited_map) 
        all_parent_cls_ = get_all_parent_class(cls_name,self.inherited_map,self.annotations)

      
        method_name = method_remain_first.strip('.')
        for add_par_cls in all_parent_cls_:
            if add_par_cls in self.cls_has_method and method_name in self.cls_has_method[add_par_cls]:
                # if self.check_function_signature(args,self.cls_has_method[add_par_cls][method_name]):
                    inherited_edge = add_par_cls+method_remain_first
                    add_flag = True
                    
                    if add_flag == True:
                        #if self.invalid_property_function(inherited_edge,scene):  
                            #   print('filter',inherited_edge)
                        #else:
                            add_inherited.add(inherited_edge)
                            
                        
                    break
    
        for add_implemente_cls in implementation_class:
            
            if add_implemente_cls in self.cls_has_method and method_name in self.cls_has_method[add_implemente_cls]:
                implement_edge = add_implemente_cls+method_remain_first
                #if self.invalid_property_function(implement_edge,scene):  
                #    print('filter',implement_edge)
                #else:
                if 1:
                    add_implementations.add(implement_edge)
            

        if len(add_inherited) > 0:
            return add_inherited
        else:
            if len(add_implementations)> 0:
                return add_implementations
            else:
                return []


    def is_special_for(self):
        if len(self.special_fors) > 0 and self.special_fors[-1] == 'For':
            return True
        return False

    def analyze_within(self,full_name_l,current_context,args,callsite=None,must=False):  
    
        if isinstance(full_name_l,CallNode):
            full_name = full_name_l.ns.replace(full_name_l.scope+'.','')
            sym_type = 'Call'
        else:
            full_name,sym_type = full_name_l

        return_disps = []
        callee_functions  = []
        max_match_within_function = None
        new_points = []
        if full_name == 'self':
            current_cls = self.self_class[-1]
            current_self = current_context[0:current_context.rindex(current_cls)+len(current_cls)]
            max_match_within_function = [current_self,'Cls']
            new_point = PointNode(max_match_within_function[0],max_match_within_function[0],max_match_within_function[1])._set('context','Self')._set('match','Exact')
            new_points.append(new_point)

        if 'self.' in full_name:
            current_cls = self.self_class[-1]  
            current_self = current_context[0:current_context.rindex(current_cls)+len(current_cls)]
            
            
            if current_self + full_name.replace('self','',1) in self.funcs_manager.names:
                max_match_within_function = [current_self + full_name.replace('self','',1),'Method']  
               

            else:
                inherited_ =  self.get_inherited_(current_self,full_name.replace('self','',1))
                if len(inherited_) > 0:
                    if len(inherited_) == 1:  
                        max_match_within_function = [list(inherited_)[0],'Method']
                    else:
                        max_match_within_function = [current_self + full_name.replace('self','',1),'Unknown'] 
                else:
                    all_parent_cls_ = get_all_parent_class(current_self,self.inherited_map,self.annotations)  
                    method_name = full_name.replace('self.','',1)
                    for cls_name in [current_self] + all_parent_cls_:
                        the_cls = self.classes_manager.names.get(cls_name)
                        if the_cls and method_name in the_cls.properties:
                            points_ = the_cls.properties[method_name].points
                            if points_:  
                                for po in points_:
                                    if 'Constant#' in po:
                                        po = po.replace('Constant#','')
                                        new_points.append(PointNode(po,po,'DT')) 
                                    else:
                                        new_points.append(PointNode(po,po,'Unknown')) 
                            break 


            if max_match_within_function:
                new_point = PointNode(max_match_within_function[0],max_match_within_function[0],max_match_within_function[1])._set('context','Self')
                new_points.append(new_point)
            else:
                if len(new_points) == 0:
                    return [],[]  


        else:
          
            if len(full_name.split('.')) > 1: 
                possible_class = full_name.split('.')[0]
                for within_class in self.classes_manager.names:
                    if possible_class == within_class.split('.')[-1]:  
                        max_match_within_function = [within_class + full_name.replace(possible_class,'',1) ,'Method'] 
                        new_point = PointNode(max_match_within_function[0],max_match_within_function[0],max_match_within_function[1])
                        new_points.append(new_point)
                
                    
        if len(new_points) > 0:
            
            for new_point in new_points:
                callee_functions.append(new_point)
                return_disps += self.add_edge(current_context,new_point,args,callsite,sym_type,must=must) 
           
            if len(self.special_items) > 0 and 'With' in self.special_items:
                for methodname in ("__enter__", "__exit__"):
                    name = new_point.point_name+'.{}'.format(methodname)
                    add_new_point = PointNode(name,name,'Unknown')
                    self.add_edge(current_context,add_new_point,args,callsite)
        else:
            
            match_callers,match_type = self.map_within_file(full_name,self.current_rel_filename.replace('.__init__',''))
            if match_callers:
                if isinstance(match_callers,str):
                    match_callers = [match_callers]
                for obj_name in match_callers:
                    new_point = PointNode(obj_name,obj_name,'Func')._set('match',match_type) 

                    callee_functions.append(new_point)
                    return_disps += self.add_edge(current_context,new_point,args,callsite,sym_type,must)

             
                    if len(self.special_items) > 0 and 'With' in self.special_items:
                        for methodname in ("__enter__", "__exit__"):
                            add_new_point = PointNode(obj_name + '.'+methodname,obj_name + '.'+methodname,'Method')
                            self.add_edge(current_context,add_new_point,args,callsite)
           

        return callee_functions,return_disps


    def get_call_name(self,ast_node):
        call_functions = []
        if isinstance(ast_node,ast.Attribute):
            call_functions = [ast_node.attr]  
            now_attrName = ast_node
            while isinstance(now_attrName,ast.Attribute):
                if isinstance(now_attrName.value,ast.Call):
                    call_functions.append(now_attrName.value)
                now_attrName = now_attrName.value
        return call_functions  

    def get_onlyattrs(self,attr_node):
        if not isinstance(attr_node,ast.Attribute):
            return False
        if isinstance(attr_node,ast.Attribute):
            full_attrName = [attr_node.attr]
            now_attrName = attr_node.value
            while isinstance(now_attrName,ast.Attribute):
                full_attrName.append(now_attrName.attr)
                now_attrName = now_attrName.value
                if not isinstance(now_attrName,(ast.Attribute,ast.Name)):
                    return False
            if isinstance(now_attrName,ast.Name):
                full_attrName.append(now_attrName.id)

            full_attrName = reversed(full_attrName)

            return '.'.join(full_attrName)

    def deal_with_dispatch(self,ast_node):
        
        if ast_node == None:
            return []
        
        current_context = self.get_current_context()
     

        if isinstance(ast_node,ast.Subscript):
            find_objects = self.deal_with_dispatch(ast_node.value)
            
        elif isinstance(ast_node,ast.Starred):
            find_objects = self.deal_with_dispatch(ast_node.value)
        elif isinstance(ast_node,ast.Attribute):
            find_objects = []
            find_objects_attr = self.deal_with_attribute(ast_node)
            for o in find_objects_attr:
                if o.origin_from== 'Unknown':
                    search_object = o.point_name
                    tmp = self.search_for_definition([search_object,'Attr'],self.get_current_context()) 
                    find_objects += tmp
                else:
                    find_objects.append(o)

        elif isinstance(ast_node,ast.Name): 
            search_object = ast_node.id
            find_objects = []
            find_objects_names = self.search_for_definition([search_object,'Var'],self.get_current_context()) 
            
            for o in  find_objects_names:
                if o.origin_from== 'Unknown':  
                    if o.point_name == 'self':
                        current_cls = self.self_class[-1]
                        current_self = current_context[0:current_context.rindex(current_cls)+len(current_cls)]
                        o.point_name = current_self
                        o.point_type = 'Cls'
                        o.origin_from = 'IntraLevel'
                        o.context = 'True'
                if o.match != 'Exact' and o.context != 'True':
                    print('impossible')
                    print(o.point_name)
                    import sys
                    sys.exit(1)
                find_objects.append(o) 


        elif isinstance(ast_node,ast.Call): 
            find_objects = self.deal_with_call(ast_node)

        elif isinstance(ast_node,ast.Lambda):
            find_objects = self.deal_with_lambda(ast_node)  
        else:
            
            return []
        

        return find_objects

    def istype_point(self,point):
        if point in self.cls_has_method:
            return 'Cls'
        if '.'.join(point.split('.')[0:-1]) in self.cls_has_method:
            return 'Method'

        return 'Func'

    def handle_inner_attribute(self,o):
        fql = o.point_name
        attr = fql.split('.')[-1]
        if attr == '__class__':
            o.point_name = '.'.join(fql.split('.')[0:-1])    
            return o
        elif attr == '__module__':
           
            o.point_name = 'str'  
            o.point_type = 'DT'
            return o
       
        elif attr == '__self__':
            o.point_type = 'Cls'
            tmp = fql.split('.')
            for i in range(len(tmp)):
                f_name = '.'.join(tmp[0:i+1])
                if f_name in self.cls_has_method:
                    o.point_name = f_name
                    return o
        return o
            

    def deal_with_attribute(self,attr_node):
        if not isinstance(attr_node,ast.Attribute):
            return []
        if isinstance(attr_node.value,ast.Str):
            find_objects = [PointNode('str','str','DT')]
        elif isinstance(attr_node.value,ast.List):
            find_objects = [PointNode('list','list','DT')]
        elif isinstance(attr_node.value,ast.Num):
            find_objects = [PointNode('num','num','DT')]
        elif isinstance(attr_node.value,ast.Set):
            find_objects = [PointNode('set','set','DT')]
        elif isinstance(attr_node.value,ast.Dict):
            find_objects = [PointNode('dict','dict','DT')]
        else:
                
            if isinstance(attr_node.value,ast.Name):
                search_object = attr_node.value.id
                find_objects = self.search_for_definition([search_object,'Var'],self.get_current_context()) 
            elif isinstance(attr_node.value,ast.Subscript):
                find_objects = self.deal_with_dispatch(attr_node.value.value)  
            elif isinstance(attr_node.value,ast.Call):
            
                find_objects = self.deal_with_call(attr_node.value)
                
            elif isinstance(attr_node.value,ast.Attribute):
                if self.get_onlyattrs(attr_node.value):  
                    search_object = self.get_onlyattrs(attr_node.value)
                    find_objects = self.search_for_definition([search_object,'Attr'],self.get_current_context()) 
                    if len(find_objects) == 0: 
                        find_objects = self.deal_with_attribute(attr_node.value)
                else:
                    find_objects = self.deal_with_attribute(attr_node.value)
                
            else:
                return []  
            
            

        full_names = []
        if find_objects == None:
            return []
        
        

        for o in find_objects:
            if o.point_name == 'None' or o.point_name == None: 
                continue 
            if o.point_name in DT_Returns:
                if attr_node.attr not in DT_Returns[o.point_name]:  
                    continue
            copy_ = o.origin_from.strip()
            if o.origin_from != 'Unknown':
                o.origin_from =  'Attribute'
                o = self.handle_inner_attribute(o)  
                if 'Return' in o.point_type:
                    pass
                else:
                    self.add_edge(self.get_current_context(),o,0,attr_node.lineno,'attribute')
                o.origin_from = copy_.strip()
                _,func_flag = get_local_name(o.point_name,0,self.annotations,self.import_map,'Return')
                
                if func_flag:
                    if o.point_name in self.cls_has_method:
                        o.point_name = '.'.join([o.point_name,attr_node.attr])
                        o.full_qualify_name = o.point_name
                        o = self.handle_inner_attribute(o)
                        o.match = 'Partial'
                        full_names.append(o)   
                    
                    else:                        
                        return_objects = self.get_return_value([o],[],[],attr_node.lineno)
                        for return_o in return_objects:
                            
                            return_o.point_name = '.'.join([return_o.point_name,attr_node.attr])
                            return_o.full_qualify_name = return_o.point_name
                            return_o = self.handle_inner_attribute(return_o)
                            return_o.match = 'Partial'
                            full_names.append(return_o)               
                    
                else:
                    
                    o.point_name = '.'.join([o.point_name,attr_node.attr])
                    o.full_qualify_name = o.point_name  
                    o = self.handle_inner_attribute(o)
                    o.match = 'Partial'
                    full_names.append(o) 
                    
                    
            else:
                
                o.point_name = '.'.join([o.point_name,attr_node.attr])
                o.full_qualify_name = o.point_name
                
              
                o = self.handle_inner_attribute(o)
                o.match = 'Partial'
                full_names.append(o)  

        return full_names
            

    def visit_Attribute(self, attr_node):
        while(1):
            if isinstance(attr_node,ast.Attribute):
                if isinstance(attr_node.value,ast.Call):
                    self.visit(attr_node.value)
                attr_node = attr_node.value
            else:
                break
    
    def deal_with_argument(self,args):
        results = {}
        i = 0
        for arg in args['args']:
            find_objects = self.deal_with_dispatch(arg)  
            results[i] = (find_objects,None) 
            i += 1
            
        for kw in args['kws']:
            find_objects = self.deal_with_dispatch(kw.value)  
            if isinstance(kw.arg,ast.Name):
                dispatch_parameter = kw.arg.id  
            elif isinstance(kw.arg,str):
                dispatch_parameter = kw.arg 
            else:
                dispatch_parameter = None

            results[i] = (find_objects,dispatch_parameter)
            i = i + 1
        return results
    
    def deal_with_ParamArgs(self,current_context,node,points_to):  
        
       
        name = self.get_node_name(node.func)  

        if name == None:
           
            key_ = current_context+'.'+'None'  
        else:
            key_ = current_context+'.'+ name


        New_call = CallNode(key_,current_context,self.current_rel_filename.replace('.__init__',''),node.lineno)
        New_call.setPos(node.lineno,node.end_lineno,node.col_offset,node.end_col_offset)
        New_call.args = self.deal_with_argument({'args':node.args,'kws':node.keywords})
       
        
        for tar in points_to:
            if isinstance(tar,str):
                New_call.type = tar
            elif isinstance(tar,list):
                New_call.point_to.append(tar)
         

        self.calls_manager.add(New_call)  
        
    def visit_Call(self,node):
        current_context = self.get_current_context()
        if self.calls_manager.if_visit(current_context,node):
            return 

        lineno = node.lineno
        args = node.args
        arg_kws = node.keywords
        all_call_names = []
        if isinstance(node.func,ast.Attribute):  
            funcs = self.get_call_name(node.func)
            if len(funcs) > 1: 
                first_call = funcs[-1]
                last_call = funcs[0]
                if len(funcs) == 2 and self.get_node_name(first_call.func) == 'super' and first_call.args == [] and first_call.keywords == []:
                    current_cls_name = self.self_class[-1]
                    cls_name = current_context[0:current_context.rindex(current_cls_name)+len(current_cls_name)]  
                   
                    if cls_name in self.inherited_map:
                
                        all_parent_cls_ = get_all_parent_class(cls_name,self.inherited_map,self.annotations)
                        func_name = self.get_node_name(last_call)
                        for add_par_cls in all_parent_cls_:
                            if add_par_cls in self.cls_has_method:
                                if add_par_cls+'.'+func_name in self.funcs_manager.names:
                                    inherited_edge = add_par_cls + '.' +func_name
                                    flag_edge = True
                                else:
                                    inherited_edge,flag_edge = get_local_name(add_par_cls+'.'+func_name,{'args':len(node.args)+len(node.keywords)},self.annotations)
                                if flag_edge: 
                                   
                                    new_point = PointNode(inherited_edge,inherited_edge,'Method')  
                                    return_d = self.add_edge(current_context,new_point,0,lineno)
                                    self.deal_with_ParamArgs(current_context,node,return_d) 
                                    break
                    else:
                        class_sc = None
                        for sc in reversed(self.scopes):
                            if sc in self.inherited_classes:  
                                class_sc = sc
                                break

                        all_parent_names = self.get_all_parent_class([class_sc])

                        func_name = self.get_node_name(last_call)
                        
                        for candidate_class in all_parent_names:
                            all_call_names.append(candidate_class+'.'+ func_name)
                else:
                    call_name = self.deal_with_attribute(node.func)  
                    
                    for o in call_name:    
                       
                            if o.origin_from == 'Unknown':
                                all_call_names.append(o.point_name)
                            else:
                                
                                return_d = self.add_edge(self.get_current_context(),o,0,lineno,must=True)  
                                self.deal_with_ParamArgs(current_context,node,return_d)  
                      


            else: 
                call_name = self.deal_with_attribute(node.func)
                for o in call_name:
                    if o.origin_from == 'Unknown':
                        all_call_names.append(o.point_name)
                    else:
                        return_d = self.add_edge(current_context,o,0,lineno,must=True)  
                        self.deal_with_ParamArgs(current_context,node,return_d) 

        elif isinstance(node.func,ast.Call): 
            find_objects = self.deal_with_call(node.func)
            for o in find_objects:
                return_d = self.add_edge(current_context,o,0,lineno,must=True) 
                self.deal_with_ParamArgs(current_context,node,return_d) 
        
        else:
            
            full_name = self.get_node_name(node.func)
            all_call_names.append(full_name)


        flag_external = False
       
        for full_name in all_call_names:
            
            
            if full_name == None:                
                continue

            New_call = CallNode(current_context + '.' + full_name,current_context,self.current_rel_filename.replace('.__init__',''),lineno)
            New_call.setPos(node.lineno,node.end_lineno,node.col_offset,node.end_col_offset)

            if full_name in BUILT_IN_FUNCTIONS or (full_name == 'super' and node.args == [] and node.keywords == []):
                New_call.ns =  New_call.scope.split('.')[0] + '.<builtin>.' + full_name 
                New_call.type = 'builtin'

        
            New_call.args = self.deal_with_argument({'args':node.args,'kws':node.keywords})
            
            if New_call.type == 'builtin':
                if current_context not in self.reachable_edges:
                    self.reachable_edges[current_context] = set()
                if New_call.ns not in self.reachable_edges[current_context]:
                    self.reachable_edges[current_context].add(New_call.ns)
                if New_call.ns.endswith('.<builtin>.iter'):
                    if len(New_call.args) == 1:
                        for arg_point in New_call.args[0][0]: 
                            if arg_point.point_name in self.cls_has_method:
                                if '__iter__' in self.cls_has_method[arg_point.point_name]:
                                    self.reachable_edges[current_context].add(arg_point.point_name+'.__iter__')
                
                if New_call.ns.endswith('.<builtin>.next'):
                    if len(New_call.args) == 1:
                        for arg_point in New_call.args[0][0]:
                            if arg_point.point_name in self.cls_has_method:
                                if '__next__' in self.cls_has_method[arg_point.point_name]:
                                    self.reachable_edges[current_context].add(arg_point.point_name+'.__next__')

            else:
                all_find_edge,result_disp = self.add_external_edges(New_call,current_context,{'args':node.args,'kws':node.keywords},lineno,must=True)
                for tar in result_disp:
                    if isinstance(tar,str):
                        New_call.type = tar
                    elif isinstance(tar,list):
                        New_call.point_to.append(tar)

                if len(all_find_edge) == 0:  
                    call_functions,result_disp = self.analyze_within(New_call,current_context,{'args':node.args,'kws':node.keywords},lineno,must=True)  
                    for tar in result_disp:
                        if isinstance(tar,str):
                            New_call.type = tar
                        elif isinstance(tar,list):
                            New_call.point_to.append(tar)
                
       
            self.calls_manager.add(New_call)  

        self.visit(node.func)  
        for arg in node.args:  
            self.visit(arg)
        for kw in node.keywords:
            self.visit(kw)
        
    
        self.add_noncall_edges(node.args+node.keywords,node.lineno)  

