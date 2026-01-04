
from stdtypes import stdtypes,simplified_types
import ast
from log import logger
logger.name = __name__

def transferConstant(node):
    if not isinstance(node, ast.Constant):
        raise ValueError("Only Support Constant AST node.")
    if isinstance(node.value, str):
        return typeObject("str", True,'DT')
    elif isinstance(node.value, bytes):
        return typeObject("bytes", True,'DT')
    elif isinstance(node.value, bool):
        return typeObject("bool", True,'DT')
    elif isinstance(node.value, float):
        return typeObject("float", True,'DT')
    elif isinstance(node.value, int):
        return typeObject("int", True,'DT')
    elif node.value == None:
        return typeObject("None", True,'DT')
    elif type(node.value) == type(Ellipsis):
        return None
    else:
        raise TypeError("Currently we do not suupport constant of type: " + str(type(node.value)))



        
class typeObject:
    def __init__(self,type_,defined=False,category=None):
        self.type = type_
        self.defined = defined
        self.category = category
    

    

class annonationObject(object):
    def __init__(self,node,search_l,current_context):
        self.node = node
        self.Import_points = search_l
        self.current_context = current_context
        self.types = []
        self.names = []
        self.convert_ast_type(node)

    def convert_ast_type(self,source_node):
        if isinstance(source_node,str):
            # source_name = [source_node.strip(),'Var']
            self.names.append([source_node.strip(),'Var'])
        
        elif isinstance(source_node,ast.Str):
            self.names.append([source_node.s,'Var'])

        elif isinstance(source_node,ast.Constant):
            if transferConstant(source_node):
                self.convert_ast_type(source_node.value)

        elif isinstance(source_node,ast.Num) or isinstance(source_node,ast.NameConstant):
            self.types.append(typeObject('num',True))
        elif isinstance(source_node,ast.Name): 
            self.names.append([source_node.id,'Var'])
        elif isinstance(source_node,ast.Attribute):
            self.names.append([self.get_node_name(source_node),'Attr'])  
        
        elif isinstance(source_node,ast.BoolOp):
            if source_node.op == ast.Add:  
                pass
            else:
                for v in source_node.values:
                    self.convert_ast_type(v)
    
        elif isinstance(source_node,ast.List): #
            if len(source_node.elts) == 0:
                self.types.append(typeObject('list',True))
            else:
                for list_value in source_node.elts:
                    self.convert_ast_type(list_value)
        elif isinstance(source_node,ast.Set): #
            if len(source_node.elts) == 0: 
                self.types.append(typeObject('set',True))
            else:
                for list_value in source_node.elts:
                    self.convert_ast_type(list_value)

        elif isinstance(source_node,ast.Tuple): #
            if len(source_node.elts) == 0: 
                self.types.append(typeObject('tuple',True))
            else:
                for tuple_value in source_node.elts:
                    self.convert_ast_type(tuple_value) 
        elif isinstance(source_node,ast.Subscript): 
            self.convert_ast_type(source_node.value) 
            if self.get_node_name(source_node.value):
                cur_module = self.get_node_name(source_node.value)
                actual_point = self.find_import_map(cur_module)  #hao
                if actual_point == None:  
                    actual_point = cur_module
                    
                if actual_point == None:
                    print('unhandeled situation------',type(source_node.value))
                    return

                tmp_len = len(actual_point.split('.'))
                mod, ty = None,None
                for i in range(tmp_len): 
                    tmp_mod = '.'.join(actual_point.split('.')[0:tmp_len-i])
                    if tmp_mod in ['collections.abc','collections','typing','types']:  
                        mod = tmp_mod.strip()
                        ty = '.'.join(actual_point.split('.')[tmp_len-i:])

                if mod == 'collections.abc':
                    if ty in ["Tuple", "Union", "Optional", "Dict", "List", "Set","Sequence"]:
                        self.convert_ast_type(source_node.slice)
                elif mod == 'collections':
                    if actual_point in simplified_types:
                        self.types.append(typeObject(actual_point.lower(),True))
                    
                elif mod == 'typing' or mod == 'types':
                    if ty in stdtypes['typing'] and ty in ["Tuple", "Union", "Optional", "Dict", "List", "Set",'Sequence']:
                        self.convert_ast_type(source_node.slice)

                elif cur_module.split('.')[-1] in ["Tuple", "Union", "Optional", "Dict", "List", "Set","Sequence"]: #loose rule
                    self.convert_ast_type(source_node.slice)
           

    def map_name_type(self,name):
        pass

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
            return self.get_node_name(ast_node.value)
        return None
    
    def only_inlude(self,sub,complete):
        
        if sub == None or complete == None:
            return False
        if '.'+sub + '.' in '.'+complete + '.' and complete.startswith(sub):
            return True
        else:
            return False

            
    def find_import_map(self,full_name):
        
        
        current_context = self.current_context
        search_targets = [[self.Import_points,'ImportLevel']]
        all_find_edge = []
    
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
                            
                            return API_name      
                        
                      

def get_onlyattrs(attr_node):
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
