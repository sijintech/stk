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
# with open(file_path, 'rb') as fileobj:
    # # Seek方法用于指定从第1000个字节位置开始读写。上传时会从您指定的第1000个字节位置开始上传，直到文件结束。
    # fileobj.seek(0, os.SEEK_SET)
    # # Tell方法用于返回当前位置。
    # current = fileobj.tell()
    # 填写Object完整路径。Object完整路径中不能包含Bucket名称。
    # bucket.put_object('msi/', fileobj)


# 上传文件到OSS
# for root, dirs, files in os.walk(source_dir):
#     print(f"root:{root}")
#     print(f"root:{dirs}")
#     print(f"root:{files}")

    # for file in files:
    #     file_path = os.path.join(root, file)
    #     oss_path = os.path.join(target_dir, os.path.relpath(file_path, source_dir))
    #     with open(file_path, 'rb') as fileobj:
    #          bucket.put_object(oss_path, fileobj)

    #     # bucket.put_object_from_file(oss_path, file_path)
    #     print(f"Uploaded {file_path} to OSS path {oss_path}")
for file in os.listdir(source_dir):
    file_path = os.path.join(source_dir, file)
    oss_path = os.path.join(target_dir, file)
    with open(file_path, 'rb') as fileobj:
        bucket.put_object(oss_path, fileobj)

    print(f"Uploaded {file_path} to OSS path {oss_path}")
