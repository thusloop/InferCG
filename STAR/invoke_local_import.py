import importlib
import inspect
import json
import re

Standard_Libs = set()
with open('stdlib.txt','r') as f:
    Standard_Libs = set(f.read().split('\n'))

def get_modules_from_json(file_path):
    with open(file_path, 'r') as file:
        modules = json.load(file)
    return modules

def print_module_source(modules):
    result_list = []
    for _,module_name in modules.items():
        if module_name != "":
            result_list.extend(module_name.strip().split('\n'))
    result_list = list(set(result_list))

    # 匹配 "import xx"
    pattern1 = r"^import\s+(\S+)$"
    # 匹配 "from yy import xx"
    pattern2 = r"^from\s+(\S+)\s+import\s+(\S+)$"
    # 匹配 "from yy import xx as zz"
    pattern3 = r"^from\s+(\S+)\s+import\s+(\S+)\s+as\s+(\S+)$"
    # 匹配 "import xx as zz"
    pattern4 = r"^import\s+(\S+)\s+as\s+(\S+)$"

    for s in result_list:
        match1 = re.match(pattern1, s)
        match2 = re.match(pattern2, s)
        match3 = re.match(pattern3, s)
        match4 = re.match(pattern4, s)
        #print(s)
        if match1:
            module_name = match1.group(1)
        elif match2:
            module_name = match2.group(1)
            name = match2.group(2)
        elif match3:
            module_name = match3.group(1)
            name = match3.group(2)
            asname = match3.group(3)
        elif match4:
            module_name = match4.group(1)
            asname = match4.group(2)
        else:
            print("error")
        try :
            if module_name in Standard_Libs:
                module = importlib.import_module(module_name)
                source_code = inspect.getsource(module)
                with open("temp.txt", 'a',encoding='utf-8') as f:
                    f.write(str(module_name) + "\n")
                    f.write(source_code)
                    f.write("\n\n\n")
        except Exception as e:
            print(f"Failed to load or inspect {module_name}: {e}\n")

# 假设你的库名存储在 modules.json 文件中
name = "asciinema"
file_path = './pre_knowledge/{}_import_info.json'.format(name)
modules = get_modules_from_json(file_path)
print_module_source(modules)