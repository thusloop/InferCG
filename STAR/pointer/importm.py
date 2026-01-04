
class ImportManager:
    def __init__(self):
        self.names = {}
    def add(self,ns,module,points=None):
        if ns not in self.names:
            func = ImportNode(ns,module,points) 
            self.names[ns] = func
        return self.names[ns]
    def get(self,ns):
        if ns in self.names:
            return self.names[ns]
    
    def get_all_imports(self):
        return self.names

class ImportNode:
    def __init__(self,ns,module,points=None):
        self.ns = ns
        self.module= module
        self.points = points

    def add_point(self,point):
        if self.points == None:
            self.points = []
        if isinstance(point,str):
            if point not in self.points:
                self.points.append(point)
        if isinstance(point,list): 
            for p in point:
                if p not in self.points:
                    self.points.append(p)

class VarManager:
    def __init__(self):
        self.names = {}
    def add(self,ns,module,points=None):
        if ns not in self.names:
            func = VarNode(ns,module,points) 
            self.names[ns] = func
        return self.names[ns]
    def get(self,ns):
        if ns in self.names:
            return self.names[ns]
    
    def get_all_vars(self):
        return self.names

class VarNode:
    def __init__(self,ns,module,points=None):
        self.ns = ns 
        self.module= module
        self.points = points
    def add_point(self,point):
        if self.points == None:
            self.points = []
        if isinstance(point,str):
            if point not in self.points:
                self.points.append(point)
        if isinstance(point,list): 
            for p in point:
                if p not in self.points:
                    self.points.append(p)