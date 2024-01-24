import oss2
import os
from oss2.credentials import EnvironmentVariableCredentialsProvider
# 从环境变量中获取访问凭证
# auth = oss2.Auth(os.environ['OSS_ACCESS_KEY_ID'], os.environ['OSS_ACCESS_KEY_SECRET'])
auth = oss2.ProviderAuth(EnvironmentVariableCredentialsProvider())

# 创建OSS Bucket对象
bucket = oss2.Bucket(auth, os.environ['OSS_ENDPOINT'], os.environ['OSS_BUCKET'])

# 指定要上传的文件或目录
source_dir = os.environ['SOURCE_DIR']

# 指定OSS中的目标目录
target_dir = os.environ['TARGET_DIR']

# 上传文件到OSS
for root, dirs, files in os.walk(source_dir):
    for file in files:
        file_path = os.path.join(root, file)
        oss_path = os.path.join(target_dir, os.path.relpath(file_path, source_dir))
        bucket.put_object_from_file(oss_path, file_path)
        print(f"Uploaded {file_path} to OSS path {oss_path}")
