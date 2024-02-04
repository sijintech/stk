import json
import os
this_dir=os.path.dirname(os.path.abspath(__file__))
conf_json_path=os.path.join(this_dir,"src-tauri\\tauri.conf.json")
with open(conf_json_path, 'r') as f:
    data = json.load(f)

# 从环境变量中获取 tag

tag = os.environ.get('TAG', '')
data['package']['version'] = tag
# data['package']['version'] = "0.0.3"
with open(conf_json_path, 'w') as f:

    json.dump(data, f, indent=2)