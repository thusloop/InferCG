class FunctionManager:
    def __init__(self):
        self.names = {}
    def add(self,ns,module,start_line,end_line):
        if ns not in self.names:
            func = FuncNode(ns,module,start_line,end_line) 
            self.names[ns] = func
        else: 
            self.names[ns].override = True
        return self.names[ns]

    def get(self,ns):
        if ns in self.names:
            return self.names[ns]
        return None
    
    def get_all_funcs(self,module=None):
        if module == None:
            return self.names
        else:
            ret_func_names = {}
            for ns in self.names:
                if self.names[ns].module == module:
                    ret_func_names[ns] = self.names[ns]
            return ret_func_names

class FuncNode:
    def __init__(self,ns,module='*',start_line=None,end_line=None):
        self.ns = ns  
        self.module = module #
        self.start_line = start_line
        self.end_line = end_line
        self.params = {}
        self.returns = []
        self.nested = []
        self.decos = []
        self.property = False
        self.type = 'func'
        self.override = False
    
    def add_return(self,point):
        pass

    def set_line(self,start_line,end_line):
        self.start_line = start_line
        self.end_line = end_line
