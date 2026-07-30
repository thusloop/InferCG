import time
import psutil


def calculate_metrics(true_edges, predicted_edges):
    """
    计算精准率、召回率，并找出真实中存在但预测中不存在的边，以及预测中存在但真实中不存在的边。
    """
    # 真正例（TP）：真实和预测都存在的边
    tp = true_edges & predicted_edges

    # 真实中存在，但预测中不存在的边（FN）
    fn = true_edges - predicted_edges

    # 预测中存在，但真实中不存在的边（FP）
    fp = predicted_edges - true_edges

    precision = len(tp) / len(predicted_edges) if predicted_edges else 0
    recall = len(tp) / len(true_edges) if true_edges else 0

    # 计算F1分数
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0

    return precision, recall, f1, fn, fp


import json
from collections import defaultdict


# STAR's source-root names differ from the ground-truth module names for these
# two repository layouts. Normalize both callers and callees before comparison.
PROJECT_SYMBOL_REPLACEMENTS = {
    "fabric": (
        ("fabric.fabric.", "fabric."),
        ("fabric.integration.", "integration."),
        ("fabric.sites.", "sites."),
        ("fabric.tasks.", "tasks."),
    ),
    "Sublist3r": (
        ("Sublist3r.sublist3r.", "sublist3r."),
        ("Sublist3r.subbrute.", "subbrute."),
    ),
}


def normalize_symbol(project, symbol, replace_list):
    for old, new in replace_list:
        symbol = symbol.replace(old, new)
    for old, new in PROJECT_SYMBOL_REPLACEMENTS.get(project, ()):
        symbol = symbol.replace(old, new)
    return symbol


def merge_list_values(pairs):
    """合并重复键的列表值"""
    merged = defaultdict(list)
    for key, value in pairs:
        # 确保值都是列表（如果不是，转换为列表）
        if not isinstance(value, list):
            value = [value]
        merged[key].extend(value)  # 合并列表内容
    
    return dict(merged)
def load_json(name, file_path, replace_list=[], skip_list=[], pre_clean=[],all_or_EA = 1):
    """
    加载 JSON 文件并将边关系转换为集合形式，便于比较。
    返回边集合，格式为 {(source, target), ...}
    """
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)



    edges = set()
    for source, targets in data.items():
        if source.split('.')[0] in skip_list:
            continue
        source = normalize_symbol(name, source, replace_list)
        if all_or_EA == 0:
            if not source.startswith('<') and not source.startswith(name):
                continue
        for target in targets:
            # if "error" in target.lower():
            #     continue
            if target.split('.')[0] in skip_list:
                continue
            target = normalize_symbol(name, target, replace_list)

            if all_or_EA == 0:
                if not target.startswith('<') and not target.startswith(name):
                    continue   
            edges.add((source, target))

    return edges

def main(name, replace_list, skip_list, pre_clean=[], precision_write = 0, recall_write = 0, Ae_or_pycg = 1, all_or_EA = 1, verbose=False):
    """
    主函数，加载 JSON 文件，计算指标并输出结果。
    """
    true_json_path = "../ground-truth-cgs-after/{}.json".format(name)  # 真实边的 JSON 文件路径
    if Ae_or_pycg == 1:
        if verbose:
            print("{} Ae:".format(name))
        predicted_json_path = "../Ae_data/{}.json".format(name)  # 预测边的 JSON 文件路径
    elif Ae_or_pycg == 0 :
        print("{} PyCG:".format(name))
        predicted_json_path = "../PyCG_data/{}.json".format(name)  # 预测边的 JSON 文件路径
    elif Ae_or_pycg == 2 :
        print("{} Depends:".format(name))
        predicted_json_path = "../Depends_data/{}.json".format(name)  # 预测边的 JSON 文件路径
    

    # 加载边集合
    true_edges = load_json(name, true_json_path, replace_list,skip_list, pre_clean, all_or_EA)
    predicted_edges = load_json(name, predicted_json_path, replace_list, skip_list, pre_clean, all_or_EA)
    # if Ae_or_pycg == 1 and all_or_EA == 0:
    #     predicted_edges = predicted_edges.union(load_json(name, "../stdlib_and_thirdlib_data/{}.json".format(name), replace_list, skip_list, pre_clean, all_or_EA))
    # 计算指标
    precision, recall, f1, fn, fp = calculate_metrics(true_edges, predicted_edges)
    precision = precision*100
    recall = recall*100
    f1 = f1*100
    # 输出结果
    
    if verbose:
        print(f"Precision: {precision:.3f}")
        print(f"Recall: {recall:.3f}")
        print(f"F1: {f1:.3f}\n")

    if recall_write:
        #召回率
        print("Edges in true JSON but not in predicted JSON (FN):")
        for edge in sorted(fn):
            print(edge)

    if precision_write:
        # 精准率
        print("\nEdges in predicted JSON but not in true JSON (FP):")
        for edge in sorted(fp):
            print(edge)
    return precision, recall, f1

project_name_list_1 = ["asciinema","autojump","fabric","face_classification","Sublist3r"]
project_name_list_2 = ['bpytop','furl','rich_cli','sqlparse','sshtunnel','textrank4zh']
# project_name_list_1 = ["asciinema","autojump"] #测试集
# project_name_list_2 = ['sqlparse','sshtunnel','textrank4zh'] #测试集
pre_clean = []
#skip_list = []
skip_list = ['test','tests','setup','uninstall','install','setup.py']
replace_list = [
    ('.__init__',''),
    ('<**PyList**>','<list>'),
    ("<**PyStr**>","<str>"),
    ("<**PyDict**>","<map>"),
    ("<**PySet**>","<set>"),
    ("<**PyTuple**>","<tuple>"),
    ("<**PyNum**>","<num>"),
    ("<**PyBool**>","<bool>"),
    ('Socket','socket'),
    ('<builtin>','<builtin>'),
    ('Socket','socket'),
    ('invoke.config.Config._set','invoke.config.DataProxy._set'),
    ('invoke.Context._set','invoke.config.DataProxy._set'),
    ('fabric.util.debug','util.debug'),
    ('invoke.terminals.pty_size','invoke.pty_size'),
    ('invoke.context.Context._run',"invoke.Context._run"),
    ('invoke.context.Context._sudo',"invoke.Context._sudo"),
    ('invoke.parser.argument.Argument',"invoke.Argument"),
    ('invoke.program.Program.core_args',"invoke.Program.core_args"),
    ('invoke.collection.Collection',"invoke.Collection"),
    ('invoke.program.Program.load_collection',"invoke.Program.load_collection"),
    ('invoke.program.Program.no_tasks_given',"invoke.Program.no_tasks_given"),
    ('invoke.program.Program.update_config',"invoke.Program.update_config"),
    ('invoke.collection.Collection',"invoke.Collection"),
    ('re.compile.findall','re.findall'),
    ('requests.sessions.Session.get','requests.Session.get'),
    ('argparse.ArgumentParser.add_argument','argparse.add_argument'),
    ('argparse.ArgumentParser.parse_args','argparse.parse_args'),
    ('threading.Thread.start','threading.start')
]

# for r in replace_list:
#     skip_list.append(r[0])
#     skip_list.append(r[1])

evaluation_started = time.perf_counter()
evaluation_process = psutil.Process()
ae_results = []
for name in project_name_list_1:
    if name == "autojump":
        replace_list.append(('bin.',''))
    elif name == "face_classification":
        replace_list.append(('src.',''))
    if name == "asciinema":
        precision, recall, f1 = main(name, replace_list, skip_list, pre_clean, precision_write=0, recall_write=0, Ae_or_pycg=1, all_or_EA=1)
    else :
        precision, recall, f1 = main(name, replace_list, skip_list, pre_clean, precision_write=0, recall_write=0, Ae_or_pycg=1, all_or_EA=1)
    ae_results.append((name, precision, recall, f1))
    if name == "autojump":
        replace_list.pop()
    elif name == "face_classification":
        replace_list.pop()
    
#project_name_list_2 = []
for name in project_name_list_2:
    precision, recall, f1 = main(name, replace_list, skip_list, pre_clean, precision_write=0, recall_write=0, Ae_or_pycg=1, all_or_EA=0)
    ae_results.append((name, precision, recall, f1))

print(f"{'Ae project':<22} {'Precision':>10} {'Recall':>10} {'F1':>10}")
for name, precision, recall, f1 in ae_results:
    print(f"{name:<22} {precision:>9.3f}% {recall:>9.3f}% {f1:>9.3f}%")

count = len(ae_results)
print(
    f"{'Macro average':<22} "
    f"{sum(item[1] for item in ae_results) / count:>9.3f}% "
    f"{sum(item[2] for item in ae_results) / count:>9.3f}% "
    f"{sum(item[3] for item in ae_results) / count:>9.3f}%"
)
print(
    "Evaluation metrics: {:.3f}s, RSS {:.1f} MiB, tokens 0".format(
        time.perf_counter() - evaluation_started,
        evaluation_process.memory_info().rss / (1024 * 1024),
    )
)

