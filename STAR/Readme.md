This documentation shows how to use STAR.

You can run the command:
```
python main.py [pro_name,pro_path,depconfig_path]
```
- pro_name: the project name 
- pro_path: the file path of the project 
- depconfig_path: the path for dependency configuration file such as setup.py or the path of the searched project

For example (also a test):
```
1. python main.py  flask repo/flask/src/flask repo/flask/setup.py
2. python main.py  flask repo/flask/src/flask repo/flask
```

The outputs are:
- Collected dependencies: in the 'depData' folder
- Generated entity information: in the 'pre_knowledge' folder 
- Generated call graph: in the 'result' folder

Required: Python 3.9