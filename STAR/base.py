
import copy
class CallManager:
    def __init__(self):
        self.names = {}
        self.calls_by_location = {}  

    def add(self,newcall,mode='remove'): 
        if newcall.ns  not in self.names:  
            self.names[newcall.ns] = []

    
        self.names[newcall.ns].append(newcall)
        
        location = newcall.get_location()


        if location not in self.calls_by_location:
            self.calls_by_location[location] = []
        
        self.calls_by_location[location].append(newcall) 


    def change(self,old_name,new_name,replace_name):
        if old_name not in self.names:
            return 
        current_names = copy.deepcopy(self.names)
        calls = current_names[old_name]
        finally_call = calls[0]
        for call in calls:
            for obj in call.point_to:
                if obj[0].ns == replace_name:
                    obj[0].ns = new_name

        self.names[new_name] = calls  
        # self.names.pop(old_name)
    def pop(self,old_name):
        if old_name in self.names:
            self.names.pop(old_name)
    
    def get(self,ns):
        if ns in self.names:
            return self.names[ns]
        
    
    def get_all_funcs(self,module=None):
        if module == None:
            return self.names
        else:
            ret_func_names = {}
            for ns in self.names:
                if self.names[ns].module == module:
                    ret_func_names[ns] = self.names[ns]
            return ret_func_names

    def if_visit(self,context,node):
        current_node_location = '{}#{}#{}#{}#{}'.format(context,node.lineno,node.end_lineno,node.col_offset,node.end_col_offset) 
        if current_node_location in self.calls_by_location:
            return True
        return False  


class CallNode:
    def __init__(self,ns,scope,module,lineno,args=None):
        self.ns = ns 
        self.scope = scope  
        self.module = module 
        self.lineno = lineno 
        self.args = args   
        self.type = 'NormalCall'
        self.defined = False  
        self.visit = False   
        self.point_to = []
        
    def get_location(self):
        return  '{}#{}#{}#{}#{}'.format(self.scope,self.lineno,self.end_lineno,self.col_offset,self.end_col_offset)
    
    def setPos(self,lineno,end_lineno,col_offset,end_col_offset):
        self.lineno = lineno
        self.end_lineno = end_lineno
        self.col_offset = col_offset
        self.end_col_offset = end_col_offset
    
    def __hash__(self):
       str_ = '{}#{}#{}#{}#{}'.format(self.scope,self.lineno,self.end_lineno,self.col_offset,self.end_col_offset)  
       return hash(str_)

    def __eq__(self,other):
        if self.scope == other.scope and self.lineno == other.lineno and self.end_lineno == other.end_lineno and self.col_offset == other.col_offset and self.end_col_offset == other.end_col_offset:
            return True
        else:
            return False



class AttrManager:
    def __init__(self):
        # self.names = {}
        self.attrs_by_location = {}  
        self.last_attr_scope = None
   

    def add(self,newattr,mode='remove'):  #
        
        if self.last_attr_scope and self.last_attr_scope != newattr.scope:
            self.attrs_by_location = {}  

        location = newattr.get_location()
        if location not in self.attrs_by_location:
            self.attrs_by_location[location] = []
        
        self.last_attr_scope = newattr.scope
        self.attrs_by_location[location] = newattr   
    
    def if_visit(self,context,node):
        current_node_location = '{}#{}#{}#{}#{}'.format(context,node.lineno,node.end_lineno,node.col_offset,node.end_col_offset) 
        if current_node_location in self.attrs_by_location:
        
            if type(self.attrs_by_location[current_node_location].point_node) == type(node):
                return self.attrs_by_location[current_node_location]
            else:
                
                return False
        return False  


class AttrNode:
    def __init__(self,ns,ast_node,scope):
        self.ns = ns  
        self.scope = scope  
        self.point_node = ast_node
 
        
        self.lineno = ast_node.lineno
        self.end_lineno = ast_node.end_lineno
        self.col_offset = ast_node.col_offset
        self.end_col_offset = ast_node.end_col_offset
        self.visit = False   
        
        self.point_to = []
        
    def get_location(self):
        return  '{}#{}#{}#{}#{}'.format(self.scope,self.lineno,self.end_lineno,self.col_offset,self.end_col_offset)
    
    def setPos(self,lineno,end_lineno,col_offset,end_col_offset):
        self.lineno = lineno
        self.end_lineno = end_lineno
        self.col_offset = col_offset
        self.end_col_offset = end_col_offset
    
    def __hash__(self):
       str_ = '{}#{}#{}#{}#{}'.format(self.scope,self.lineno,self.end_lineno,self.col_offset,self.end_col_offset)  
       return hash(str_)

    def __eq__(self,other):
        if self.scope == other.scope and self.lineno == other.lineno and self.end_lineno == other.end_lineno and self.col_offset == other.col_offset and self.end_col_offset == other.end_col_offset:
            return True
        else:
            return False



class PointNode():
    def __init__(self,name,fqn,point_type,old_node=None):  
        self.point_name = name 
        self.full_qualify_name = fqn
        self.point_type = point_type  

        if old_node:
            self.origin_from = old_node.origin_from
            self.file_loc = old_node.file_loc   
            self.context=old_node.context
            self.match=old_node.match
            self.control = old_node.control
            self.defined = old_node.defined
        else:
            self.origin_from = 'IntraLevel'
            self.file_loc = '*'  
            self.context= 'Normal'
            self.match= 'Partial'
            self.control = ''
            self.defined = False


    def pass_(self,old_node):
        pass

    def _set(self,key,value):
        if key == 'context':
            self.context = value
        if key == 'match':
            self.match= value
        if key == 'control':
            self.control = value
        if key == 'origin_from':
            self.origin_from = value

        return self


class UnknownNode:
    def __init__(self,ns,scope='*',module='*',lineno=None):
        self.ns = ns 
        self.scope = scope 
        self.module = module 
        self.lineno = lineno  
        self.params = {}  
        self.type = 'Call'  
        self.defined = False  
        self.point_to = None
        
class UnknownManager:
    def __init__(self):
        self.names = []
    
    def add(self,ns,scope,module,lineno,params=None):
        if ns not in self.names:
            call = UnknownNode(ns,scope,module,lineno,params) 
            self.names[ns] = call
        return self.names[ns]
    
    def get(self,ns):
        if ns in self.names:
            return self.names[ns]
    
    def get_all_funcs(self,module=None):
        if module == None:
            return self.names
        else:
            ret_func_names = {}
            for ns in self.names:
                if self.names[ns].module == module:
                    ret_func_names[ns] = self.names[ns]
            return ret_func_names

class CallContext:
    def __init__(self,ns,point_,scope,module='*',lineno='1'):
        self.ns = ns  
        self.point_ = point_  
        self.scope = scope  
        self.module = module
        self.lineno = lineno 
       
    def __hash__(self):
       str_ = '#'.join([self.ns,self.scope,self.lineno])
       return hash(str_)
    
    def __eq__(self,other):
        if self.ns == other.ns and self.scope == other.scope and self.lineno == other.lineno:
            return True
        else:
            return False
    
    def __str__(self):
        return ','.join([self.ns,self.scope,self.lineno])

class LambdaContext:
    def __init__(self,ns,point_,scope,module='*',lineno='1'):
        self.ns = ns 
        self.point_ = point_  
        self.scope = scope  
        self.visit = False  
        self.module = module 
        self.lineno = lineno  
    
    def __str__(self):
        return ','.join([self.ns,self.scope,self.lineno])

            
class LambdaNode:
    def __init__(self,ns,scope,module='*',lineno='1'):
        self.ns = ns  
        self.scope = scope  
        self.visit = False  
        self.module = module 
        self.lineno = lineno 
        self.params = []
        self.body_asts = []  
    
    def setPos(self,lineno,end_lineno,col_offset,end_col_offset):
        self.lineno = lineno
        self.end_lineno = end_lineno
        self.col_offset = col_offset
        self.end_col_offset = end_col_offset

    
    def __eq__(self,other):
        if self.scope == other.scope and self.lineno == other.lineno and self.end_lineno == other.end_lineno and self.col_offset == other.col_offset and self.end_col_offset == other.end_col_offset:
            return True
        else:
            return False

    def __str__(self):
        return ','.join([self.ns,self.scope,self.lineno]) 
