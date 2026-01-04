import ast
from .class_visitor import ClassVisitor
from .fun_def_visitor import FunDefVisitor

class function_node(object):
    def __init__(self,name,args,args_default,filepath='*',lineno='*',namespace='*'):
        self.name = name
        self.args = args
        self.args_default = args_default
        self.filepath = filepath
        self.lineno = lineno
        self.namespace = namespace

def get_keywords(node,filepath='*'):
    args = node.args
    arg_names = []
    defaults = args.defaults
    for arg in args.args:
        arg_names += [arg.arg]
    # tmp = function_node(node.name,arg_names,len(defaults),filepath,node.lineno,'.'.join(scope)) 

    return (arg_names, len(defaults),node.lineno)


def get_node_name(ast_node):
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

class SourceVisitor(ast.NodeVisitor):
    def __init__(self):
        self.result = {}
        self.scope = []
        self.current_class_stack = []  # 跟踪类嵌套层级

    def visit_FunctionDef(self, node, prefix=""): 
        # 获取函数的参数信息
        kw_names = get_keywords(node)
        func_name = prefix + node.name
        self.result[func_name] = kw_names
        
        # 处理嵌套函数（递归）
        for child_node in node.body:
            if isinstance(child_node, ast.FunctionDef):
                self.visit_FunctionDef(child_node, prefix=func_name + ".")
        return node
        
    def visit_AsyncFunctionDef(self, node, prefix=""):
        self.visit_FunctionDef(node, prefix)

    def visit_ClassDef(self, node):
        visitor = ClassVisitor()
        visitor.visit(node)
        visitor.result['self_init'] = ('*', '*', node.lineno)  # 初始化即使没有method
        self.result[node.name] = visitor.result
        return node


