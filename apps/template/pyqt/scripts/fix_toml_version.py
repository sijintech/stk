import os
import toml


this_dir = os.path.dirname(os.path.abspath(__file__))
toml_path = os.path.join(this_dir, "../confs/pyproject.toml")


# Read the pyproject.toml file

with open(toml_path, "r") as f:
    data = toml.load(f)


# 从环境变量中获取 tag

tag = os.environ.get('TAG', '')

# Modify the version

data["project"]["version"] = tag

# data['project']['version'] = "0.0.34"

with open(toml_path, 'w') as f:


    toml.dump(data, f)