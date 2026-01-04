""""
生成训练数据

"""
import json
import csv
import re
import pandas as pd
import os

# 1. 定义项目ID列表
project_list_id = [1,3,4,6,7,8,9,11,12,13,15,16,18,19,20,22,23,24,25,28,29,31,32,33,35,36,37,38,45,46,48,50,52,53,5,57,58]

# 2. 定义清洗名称的函数
def clean_name(name):
    """
    清洗caller和callee名称。
    移除 ['src.', 'bin.', 'project*.'] 前缀。
    使用循环移除以处理嵌套前缀（如 project1.src.xxx）。
    """
    if not isinstance(name, str):
        return ""
    
    # 定义匹配模式：匹配以 src. 或 bin. 或 project数字. 开头的字符串
    pattern = r'^(src\.|bin\.|project\d+\.)'
    
    while True:
        original = name
        # 替换开头的匹配项为空
        name = re.sub(pattern, '', name)
        # 如果没有变化，说明清洗完成
        if name == original:
            break
    replace_list = [  
        ('<**PyList**>.','list.'),
        ("<**PyStr**>.","str."),
        ("<**PyDict**>.","dict."),
        ("<**PySet**>.","set."),
        ("<**PyTuple**>.","tuple."),
        ("<**PyNum**>.","num."),
        ("<**PyBool**>.","bool."),
        ("<builtin>.","builtins."),
        ("<**PyFile**>.","TextIOWrapper."),
        # ("mezzanine.","")
    ]
    name = name.replace('.__init__','')
    for r in replace_list:
        if name.startswith(r[1]):
            name = name.replace(r[1],r[0])
    return name

# 3. 解析第二列长文本的函数
def parse_info_text(text):
    """
    从merged.csv的第2列文本中解析文件路径和代码。
    能够处理 emojis (✅) 和不规则的换行符。
    """
    if not isinstance(text, str):
        return "", "", "", ""
    
    # 1. 截断不需要的尾部提示文本
    # 使用 split 切割，只要包含 "你需要一步一步"，后面的全部丢弃
    # 这样无论是 "你需要一步一步……" 还是 "你需要一步一步分析..." 都能处理
    if "你需要" in text:
        text = text.split("你需要")[0]
    
    # 初始化结果
    caller_path = ""
    caller_code = ""
    callee_path = ""
    callee_code = ""
    
    # 2. 使用正则表达式提取内容
    # re.DOTALL: 让 . 匹配包括换行符在内的所有字符 (包含 emojis)
    # \s*: 匹配任意数量的空白字符 (换行、空格)，解决标题与内容间可能有空行的问题
    # (?=...): 正向预查（Lookahead），匹配...前面的位置，但不消耗字符
    
    try:
        # --- 提取调用者文件路径 ---
        # 逻辑：在 "调用者文件路径:" 之后，直到遇到 "调用者代码:" 或 "被调用者名称:"
        p_match = re.search(r'调用者文件路径:(.*?)(?=调用者代码:|被调用者名称:)', text, re.DOTALL)
        if p_match:
            caller_path = p_match.group(1).strip()

        # --- 提取调用者代码 ---
        # 逻辑：在 "调用者代码:" 之后，直到遇到 "被调用者名称:"
        # 这里的 (.*?) 会捕获包括 "✅" 在内的所有代码内容
        c_match = re.search(r'调用者代码:(.*?)(?=被调用者名称:)', text, re.DOTALL)
        if c_match:
            caller_code = c_match.group(1).strip()

        # --- 提取被调用者文件路径 ---
        # 逻辑：在 "被调用者文件路径:" 之后，直到遇到 "被调用者代码:" 或 文本结束
        ce_p_match = re.search(r'被调用者文件路径:(.*?)(?=被调用者代码:|$)', text, re.DOTALL)
        if ce_p_match:
            callee_path = ce_p_match.group(1).strip()

        # --- 提取被调用者代码 ---
        # 逻辑：在 "被调用者代码:" 之后的所有内容
        ce_c_match = re.search(r'被调用者代码:(.*)', text, re.DOTALL)
        if ce_c_match:
            callee_code = ce_c_match.group(1).strip()
            
    except Exception as e:
        print(f"解析文本出错: {e}")

    return caller_path, caller_code, callee_path, callee_code

def main():
    print("Step 1: 加载并清洗 project*.json 中的真实调用关系...")
    # 结构: {'project1': {('caller', 'callee'), ...}, 'project3': ...}
    ground_truth = {}
    
    for pid in project_list_id:
        project_name = f"project{pid}"
        json_filename = f"../ground-truth-cgs/{project_name}.json"
        
        if not os.path.exists(json_filename):
            print(f"警告: 文件 {json_filename} 不存在，跳过。")
            ground_truth[project_name] = set()
            continue
            
        try:
            with open(json_filename, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
            edges = set()
            for caller, callees in data.items():
                clean_caller = clean_name(caller)
                # json中callee可能是列表，需要去重并清洗
                # 注意：callees 可能有None的情况，需要过滤
                if callees:
                    for callee in callees:
                        if callee:
                            clean_callee = clean_name(callee)
                            edges.add((clean_caller, clean_callee))
            
            ground_truth[project_name] = edges
            
        except Exception as e:
            print(f"读取 {json_filename} 出错: {e}")
            ground_truth[project_name] = set()

    print("Step 2: 处理 merged.csv 并生成训练数据...")
    
    # 读取 merged.csv，假设没有header，使用 pandas 读取
    # 列索引: 0=Index, 1=?, 2=InfoText, 3=Caller, 4=Callee, 5=ProjectName
    try:
        df_merged = pd.read_csv(r'E:\001_some_AI_code\003_AutoExtension\src\Archive\dpskr1-dynamic\data\merged_data.csv', header=None, encoding='utf-8')
    except FileNotFoundError:
        print("错误: 找不到 merged.csv 文件")
        return

    output_rows = []
    
    # 遍历 merged.csv 的每一行
    # 使用 itertuples 遍历速度较快
    for row in df_merged.itertuples(index=False):
        # 确保列索引没有越界，根据题目描述
        # row[2] 是文本, row[3] 是caller, row[4] 是callee, row[5] 是project
        
        # 安全获取数据
        try:
            info_text = row[2]
            raw_caller = str(row[3])
            raw_callee = str(row[4])
            project_name = str(row[5]).strip()
        except IndexError:
            continue # 跳过格式错误的行

        # 1. 清洗名称
        caller_name = clean_name(raw_caller)
        callee_name = clean_name(raw_callee)

        
        # 2. 解析文本信息
        caller_path, caller_code, callee_path, callee_code = parse_info_text(info_text)
        
        # 3. 确定标签 (Label)
        label = 0
        # 检查该项目是否存在于我们的 ground_truth 中
        if project_name in ground_truth:
            if (caller_name, callee_name) in ground_truth[project_name]:
                label = 1
        else:
            # 如果 merged.csv 中的项目不在 json 列表中，默认为 0 (或者根据需求处理)
            label = 0
            
        # 4. 收集结果
        # id 将在创建 DataFrame 时生成
        output_rows.append({
            'caller': caller_name,
            'callee': callee_name,
            'caller_code': caller_code,
            'callee_code': callee_code,
            'caller_path': caller_path,
            'callee_path': callee_path,
            'project': project_name,
            'label': label
        })

    print(f"Step 3: 保存结果到 train_dataset.csv (共 {len(output_rows)} 条数据)...")
    
    # 创建结果 DataFrame
    df_out = pd.DataFrame(output_rows)
    
    # 添加 ID 列 (从0开始)
    df_out.insert(0, 'id', range(len(df_out)))
    
    # 保存 CSV
    # quoting=csv.QUOTE_ALL 确保包含换行符的代码块被正确包裹
    df_out.to_csv('train_dataset.csv', index=False, encoding='utf-8-sig', quoting=csv.QUOTE_ALL)
    
    print("完成！")

if __name__ == "__main__":
    main()