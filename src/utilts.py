import ast
import textwrap
import re

Standard_DataType = {"str":"<**PyStr**>","list":"<**PyList**>","dict":"<**PyDict**>","set":"<**PySet**>","tuple":"<**PyTuple**>","num":"<**PyNum**>","<**PyFile**>":'<**PyFile**>',"bool":"<**PyBool**>"}

DT_Returns = {
    "str":[
    "capitalize",
"casefold",
"center",
"count",
"encode",
"decode",
"endswith",
"expandtabs",
"find",
"format",
"format_map",
"index",
"isalnum",
"isalpha",
"isascii",
"isdecimal",
"isdigit",
"isidentifier",
"islower",
"isnumeric",
"isprintable",
"isspace",
"istitle",
"isupper",
"join",
"ljust",
"lower",
"lstrip",
"maketrans",
"partition",
"replace",
"rfind",
"rindex",
"rjust",
"rpartition",
"rsplit",
"rstrip",
"split",
"splitlines",
"startswith",
"strip",
"swapcase",
"title",
"translate",
"upper",
"zfill"
    ],
"list":[
    "append",
    "clear",
    "copy",
    "count",
    "extend",
    "index",
    "insert",
    "pop",
    "remove",
    "reverse",
    "sort",
    "allitems",
    "iterallitems",
    "iteritems",
],
"dict":[
    "clear",
"copy",
"fromkeys",
"get",
"items",
"keys",
"pop",
"popitem",
"setdefault",
"update",
"values"
],
"tuple":[
    "count",
"index"
],
"num":[
    "bit_length",
    "bit_count",
    "conjugate",
    "from_bytes",
    "to_bytes"
],
"file":[
    
],
"<**PyFile**>":[
    "read"
],
"set":[
    "add",
"clear",
"copy",
"difference",
"difference_update",
"discard",
"intersection",
"intersection_update",
"isdisjoint",
"issubset",
"issuperset",
"pop",
"remove",
"symmetric_difference",
"symmetric_difference_update",
"union",
"update"
],
"bool":
[

],

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
        "__version__", "__all__",  "__docformat__", "__package__",
        #others
        "dict","list","repr","set"
        }
        



import ast
import importlib

class ImportCollector(ast.NodeVisitor):
    def __init__(self):
        self.symbols = {}
        self.module_list = []

    def visit_Import(self, node):
        for alias in node.names:
            module = alias.name
            asname = alias.asname or module.split('.')[0]
            self.symbols[module] = asname
            self.module_list.append(module)

    def visit_ImportFrom(self, node):
        module = node.module
        for alias in node.names:
            imported_name = alias.name
            asname = alias.asname or imported_name
            full_name = f"{module}.{imported_name}" if module else imported_name
            self.symbols[full_name] = asname
            self.module_list.append(module)

def get_std_lib_modules():
    return {'os', 'os.path', 'configparser', 'configparser.ConfigParser'}

def get_non_standard_calls(code, stdlib_modules=None):
    # 解析代码生成AST
    tree = ast.parse(code)
    stdlib_modules = set()
    with open('stdlib.txt','r',encoding='utf-8') as f:
        stdlib_modules = set(f.read().split('\n'))
    # 第一步：收集所有导入的符号及其全名
    class ImportCollector(ast.NodeVisitor):
        def __init__(self):
            self.symbols = {}

        def visit_Import(self, node):
            for alias in node.names:
                module = alias.name
                asname = alias.asname or module.split('.')[0]
                self.symbols[asname] = module

        def visit_ImportFrom(self, node):
            module = node.module
            for alias in node.names:
                imported_name = alias.name
                asname = alias.asname or imported_name
                full_name = f"{module}.{imported_name}" if module else imported_name
                self.symbols[asname] = full_name

    import_collector = ImportCollector()
    import_collector.visit(tree)
    symbol_table = import_collector.symbols

    # 第二步：处理赋值语句，扩展符号表
    class AssignmentTracker(ast.NodeVisitor):
        def __init__(self, symbol_table):
            self.symbol_table = symbol_table

        def visit_Assign(self, node):
            if len(node.targets) != 1:
                return
            target = node.targets[0]
            if not isinstance(target, ast.Name):
                return

            var_name = target.id
            # 解析右侧表达式的全名
            full_name = self._resolve_expression(node.value)
            if full_name:
                self.symbol_table[var_name] = full_name

        def _resolve_expression(self, node):
            if isinstance(node, ast.Name):
                return self.symbol_table.get(node.id, None)
            elif isinstance(node, ast.Attribute):
                value_full = self._resolve_expression(node.value)
                if value_full:
                    return f"{value_full}.{node.attr}"
                return None
            return None

    AssignmentTracker(symbol_table).visit(tree)

    # 第三步：收集所有非标准库的函数调用
    class CallCollector(ast.NodeVisitor):
        def __init__(self, symbol_table, stdlib_modules):
            self.symbol_table = symbol_table
            self.stdlib_modules = stdlib_modules
            self.calls = []
            self.scope_stack = []  # 作用域栈，追踪当前所在函数

        def visit_FunctionDef(self, node):
            self.scope_stack.append(node.name)  # 进入函数
            self.generic_visit(node)
            self.scope_stack.pop()  # 退出函数

        def visit_Call(self, node):
            func_full_name = self._get_func_full_name(node.func)
            if func_full_name:
                root_module = func_full_name.split('.', 1)[0]
                if root_module not in self.stdlib_modules and len(self.scope_stack)<=1:
                    self.calls.append(func_full_name)
            self.generic_visit(node)

        def _get_func_full_name(self, node):
            if isinstance(node, ast.Name):
                return self.symbol_table.get(node.id, None)
            elif isinstance(node, ast.Attribute):
                value_full = self._get_func_full_name(node.value)
                if value_full:
                    return f"{value_full}.{node.attr}"
                return None
            return None

    call_collector = CallCollector(symbol_table, stdlib_modules)
    call_collector.visit(tree)
    print(call_collector.symbol_table)
    return call_collector.calls

def extract_standard_calls(func_code, std_lib=None):
    func_code = textwrap.dedent(func_code)
    # if std_lib is None:
    #     std_lib = get_std_lib_modules()
    std_lib = set()
    with open('stdlib.txt','r',encoding='utf-8') as f:
        std_lib = set(f.read().split('\n'))
    class ImportVisitor(ast.NodeVisitor):
        def __init__(self):
            self.symbols = {}  # 别名到标准库全名的映射
            self.mou

        def visit_Import(self, node):
            for alias in node.names:
                module_name = alias.name
                alias_name = alias.asname if alias.asname else module_name
                self.symbols[alias_name] = module_name
            self.generic_visit(node)

        def visit_ImportFrom(self, node):
            module = node.module
            for alias in node.names:
                imported_name = alias.name
                full_import = f"{module}.{imported_name}" if module else imported_name
                alias_name = alias.asname if alias.asname else imported_name
                self.symbols[alias_name] = full_import
            self.generic_visit(node)

    class AssignmentVisitor(ast.NodeVisitor):
        def __init__(self, symbols, std_lib):
            self.var_types = {}  # 变量属性链到类型的映射
            self.symbols = symbols
            self.std_lib = std_lib

        def get_attribute_chain(self, node):
            if isinstance(node, ast.Name):
                return node.id
            elif isinstance(node, ast.Attribute):
                value_chain = self.get_attribute_chain(node.value)
                return f"{value_chain}.{node.attr}" if value_chain else node.attr
            return None

        def resolve_callable_name(self, node):
            if isinstance(node, ast.Name):
                return self.symbols.get(node.id, node.id)
            elif isinstance(node, ast.Attribute):
                value = self.resolve_callable_name(node.value)
                return f"{value}.{node.attr}" if value else None
            return None


        def visit_Assign(self, node):
            if isinstance(node.value, ast.Call):
                func_name = self.resolve_callable_name(node.value.func)
                # 修改判断条件：检查根模块是否在标准库中
                if func_name and (func_name.split('.', 1)[0] in self.std_lib ):
                    for target in node.targets:
                        chain = self.get_attribute_chain(target)
                        if chain:
                            self.var_types[chain] = func_name
            self.generic_visit(node)

    class CallVisitor(ast.NodeVisitor):
        def __init__(self, symbols, var_types, std_lib):
            self.symbols = symbols
            self.var_types = var_types
            self.std_lib = std_lib
            self.calls = []
            self.scope_stack = []  # 作用域栈，追踪当前所在函数
        
        def visit_FunctionDef(self, node):
            self.scope_stack.append(node.name)  # 进入函数
            self.generic_visit(node)
            self.scope_stack.pop()  # 退出函数

        def resolve_attribute(self, node):
            if isinstance(node, ast.Attribute):
                value = self.resolve_attribute(node.value)
                attr = node.attr
                if value is None:
                    return None
                if value in self.std_lib :
                    return f"{value}.{attr}"
                chain = self.get_attribute_chain(node.value)
                if chain in self.var_types:
                    return f"{self.var_types[chain]}.{attr}"
                return f"{value}.{attr}" if value else None
            elif isinstance(node, ast.Name):
                id_name = node.id
                resolved = self.symbols.get(id_name, id_name)
                if resolved in self.std_lib :
                    return resolved
                if id_name in self.var_types:
                    return self.var_types[id_name]
                return resolved
            return None

        def get_attribute_chain(self, node):
            if isinstance(node, ast.Name):
                return node.id
            elif isinstance(node, ast.Attribute):
                value_chain = self.get_attribute_chain(node.value)
                return f"{value_chain}.{node.attr}" if value_chain else node.attr
            return None

        def visit_Call(self, node):
            scope = self.scope_stack[-1] if self.scope_stack else "global"
            func_name = self.resolve_attribute(node.func)
            if func_name and (func_name.split(".", 1)[0] in self.std_lib) and len(self.scope_stack)<=1:
                self.calls.append(func_name)
            self.generic_visit(node)
 
    try:
        tree = ast.parse(func_code)
    except:
        tree = ast.parse("")
    import_visitor = ImportVisitor()
    import_visitor.visit(tree)
    #print(import_visitor.symbols)
    symbols = import_visitor.symbols
    assignment_visitor = AssignmentVisitor(symbols, std_lib)
    assignment_visitor.visit(tree)
    #print(assignment_visitor.symbols)
    #print(assignment_visitor.var_types)
    call_visitor = CallVisitor(symbols, assignment_visitor.var_types, std_lib)
    call_visitor.visit(tree)
    return call_visitor.calls



def generate_call_graph(code):
    class ImportVisitor(ast.NodeVisitor):
        def __init__(self):
            self.imports = {}  # 存储别名到完整路径的映射

        def visit_Import(self, node):
            for alias in node.names:
                if alias.asname:
                    if alias.asname not in self.imports:
                        self.imports[alias.asname] = alias.name
                else:
                    if alias.name not in self.imports:
                        self.imports[alias.name] = alias.name
            self.generic_visit(node)

        def visit_ImportFrom(self, node):
            module = node.module
            level = node.level  # 处理相对导入，但本例暂不考虑
            for alias in node.names:
                if module:
                    full_path = f"{module}.{alias.name}"
                else:
                    full_path = alias.name  # 例如 from .. import module
                if alias.asname:
                    if alias.asname not in self.imports:
                        self.imports[alias.asname] = full_path
                else:
                    if alias.name not in self.imports:
                        self.imports[alias.name] = full_path
            self.generic_visit(node)

    class AssignmentVisitor(ast.NodeVisitor):
        def __init__(self, imports):
            self.imports = imports
            self.vars = {}  # 存储变量名或属性链到来源的映射

        def visit_Assign(self, node):
            value_source = self.get_source(node.value)
            if value_source:
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        self.vars[target.id] = value_source
                    elif isinstance(target, ast.Attribute):
                        attr_chain = self.get_attribute_chain(target)
                        if attr_chain:
                            self.vars[attr_chain] = value_source
            self.generic_visit(node)

        def get_attribute_chain(self, node):
            if isinstance(node, ast.Attribute):
                prefix = self.get_attribute_chain(node.value)
                if prefix is None:
                    return None
                return f"{prefix}.{node.attr}"
            elif isinstance(node, ast.Name):
                return node.id
            else:
                return None

        def get_source(self, node):
            if isinstance(node, ast.Name):
                return self.imports.get(node.id, None)
            elif isinstance(node, ast.Attribute):
                value_part = self.get_source(node.value)
                if value_part:
                    return f"{value_part}.{node.attr}"
                else:
                    return None
            elif isinstance(node, ast.Call):
                # 处理构造函数调用，如ConfigParser()
                func_source = self.get_source(node.func)
                return func_source  # 返回类名，忽略参数
            else:
                return None

    class CallVisitor(ast.NodeVisitor):
        def __init__(self, imports, vars):
            self.imports = imports
            self.vars = vars
            self.calls = []
            self.scope_stack = []  # 作用域栈，追踪当前所在函数

        def visit_FunctionDef(self, node):
            self.scope_stack.append(node.name)  # 进入函数
            self.generic_visit(node)
            self.scope_stack.pop()  # 退出函数

        def visit_Call(self, node):
            call_path = self.resolve_call(node.func)
            if call_path and len(self.scope_stack)<=1:
                self.calls.append(call_path)
            self.generic_visit(node)

        def resolve_call(self, node):
            # 先尝试生成完整的属性链
            full_chain = self.get_full_chain(node)
            if full_chain in self.vars:
                return self.vars[full_chain]
            if full_chain in self.imports:
                return self.imports[full_chain]
            # 否则按原逻辑处理
            if isinstance(node, ast.Attribute):
                value_part = self.resolve_call(node.value)
                if value_part:
                    return f"{value_part}.{node.attr}"
                else:
                    return None
            elif isinstance(node, ast.Name):
                var_source = self.vars.get(node.id, None)
                if var_source:
                    return var_source
                else:
                    return self.imports.get(node.id, None)
            return None

        def get_full_chain(self, node):
            if isinstance(node, ast.Attribute):
                prefix = self.get_full_chain(node.value)
                if prefix is None:
                    return node.attr
                return f"{prefix}.{node.attr}"
            elif isinstance(node, ast.Name):
                return node.id
            else:
                return None

    
    try:
        code = textwrap.dedent(code)
        tree = ast.parse(code)
    except:
        tree = ast.parse("")
    import_visitor = ImportVisitor()
    import_visitor.visit(tree)
    assignment_visitor = AssignmentVisitor(import_visitor.imports)
    assignment_visitor.visit(tree)
    call_visitor = CallVisitor(import_visitor.imports, assignment_visitor.vars)
    call_visitor.visit(tree)
    return call_visitor.calls



def find_identifiers_scope(source_code):
    
    try:
        source_code = textwrap.dedent(source_code)
        tree = ast.parse(source_code)
    except:
        tree = ast.parse("")
    scopes = {}  # 记录每个标识符的作用域

    class FunctionScopeVisitor(ast.NodeVisitor):
        def __init__(self):
            self.scope_stack = []  # 作用域栈，追踪当前所在函数

        def visit_FunctionDef(self, node):
            self.scope_stack.append(node.name)  # 进入函数
            self.generic_visit(node)
            self.scope_stack.pop()  # 退出函数

        def visit_Name(self, node):
            scope = self.scope_stack[-1] if self.scope_stack else "global"
            scopes.setdefault(scope, {"assignments": {}, "function_calls": set(), "exceptions": set(), "variable":set()})
            scopes[scope]["variable"].add(node.id)  # 记录标识符及其作用域
            self.generic_visit(node)

        def visit_Attribute(self, node):
            """ 处理 obj.method() 这样的属性访问 """
            scope = self.scope_stack[-1] if self.scope_stack else "global"
            scopes.setdefault(scope, {"assignments": {}, "function_calls": set(), "exceptions": set(), "variable":set()})
            obj_name = self.get_func_name(node.value)  # 递归获取前缀对象
            tmp_name = f"{obj_name}.{node.attr}" if obj_name else node.attr   
            scopes[scope]["variable"].add(str(tmp_name))
            if obj_name:
                scopes[scope]["variable"].add(str(obj_name))
                scopes[scope]["variable"].add(str(node.attr))
            else :
                scopes[scope]["variable"].add(str(node.attr))
            self.generic_visit(node)

        # def visit_Assign(self, node):
        #     """ 处理变量赋值，如 x = 10 或 y = f(x) """
        #     scope = self.scope_stack[-1] if self.scope_stack else "global"
        #     scopes.setdefault(scope, {"assignments": {}, "function_calls": set(), "exceptions": set(), "variable":set()})

        #     # 获取赋值右侧表达式的字符串表示
        #     value_expr = ast.unparse(node.value) if hasattr(ast, "unparse") else "unknown"

        #     for target in node.targets:  # 遍历所有赋值目标
        #         if isinstance(target, ast.Name):  # 变量赋值
        #             #scopes[scope]["assignments"][value_expr] = target.id
        #             pass
        #         elif isinstance(target, ast.Attribute):  # 处理对象属性赋值，如 self.url = url
        #             obj_name = ast.unparse(target)  # 还原 `self.url`
        #             #scopes[scope]["assignments"][value_expr] = obj_name
        #             pass
        #     self.visit(node.value)

        def visit_Call(self, node):
            """ 处理函数调用，如 foo() 或 obj.method() """
            scope = self.scope_stack[-1] if self.scope_stack else "global"
            scopes.setdefault(scope, {"assignments": {}, "function_calls": set(), "exceptions": set(), "variable":set()})
            self.get_func_name(node.func)
            func_name = None
            if isinstance(node.func, ast.Name):  # 直接调用，如 foo()
                func_name = node.func.id
            elif isinstance(node.func, ast.Attribute):  # 方法调用，如 obj.method()
                if isinstance(node.func.value, ast.Call) and isinstance(node.func.value.func, ast.Name):
                    if node.func.value.func.id == "super":  # 识别 super(...)
                        super_func_name = f"super.{node.func.attr}"
                        scopes[scope]["function_calls"].add("super")
                        scopes[scope]["variable"].add("super")  # 记录 super 关键字
                func_name = node.func.attr     
                obj_name = self.get_func_name(node.func.value)  # 递归获取前缀对象
                tmp_name = f"{obj_name}.{node.func.attr}" if obj_name else node.func.attr   
                scopes[scope]["function_calls"].add(str(tmp_name))   
                scopes[scope]["variable"].add(str(tmp_name))
            if func_name:
                scopes[scope]["function_calls"].add(func_name)
                scopes[scope]["variable"].add(func_name)

            self.generic_visit(node)
            # 递归解析嵌套函数调用
            if isinstance(node.func, ast.Call):  
                self.visit_Call(node.func)  # 递归解析 super(Class, self).__init__()
            # 递归检查参数中的函数调用
            for arg in node.args:
                self.visit(arg)
                # if isinstance(arg, ast.Call):  
                #     self.visit_Call(arg)  # 递归解析 maybe_str(cfg.record_idle_time_limit)

            for keyword in node.keywords:
                self.visit(keyword)
                if isinstance(keyword.value, ast.Call):  
                    self.visit_Call(keyword.value)  # 递归解析 `default=maybe_str(...)`
        
        def visit_ExceptHandler(self, node):
            """ 处理 except 语句，收集异常类型 """
            scope = self.scope_stack[-1] if self.scope_stack else "global"
            scopes.setdefault(scope, {"assignments": {}, "function_calls": set(), "exceptions": set(), "variable":set()})

            def get_exception_name(exception_node):
                """ 递归解析异常名称，支持 urllib.error.HTTPError 这种情况 """
                if isinstance(exception_node, ast.Name):  # 处理 OSError 这种简单异常
                    return exception_node.id
                elif isinstance(exception_node, ast.Attribute):  # 处理 urllib.error.HTTPError
                    return get_exception_name(exception_node.value) + "." + exception_node.attr
                return None

            if node.type:
                if isinstance(node.type, ast.Tuple):  # except (OSError, urllib.error.HTTPError):
                    exception_names = {get_exception_name(exc) for exc in node.type.elts}
                else:  # except ValueError: or except urllib.error.HTTPError:
                    exception_names = {get_exception_name(node.type)}

                scopes[scope]["exceptions"].update(exception_names)

            self.generic_visit(node)  # 继续遍历 except 代码块


        def get_func_name(self, func_node):
            """ 获取函数调用的名称 """
            scope = self.scope_stack[-1] if self.scope_stack else "global"
            scopes.setdefault(scope, {"assignments": {}, "function_calls": set(), "exceptions": set(), "variable":set()})
            if isinstance(func_node, ast.Name):  # 直接调用，如 foo()
                scopes[scope]["variable"].add(func_node.id)
                return func_node.id
            elif isinstance(func_node, ast.Attribute):  # 方法调用，如 obj.method()
                scopes[scope]["variable"].add(str(func_node.attr))
                return str(self.get_func_name(func_node.value)) + "." + str(func_node.attr)
            return None
        
    visitor = FunctionScopeVisitor()
    visitor.visit(tree)
    return scopes

def contains_in_code(caller_code: str, class_name: str) -> bool:
    if class_name not in caller_code:
        return False
    pattern = rf"(?<![a-zA-Z0-9._]){re.escape(class_name)}\s*\("
    return re.search(pattern, caller_code) is not None

def find_builtin_func(code,caller_name,call_dict,global_fg):
    scopes = find_identifiers_scope(code)
    # print(scopes)
    candidates = []
    for key,method_list in DT_Returns.items():
        for method in method_list:
            if global_fg:
                tmp_name = 'global'
            else:
                tmp_name = caller_name
            if tmp_name in scopes and method in scopes[tmp_name]["function_calls"]:
                candidates.append(Standard_DataType[key] + "." + str(method))
    
    for method in BUILT_IN_FUNCTIONS:
        if global_fg:
            tmp_name = 'global'
        else:
            tmp_name = caller_name
        if "<builtin>" + "." + str(method) not in call_dict and tmp_name in scopes and method in scopes[tmp_name]["function_calls"] and contains_in_code(code,method):
            candidates.append("<builtin>" + "." + str(method))

    return candidates

if __name__ == "__main__":
    # 测试代码
#     code ='''
# @dec\ndef func():\n    pass
#       '''
#     caller_name = "get_similarity"
#     candidates = find_builtin_func(code,caller_name,{},0)
#     print(candidates)
#     # # for method in candidates:
#     # #     print(method)
#     scopes = find_identifiers_scope(code)
#     print(scopes)
    # print(contains_in_code(code,'try'))
    # {'caller': ['x', 'z'], 'inner': ['y']}
    
    code ='''
import ExceptionHandlingThread
def run():
        thread = ExceptionHandlingThread()
        thread.start()
        os.write()
        
'''
    print(generate_call_graph(code))
#     print(extract_standard_calls(code))  # 输出 ['configparser.ConfigParser', 'configparser.ConfigParser.read']
#     print(get_non_standard_calls(code))
