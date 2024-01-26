import oss2
import os
from oss2.credentials import EnvironmentVariableCredentialsProvider
# 从环境变量中获取访问凭证
# auth = oss2.Auth(os.environ['OSS_ACCESS_KEY_ID'], os.environ['OSS_ACCESS_KEY_SECRET'])
auth = oss2.ProviderAuth(EnvironmentVariableCredentialsProvider())

# 创建OSS Bucket对象
bucket = oss2.Bucket(auth, os.environ['OSS_ENDPOINT'], os.environ['OSS_BUCKET'])

# 指定要上传的文件或目录
# source_dir = os.environ['SOURCE_DIR']
this_dir=os.path.dirname(os.path.abspath(__file__))
source_dir = os.path.join(this_dir, os.environ['SOURCE_DIR'])

# 指定OSS中的目标目录
target_dir = os.environ['TARGET_DIR']
print(f"source_dir:{source_dir}")

# 必须以二进制的方式打开文件。
# 填写本地文件的完整路径。如果未指定本地路径，则默认从示例程序所属项目对应本地路径中上传文件。


for file in os.listdir(source_dir):
    # if sys.platform.startswith('linux'):
        if file.endswith('.AppImage.tar.gz'):
            file_path = os.path.join(source_dir, file)
            oss_path = os.path.join(target_dir, file)
            with open(file_path, 'rb') as fileobj:
                bucket.put_object(oss_path, fileobj)
            print(f"Uploaded {file_path} to OSS path {oss_path}")
    # elif sys.platform == 'win64':
        if file.endswith('.msi.zip'):
            file_path = os.path.join(source_dir, file)
            oss_path = os.path.join(target_dir, file)
            with open(file_path, 'rb') as fileobj:
                bucket.put_object(oss_path, fileobj)
            print(f"Uploaded {file_path} to OSS path {oss_path}")  
    # else:
    #     print("Unknown operating system")
    

