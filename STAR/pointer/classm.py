# 2022/9/17 为class专门搞一个管理器
from .function import FuncNode
class ClassManager:
    def __init__(self):
        self.names = {}
    def get(self,name):
        if name in self.names:
            return self.names[name]
    def add(self,name,module):
        if not name in self.names:
            cls = ClassNode(name,module)
            self.names[name]= cls
        return self.names[name]

    def get_all_classes(self):
        return self.names

class ClassNode:
    def __init__(self,ns,module='*'):
        self.ns = ns  #全名称名字
        self.module = module # 类所在的模块名
        self.mro = [ns]  #继承关系了
        self.reverse_mro = []
        self.methods = {} #类包含的方法
        self.properties = {} #类包含的属性
        self.type = 'class'
    
    def add_method(self,m):
        if isinstance(m,FuncNode):
            self.methods[m.ns] = m
        else:
            print('uncomplete')

    def add_property(self,pr):
        if isinstance(pr,str):
            self.properties[pr] = ''
        else:
            self.properties[pr.ns] = pr 
            
    def get_mro(self):
        return self.mro
    
    def add_parent(self,parent):
        if isinstance(parent, str):
            self.mro.append(parent)
        elif isinstance(parent, list):
            for item in parent:
                self.mro.append(item)
        # self.fix_mro()
    # def compute_mro(self):
    #     all_parent_names = []
    #     sc = all_start_class
    #     if sc in inherited_classes:
    #         # all_parent_names = set(inherited_classes[sc])   #所有的父类
    #         # full_names = inherited_classes[sc]
    #         full_names = [sc]
    #         while len(full_names) > 0:
    #             new_parent_names = []
    #             for parent in full_names:
    #                 parent,_ = get_local_name(parent,None,annonations) #标准化之后才可以，烦死了
    #                 if parent in inherited_classes:
    #                     for pr in inherited_classes[parent]:
    #                         new_parent_names.append(get_local_name(pr,None,annonations)[0])
    #             full_names = list(new_parent_names) #怎么了调不出来了? #陷入循环了
    #             all_parent_names = all_parent_names + new_parent_names  #要按照这个MRO顺序才对，不能随便调顺序
    #     return all_parent_names

    def clear_mro(self):
        self.mro = [self.ns]

    