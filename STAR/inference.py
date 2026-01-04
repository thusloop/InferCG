
from invoke_local import get_cls_method
import inspect
import json
from queue import Queue
from invoke_local import get_local_name,Standard_Libs,BUILT_IN_FUNCTIONS



def get_prefix(edg,mode):
            
    edg_level,edg = edg.split('@')
    flag_method = 0
    if 'arg_#' in edg:
        function_name = []
        function_context = []
        for tmp in edg.split('.'):
            if 'arg_#' in tmp:
                flag_method = 1
                function_context.append(tmp)
                continue
            if flag_method:
                function_name.append(tmp)
            else:
                function_context.append(tmp)

        function_context = '.'.join(function_context)
        if len(function_name) > 0:
            function_name = (function_name[0],edg_level)  
        else:
            function_name = ('',edg_level)
       
    else:  
        if mode == 3:
            function_context = '.'.join(edg.split('.')[0:-1])
            function_name = (edg.split('.')[-1],edg_level)
            if function_context in Standard_Libs or function_context in BUILT_IN_FUNCTIONS:
                 function_context = False
                 function_name = False
        else:
            function_context = False
            function_name = False
    
    return function_context,function_name




def get_closure(pair,search_l): #TODO
    def judge_equal(b,equals):
        tmp = b.strip()
        if 'Unknown@' in b:
            tmp = b.split('@')[2]
        
        for pairs in equals:
            if tmp in pairs:
                return True
        return False
    def add_equals(a,b,equals):
        for pairs in equals:
            if a in pairs or b in pairs:
                pairs.add(b)
                pairs.add(a)
                return equals
        equals.append(set([a,b]))
        
    paras = []
    pairs = Queue()
    pairs.put(pair)
    new_edges = []
    first_ = 0
    equals = [] 

    scopes = set()
    while(not pairs.empty()):
        
        a,b = pairs.get()
        if judge_equal(b,equals):
            continue
   
        for callers_ori in search_l.keys():
            
            if 'arg_#' not in callers_ori or 'arg_#' not in b:
                continue
            if b.rsplit('#',2)[2] == 'None' or callers_ori.rsplit('#',2)[2] == 'None':
                
                if not callers_ori.startswith(b.rsplit('#',1)[0]) or len(callers_ori.split('.')) != len(b.split('.')):
                    continue
            else:
                if (not callers_ori.startswith(b.rsplit('#',2)[0])):
                    continue
                else:
                    if callers_ori.split('#',2)[-1] != b.split('#',2)[-1]:
                        continue
            
            add_equals(callers_ori,b,equals) 

            paras.append(callers_ori)  
    
            for point in search_l[callers_ori]:
                scopes.add(point.scope) 
                if 'Unknown@' in point.ns or 'arg_#' in point.ns:
                    if 'Unknown@' in point.ns:
                        if callers_ori != point.ns.split('@')[2]:
                            pairs.put((callers_ori,point.ns.split('@')[2]))  
                    else:
                        pairs.put((callers_ori,point.ns))  #
                else:                  
                    new_edges.append((callers_ori,point))
                    
    return new_edges,scopes


def inference(pro,processor,annotations,to_file,mode=3):
    
    unknown_edge = {}
    new_edge = {}
    
    collections_unknown_points = {}
    pass_argument_parameter = {}

    map_attr_cls = {}
    reachable_edges = processor.reachable_edges
    dataflows = processor.data_flows
    for caller,calls in reachable_edges.items():
        if caller == None:
            continue
        if 'arg_#' not in caller:
            new_edge[caller] = []

        for callee in calls:
            if  'Unknown@' in callee:
                
                function_context,function_name = get_prefix(callee.replace('Unknown@',''),mode)
                
                if function_context not in unknown_edge:
                    unknown_edge[function_context] = set()

                unknown_edge[function_context].add(caller)
                if function_context and function_context != 'None':    
                    if '.arg_#' in function_context: 
                        if function_context not in collections_unknown_points:
                            collections_unknown_points[function_context] = set()

                        collections_unknown_points[function_context].add(function_name)
                        
            else:
                if caller in new_edge:
                    if callee in processor.classes_manager.names:
                        continue
                    if len(callee.split('.')) == 1:
                        continue
                    new_edge[caller].append(callee)
                    callee_func = processor.funcs_manager.get(callee)
                    if callee_func:
                        callee_func_nested = callee_func.nested
                        for ad in callee_func_nested:
                            if ad in processor.decorator_relation:
                                for ad_func in processor.decorator_relation[ad]:
                                    new_edge[caller].append(ad_func)

    
   
    new_collections_unknown_points = collections_unknown_points.copy()

    for prefix,_ in new_collections_unknown_points.items():
        point_objects,scopes_s = get_closure((None,prefix),dataflows)
        if len(point_objects) == 0:
            continue
        callers = unknown_edge[prefix]
        for caller in callers:
            for call in reachable_edges[caller]:
               
                if 'Unknown@' in call:
                    call = call.split('@')[2]
                else:
                    continue
              
                if call.startswith(prefix): 
                    for c,point_object in point_objects:
                        
                        callee = call.replace(prefix,point_object.ns)
                        if point_object.ns in BUILT_IN_FUNCTIONS or point_object.ns in ['None','True','False']: 
                            continue
                        if 'Unknown@' not in callee:
                            if callee not in reachable_edges[caller]:
                                if callee.split('.')[-1] != '__init__':
                                    callee = callee.replace('.__init__','')
                                callee,flag = get_local_name(callee,None,annotations,processor.import_map,'Return')  

                               
                                if flag:
                                    if processor.funcs_manager.get(point_object.ns) and caller not in scopes_s and len(processor.funcs_manager.get(point_object.ns).decos) == 0: 
                                        
                                        pass
                                    else:
                                            if prefix in collections_unknown_points:
                                                collections_unknown_points.pop(prefix)
                                            if callee in processor.classes_manager.names:  
                                                if point_object and point_object.point_.context == 'iter':
                                                    if '__next__' in processor.cls_has_method[callee]:
                                                        new_edge[caller].append(callee +'.__next__') 
                                                    if '__iter__' in processor.cls_has_method[callee]:
                                                        new_edge[caller].append(callee +'.__iter__') 
                                                continue
                                            new_edge[caller].append(callee)                        
    
    with open(to_file,'w') as f:
        json.dump(new_edge,f,indent=4)

   