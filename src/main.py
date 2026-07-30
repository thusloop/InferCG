import time as time_module
import hashlib

PROCESS_STARTED_AT = time_module.perf_counter()

from time import time
import argparse
import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from openai import OpenAI
import psutil

from transformers import AutoTokenizer
import json
import ast
import sys
#import ollama
import textwrap
import asyncio
import shutil
from utilts import find_identifiers_scope,find_builtin_func,extract_standard_calls,get_non_standard_calls,ImportCollector,generate_call_graph
from prompt import system_prompt_comm,user_prompt_comm_step1,user_prompt_comm_step2,system_prompt_builtin,user_prompt_builtin_step1,user_prompt_builtin_step2,system_prompt_stdlib_and_thirdlib,user_prompt_stdlib_and_thirdlib_step1,user_prompt_stdlib_and_thirdlib_step2

import csv
import re
from tqdm import tqdm


def response_token_usage(response):
    """Return token accounting from an OpenAI-compatible response."""
    usage = getattr(response, "usage", None)
    return {
        "prompt_tokens": getattr(usage, "prompt_tokens", 0) or 0,
        "completion_tokens": getattr(usage, "completion_tokens", 0) or 0,
        "total_tokens": getattr(usage, "total_tokens", 0) or 0,
    }


class RunMetrics:
    """Collect wall-clock duration and peak RSS for one pipeline run."""

    def __init__(self):
        self.process = psutil.Process()
        self.started_at = time_module.perf_counter()
        self.peak_rss_bytes = self._rss_bytes()
        self.stop_event = threading.Event()
        self.monitor = threading.Thread(target=self._monitor_memory, daemon=True)
        self.monitor.start()

    def _rss_bytes(self):
        try:
            return self.process.memory_info().rss
        except psutil.Error:
            return 0

    def _monitor_memory(self):
        while not self.stop_event.wait(0.1):
            self.peak_rss_bytes = max(self.peak_rss_bytes, self._rss_bytes())

    def snapshot(self):
        self.peak_rss_bytes = max(self.peak_rss_bytes, self._rss_bytes())
        return {
            "pipeline_wall_time_seconds": time_module.perf_counter() - self.started_at,
            "process_wall_time_seconds": time_module.perf_counter() - PROCESS_STARTED_AT,
            "peak_rss_bytes": self.peak_rss_bytes,
            "peak_rss_mib": self.peak_rss_bytes / (1024 * 1024),
        }

    def finish(self):
        self.stop_event.set()
        self.monitor.join(timeout=1)
        return self.snapshot()


def inference_checkpoint_key(call):
    return json.dumps([call.caller, call.callee], ensure_ascii=False, separators=(",", ":"))


def new_inference_checkpoint(project, model):
    return {
        "project": project,
        "model": model,
        "responses": {},
        "failures": {},
        "token_usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }


def inference_prompt_fingerprint(call):
    prompt = "\x1f".join((call.system_prompt[:7000], call.prompt_step1[:7000], call.prompt_step2[:7000]))
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()


def load_inference_checkpoint(path, project, model):
    if not os.path.exists(path):
        return new_inference_checkpoint(project, model)
    try:
        with open(path, "r", encoding="utf-8") as stream:
            checkpoint = json.load(stream)
    except (OSError, json.JSONDecodeError):
        return new_inference_checkpoint(project, model)
    if checkpoint.get("project") != project or checkpoint.get("model") != model:
        return new_inference_checkpoint(project, model)
    checkpoint.setdefault("responses", {})
    checkpoint.setdefault("failures", {})
    checkpoint.setdefault("token_usage", {})
    for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
        checkpoint["token_usage"].setdefault(key, 0)
    journal_path = "{}.journal.jsonl".format(path)
    if os.path.exists(journal_path):
        with open(journal_path, "r", encoding="utf-8") as stream:
            for line in stream:
                try:
                    apply_inference_checkpoint_event(checkpoint, json.loads(line))
                except json.JSONDecodeError:
                    continue
    return checkpoint


def save_inference_checkpoint(path, checkpoint):
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    temporary_path = "{}.tmp".format(path)
    with open(temporary_path, "w", encoding="utf-8") as stream:
        json.dump(checkpoint, stream, ensure_ascii=False, indent=2)
    os.replace(temporary_path, path)
    journal_path = "{}.journal.jsonl".format(path)
    if os.path.exists(journal_path):
        with open(journal_path, "w", encoding="utf-8"):
            pass


def apply_inference_checkpoint_event(checkpoint, event):
    key = event["key"]
    if event["kind"] == "response":
        checkpoint["responses"][key] = event["record"]
        checkpoint["failures"].pop(key, None)
        for usage_key, value in event["usage"].items():
            checkpoint["token_usage"][usage_key] += value
    elif event["kind"] == "failure":
        checkpoint["failures"][key] = event["record"]
        for usage_key, value in event.get("usage", {}).items():
            checkpoint["token_usage"][usage_key] += value


def append_inference_checkpoint_event(path, checkpoint, event):
    apply_inference_checkpoint_event(checkpoint, event)
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    journal_path = "{}.journal.jsonl".format(path)
    with open(journal_path, "a", encoding="utf-8") as stream:
        stream.write(json.dumps(event, ensure_ascii=False) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def write_run_metrics(path, run_metrics, **values):
    report = run_metrics.finish()
    return write_metrics_report(path, report, **values)


def write_metrics_snapshot(path, run_metrics, **values):
    return write_metrics_report(path, run_metrics.snapshot(), **values)


def write_metrics_report(path, report, **values):
    report.update(values)
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    temporary_path = "{}.tmp".format(path)
    with open(temporary_path, "w", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
    os.replace(temporary_path, path)
    return report

# 加载 JSON 文件
def extract_confidence_percentage(text):
    if not isinstance(text, str):
        return None
    match = re.search(r'(?<![-\d])(?:100|[1-9]?\d(?:\.\d)?)%(?!\d)', text)
    return float(match.group(0).rstrip('%')) if match else None


def rebuild_graph_from_checkpoint(
    name,
    all_or_EA=1,
    model="gpt-5.4",
    confidence_threshold=60.0,
    output_path=None,
    metrics_output_path=None,
    checkpoint_path=None,
):
    """Reapply a threshold to cached LLM responses without rebuilding prompts."""
    run_metrics = RunMetrics()
    filename_with_extension = "{}.json".format(name)
    graph_output_path = output_path or "../Ae_data/{}".format(filename_with_extension)
    metrics_output_path = metrics_output_path or "../Ae_data/{}_metrics.json".format(name)
    checkpoint_path = checkpoint_path or "{}.infer.checkpoint.json".format(
        os.path.splitext(os.path.abspath(graph_output_path))[0]
    )
    checkpoint = load_inference_checkpoint(checkpoint_path, name, model)
    func_info_dict = build_func_info_dict(
        load_json("../STAR/pre_knowledge/{}_pre_annotations.json".format(name))
    )

    project_data = {}
    completed_candidates = 0
    for response in checkpoint["responses"].values():
        caller = response.get("caller")
        callee = response.get("callee")
        if not caller or not callee:
            continue
        completed_candidates += 1
        confidence = extract_confidence_percentage(response.get("step2"))
        if confidence is not None and confidence > confidence_threshold:
            project_data.setdefault(caller, []).append(callee)

    skipped_third_party_callers = remove_third_party_callers(project_data, func_info_dict)
    duplicate_edges_removed = deduplicate_call_graph(project_data)
    directory = os.path.dirname(graph_output_path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(graph_output_path, "w", encoding="utf-8") as stream:
        json.dump(project_data, stream, ensure_ascii=False, indent=4)

    previous_metrics = {}
    if os.path.exists(metrics_output_path):
        try:
            with open(metrics_output_path, "r", encoding="utf-8") as stream:
                previous_metrics = json.load(stream)
        except (OSError, json.JSONDecodeError):
            pass
    candidate_count = previous_metrics.get(
        "candidate_count", completed_candidates + len(checkpoint["failures"])
    )
    pending_failures = len(checkpoint["failures"])
    report = write_run_metrics(
        metrics_output_path,
        run_metrics,
        status="incomplete" if pending_failures or completed_candidates < candidate_count else "completed",
        project=name,
        mode="infer",
        model=model,
        confidence_threshold=confidence_threshold,
        checkpoint_only=True,
        checkpoint_prompt_validation="not_rebuilt",
        candidate_count=candidate_count,
        predicted_edge_count=sum(len(callees) for callees in project_data.values()),
        skipped_third_party_callers=skipped_third_party_callers,
        merged_file2class_edges=0,
        skipped_external_file2class_edges=0,
        duplicate_edges_removed=duplicate_edges_removed,
        parameter_mismatch_rejections=previous_metrics.get("parameter_mismatch_rejections", 0),
        inference_checkpoint_path=checkpoint_path,
        inference_completed_candidates=completed_candidates,
        inference_checkpoint_hits=completed_candidates,
        inference_attempted_candidates=0,
        inference_failed_candidates=0,
        inference_missing_checkpoint_candidates=max(0, candidate_count - completed_candidates - pending_failures),
        inference_pending_failures=pending_failures,
        prompt_tokens=checkpoint["token_usage"]["prompt_tokens"],
        completion_tokens=checkpoint["token_usage"]["completion_tokens"],
        total_tokens=checkpoint["token_usage"]["total_tokens"],
        session_prompt_tokens=0,
        session_completion_tokens=0,
        session_total_tokens=0,
    )
    print(
        "Checkpoint-only: {} cached responses, {} retained above {}%; {:.2f}s, peak RSS {:.1f} MiB".format(
            completed_candidates,
            report["predicted_edge_count"],
            confidence_threshold,
            report["pipeline_wall_time_seconds"],
            report["peak_rss_mib"],
        )
    )
    return project_data


def load_json(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)

# 构建调用关系字典
def build_call_dict_and_reverse(project_data):
    """
    构建调用关系字典 (caller -> callee) 和反向字典 (callee -> callerD)
    """
    call_dict = {}
    callee_to_callers_dict = {}

    # 假设 project_data 是一个字典，包含了所有的调用关系数据
    for caller, callees in project_data.items():
        if caller not in call_dict:
            call_dict[caller] = []
        
        # 构建 caller -> callee 的字典
        for callee in callees:
            call_dict[caller].append(callee)
            
            # 构建 callee -> callers 的反向字典
            if callee not in callee_to_callers_dict:
                callee_to_callers_dict[callee] = []
            callee_to_callers_dict[callee].append(caller)

    return call_dict, callee_to_callers_dict


# 构建函数信息字典
def build_func_info_dict(pre_annotations_data):
    func_info_dict = {}
    for func_name, func_info in pre_annotations_data.items():
        func_info_dict[func_name] = func_info
    return func_info_dict


def remove_third_party_callers(project_data, func_info_dict):
    """Ensure third-party library symbols can only be callees in the output graph."""
    third_party_callers = [
        caller for caller in project_data
        if func_info_dict.get(caller, {}).get("name_type") == "third library"
    ]
    for caller in third_party_callers:
        del project_data[caller]
    return len(third_party_callers)


def merge_project_file2class_edges(project_data, file2class_graph, project_name):
    """Merge file-to-class edges whose callers belong to the target project."""
    merged_edges = 0
    skipped_external_edges = 0
    for caller, callees in file2class_graph.items():
        if caller.split(".")[0] != project_name:
            skipped_external_edges += len(callees)
            continue
        existing_callees = project_data.setdefault(caller, [])
        existing = set(existing_callees)
        for callee in callees:
            if callee not in existing:
                existing_callees.append(callee)
                existing.add(callee)
                merged_edges += 1
    return merged_edges, skipped_external_edges


def deduplicate_call_graph(project_data):
    """Remove repeated caller-callee edges while preserving their first-seen order."""
    removed_edges = 0
    for caller, callees in project_data.items():
        unique_callees = []
        seen = set()
        for callee in callees:
            if callee in seen:
                removed_edges += 1
                continue
            seen.add(callee)
            unique_callees.append(callee)
        project_data[caller] = unique_callees
    return removed_edges

def is_magic_method(method_name: str) -> bool:
    # 判断字符串是否以双下划线开头和结尾
    return method_name.startswith('__') and method_name.endswith('__')

def remove_comments(code: str) -> str:
    if code :
        # 移除单行注释
        code = re.sub(r'#.*', '', code)
        # 移除多行注释（单引号和双引号）
        code = re.sub(r'"""(.*?)"""', '', code, flags=re.DOTALL)
        code = re.sub(r"'''(.*?)'''", '', code, flags=re.DOTALL)
        # code = re.sub(r"'(.*?)'", '', code, flags=re.DOTALL)
        # code = re.sub(r'"(.*?)"', '', code, flags=re.DOTALL)
        return code
    else :
        return ""

def contains_in_code(caller_code: str, class_name: str) -> bool:
    if caller_code == None:
        return False
    if class_name not in caller_code:
        return False
    # caller_code 中是否存在 class_name
    # 前面不能是 except，前后不能是字母、数字、 或 
    pattern = rf"(?<![a-zA-Z0-9]){re.escape(class_name)}(?![a-zA-Z0-9])"
    # if re.search(rf"\bexcept\s+{re.escape(class_name)}\b", caller_code):
    #     return False
    return re.search(pattern, caller_code) is not None


def collect_call_argument_counts(source_code):
    """Return direct-call argument counts keyed by the final callable name."""
    try:
        tree = ast.parse(textwrap.dedent(source_code))
    except (SyntaxError, TypeError):
        return {}

    call_counts = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name):
            callable_name = node.func.id
        elif isinstance(node.func, ast.Attribute):
            callable_name = node.func.attr
        else:
            continue

        has_unknown_arity = any(isinstance(argument, ast.Starred) for argument in node.args)
        has_unknown_arity = has_unknown_arity or any(keyword.arg is None for keyword in node.keywords)
        count = None if has_unknown_arity else len(node.args) + len(node.keywords)
        call_counts.setdefault(callable_name, []).append(count)
    return call_counts


def parameter_bounds(function_info):
    """Return the supported argument-count interval, or None when unavailable."""
    body = function_info.get("body", "")
    try:
        tree = ast.parse(textwrap.dedent(body))
        definition = next(
            node for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        )
    except (StopIteration, SyntaxError, TypeError):
        return None

    arguments = definition.args
    positional = list(arguments.posonlyargs) + list(arguments.args)
    implicit_receiver = 1 if positional and positional[0].arg in {"self", "cls"} else 0
    positional_count = len(positional) - implicit_receiver
    required_positional = len(positional) - len(arguments.defaults) - implicit_receiver
    required_keyword_only = sum(default is None for default in arguments.kw_defaults)
    minimum = max(0, required_positional) + required_keyword_only

    if arguments.vararg is not None or arguments.kwarg is not None:
        return minimum, None
    maximum = positional_count + len(arguments.kwonlyargs)
    return minimum, maximum


def filter_call_infos_by_parameter_count(call_info_list, func_info_dict):
    """Reject only explicit direct calls whose arity conflicts with the callee."""
    call_count_cache = {}
    bounds_cache = {}
    filtered_calls = []
    rejected = 0

    for call in call_info_list:
        caller_info = func_info_dict.get(call.caller)
        callee_info = func_info_dict.get(call.callee)
        callee_name = call.callee.split(".")[-1]
        if (
            caller_info is None
            or callee_info is None
            or (callee_name.startswith("__") and callee_name.endswith("__"))
        ):
            filtered_calls.append(call)
            continue

        if call.caller not in call_count_cache:
            call_count_cache[call.caller] = collect_call_argument_counts(caller_info.get("body", ""))
        observed_counts = call_count_cache[call.caller].get(callee_name)
        if not observed_counts:
            # The static candidate can represent a wrapper, callback, inherited
            # method, or another indirect call that is absent from this body.
            # Lack of a direct call site is therefore not an arity mismatch.
            filtered_calls.append(call)
            continue

        if call.callee not in bounds_cache:
            bounds_cache[call.callee] = parameter_bounds(callee_info)
        bounds = bounds_cache[call.callee]
        if bounds is None:
            filtered_calls.append(call)
            continue

        minimum, maximum = bounds
        compatible = any(
            count is None or (count >= minimum and (maximum is None or count <= maximum))
            for count in observed_counts
        )
        if compatible:
            filtered_calls.append(call)
        else:
            rejected += 1
    return filtered_calls, rejected


def micro_benchmark_case_id(function_info):
    """Return the benchmark sample owning a symbol, not only its source file."""
    filepath = function_info["filepath"].split(".")
    if len(filepath) < 3 or filepath[0] != "micro-benchmark":
        raise ValueError("Invalid micro-benchmark filepath: {}".format(function_info["filepath"]))
    return tuple(filepath[:3])

# 获取候选被调函数
def get_candidate_callees(name, call_dict, func_info_dict, import_info,all_or_EA):
    candidate_callees = {}
    candidate_callees_builtin = {}
    candidate_callees_stdlib = {}
    candidate_callees_non_stdlib = {}
    candidate_callees_stdlib_and_thirdlib = {}
    for caller in func_info_dict:
        # if caller in func_info_dict and caller == func_info_dict[caller]["filepath"]:
        #     continue
        #print(caller)
        if caller not in func_info_dict or func_info_dict[caller]["name_type"] != "local_name":#只选取local_name作为调用函数
            continue
        caller_code = func_info_dict[caller]["body"]
        caller_name = caller.split('.')[-1]
        import_module = import_info[func_info_dict[caller]["filepath"]]
        global_fg = 0
        if caller == func_info_dict[caller]["filepath"]:#调用者是global的情况 
            global_fg = 1
        had_fun = []
        caller_case = micro_benchmark_case_id(func_info_dict[caller]) if name == "micro-benchmark" else None
        # if caller in call_dict:
        #     had_fun = call_dict[caller]
        if caller_code != "":  
            candidate_callees_builtin[caller] = find_builtin_func(caller_code,caller_name,had_fun,global_fg)
            #candidate_callees_stdlib[caller] = extract_standard_calls(import_module.rstrip() + "\n\n" + textwrap.dedent(caller_code))
            #candidate_callees_non_stdlib[caller] = get_non_standard_calls(import_module.rstrip() + "\n\n" + textwrap.dedent(caller_code))
            try :
                candidate_callees_stdlib_and_thirdlib[caller] = generate_call_graph(import_module.rstrip() + "\n\n" + textwrap.dedent(caller_code))
            except:
                pass

        candidates = []
        for callee in func_info_dict:
            if name == "micro-benchmark":
                if caller_case != micro_benchmark_case_id(func_info_dict[callee]):
                    continue
                if caller == callee:
                    continue
                if func_info_dict[callee]["name_type"] != "local_name":
                    continue
                if contains_in_code(caller_code, callee.split(".")[-1]):
                    candidates.append(callee)
                continue
            if all_or_EA == 0:#只选取local_name的情况
                if callee not in func_info_dict or func_info_dict[callee]["name_type"] != "local_name":
                    continue
            # if (caller in call_dict and callee in call_dict[caller]) or caller == callee:
            #     continue
            if callee not in func_info_dict or func_info_dict[callee]["name_type"] == "stdlib":#stdlib不用处理
                continue
            if callee not in func_info_dict or func_info_dict[callee]["name_type"] == "third library":#第三方库不用处理
                pass
                #continue
            if callee == func_info_dict[callee]["filepath"]:#被调用者是global的情况
                continue
            # if callee in func_info_dict and func_info_dict[callee]["body"] == "":
            #     continue
            if callee.split('.')[-1] == "__init__":#调用类放在下面处理
                continue
            # if func_info_dict[callee]["name_type"] != "local_name": #被调用者不是local_name的情况(可能是标准库和第三方库)
            #     scopes = find_identifiers_scope(caller_code)
            #     if callee.split('.')[-1].startswith("__") and callee.split('.')[-1].endswith("__"):
            #         check_list = callee.split('.')[:-1]
            #     else :
            #         check_list = callee.split('.')
            #     flag = 1
            #     for i in check_list:
            #         if contains_in_code(import_module,i) == False and contains_in_code(caller_code,i) == False:
            #             flag = 0
            #     if flag == 1:
            #         candidates.append(callee)
            # else :
            
            tree = ast.parse(import_module)
            import_collector = ImportCollector()
            import_collector.visit(tree)
            init_module = "\n"
            for module in import_collector.module_list:
                if module and '.' not in module and module in import_info:
                    init_module += import_info[module]
            if caller == "integration.group.Group_.failed_command":
                pass
                #print(init_module)

            if func_info_dict[callee]["namespace"] == callee.split('.')[-1]:
                #是类的情况
                class_name = func_info_dict[callee]["namespace"]
                module_name = func_info_dict[callee]["filepath"].split('.')[-1]
                if contains_in_code(import_module + init_module,module_name) == False and contains_in_code(import_module,class_name)==False and func_info_dict[callee]["filepath"] != func_info_dict[caller]["filepath"]: #如果是相同文件下
                    continue
                # if caller.split('.')[-1] == "__init__" and func_info_dict[caller]["namespace"] == caller.split('.')[-2]:#调用者和被调用者都是__init__(类)的情况下,避免的只存在赋值，而没有初始化的情况
                #     continue

                if contains_in_code(caller_code ,class_name) == False:
                    if class_name not in import_collector.symbols:
                        continue
                    if class_name in import_collector.symbols and contains_in_code(caller_code,import_collector.symbols[class_name]) == False: # or callee + ".__init__"  not in func_info_dict:#必须存在__init_方法????
                        continue
 
                scopes = find_identifiers_scope(caller_code)  
                # if caller_name in scopes and class_name not in scopes[caller_name]["variable"] :
                #     continue    
                if caller_name in scopes:
                    if any(contains_in_code(callee, except_name) for except_name in scopes[caller_name]['exceptions']):
                        continue
                

                candidates.append(callee)
                
            elif callee.split('.')[-1].startswith("__") and callee.split('.')[-1].endswith("__"):
                # if callee.split('.')[-1] != "__init__" or callee.split('.')[-1] != "__enter__" or callee.split('.')[-1] != "__exit__":
                #     continue
                # 魔术方法
                module_name = func_info_dict[callee]["filepath"].split('.')[-1]
                class_name = func_info_dict[callee]["namespace"] 
                if class_name != "*" and contains_in_code(caller_code,class_name) and (contains_in_code(import_module + init_module,module_name) or func_info_dict[caller]["filepath"] == func_info_dict[callee]["filepath"]):
                    candidates.append(callee)
            elif contains_in_code(caller_code,callee.split('.')[-1]):
                #主要处理嵌套函数的情况，只有callee在当前caller主函数中有时才放入
                scopes = find_identifiers_scope(caller_code)
                module_name = func_info_dict[callee]["filepath"].split('.')[-1]
                class_name = func_info_dict[callee]["namespace"] # 类名在calle的倒数第二部分
                callee_name = callee.split('.')[-1]
                if caller == func_info_dict[caller]["filepath"]:#说明是global的情况
                    tmp_name = 'global'
                else :
                    tmp_name = caller_name

                if tmp_name in scopes:
                    # 这里如果类名在init也是可以的? variable防止变量赋值函数
                    if tmp_name in scopes and callee_name in scopes[tmp_name]['variable'] and (contains_in_code(caller_code,class_name) or (class_name in import_collector.symbols and contains_in_code(caller_code,import_collector.symbols[class_name]))  or class_name == func_info_dict[caller]["namespace"] or class_name == "*" ) and (contains_in_code(import_module + init_module,module_name) or func_info_dict[caller]["filepath"] == func_info_dict[callee]["filepath"]):
                        candidates.append(callee)
                    else :
                        if "_" in callee_name and callee_name in scopes[tmp_name]['variable']:#奇怪的优化，有_的，主要对应7.一个函数的返回值是类
                            candidates.append(callee) 
                        # if callee_name in scopes[tmp_name]['variable']:#奇怪的优化，有_的，主要对应7.一个函数的返回值是类
                        #     candidates.append(callee) 
                        else :
                            for tmp in scopes[tmp_name]['variable']:
                                if tmp.split('.')[0] == 'self' and tmp.split('.')[-1] == callee_name:
                                    candidates.append(callee)           
        candidate_callees[caller] = candidates
    return candidate_callees,candidate_callees_builtin,candidate_callees_stdlib,candidate_callees_non_stdlib,candidate_callees_stdlib_and_thirdlib




def solve(
    name="asciinema",
    all_or_EA=1,
    mode="candidates",
    api_key=None,
    base_url=None,
    model="gpt-5.4",
    confidence_threshold=60.0,
    max_candidates=None,
    start_index=0,
    output_path=None,
    metrics_output_path=None,
    checkpoint_path=None,
    workers=1,
    checkpoint_only=False,
):
    """Generate candidate edges or retain only edges accepted by an online model."""
    run_metrics = RunMetrics()

    filename_with_extension = "{}.json".format(name)
    pre_annotations_path = "../STAR/pre_knowledge/{}_pre_annotations.json".format(name)
    import_info_path = "../STAR/pre_knowledge/{}_import_info.json".format(name)
    inherited_info_path = "../STAR/pre_knowledge/{}_pre_inherited.json".format(name)

    choice = "api"
    #choice = "ollama"

    # 加载数据
    pre_annotations_data = load_json(pre_annotations_path)
    import_info = load_json(import_info_path)
    inherited_info = load_json(inherited_info_path)

    # 构建调用关系字典
    # call_dict, callee_to_callers_dict = build_call_dict_and_reverse(project_data)
    call_dict = {}
    # 构建函数信息字典
    func_info_dict = build_func_info_dict(pre_annotations_data)

    # 获取候选被调函数
    candidate_callees, candidate_callees_builtin, candidate_callees_stdlib, candidate_callees_non_stdlib, candidate_callees_stdlib_and_thirdlib = get_candidate_callees(name, call_dict, func_info_dict,import_info,all_or_EA)

    # Sample prompts.
    # 提示示例
    generating_prompts = []
    caller_candidates = []

    class call_info:
        def get(self,x):
            pass
        def __init__(self,caller,caller_code="",caller_init="",caller_import_info="",caller_file_path="",callee="",callee_code="",callee_init="",callee_import_info="",callee_file_path="",global_info="",system_prompt="",prompt_step1="",prompt_step2=""):
            self.caller = caller
            self.caller_code = caller_code
            self.caller_init = caller_init
            self.caller_import_info = caller_import_info
            self.caller_file_path = caller_file_path
            self.callee = callee
            self.callee_code = callee_code
            self.callee_init = callee_init
            self.callee_import_info = callee_import_info
            self.callee_file_path = callee_file_path
            self.global_info = global_info
            self.system_prompt = system_prompt
            self.prompt_step1 = prompt_step1
            self.prompt_step2 = prompt_step2
            #pass

    #内置函数
    call_info_list = []
    for caller, candidates in candidate_callees.items():
        global_info = ""
        grandcaller = ""
        # if caller in callee_to_callers_dict:
        #     for grandcaller_ in callee_to_callers_dict[caller]:
        #         if grandcaller_ in func_info_dict and func_info_dict[grandcaller_]["body"] != "":
        #             global_info = func_info_dict[grandcaller_]["body"]
        #             grandcaller = grandcaller_
        #             break
        # if global_info != "" and grandcaller in func_info_dict and func_info_dict[grandcaller]["filepath"] in import_info:
        #     global_info = import_info[func_info_dict[grandcaller]["filepath"]] + global_info
            
        for candidate in candidates:
            caller_code = ""
            candidate_code = ""
            #查找caller和candidate的代码
            caller_callee = call_info(caller)
            if caller in func_info_dict:
                caller_code = func_info_dict[caller]["body"]
                caller_code = remove_comments(caller_code)
                caller_callee.caller_code = caller_code
                caller_callee.caller_file_path = func_info_dict[caller]["filepath"]
                if func_info_dict[caller]["namespace"] != "*":
                    caller_class = ".".join(caller.rsplit(".", 1)[:-1])
                    caller_init = caller_class + ".__init__"
                    if caller_init in func_info_dict and caller_init != caller:
                        caller_init_code = func_info_dict[caller_init]["body"]
                        caller_init_code = remove_comments(caller_init_code)

                        #消融 wo-global
                        #caller_init_code = ""

                        if caller_class in inherited_info and inherited_info[caller_class]["inherited"]:  #有继承
                            #caller_code = "class "+ func_info_dict[caller]["namespace"] + "(" + inherited_info[caller_class]["inherited"][0] + ")" + ":\n" + caller_init_code + "\n" + caller_code
                            caller_callee.caller_code = "class "+ func_info_dict[caller]["namespace"] + "(" + inherited_info[caller_class]["inherited"][0] + ")" + ":\n" + caller_init_code + "\n" + caller_code
                            caller_callee.caller_init = caller_init_code
                        else :
                            #caller_code = "class "+ func_info_dict[caller]["namespace"] + ":\n" + caller_init_code + "\n" + caller_code
                            caller_callee.caller_code = "class "+ func_info_dict[caller]["namespace"] + ":\n" + caller_init_code + "\n" + caller_code
                            caller_callee.caller_init = caller_init_code
                    else :
                
                        if caller_class in inherited_info and inherited_info[caller_class]["inherited"]:
                            #caller_code = "class "+ func_info_dict[caller]["namespace"] + "(" + inherited_info[caller_class]["inherited"][0] + ")" + ":\n" + caller_code
                            caller_callee.caller_code = "class "+ func_info_dict[caller]["namespace"] + "(" + inherited_info[caller_class]["inherited"][0] + ")" + ":\n" + caller_code
                        else :
                            #caller_code = "class "+ func_info_dict[caller]["namespace"] + ":\n" + caller_code
                            caller_callee.caller_code = "class "+ func_info_dict[caller]["namespace"] + ":\n" + caller_code 

            if candidate in func_info_dict:
                caller_callee.callee = candidate
                candidate_code = func_info_dict[candidate]["body"]
                candidate_code = remove_comments(candidate_code)
                caller_callee.callee_code = candidate_code
                caller_callee.callee_file_path = func_info_dict[candidate]["filepath"]
                if func_info_dict[candidate]["namespace"] != "*":
                    candidate_class = ".".join(candidate.rsplit(".", 1)[:-1])
                    candidate_init = candidate_class + ".__init__"
                    if candidate_init in func_info_dict and candidate_init != candidate:
                        candidate_init_code = func_info_dict[candidate_init]["body"]
                        candidate_init_code = remove_comments(candidate_init_code)

                        #消融 wo-global
                        #candidate_init_code = ""

                        if candidate_class in inherited_info and inherited_info[candidate_class]["inherited"]:
                            #candidate_code = "class "+ func_info_dict[candidate]["namespace"] + "(" + inherited_info[candidate_class]["inherited"][0] + ")" + ":\n" + candidate_init_code + "\n" +  candidate_code
                            caller_callee.callee_code = "class "+ func_info_dict[candidate]["namespace"] + "(" + inherited_info[candidate_class]["inherited"][0] + ")" + ":\n" + candidate_init_code + "\n" +  candidate_code
                            caller_callee.callee_init = candidate_init_code
                        else: 
                            #candidate_code = "class "+ func_info_dict[candidate]["namespace"] + ":\n" + candidate_init_code + "\n" +  candidate_code
                            caller_callee.callee_code = "class "+ func_info_dict[candidate]["namespace"] + ":\n" + candidate_init_code + "\n" +  candidate_code
                            caller_callee.callee_init = candidate_init_code
                    else :
                        if candidate_class in inherited_info and inherited_info[candidate_class]["inherited"]:
                            #candidate_code = "class "+ func_info_dict[candidate]["namespace"] + "(" + inherited_info[candidate_class]["inherited"][0] + ")" + ":\n" + candidate_code
                            caller_callee.callee_code = "class "+ func_info_dict[candidate]["namespace"] + "(" + inherited_info[candidate_class]["inherited"][0] + ")" + ":\n" + candidate_code
                        else :
                            #candidate_code = "class "+ func_info_dict[candidate]["namespace"] + ":\n" + candidate_code
                            caller_callee.callee_code = "class "+ func_info_dict[candidate]["namespace"] + ":\n" + candidate_code
                       
            # if caller_code != "":
            #     caller_candidates.append({"caller":caller,"candidate":candidate})
            # 代码上加上import信息
            if caller in func_info_dict and func_info_dict[caller]["filepath"] in import_info:
                #caller_code = import_info[func_info_dict[caller]["filepath"]] + caller_code
                caller_callee.caller_import_info = import_info[func_info_dict[caller]["filepath"]]
            if candidate in func_info_dict and func_info_dict[candidate]["filepath"] in import_info:
                #candidate_code = import_info[func_info_dict[candidate]["filepath"]] + candidate_code   
                caller_callee.callee_import_info = import_info[func_info_dict[candidate]["filepath"]]  
            caller_callee.global_info = global_info

            caller_all_code=""
            callee_all_code=""
            if name == "micro-benchmark":
                try:
                    file_path = "../STAR/repo/{}.py".format('/'.join(caller_callee.caller_file_path.split('.')))
                    with open(file_path, "r", encoding="utf-8") as f:
                        caller_all_code = f.read()
                except:
                    file_path = "../STAR/repo/{}/__init__.py".format('/'.join(caller_callee.caller_file_path.split('.')))
                    with open(file_path, "r", encoding="utf-8") as f:
                        caller_all_code = f.read()
                try:
                    file_path = "../STAR/repo/{}.py".format('/'.join(caller_callee.callee_file_path.split('.')))
                    with open(file_path, "r", encoding="utf-8") as f:
                        callee_all_code = f.read()   
                except:
                    file_path = "../STAR/repo/{}/__init__.py".format('/'.join(caller_callee.callee_file_path.split('.')))
                    with open(file_path, "r", encoding="utf-8") as f:
                        callee_all_code = f.read()                       
            #prompts_info = "\n调用者名称:"+ caller + "\n调用者代码:\n" + caller_code+ "\n被调用者名称: " + candidate + "\n被调用者代码:\n" + candidate_code + "\n全局信息的代码:\n" + global_info
            caller_callee.system_prompt = system_prompt_comm

            #消融实验，缺失被调用者代码
            # caller_callee.callee_code = ""
            # caller_callee.caller_import_info = ""
            # caller_callee.callee_import_info =""
            # caller_callee.caller_file_path=""
            # caller_callee.callee_file_path=""

            caller_callee.prompt_step1 = user_prompt_comm_step1.format(
                caller = caller_callee.caller,
                caller_code = caller_callee.caller_code,
                callee = caller_callee.callee,
                callee_code = caller_callee.callee_code,
                global_info = caller_callee.global_info,
                caller_import_info = caller_callee.caller_import_info,
                callee_import_info = caller_callee.callee_import_info,
                caller_file_path = caller_callee.caller_file_path,
                callee_file_path = caller_callee.callee_file_path,
                caller_all_code = caller_all_code,
                callee_all_code = callee_all_code
            )
            caller_callee.prompt_step2 = user_prompt_comm_step2.format(
                caller = caller_callee.caller,
                callee = caller_callee.callee
            )
            #generating_prompts.append(prompts_info)
            call_info_list.append(caller_callee)

    for caller, candidates in candidate_callees_builtin.items():
        caller_code = ""
        for candidate in candidates:
            if caller in func_info_dict:
                caller_callee = call_info(caller)
                caller_callee.callee = candidate
                caller_code = func_info_dict[caller]["body"]
                caller_code = remove_comments(caller_code)
                caller_callee.caller_code = caller_code
                if func_info_dict[caller]["namespace"] != "*":
                    caller_class = ".".join(caller.rsplit(".", 1)[:-1])
                    caller_init = caller_class + ".__init__"
                    if caller_init in func_info_dict and caller_init != caller:
                        caller_init_code = func_info_dict[caller_init]["body"]
                        caller_init_code = remove_comments(caller_init_code)

                        #消融 wo-global
                        #caller_init_code = ""
                        
                        if caller_class in inherited_info and inherited_info[caller_class]["inherited"]:  #有继承
                            #caller_code = "class "+ func_info_dict[caller]["namespace"] + "(" + inherited_info[caller_class]["inherited"][0] + ")" + ":\n" + caller_init_code + "\n" + caller_code
                            caller_callee.caller_code = "class "+ func_info_dict[caller]["namespace"] + "(" + inherited_info[caller_class]["inherited"][0] + ")" + ":\n" + caller_init_code + "\n" + caller_code
                            caller_callee.caller_init = caller_init_code
                        else :
                            #caller_code = "class "+ func_info_dict[caller]["namespace"] + ":\n" + caller_init_code + "\n" + caller_code
                            caller_callee.caller_code = "class "+ func_info_dict[caller]["namespace"] + ":\n" + caller_init_code + "\n" + caller_code
                            caller_callee.caller_init = caller_init_code
                    else :
                        if caller_class in inherited_info and inherited_info[caller_class]["inherited"]:
                            #caller_code = "class "+ func_info_dict[caller]["namespace"] + "(" + inherited_info[caller_class]["inherited"][0] + ")" + ":\n" + caller_code
                            caller_callee.caller_code = "class "+ func_info_dict[caller]["namespace"] + "(" + inherited_info[caller_class]["inherited"][0] + ")" + ":\n" + caller_code
                        else :
                            #caller_code = "class "+ func_info_dict[caller]["namespace"] + ":\n" + caller_code
                            caller_callee.caller_code = "class "+ func_info_dict[caller]["namespace"] + ":\n" + caller_code

            caller_callee.global_info = global_info[:4000]
            # if caller_code != "":
            #     caller_candidates.append({"caller":caller,"candidate":candidate})

            #prompts_info = "\n调用者名称:"+ caller + "\n调用者代码:\n" + caller_code+ "\n被调用者名称: " + candidate
            callee_obj = ""
            if caller_callee.callee.split('.')[0] == "<**PyStr**>":
                callee_obj = "The string (str) object calls"
            elif caller_callee.callee.split('.')[0] == "<**PyList**>":
                callee_obj = "The list object calls"
            elif caller_callee.callee.split('.')[0] == "<**PyDict**>":
                callee_obj = "The dictionary (dict) object calls"
            elif caller_callee.callee.split('.')[0] == "<**PySet**>":
                callee_obj = "The set object calls"
            elif caller_callee.callee.split('.')[0] == "<**PyTuple**>":
                callee_obj = "The tuple object calls"
            elif caller_callee.callee.split('.')[0] == "<**PyNum**>":
                callee_obj = "The numeric (int type) object called"
            elif caller_callee.callee.split('.')[0] == "<**PyFile**>":
                callee_obj = "The file object calls"
            elif caller_callee.callee.split('.')[0] == "<builtin>":
                callee_obj = "Python built-in functions"

            caller_callee.caller_code = caller_callee.caller_code[:10000]
            caller_callee.callee_code = caller_callee.callee_code[:2000]
            caller_callee.system_prompt = system_prompt_builtin
            caller_callee.prompt_step1 = user_prompt_builtin_step1.format(
                caller = caller_callee.caller,
                caller_code = caller_callee.caller_code,
                callee = caller_callee.callee,
                callee_code = caller_callee.callee_code,
                global_info = caller_callee.global_info,
                caller_import_info = caller_callee.caller_import_info,
                callee_name = caller_callee.callee.split('.')[-1]
            )

            caller_callee.prompt_step2 = user_prompt_builtin_step2.format(
                caller = caller_callee.caller,
                callee = caller_callee.callee,
                callee_name = caller_callee.callee.split('.')[-1],
                callee_obj = callee_obj
            )
            #generating_prompts.append(prompts_info)
            call_info_list.append(caller_callee)

    for key in candidate_callees_stdlib_and_thirdlib:#删除local_name
        candidate_callees_stdlib_and_thirdlib[key] = [
            s for s in candidate_callees_stdlib_and_thirdlib[key] 
            if not any((s == k or s in k) and func_info_dict.get(k, {}).get("name_type") == "local_name" 
                    for k in func_info_dict)
        ]
    for key in candidate_callees_stdlib_and_thirdlib:#删除name
        candidate_callees_stdlib_and_thirdlib[key] = [
            s for s in candidate_callees_stdlib_and_thirdlib[key] 
            if name not in s
        ]
    if all_or_EA == 0:
        candidate_callees_stdlib_and_thirdlib = {}
        # for key in candidate_callees_stdlib_and_thirdlib:#删除thirdlib
        #     candidate_callees_stdlib_and_thirdlib[key] = [
        #         s for s in candidate_callees_stdlib_and_thirdlib[key] 
        #         if not any((s == k or s in k or k.split('.')[0] in s) and func_info_dict.get(k, {}).get("name_type") == "third library" 
        #             for k in func_info_dict)
        #     ]


    for caller,candidates in candidate_callees_stdlib_and_thirdlib.items():
        caller_code = ""
        for candidate in candidates:
            if caller in func_info_dict:
                caller_callee = call_info(caller)
                caller_callee.callee = candidate
                caller_code = func_info_dict[caller]["body"]
                caller_code = remove_comments(caller_code)
                caller_callee.caller_code = caller_code
                if func_info_dict[caller]["namespace"] != "*":
                    caller_class = ".".join(caller.rsplit(".", 1)[:-1])
                    caller_init = caller_class + ".__init__"
                    if caller_init in func_info_dict and caller_init != caller:
                        caller_init_code = func_info_dict[caller_init]["body"]
                        caller_init_code = remove_comments(caller_init_code)

                        #消融 wo-global
                        #caller_init_code = ""
                        
                        if caller_class in inherited_info and inherited_info[caller_class]["inherited"]:  #有继承
                            #caller_code = "class "+ func_info_dict[caller]["namespace"] + "(" + inherited_info[caller_class]["inherited"][0] + ")" + ":\n" + caller_init_code + "\n" + caller_code
                            caller_callee.caller_code = "class "+ func_info_dict[caller]["namespace"] + "(" + inherited_info[caller_class]["inherited"][0] + ")" + ":\n" + caller_init_code + "\n" + caller_code
                            caller_callee.caller_init = caller_init_code
                        else :
                            #caller_code = "class "+ func_info_dict[caller]["namespace"] + ":\n" + caller_init_code + "\n" + caller_code
                            caller_callee.caller_code = "class "+ func_info_dict[caller]["namespace"] + ":\n" + caller_init_code + "\n" + caller_code
                            caller_callee.caller_init = caller_init_code
                    else :
                        if caller_class in inherited_info and inherited_info[caller_class]["inherited"]:
                            #caller_code = "class "+ func_info_dict[caller]["namespace"] + "(" + inherited_info[caller_class]["inherited"][0] + ")" + ":\n" + caller_code
                            caller_callee.caller_code = "class "+ func_info_dict[caller]["namespace"] + "(" + inherited_info[caller_class]["inherited"][0] + ")" + ":\n" + caller_code
                        else :
                            #caller_code = "class "+ func_info_dict[caller]["namespace"] + ":\n" + caller_code
                            caller_callee.caller_code = "class "+ func_info_dict[caller]["namespace"] + ":\n" + caller_code

            caller_callee.caller_code = caller_callee.caller_code[:10000]
            caller_callee.callee_code = caller_callee.callee_code[:2000]

            #消融实验，缺失被调用者代码
            #caller_callee.callee_code = ""

            caller_callee.system_prompt = system_prompt_stdlib_and_thirdlib
            caller_callee.prompt_step1 = user_prompt_stdlib_and_thirdlib_step1.format(
                caller = caller_callee.caller,
                caller_code = caller_callee.caller_code,
                callee = caller_callee.callee,
                callee_code = caller_callee.callee_code,
                global_info = caller_callee.global_info,
                caller_import_info = caller_callee.caller_import_info,
                callee_name = caller_callee.callee.split('.')[-1]
            )

            caller_callee.prompt_step2 = user_prompt_stdlib_and_thirdlib_step2.format(
                caller = caller_callee.caller,
                callee = caller_callee.callee,
                callee_name = caller_callee.callee.split('.')[-1],
                callee_obj = callee_obj
            )
            #generating_prompts.append(prompts_info)
            call_info_list.append(caller_callee)
            



    unique_calls = {}
    for call in call_info_list:
        unique_calls.setdefault((call.caller, call.callee), call)
    call_info_list = list(unique_calls.values())
    call_info_list, parameter_mismatch_rejections = filter_call_infos_by_parameter_count(
        call_info_list, func_info_dict
    )
    if name == "micro-benchmark":
        invalid_candidates = [
            (call.caller, call.callee)
            for call in call_info_list
            if call.caller in func_info_dict
            and call.callee in func_info_dict
            and micro_benchmark_case_id(func_info_dict[call.caller])
            != micro_benchmark_case_id(func_info_dict[call.callee])
        ]
        if invalid_candidates:
            raise AssertionError(
                "Cross-case micro-benchmark candidates are forbidden: {}".format(
                    invalid_candidates[:3]
                )
            )
    if start_index:
        call_info_list = call_info_list[start_index:]

    with open("./prompt/{}_prompt_update.txt".format(name),"w",encoding="utf-8") as f:
        for call in call_info_list:
            f.write(str(call.system_prompt[:9000]))
            f.write(str(call.prompt_step1[:10000]))
            f.write(str(call.prompt_step2[:9000]))
            f.write("\n\n\n")
    print("{:<20} total prompts:".format(name),end="")
    print(len(call_info_list))
    if max_candidates is not None:
        call_info_list = call_info_list[:max_candidates]
        print("{:<20} processing prompts:".format(name), len(call_info_list))
    candidate_count = len(call_info_list)
    custom_id = 0
    start_id = custom_id
    with open('./data/{}_data.csv'.format(name), mode='w', newline='', encoding='utf-8') as file:
        writer = csv.writer(file)
        for call in call_info_list:
            writer.writerow([custom_id, call.system_prompt[:9000], call.prompt_step1[:10000] + call.prompt_step2[:9000], call.caller,call.callee,name])
            custom_id += 1

    project_data = {}
    file2class = {}
    for i, call in enumerate(call_info_list):  
        caller, candidate = call.caller, call.callee
        if caller in project_data:
            project_data[caller].append(candidate)  # 将 candidate 添加到原列表
            # 去重
            project_data[caller] = list(set(project_data[caller]))
        else:
            project_data[caller] = []
            project_data[caller].append(candidate)  # 如果 caller 不存在，直接插入        
    graph_output_path = output_path or "../Ae_data/{}".format(filename_with_extension)
    metrics_output_path = metrics_output_path or "../Ae_data/{}_metrics.json".format(name)
    if all_or_EA == 0 and name != "micro-benchmark":
        for caller in func_info_dict:
            if func_info_dict[caller]["namespace"] == caller.split('.')[-1]:
                if func_info_dict[caller]["filepath"] in file2class:
                    file2class[func_info_dict[caller]["filepath"]].append(caller)
                    file2class[func_info_dict[caller]["filepath"]] = list(set(file2class[func_info_dict[caller]["filepath"]]))
                else:
                    file2class[func_info_dict[caller]["filepath"]] = []
                    file2class[func_info_dict[caller]["filepath"]].append(caller)
        for caller in import_info:
            tree = ast.parse(import_info[caller])
            import_collector = ImportCollector()
            import_collector.visit(tree)
            for callee,_ in import_collector.symbols.items():
                if name not in callee or '*' in callee:
                    continue
                callee = str(callee)
                if caller in file2class:
                    file2class[caller].append(callee)
                    file2class[caller] = list(set(file2class[caller]))
                else:
                    file2class[caller] = []
                    file2class[caller].append(callee)


    for caller,candidate in candidate_callees_stdlib_and_thirdlib.items():
        if caller in project_data:
            project_data[caller].extend(candidate)
        else :
            project_data[caller]=candidate
    # for caller,candidate in call_dict.items():
    #     if caller in project_data:
    #         project_data[caller].extend(candidate)
    #     else :
    #         project_data[caller]=candidate        
    if mode == "candidates":
        skipped_third_party_callers = remove_third_party_callers(project_data, func_info_dict)
        merged_file2class_edges = 0
        skipped_external_file2class_edges = 0
        if all_or_EA == 0:
            merged_file2class_edges, skipped_external_file2class_edges = merge_project_file2class_edges(
                project_data, file2class, name
            )
        duplicate_edges_removed = deduplicate_call_graph(project_data)
        with open(graph_output_path, "w", encoding="utf-8") as file:
            json.dump(project_data, file, indent=4, ensure_ascii=False)
        with open("../file2class_data/{}".format(filename_with_extension), "w", encoding="utf-8") as file:
            json.dump(file2class, file, indent=4, ensure_ascii=False)
        with open("../stdlib_and_thirdlib_data/{}".format(filename_with_extension), "w", encoding="utf-8") as file:
            json.dump(candidate_callees_stdlib_and_thirdlib, file, indent=4, ensure_ascii=False)
        report = write_run_metrics(
            metrics_output_path,
            run_metrics,
            status="completed",
            project=name,
            mode=mode,
            candidate_count=candidate_count,
            predicted_edge_count=sum(len(callees) for callees in project_data.values()),
            skipped_third_party_callers=skipped_third_party_callers,
            merged_file2class_edges=merged_file2class_edges,
            skipped_external_file2class_edges=skipped_external_file2class_edges,
            duplicate_edges_removed=duplicate_edges_removed,
            parameter_mismatch_rejections=parameter_mismatch_rejections,
            prompt_tokens=0,
            completion_tokens=0,
            total_tokens=0,
            session_prompt_tokens=0,
            session_completion_tokens=0,
            session_total_tokens=0,
        )
        print(
            "Metrics: total {:.2f}s (pipeline {:.2f}s), peak RSS {:.1f} MiB, tokens 0".format(
                report["process_wall_time_seconds"],
                report["pipeline_wall_time_seconds"],
                report["peak_rss_mib"],
            )
        )
        return project_data
    if mode != "infer":
        raise ValueError("mode must be 'candidates' or 'infer'")
    if not api_key and not checkpoint_only:
        raise ValueError("OPENAI_API_KEY is required when mode is 'infer'")

    client = None if checkpoint_only else OpenAI(api_key=api_key, base_url=base_url)

    vote_time = 1
    outputs = [[] for _ in range(vote_time)]
    token_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    # Candidate generation above is intentionally retained for inspection. Inference
    # starts with an empty graph and adds only edges the model accepts.
    project_data = {}
    messages_list = []
    checkpoint_path = checkpoint_path or "{}.infer.checkpoint.json".format(
        os.path.splitext(os.path.abspath(graph_output_path))[0]
    )
    checkpoint = load_inference_checkpoint(checkpoint_path, name, model)
    checkpoint_hits = 0
    failed_candidates = []
    attempted_candidates = 0
    missing_checkpoint_candidates = []
    events_since_compaction = 0

    def matching_checkpoint_counts():
        completed = 0
        failed = 0
        for call in call_info_list:
            key = inference_checkpoint_key(call)
            fingerprint = inference_prompt_fingerprint(call)
            response = checkpoint["responses"].get(key)
            if response and response.get("prompt_fingerprint") == fingerprint:
                completed += 1
                continue
            failure = checkpoint["failures"].get(key)
            if failure and failure.get("prompt_fingerprint") == fingerprint:
                failed += 1
        return completed, failed

    def persist_inference_metrics(status):
        completed, pending_failures = matching_checkpoint_counts()
        return write_metrics_snapshot(
            metrics_output_path,
            run_metrics,
            status=status,
            project=name,
            mode=mode,
            model=model,
            candidate_count=candidate_count,
            inference_completed_candidates=completed,
            inference_checkpoint_hits=checkpoint_hits,
            inference_attempted_candidates=attempted_candidates,
            inference_failed_candidates=len(failed_candidates),
            inference_missing_checkpoint_candidates=len(missing_checkpoint_candidates),
            inference_pending_failures=pending_failures,
            inference_checkpoint_path=checkpoint_path,
            prompt_tokens=checkpoint["token_usage"]["prompt_tokens"],
            completion_tokens=checkpoint["token_usage"]["completion_tokens"],
            total_tokens=checkpoint["token_usage"]["total_tokens"],
            session_prompt_tokens=token_usage["prompt_tokens"],
            session_completion_tokens=token_usage["completion_tokens"],
            session_total_tokens=token_usage["total_tokens"],
        )

    def persist_inference_event(event):
        nonlocal events_since_compaction
        append_inference_checkpoint_event(checkpoint_path, checkpoint, event)
        events_since_compaction += 1
        persist_inference_metrics("in_progress")
        if events_since_compaction >= 50:
            save_inference_checkpoint(checkpoint_path, checkpoint)
            events_since_compaction = 0

    persist_inference_metrics("in_progress")

    def infer_one(index, call):
        last_error = None
        usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        for attempt in range(3):
            try:
                messages = [{"role": "system", "content": call.system_prompt[:7000]}]
                messages.append({"role": "user", "content": call.prompt_step1[:7000]})
                step1_response = client.chat.completions.create(
                    model=model,
                    messages=messages,
                )
                step1 = step1_response.choices[0].message.content
                for key, value in response_token_usage(step1_response).items():
                    usage[key] += value
                messages.append({"role": "assistant", "content": step1})
                messages.append({"role": "user", "content": call.prompt_step2[:7000]})
                step2_response = client.chat.completions.create(
                    model=model,
                    messages=messages,
                )
                step2 = step2_response.choices[0].message.content
                for key, value in response_token_usage(step2_response).items():
                    usage[key] += value
                return index, step1, step2, usage, None
            except Exception as error:
                last_error = error
                if attempt < 2:
                    time_module.sleep(2 ** attempt)
        return index, None, None, usage, str(last_error)

    if checkpoint_only:
        cached_outputs = []
        for call in tqdm(call_info_list, desc="Loading inference checkpoint"):
            key = inference_checkpoint_key(call)
            fingerprint = inference_prompt_fingerprint(call)
            cached = checkpoint["responses"].get(key)
            if cached and cached.get("prompt_fingerprint") == fingerprint:
                cached_outputs.append(cached.get("step2"))
                checkpoint_hits += 1
            else:
                cached_outputs.append(None)
                missing_checkpoint_candidates.append((call.caller, call.callee))
        outputs[0] = cached_outputs
    elif workers > 1:
        parallel_outputs = [None] * len(call_info_list)
        pending_calls = []
        for index, call in enumerate(call_info_list):
            key = inference_checkpoint_key(call)
            fingerprint = inference_prompt_fingerprint(call)
            cached = checkpoint["responses"].get(key)
            if cached and cached.get("prompt_fingerprint") == fingerprint:
                parallel_outputs[index] = cached.get("step2")
                checkpoint_hits += 1
            else:
                pending_calls.append((index, call, key, fingerprint))
        attempted_candidates += len(pending_calls)
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(infer_one, index, call): (index, call, key, fingerprint)
                for index, call, key, fingerprint in pending_calls
            }
            for future in tqdm(as_completed(futures), total=len(futures), desc="Processing online inference"):
                index, call, key, fingerprint = futures[future]
                _, step1, step2, usage, error = future.result()
                if error is not None:
                    for usage_key, value in usage.items():
                        token_usage[usage_key] += value
                    persist_inference_event({
                        "kind": "failure",
                        "key": key,
                        "record": {
                            "caller": call.caller,
                            "callee": call.callee,
                            "prompt_fingerprint": fingerprint,
                            "error": error,
                        },
                        "usage": usage,
                    })
                    failed_candidates.append((call.caller, call.callee))
                else:
                    parallel_outputs[index] = step2
                    for usage_key, value in usage.items():
                        token_usage[usage_key] += value
                    persist_inference_event({
                        "kind": "response",
                        "key": key,
                        "record": {
                            "caller": call.caller,
                            "callee": call.callee,
                            "prompt_fingerprint": fingerprint,
                            "step2": step2,
                        },
                        "usage": usage,
                    })
                    with open("./infer_log/infer_{}.txt".format(name), "a", encoding="utf-8") as stream:
                        stream.write(call.prompt_step1[:7000] + "\n")
                        stream.write("Step 1:\n" + str(step1) + "\n\n")
                        stream.write(str(step2) + "\n\n\n")
                
        outputs[0] = parallel_outputs

    for j in range(vote_time if workers == 1 and not checkpoint_only else 0):
        for i, call in enumerate(tqdm(call_info_list, desc="Processing generate yesno")):
            key = inference_checkpoint_key(call)
            fingerprint = inference_prompt_fingerprint(call)
            cached = checkpoint["responses"].get(key)
            if cached and cached.get("prompt_fingerprint") == fingerprint:
                outputs[j].append(cached.get("step2"))
                checkpoint_hits += 1
                continue

            attempted_candidates += 1
            _, step1, step2, usage, error = infer_one(i, call)
            if error is not None:
                for usage_key, value in usage.items():
                    token_usage[usage_key] += value
                persist_inference_event({
                    "kind": "failure",
                    "key": key,
                    "record": {
                        "caller": call.caller,
                        "callee": call.callee,
                        "prompt_fingerprint": fingerprint,
                        "error": error,
                    },
                    "usage": usage,
                })
                failed_candidates.append((call.caller, call.callee))
                outputs[j].append(None)
                continue

            for usage_key, value in usage.items():
                token_usage[usage_key] += value
            persist_inference_event({
                "kind": "response",
                "key": key,
                "record": {
                    "caller": call.caller,
                    "callee": call.callee,
                    "prompt_fingerprint": fingerprint,
                    "step2": step2,
                },
                "usage": usage,
            })
            outputs[j].append(step2)
            with open("./infer_log/infer_{}.txt".format(name), "a", encoding="utf-8") as stream:
                stream.write(call.prompt_step1[:7000] + "\n")
                stream.write("Step 1:\n" + str(step1) + "\n\n")
                stream.write(str(step2) + "\n\n\n")
            continue



    
    
    result = [[0] * len(call_info_list) for _ in range(vote_time)]
    def extract_percentage(text):
        match = re.search(r'(?<![-\d])(?:100|[1-9]?\d(?:\.\d)?)%(?!\d)', text)
        return match.group(0) if match else None
    for j in range(vote_time):
        for i, output in enumerate(outputs[j]):
            generated_text = output
            if generated_text is None:
                continue
            precent = extract_percentage(generated_text)
            if precent:
                percent = float(precent.rstrip('%'))
                if percent > confidence_threshold:
                    result[j][i] += 1


    for i, call in enumerate(call_info_list):
        
        caller, candidate = call.caller, call.callee
        yes_total = 0
        for j in range(vote_time):
            yes_total += result[j][i]
        if yes_total > vote_time/2:
            if caller in project_data:
                project_data[caller].append(candidate)  # 将 candidate 添加到原列表
                # 去重
                project_data[caller] = list(set(project_data[caller]))
            else:
                project_data[caller] = [candidate]

    graph_output_path = output_path or "../Ae_data/{}".format(filename_with_extension)
    skipped_third_party_callers = remove_third_party_callers(project_data, func_info_dict)
    merged_file2class_edges = 0
    skipped_external_file2class_edges = 0
    if all_or_EA == 0:
        merged_file2class_edges, skipped_external_file2class_edges = merge_project_file2class_edges(
            project_data, file2class, name
        )
    duplicate_edges_removed = deduplicate_call_graph(project_data)
    with open(graph_output_path, "w", encoding="utf-8") as file:
        json.dump(project_data, file, indent=4, ensure_ascii=False)
    if all_or_EA == 0:
        with open("../file2class_data/{}".format(filename_with_extension), "w", encoding="utf-8") as file:
            json.dump(file2class, file, indent=4, ensure_ascii=False)
    save_inference_checkpoint(checkpoint_path, checkpoint)
    completed_candidates, pending_failures = matching_checkpoint_counts()
    report = write_run_metrics(
        metrics_output_path,
        run_metrics,
        status="incomplete" if pending_failures or missing_checkpoint_candidates else "completed",
        project=name,
        mode=mode,
        model=model,
        candidate_count=candidate_count,
        predicted_edge_count=sum(len(callees) for callees in project_data.values()),
        skipped_third_party_callers=skipped_third_party_callers,
        merged_file2class_edges=merged_file2class_edges,
        skipped_external_file2class_edges=skipped_external_file2class_edges,
        duplicate_edges_removed=duplicate_edges_removed,
        parameter_mismatch_rejections=parameter_mismatch_rejections,
        inference_checkpoint_path=checkpoint_path,
        inference_completed_candidates=completed_candidates,
        inference_checkpoint_hits=checkpoint_hits,
        inference_attempted_candidates=attempted_candidates,
        inference_failed_candidates=len(failed_candidates),
        inference_missing_checkpoint_candidates=len(missing_checkpoint_candidates),
        inference_pending_failures=pending_failures,
        prompt_tokens=checkpoint["token_usage"]["prompt_tokens"],
        completion_tokens=checkpoint["token_usage"]["completion_tokens"],
        total_tokens=checkpoint["token_usage"]["total_tokens"],
        session_prompt_tokens=token_usage["prompt_tokens"],
        session_completion_tokens=token_usage["completion_tokens"],
        session_total_tokens=token_usage["total_tokens"],
    )
    print(
        "Metrics: total {:.2f}s (pipeline {:.2f}s), peak RSS {:.1f} MiB, tokens {} (prompt {}, completion {})".format(
            report["process_wall_time_seconds"],
            report["pipeline_wall_time_seconds"],
            report["peak_rss_mib"],
            report["total_tokens"],
            report["prompt_tokens"],
            report["completion_tokens"],
        )
    )
    if failed_candidates:
        print(
            "Inference checkpoint saved with {} failed candidates. Rerun the same command to retry only them.".format(
                len(failed_candidates)
            )
        )
    elif checkpoint_hits:
        print("Inference checkpoint reused {} successful candidates.".format(checkpoint_hits))
    if checkpoint_only and missing_checkpoint_candidates:
        print(
            "Checkpoint-only mode omitted {} candidates without cached successful results.".format(
                len(missing_checkpoint_candidates)
            )
        )
    return project_data
    

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Infer a Python call graph for one project.")
    parser.add_argument("--project", required=True, help="Project artifact name, e.g. micro-benchmark.")
    parser.add_argument("--mode", choices=("candidates", "infer"), default="candidates")
    parser.add_argument("--model", default="gpt-5.4")
    parser.add_argument(
        "--base-url",
        default=os.environ.get("OPENAI_BASE_URL", "https://api.example.com/v1"),
        help="OpenAI-compatible API base URL (default: OPENAI_BASE_URL or https://api.example.com/v1).",
    )
    parser.add_argument("--confidence-threshold", type=float, default=60.0)
    parser.add_argument("--max-candidates", type=int, default=None)
    parser.add_argument("--start-index", type=int, default=0)
    parser.add_argument("--output", default=None, help="Output graph path; useful for batch shards.")
    parser.add_argument("--metrics-output", default=None, help="JSON path for duration, memory, and token metrics.")
    parser.add_argument("--workers", type=int, default=1, help="Concurrent online inference requests.")
    parser.add_argument(
        "--checkpoint-only",
        action="store_true",
        help="Reuse cached inference responses only; never call the online model.",
    )
    parser.add_argument("--all-or-ea", type=int, choices=(0, 1), default=0)
    args = parser.parse_args()
    output_path = os.path.abspath(args.output) if args.output else None
    metrics_output_path = os.path.abspath(args.metrics_output) if args.metrics_output else None

    # The pipeline still uses relative data directories, so make CLI execution
    # independent of the directory from which Python was started.
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    solve(
        name=args.project,
        all_or_EA=args.all_or_ea,
        mode=args.mode,
        api_key=os.environ.get("OPENAI_API_KEY"),
        base_url=args.base_url,
        model=args.model,
        confidence_threshold=args.confidence_threshold,
        max_candidates=args.max_candidates,
        start_index=args.start_index,
        output_path=output_path,
        metrics_output_path=metrics_output_path,
        workers=args.workers,
        checkpoint_only=args.checkpoint_only,
    )
    raise SystemExit(0)

    print("strat1...")
    project_name_list_1 = ["asciinema","autojump","fabric","face_classification","Sublist3r"]
    project_name_list_2 = ['bpytop','furl','rich_cli','sqlparse','sshtunnel','textrank4zh']
    project_list_id = [
        1,3,4,6,7,8,9,11,12,13,14,15,16,17,18,19,20,22,23,24,25,28,29,31,32,33,35,36,37,38,45,46,48,50,52,53,56,57,58
    ]

    for project_name in project_name_list_1:
        solve(project_name, 1)
    for project_name in project_name_list_2:
        solve(project_name, 0)


