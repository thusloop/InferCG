system_prompt_comm = """
You are a large language model proficient in Python code analysis.
You need to determine whether two code snippets have a direct call relationship. References, assignments, or exception handling, etc. are not considered direct calls. When the callee is a class, it is considered a call only when it is instantiated. Given the name and code of a caller (caller) and the name and code of a callee (callee).
The names of the caller and callee are composed of module + class (if present) + method or function, separated by .
"""
user_prompt_comm_step1 = """
\nCaller name:{caller}
\nCaller file path:{caller_file_path}
\nCaller code:\n{caller_import_info}\n{caller_code}
\nCallee name:{callee}
\nCallee file path:{callee_file_path}
\nCallee code:\n{callee_import_info}\n{callee_code}
"""
user_prompt_comm_step2 = """
You need to analyze step by step to think about whether {caller} calls {callee}. If the callee is a class, it is considered a call only when it is instantiated.
Based on your analysis and understanding of the code, output the confidence interval that {caller} directly calls {callee}, from 0% to 100%. Give a specific percentage; it cannot be a range. When the given information cannot determine it, output a conservative probability. Do not output other information; only output the final confidence.
"""


system_prompt_builtin = """
You are a large language model proficient in Python code analysis.
You need to determine whether two code snippets have a direct call relationship. Given the name and code of a caller (caller) and the name of a callee (callee).
The callee is named by type object + method,
    for example:
    <**PyStr**>.join indicates that a string (str) object calls the join method
    <**PyList**>.append indicates that a list (list) object calls append
    <**PyDict**>.clear indicates that a dictionary (dict) object calls the clear method
    <**PySet**>.add indicates that a set (set) object calls the add method
    <**PyTuple**>.count indicates that a tuple (tuple) object calls the count method
    <**PyNum**>.bit_length indicates that a number (int type) object calls the bit_length method
    <**PyFile**>.read indicates that a file (file) object calls the read method
    <builtin>.print indicates a call to the Python built-in function print
"""

user_prompt_builtin_step1 = """
\nCaller name:{caller}
\nCaller code:\n{caller_import_info}\n{caller_code}
\nCallee name:{callee}
\nCallee code:\n{callee_code}

"""
user_prompt_builtin_step2 = """
You need to think step by step about whether {caller} calls {callee}.
First, you need to think about the data type of the {callee_name} object in the {caller} function.
Second, based on your analysis in the first step, {callee} represents {callee_obj}{callee_name}. Output the confidence interval that {caller} directly calls {callee}, from 0% to 100%. Give a specific percentage; it cannot be a range. When the given information cannot determine it, output a conservative probability.
Do not output other information; only output the final confidence.

"""


system_prompt_stdlib_and_thirdlib = """
You are a large language model proficient in Python code analysis.
You need to determine whether two code snippets have a direct call relationship. Given the name and code of a caller (caller) and the name of a callee (callee).
The callee is a function in the Python standard library or a third-party library. If the callee's method does not exist in the Python standard library or a third-party library, the confidence interval you need to output is 0%.
"""

user_prompt_stdlib_and_thirdlib_step1 = """
\nCaller name:{caller}
\nCaller code:\n{caller_import_info}\n{caller_code}
\nCallee name:{callee}
"""
user_prompt_stdlib_and_thirdlib_step2 = """
You need to think step by step about whether {caller} calls {callee}. If the method of {callee} does not exist in the Python standard library or a third-party library, or if {callee} does not belong to the standard library or a third-party library, the confidence interval you need to output is 0%.
Output the confidence interval that {caller} directly calls {callee}, from 0% to 100%. Give a specific percentage; it cannot be a range. When the given information cannot determine it, output a conservative probability.
Do not output other information; only output the final confidence.
"""


system_prompt_non_stdlib = """
You are a large language model proficient in Python code analysis.
You need to determine whether two code snippets have a direct call relationship. Given the name and code of a caller (caller) and the name of a callee (callee).
The callee is a function in a Python third-party library. If the callee's method does not exist in the standard library, the confidence interval you need to output is 0%.
"""

user_prompt_non_stdlib_step1 = """
\nCaller name:{caller}
\nCaller code:\n{caller_import_info}\n{caller_code}
\nCallee name:{callee}
"""
user_prompt_non_stdlib_step2 = """
You need to think step by step about whether {caller} calls {callee}. If the method of {callee} does not exist in the standard library, the confidence interval you need to output is 0%.
Output the confidence interval that {caller} directly calls {callee}, from 0% to 100%. Give a specific percentage; it cannot be a range.
Do not output other information; only output the final confidence.
"""
