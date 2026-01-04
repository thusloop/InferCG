

import os
import json

type_button = True

Standard_Libs = set()
with open('stdlib.txt','r') as f:
    Standard_Libs = set(f.read().split('\n'))

Standard_DataType = {"str":"<**PyStr**>","list":"<**PyList**>","dict":"<**PyDict**>","set":"<**PySet**>","tuple":"<**PyTuple**>","defaultdict":"<**PyDefaultdict**>","num":"<**PyNum**>","<**PyFile**>":'<**PyFile**>',"bool":"<**PyBool**>"}

DT_Returns = {
    "str":{
    "capitalize":"str",
"casefold": "str",
"center":"str",
"count":"num",
"encode":"str",
"endswith":"bool",
"expandtabs":"str",
"find":"num",
"format":"str",
"format_map":"str",
"index":"num",
"isalnum":"bool",
"isalpha":"bool",
"isascii":"bool",
"isdecimal":"bool",
"isdigit":"bool",
"isidentifier":"bool",
"islower":"bool",
"isnumeric":"bool",
"isprintable":"bool",
"isspace":"bool",
"istitle":"bool",
"isupper":"bool",
"join":"str",
"ljust":"str",
"lower":"str",
"lstrip":"str",
"maketrans":"None",
"partition":"str",
"replace":"str",
"rfind":"num",
"rindex":"num",
"rjust":"str",
"rpartition":"tuple",
"rsplit":"list",
"rstrip":"str",
"split":"list",
"splitlines":"list",
"startswith":"bool",
"strip":"str",
"swapcase":"str",
"title":"str",
"translate":"str",
"upper":"str",
"zfill":"str"
    },
"list":{
    "append":"none",
    "clear":"none",
    "copy":"list",
    "count":"num",
    "extend":"none",
    "index":"num",
    "insert":"none",
    "pop":"none",
    "remove":"none",
    "reverse":"list",
    "sort":"list"
},
"dict":{
    "clear":"none",
"copy":"dict",
"fromkeys":"none",
"get":"none",
"items":"none",
"keys":"none",
"pop":"none",
"popitem":"none",
"setdefault":"none",
"update":"dict",
"values":"none"
},
"tuple":{
    "count":"num",
"index":"num"
},
"num":{
    "bit_length":"num",
    "bit_count":"num",
    "conjugate":"num",
    "from_bytes":"num",
    "to_bytes":"byte"
},
"file":{
    
},
"<**PyFile**>":{
    "read":"str"
},
"set":{
    "add":"none",
"clear":"none",
"copy":"set",
"difference":"set",
"difference_update":"none",
"discard":"none",
"intersection":"set",
"intersection_update":"none",
"isdisjoint":"none",
"issubset":"none",
"issuperset":"none",
"pop":"none",
"remove":"none",
"symmetric_difference":"none",
"symmetric_difference_update":"none",
"union":"set",
"update":"set"
},
"bool":
{

},
"defaultdict":
{
    "clear":"none",
    "copy":"dict",
    "fromkeys":"none",
    "get":"none",
    "items":"none",
    "keys":"none",
    "pop":"none",
    "popitem":"none",
    "setdefault":"none",
    "update":"dict",
    "values":"none"
}
}

BUILT_IN_Returns = {"re.findall":"str","open":"<**PyFile**>"}

BUILT_IN_FUNCTIONS = { 
         ### built-in functions
         "iteritems",
        "abs","delattr", "print", "str", "bin", "int", "xrange", "eval", "all", "exit", "basestring"
        "float", "open", "unicode", "exec", "breakpoint", "cmp",
        "hash","memoryview", "range" , "all","help","min","setattr","any","dir","hex","next","slice",
        "ascii","divmod","enumerate","id", "isinstance", "object","sorted","bin","enumerate","input",
        "staticmethod","bool", "eval" "int", "len", "breakpoint", "exec", "isinstance" ,"ord",
        "sum", "bytearray", "filter", "issubclass", "pow", "super", "bytes", "float", "iter", "print"
        "tuple", "callable", "format", "len", "property", "type", "chr","frozenset", "list", "range", "vars", 
        "classmethod", "getattr", "locals", "repr", "repr", "zip", "compile", "globals", "map", "reversed",  "__import__", "complex", "hasattr", "max", "round", "get_ipython",
        "ord","isinstance",
        ### cyl加的
        ###  built-in exceptions
        "BaseException", "SystemExit", "KeyboardInterrupt", "GeneratorExit", "Exception",
        "StopIteration", "StopAsyncIteration","ArithmeticError", "FloatingPointError", "OverflowError",
        "ZeroDivisionError","AssertionError", "AttributeError", "BufferError", "EOFError",
        "ImportError", "ModuleNotFoundError", "LookupError", "IndexError" , "KeyError", "MemoryError", "NameError",
        "UnboundLocalError", "OSError", "IOError", "BlockingIOError", "ChildProcessError", "ConnectionError",
        "BrokenPipeError", "ConnectionAbortedError", "ConnectionRefusedError","ConnectionResetError",
        "FileExistsError", "FileNotFoundError", "InterruptedError","IsADirectoryError", "NotADirectoryError",
        "PermissionError","ProcessLookupError", "TimeoutError", "ReferenceError", "RuntimeError",
        "NotImplementedError","RecursionError", "SyntaxError", "IndentationError", "TabError", "EnvironmentError",
        "SystemError", "TypeError", "ValueError","UnicodeError","UnicodeDecodeError","UnicodeEncodeError","UnicodeTranslateError",
        # built-in warnings
        "Warning","DeprecationWarning","PendingDeprecationWarning","RuntimeWarning","SyntaxWarning",
        "UserWarning", "FutureWarning","ImportWarning","UnicodeWarning","BytesWarning","ResourceWarning",
        # Others
        "NotImplemented", "__main__", "__doc__", "__file__", "__name__", "__debug__", "__class__", "__name__"
        "__version__", "__all__",  "__docformat__", "__package__"
        }


BUILT_IN_Method_CLS = {'__class__',
'__init__',
'__new__',
'__delattr__',
'__dict__',
'__dir__',
'__doc__',
'__eq__',
'__format__ ',      
'__ge__',
'__getattribute__ ',
'__gt__',
'__hash__',
'__init_subclass__',
'__le__',
'__lt__',
'__module__',     
'__ne__',
'__reduce__',
'__reduce_ex__',
'__repr__',
'__setattr__',
'__sizeof__',
'__str__',
'__subclasshook__',
'__weakref__'
}

Standard_Libs = set()
with open('stdlib.txt','r') as f:
    Standard_Libs = set(f.read().split('\n'))

def get_all_parent_class(all_start_class,inherited_classes,annonations):
    all_parent_names = []
    sc = all_start_class
    if sc in inherited_classes:
     
        full_names = [sc]
        while len(full_names) > 0:
            new_parent_names = []
            for parent in full_names:
                parent,_ = get_local_name(parent,None,annonations) 
                if parent in inherited_classes:
                    for pr in inherited_classes[parent]:
                        new_parent_names.append(get_local_name(pr,None,annonations)[0])
            full_names = list(new_parent_names) 
            all_parent_names = all_parent_names + new_parent_names  
    return all_parent_names

def get_implementation_class(all_start_class,inherited_classes):

    sc = all_start_class
   
    new_childs = []
    for child in inherited_classes:
        if sc in inherited_classes[child]:
            new_childs.append(child)
       
    return new_childs



def get_cls_method(client_):
    with open( f'pre_knowledge/{client_}_pre_inherited.json') as f:
        inherited_map = json.load(f)
        new_ = {}
        cls_has_method = {}
        for k,v in inherited_map.items():
            if 'method' in v: 
                new_[k] = v['inherited']
                cls_has_method[k] = {}
                for mf in v['method']:
                    cls_has_method[k][mf['name']]=mf

        inherited_map = new_

    return inherited_map,cls_has_method

def get_annotation(client_,benchmark='dynamic'):  #micro
    # return {}
    with open(f'pre_knowledge\\{client_}_pre_annotations.json','r') as f:
        annotations = json.load(f)
    
    if benchmark == 'micro':
        new_dict = {}
        for k,v in annotations.items():
            new_dict[k.split('#')[1]] = v
        return  new_dict
    
    return annotations


def get_local_name(API,args,annotations,import_map=None,mode='Call'):
    if 'src.' in API:
        API = API.replace('src.','')

    proj = API.split('.')[0]
    
    if import_map and proj not in annotations:
        for map_ in import_map:
            if  API.startswith(map_):
                API = API.replace(map_,import_map[map_],1)
                proj = API.split('.')[0]

    if proj in annotations:
        if API in annotations[proj]: 
            callee_loc_name = annotations[proj][API]['loc_name']
            if callee_loc_name.startswith('*'):
                return API,False
            
            return callee_loc_name,True
        else:
           return API,False

               

    if mode == 'Call':
        return API, True  
    else:
        return API,False  