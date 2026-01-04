"""

根据test_dataset_predict.csv生成各个项目的json形式的调用图
"""

import pandas as pd
import json
import os

def load_json(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)
    
def generate_json_graphs(input_csv_path, output_dir="predicted_jsons"):
    """
    读取预测结果CSV，并为每个项目生成对应的调用图JSON文件。
    """
    
    # 1. 检查文件是否存在
    if not os.path.exists(input_csv_path):
        print(f"错误: 找不到文件 {input_csv_path}")
        return

    # 2. 创建输出目录
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        print(f"创建输出目录: {output_dir}")

    print("正在读取 CSV 文件...")
    try:
        # 使用 utf-8-sig 以防止中文乱码
        df = pd.read_csv(input_csv_path, encoding='utf-8-sig')
    except UnicodeDecodeError:
        df = pd.read_csv(input_csv_path, encoding='utf-8')

    # 3. 筛选预测为正样本 (prediction == 1) 的数据
    # 确保 prediction 列是整数类型
    df['prediction'] = df['prediction'].astype(int)
    df_positive = df[df['prediction'] == 1]

    if len(df_positive) == 0:
        print("警告: CSV中没有预测为 1 的数据，未生成任何 JSON 文件。")
        return

    # 4. 获取所有涉及的项目名称
    projects = df_positive['project'].unique()
    print(f"共发现 {len(projects)} 个包含预测边的项目。")
    print(projects)

    project_name_list_2 = ['sqlparse','sshtunnel','textrank4zh'] #测试集
    project_data = {}
    for name in project_name_list_2:
        project_json_path = "../file2class_data/{}.json".format(name)
        project_data[name] = load_json(project_json_path)
    # 5. 遍历每个项目并生成 JSON
    for project_name in projects:
        # 提取当前项目的数据
        project_df = df_positive[df_positive['project'] == project_name]
        
        # 构建字典: {caller: [callee1, callee2, ...]}
        # 使用 groupby 聚合 callee
        # 使用 set() 去重，然后转回 list
        call_graph = project_df.groupby('caller')['callee'].apply(lambda x: list(set(x))).to_dict()
        if project_name in project_name_list_2 and project_name in project_data:
            extra_data = project_data[project_name]
            # 遍历额外数据，合并到call_graph中
            for caller, callees in extra_data.items():
                if caller in call_graph:
                    # 合并列表并去重
                    call_graph[caller] = list(set(call_graph[caller] + callees))
                else:
                    # 如果caller不存在，直接添加
                    call_graph[caller] = callees
        # 定义输出文件名
        # 假设 project_name 就是 "project1", "project3" 等
        json_filename = f"{project_name}.json"
        output_path = os.path.join(output_dir, json_filename)

        # 写入 JSON 文件
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                # indent=2 格式化输出，方便阅读
                # ensure_ascii=False 保证中文正常显示
                json.dump(call_graph, f, indent=2, ensure_ascii=False)
            # print(f"已生成: {output_path}")
        except Exception as e:
            print(f"写入 {output_path} 失败: {e}")

    print("\n所有 JSON 文件生成完毕！")

if __name__ == "__main__":
    # 输入文件名
    INPUT_FILE = "test_dataset_predict.csv"
    
    # 输出文件夹名称 (所有json会保存在这个文件夹下，保持整洁)
    OUTPUT_DIR = "../Ae_data"
    
    generate_json_graphs(INPUT_FILE, OUTPUT_DIR)