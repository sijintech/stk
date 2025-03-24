import requests
import time
import socket


def validate_ollama_server(host, port, timeout=5):
    """
    验证Ollama服务器是否可访问，并获取基本信息

    参数:
    host (str): 服务器主机名或IP
    port (str): 服务器端口
    timeout (int): 请求超时时间(秒)

    返回:
    dict: 包含验证结果的字典
    """
    result = {
        "accessible": False,
        "models": [],
        "error": None,
        "response_time": 0,
        "server_info": None,
    }

    # 检查主机可达性
    try:
        start = time.time()
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect((host, int(port)))
        sock.close()
        result["accessible"] = True
    except Exception as e:
        result["error"] = f"连接失败: {str(e)}"
        return result

    # 测试API接口
    try:
        # 获取模型列表
        start_time = time.time()
        response = requests.get(f"http://{host}:{port}/api/tags", timeout=timeout)
        end_time = time.time()
        result["response_time"] = round((end_time - start_time) * 1000)  # 毫秒

        if response.status_code == 200:
            data = response.json()

            # 针对验证到的Ollama API响应格式进行精确处理
            if isinstance(data, dict) and "models" in data:
                result["models"] = []
                for model in data["models"]:
                    if isinstance(model, dict) and "name" in model:
                        result["models"].append(model["name"])
                        # 添加详细信息
                        if "details" in model and isinstance(model["details"], dict):
                            if "model_info" not in result["server_info"]:
                                result["server_info"] = {"model_info": {}}
                            result["server_info"]["model_info"][model["name"]] = {
                                "family": model["details"].get("family", "未知"),
                                "parameter_size": model["details"].get(
                                    "parameter_size", "未知"
                                ),
                                "quantization": model["details"].get(
                                    "quantization_level", "未知"
                                ),
                            }
                result["server_info"] = result.get("server_info", {})
                result["server_info"]["model_count"] = len(result["models"])
            else:
                # 保存原始响应以便调试
                result["server_info"] = {
                    "api_response": (
                        str(data)[:200] + "..." if len(str(data)) > 200 else str(data)
                    )
                }
        else:
            result["error"] = f"API请求返回错误状态码: {response.status_code}"
    except requests.exceptions.RequestException as e:
        result["error"] = f"API请求异常: {str(e)}"
    except Exception as e:
        result["error"] = f"验证过程中出错: {str(e)}"

    return result


def print_validation_result(result):
    """打印验证结果"""
    if result["accessible"]:
        print(f"✅ 服务器可访问")
        if result["error"] is None:
            print(f"✅ API接口正常，响应时间: {result['response_time']}ms")
            print(f"📋 发现模型: {len(result['models'])}")
            for i, model in enumerate(result["models"], 1):
                print(f"  {i}. {model}")
        else:
            print(f"❌ API接口异常: {result['error']}")
    else:
        print(f"❌ 服务器不可访问: {result['error']}")


def check_windows_service_config():
    """检查Windows环境下Ollama的配置"""
    import os
    import subprocess

    print("Windows系统Ollama配置检查:")

    # 检查环境变量
    ollama_host = os.environ.get("OLLAMA_HOST", "未设置")
    print(f"OLLAMA_HOST环境变量: {ollama_host}")

    # 检查防火墙规则
    try:
        result = subprocess.run(
            [
                "powershell",
                "-Command",
                "Get-NetFirewallRule -DisplayName '*Ollama*' | Format-Table -Property DisplayName,Enabled,Direction,Action -AutoSize",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if "Ollama" in result.stdout:
            print("防火墙规则检查: 找到Ollama相关规则")
            print(result.stdout)
        else:
            print("防火墙规则检查: 未找到Ollama相关规则，可能需要添加")
    except Exception as e:
        print(f"防火墙规则检查失败: {str(e)}")

    # 检查端口监听情况
    try:
        result = subprocess.run(
            ["powershell", "-Command", "netstat -ano | findstr :11435"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.stdout.strip():
            print("端口监听检查: 端口11435正在监听")
            for line in result.stdout.strip().split("\n"):
                parts = line.split()
                if len(parts) >= 2:
                    listen_addr = parts[1].split(":")[0]
                    if listen_addr == "0.0.0.0":
                        print("✅ Ollama正在监听所有网络接口 (0.0.0.0)")
                    elif listen_addr == "127.0.0.1":
                        print("❌ Ollama仅监听本地接口 (127.0.0.1)，需要修改配置")
        else:
            print("❌ 端口监听检查: 端口11435未在监听")
    except Exception as e:
        print(f"端口监听检查失败: {str(e)}")


if __name__ == "__main__":
    import sys

    # 默认参数
    host = "47.119.33.1"
    port = "11435"

    # 从命令行获取参数
    if len(sys.argv) > 1:
        host = sys.argv[1]
    if len(sys.argv) > 2:
        port = sys.argv[2]

    if host == "localhost" or host == "127.0.0.1":
        # 本地服务器检查
        check_windows_service_config()

    print(f"正在验证Ollama服务器: {host}:{port}")
    result = validate_ollama_server(host, port)
    print_validation_result(result)
