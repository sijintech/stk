import json
import os

import oss2

from oss2.credentials import EnvironmentVariableCredentialsProvider

# import sys


auth = oss2.ProviderAuth(EnvironmentVariableCredentialsProvider())


bucket = oss2.Bucket(auth, os.environ['OSS_ENDPOINT'], os.environ['OSS_BUCKET'])


# 填写Object完整路径，完整路径中不包含Bucket名称，例如testfolder/exampleobject.txt。

# 下载Object到本地文件，并保存到指定的本地路径D:\\localpath\\examplefile.txt。如果指定的本地文件存在会覆盖，不存在则新建。

this_dir=os.path.dirname(os.path.abspath(__file__))
update_json_path=os.path.join(this_dir,"update.json")

bucket.get_object_to_file('update.json', update_json_path)


source_dir = os.path.join(this_dir, os.environ['SOURCE_DIR'])
target_dir = os.environ['TARGET_DIR']
oss_path="update.json"


# 读取 update.json

with open(update_json_path, 'r') as f:

    data = json.load(f)


# 从环境变量中获取 tag

tag = os.environ.get('TAG', '')


# 更新 updateData 中的 name 和 pub_date

data['version'] = tag

data['pub_date'] = '${{ github.event.head_commit.timestamp }}'

for file in os.listdir(source_dir):


    if file.endswith('.msi.zip'):

        download_path="https://sijin-suan-update.oss-cn-beijing.aliyuncs.com/msi/"+file

        # oss_path = os.path.join(target_dir, file)

        data['platforms']['win64']['url'] = download_path

        data['platforms']['windows-x86_64']['url'] = download_path

    if file.endswith('.msi.zip.sig'):
        sig_path = os.path.join(source_dir, file)
    

        with open(sig_path, 'rb') as sig_file:
            signature = sig_file.read().decode('utf-8')
            data['platforms']['win64']['signature'] = signature
            data['platforms']['windows-x86_64']['signature'] = signature


# if sys.platform.startswith('linux'):

#     for file in os.listdir(source_dir):


#         if file.endswith('.AppImage.tar.gz'):

#             download_path="https://sijin-suan-update.oss-cn-beijing.aliyuncs.com/msi/"+file

            # oss_path = os.path.join(target_dir, file)

#             data['platforms']['linux']['url'] = download_path

#             data['platforms']['linux-x86_64']['url'] = download_path

#         if file.endswith('.AppImage.tar.gz.sig'):
#             sig_path = os.path.join(source_dir, file)

#             with open(sig_path, 'rb') as sig_file:

#                 signature = sig_file.read()

#                 data['platforms']['linux']['signature'] = signature

#                 data['platforms']['linux-x86_64']['signature'] = signature
    
        

# elif sys.platform == 'win64':

#     for file in os.listdir(source_dir):


#         if file.endswith('.msi.zip'):

#             download_path="https://sijin-suan-update.oss-cn-beijing.aliyuncs.com/msi/"+file

#             oss_path = os.path.join(target_dir, file)

#             data['platforms']['win64']['url'] = download_path

#             data['platforms']['windows-x86_64']['url'] = download_path

#         if file.endswith('.msi.zip.sig'):
#             sig_path = os.path.join(source_dir, file)
        

#             with open(sig_path, 'rb') as sig_file:

#                 signature = sig_file.read()

#                 data['platforms']['win64']['signature'] = signature

#                 data['platforms']['windows-x86_64']['signature'] = signature
    

# else:

#     print("Unknown operating system")

# 将修改后的数据保存回 update.json

with open(update_json_path, 'w') as f:

    json.dump(data, f, indent=2)


# 上传update.json

with open(update_json_path, 'rb') as fileobj:

    bucket.put_object(oss_path, fileobj)

print(f"Uploaded {update_json_path} to OSS path {oss_path}")

