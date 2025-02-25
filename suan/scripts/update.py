import json
import os

import oss2

from oss2.credentials import EnvironmentVariableCredentialsProvider

# import sys


auth = oss2.ProviderAuth(EnvironmentVariableCredentialsProvider())


bucket = oss2.Bucket(auth, os.environ['OSS_ENDPOINT'], os.environ['OSS_BUCKET'])


# 填写Object完整路径，完整路径中不包含Bucket名称，例如testfolder/exampleobject.txt。

# 下载Object到本地文件，并保存到指定的本地路径D:\\localpath\\examplefile.txt。如果指定的本地文件存在会覆盖，不存在则新建。

this_dir = os.path.dirname(os.path.abspath(__file__))
update_json_path = os.path.join(this_dir, "../confs/update.json")

bucket.get_object_to_file('update.json', update_json_path)


source_dir = os.path.join(this_dir, os.environ['SOURCE_DIR'])
target_dir = os.environ['TARGET_DIR']
oss_path = "../confs/update.json"


# 读取 update.json

with open(update_json_path, 'r') as f:

    data = json.load(f)


# 从环境变量中获取 tag

tag = os.environ.get('TAG', '')


# 更新 updateData 中的version 和 releasetime

data['version'] = tag
data['releasetime'] = '${{ github.event.head_commit.timestamp }}'

for file in os.listdir(source_dir):

    if file.endswith('suan_pyqt.exe'):

        download_path="https://sijin-suan-update.oss-cn-beijing.aliyuncs.com/nsis/"+file

        data['win_download']= download_path



# 将修改后的数据保存回 update.json

with open(update_json_path, 'w') as f:

    json.dump(data, f, indent=2)


# 上传update.json

with open(update_json_path, 'rb') as fileobj:

    bucket.put_object(oss_path, fileobj)

print(f"Uploaded {update_json_path} to OSS path {oss_path}")

