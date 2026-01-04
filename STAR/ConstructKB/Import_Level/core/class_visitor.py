import ast
from .fun_def_visitor import FunDefVisitor

def get_keywords(node):
    args = node.args
    arg_names = []
    defaults = args.defaults
    for arg in args.args:
        arg_names += [arg.arg]
    return (arg_names, len(defaults),node.lineno)

class ClassVisitor(ast.NodeVisitor):
    def __init__(self):
        self.result = {}

    def visit_FunctionDef(self, node, prefix="",dep=0): 
        # 获取函数的参数信息
        kw_names = get_keywords(node)
        func_name = prefix + node.name
        self.result[func_name] = kw_names
        
        # 处理嵌套函数（递归）
        for child_node in node.body:
            if isinstance(child_node, ast.ClassDef):
                self.visit_ClassDef(child_node, prefix=func_name + ".",dep=dep+1)
            if isinstance(child_node, ast.FunctionDef):
                self.visit_FunctionDef(child_node, prefix=func_name + ".",dep=dep+1)
        return node
        
    def visit_AsyncFunctionDef(self, node, prefix=""):
        self.visit_FunctionDef(node, prefix)

    def visit_ClassDef(self, node, prefix="",dep=0):
        #kw_names = get_keywords(node)
        func_name = ""
        if dep > 0:
            func_name = prefix + node.name
            self.result[func_name] = ('*', '*', node.lineno)

        # 处理嵌套函数（递归）
        for child_node in node.body:
            if isinstance(child_node, ast.ClassDef):
                self.visit_ClassDef(child_node, prefix = func_name + "." if dep != 0 else "",dep=dep+1)
            if isinstance(child_node, ast.FunctionDef):
                self.visit_FunctionDef(child_node, prefix = func_name + "." if dep != 0 else "",dep=dep+1)
        return node

