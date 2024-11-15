# https://github.com/duolabmeng6/qtAutoUpdateApp/releases
import re
import urllib.request
import json




import requests


# def 获取最新版本号和下载地址(project_name):
#     # 通过访问最新的页面 获取版本号和下载地址和更新内容
#     # https://github.com/duolabmeng6/qtAutoUpdateApp/releases/latest
#     # 镜像地址也可以自己造一个 https://quiet-boat-a038.duolabmeng.workers.dev/
#     #https://github.com/duolabmeng6/qoq/releases/expanded_assets/v0.1.5
#     # https://github.com/duolabmeng6/qtAutoUpdateApp/releases/tag/v0.0.68
#     # https://ghproxy.com/https://github.com/{project_name}/releases/latest
#     print('开始解析网页')
#     url = f"https://github.com/{project_name}/releases/latest"
#     print(url)
#     # jsondata = requests.get(url,proxies={})
#     response = urllib.request.urlopen(url)
#     # jsondata = json.loads(response.read().decode('utf-8'))
#     jsondata = response.read().decode('utf-8')
#     # print(response.read())


#     # 写出文件
#     # with open('test.html', "w", encoding="utf-8") as f:
#     #     f.write(jsondata.text)
#     # 获取版本号



#     return 解析网页信息(jsondata,project_name)
def get_version_and_download_addr(url):
    try:
        response = urllib.request.urlopen(url)
        if response.getcode() == 200:
            data = json.loads(response.read().decode('utf-8'))
            return {
                "版本号": data["version"],
                "下载地址列表": data["download_list"],
                "更新内容": data["changelog"],
                "发布时间": data["releasetime"],
                "mac下载地址": data["mac_download"],
                "win下载地址": data["win_download"]
            }
        else:
            print("HTTP 请求失败:", response.getcode())
            return None
    except Exception as e:
        print("请求失败:", e)
        return None


def refresh_web(web, project_name):
    版本号 = web.find('<span class="ml-1">')
    版本号 = web[版本号 + len('<span class="ml-1">'):]
    版本号 = 版本号[:版本号.find('</span>')].strip()
    print(版本号)
    # 获取更新内容
    # <div data-pjax="true" data-test-selector="body-content" data-view-component="true" class="markdown-body my-3"><h1>自动更新程序</h1>
    # <ul>
    # <li>更新了自动构建</li>
    # <li>自动获取版本</li>
    # <li>自动下载</li>
    # <li>自动替换</li>
    # </ul></div>
    # </div>

    更新内容 = web.find(
        '<div data-pjax="true" data-test-selector="body-content" data-view-component="true" class="markdown-body my-3">')
    更新内容 = web[更新内容 + len(
        '<div data-pjax="true" data-test-selector="body-content" data-view-component="true" class="markdown-body my-3">'):]
    更新内容 = 更新内容[:更新内容.find('</div>')]
    # print(更新内容)
    # 获取下载地址列表
    #             <a href="/duolabmeng6/qtAutoUpdateApp/releases/download/0.0.4/my_app_MacOS.zip" rel="nofollow" data-skip-pjax>
    #               <span class="px-1 text-bold">my_app_MacOS.zip</span>
    #
    #             </a>

    下载地址列表 = []
    mac下载地址 = ""
    win下载地址 = ""
    # 重新重新访问页面
    # https://github.com/duolabmeng6/qoq/releases/expanded_assets/v0.1.5
    url = f"https://github.com/{project_name}/releases/expanded_assets/{版本号}"
    # 网页2 = requests.get(url).text
    网页2 = urllib.request.urlopen(url).read().decode('utf-8')

    pattern = re.compile( r'class="Truncate-text text-bold">(.*?)</span>' )
    result = pattern.findall(网页2)
    # print(result)
    for item in result:
        # print(item)
        下载地址 = item
        下载地址 = f"https://github.com/{project_name}/releases/download/{版本号}/{下载地址}"
        文件名 = item
        if 文件名.find('Source code') != -1:
            continue

        下载地址列表.append({文件名: 下载地址})

        if 文件名.find('MacOS.zip') != -1:
            mac下载地址 = 下载地址
        if 文件名.find('.exe') != -1:
            win下载地址 = 下载地址


    print(下载地址列表)

    # 获取发布时间
    # <relative-time datetime="2022-07-22T17:32:41Z" class="no-wrap"></relative-time>
    发布时间 = 网页2.find('<relative-time datetime="')
    发布时间 = 网页2[发布时间 + len('<relative-time datetime="'):]
    发布时间 = 发布时间[:发布时间.find('"')]
    # 去掉 t z
    发布时间 = 发布时间.replace("T", " ").replace("Z", "")

    # 版本号大于20个字符就清空
    if len(版本号) > 20:
        版本号 = ""
        发布时间 = ""
        更新内容 = ""

    return {
        "版本号": 版本号,
        "下载地址列表": 下载地址列表,
        "更新内容": 更新内容,
        "发布时间": 发布时间,
        "mac下载地址": mac下载地址,
        "win下载地址": win下载地址,
    }


# 测试
if __name__ == '__main__':
    # data = 获取最新版本号和下载地址("duolabmeng6/qoq2")
    # print(data)
    # data = 解析网页信息("")
    # print(data)
    data = get_version_and_download_addr("https://sijin-suan-update.oss-cn-beijing.aliyuncs.com/update.json")
    print(data)
