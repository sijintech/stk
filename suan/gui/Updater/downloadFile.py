# requests 文件下载的模块带进度
# requests 文件下载的模块带进度
import requests
import time
import urllib.request


def download_progressbar(url, save_addr):
    # 终端的进度条
    try:
        from tqdm import tqdm
    except ImportError:
        print("请安装 pip install tqdm")
        return False

    r = requests.get(url, stream=True)
    with open(save_addr, 'wb') as f:
        total_length = int(r.headers.get('content-length'))
        print(f"文件大小 {total_length}")
        for chunk in tqdm(r.iter_content(chunk_size=1024), total=total_length / 1024):
            if chunk:
                f.write(chunk)
                f.flush()
    return True


# def 下载文件(url, 保存地址, 回调函数=None):
#     # 回调函数例子
#     #     def 进度(进度百分比, 已下载大小, 文件大小, 下载速率, 剩余时间):
#     #         信息 = f"进度 {进度百分比}% 已下载 {已下载大小}MB 文件大小 {文件大小}MB 下载速率 {下载速率}MB 剩余时间 {剩余时间}秒"
#     #         print(f"\r {信息}", end="")
#     if 回调函数:
#         start_time = time.time()
#     # r = requests.get(url, stream=True)
#     r=urllib.request.urlopen(url)

#     with open(保存地址, 'wb') as f:
#         total_length = int(r.headers.get('content-length'))
#         # 获取百分比 并调用回调函数
#         for chunk in r.read(10 * 1024):
#             if chunk:
#                 f.write(chunk)
#                 f.flush()
#                 if 回调函数:
#                     # 转化为百分比
#                     进度百分比 = int(f.tell() * 100 / total_length)
#                     已下载大小 = f.tell() / 1024 / 1024
#                     文件大小MB = total_length / 1024 / 1024
#                     下载速率MB = 已下载大小 / (time.time() - start_time)
#                     # 获取剩余时间取秒
#                     剩余时间 = (文件大小MB - 已下载大小) / 下载速率MB
#                     剩余时间 = int(剩余时间)
#                     # 所有数据保留两位小数
#                     下载速率MB = round(下载速率MB, 2)
#                     文件大小MB = round(文件大小MB, 2)
#                     已下载大小 = round(已下载大小, 2)
#                     进度百分比 = round(进度百分比, 2)
#                     回调函数(进度百分比, 已下载大小, 文件大小MB, 下载速率MB, 剩余时间)
#     return True

def download_file(url, save_addr, callback=None):
    if callback:
        start_time = time.time()
    r = urllib.request.urlopen(url)
    total_length = int(r.headers.get('content-length'))
    downloaded_length = 0
    chunk_size = 10 * 1024

    with open(save_addr, 'wb') as f:
        while True:
            chunk = r.read(chunk_size)
            if not chunk:
                break
            f.write(chunk)
            f.flush()
            downloaded_length += len(chunk)
            if callback:
                进度百分比 = downloaded_length * 100 // total_length
                已下载大小 = downloaded_length / 1024 / 1024
                文件大小MB = total_length / 1024 / 1024
                下载速率MB = 已下载大小 / (time.time() - start_time)
                剩余时间 = (文件大小MB - 已下载大小) / 下载速率MB
                剩余时间 = int(剩余时间)
                下载速率MB = round(下载速率MB, 2)
                文件大小MB = round(文件大小MB, 2)
                已下载大小 = round(已下载大小, 2)
                进度百分比 = round(进度百分比, 2)
                callback(进度百分比, 已下载大小, 文件大小MB, 下载速率MB, 剩余时间)
    return True


if __name__ == "__main__":
    # 下载一个大一点的文件
    def progress(进度百分比, 已下载大小, 文件大小, 下载速率, 剩余时间):
        信息 = f"进度 {进度百分比}% 已下载 {已下载大小}MB 文件大小 {文件大小}MB 下载速率 {下载速率}MB 剩余时间 {剩余时间}秒"
        # 控制台当行输出
        print(f"\r {信息}", end="")


    # 下载文件("https://github.com/duolabmeng6/QtEsayDesigner/releases/download/0.0.32/QtEsayDesigner_MacOS.zip",
    #         "QtEsayDesigner_MacOS.zip", 进度)
    download_file("https://sijin-suan-update.oss-cn-beijing.aliyuncs.com/nsis/suan_pyqt_0.0.1.exe",
                  "suan_pyqt_0.0.1.exe", progress)
