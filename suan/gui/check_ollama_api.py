import requests
import json
import sys
import socket
import time
import os


def check_ai_model_configs():
    """检查已保存的AI模型配置"""
    config_path = os.path.join(os.path.expanduser("~"), ".stk", "ai_models.json")

    if not os.path.exists(config_path):
        print("未找到AI模型配置文件")
        return

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            configs = json.load(f)

        print(f"找到 {len(configs)} 个AI模型配置:")
        for i, config in enumerate(configs, 1):
            model_type = config.get("type", "未知")
            model_name = config.get("model_name", "未指定")

            if model_type == "ollama":
                host = config.get("host", "")
                port = config.get("port", "")
                print(
                    f"{i}. {config.get('name', '未命名')} - Ollama模型 ({model_name})"
                )
                print(f"   地址: {host}:{port}")
            elif model_type == "openai":
                print(
                    f"{i}. {config.get('name', '未命名')} - OpenAI模型 ({model_name})"
                )
                api_key_masked = "已设置" if config.get("api_key") else "未设置"
                print(f"   API密钥: {api_key_masked}")
            else:
                print(f"{i}. {config.get('name', '未命名')} - 自定义API ({model_name})")
                host = config.get("host", "")
                port = config.get("port", "")
                print(f"   地址: {host}:{port}")

            # 检查代理设置
            if config.get("use_proxy", False) and config.get("proxy"):
                print(f"   代理: {config.get('proxy')}")

            print("")
    except Exception as e:
        print(f"读取配置文件出错: {str(e)}")


def check_ollama_api(host, port):
    """检查Ollama API并输出详细信息"""
    url = f"http://{host}:{port}/api/tags"
    print(f"正在检查Ollama API: {url}")

    # 先测试TCP连接
    try:
        start_time = time.time()
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(3)
        sock.connect((host, int(port)))
        sock.close()
        tcp_time = (time.time() - start_time) * 1000
        print(f"✅ TCP连接成功 (响应时间: {tcp_time:.2f}ms)")
    except Exception as e:
        print(f"❌ TCP连接失败: {str(e)}")
        print("请检查以下可能的问题:")
        print("1. 确认Ollama服务正在运行")
        print("2. 检查防火墙是否允许该端口")
        print("3. 确认Ollama配置为监听0.0.0.0而不是127.0.0.1")
        return

    try:
        start_time = time.time()
        response = requests.get(url, timeout=5)
        http_time = (time.time() - start_time) * 1000
        print(f"状态码: {response.status_code} (响应时间: {http_time:.2f}ms)")

        if response.status_code == 200:
            data = response.json()
            print("API响应结构:")
            print(json.dumps(data, indent=2, ensure_ascii=False))

            # 分析响应结构
            if isinstance(data, dict):
                print("响应是字典类型")
                print(f"顶级键: {list(data.keys())}")
                if "models" in data:
                    models = data["models"]
                    print(f"发现 {len(models)} 个模型:")
                    for i, model in enumerate(models, 1):
                        name = model.get("name", "未知")
                        size_mb = model.get("size", 0) / (1024 * 1024)
                        details = model.get("details", {})
                        family = details.get("family", "未知")
                        param_size = details.get("parameter_size", "未知")

                        print(
                            f"  {i}. {name} ({param_size}, {family}, {size_mb:.1f}MB)"
                        )

                    if models and isinstance(models[0], dict):
                        print(f"模型对象键: {list(models[0].keys())}")

                    # 测试查询特定模型
                    test_model = "deepseek-r1:1.5b"
                    if any(m.get("name") == test_model for m in models):
                        print(f"\n测试与模型 {test_model} 的简单对话...")
                        try:
                            ollama_client = requests.post(
                                f"http://{host}:{port}/api/chat",
                                json={
                                    "model": test_model,
                                    "messages": [
                                        {
                                            "role": "user",
                                            "content": "你好，请简短介绍一下你自己",
                                        }
                                    ],
                                    "stream": False,
                                },
                                timeout=10,
                            )
                            if ollama_client.status_code == 200:
                                chat_response = ollama_client.json()
                                print(
                                    f"✅ 模型响应成功: {chat_response.get('message', {}).get('content', '')[:100]}..."
                                )
                            else:
                                print(f"❌ 模型响应失败: {ollama_client.status_code}")
                        except Exception as e:
                            print(f"❌ 模型对话测试失败: {str(e)}")
            elif isinstance(data, list):
                print("响应是列表类型")
                if data and isinstance(data[0], dict):
                    print(f"模型对象键: {list(data[0].keys())}")
            else:
                print(f"响应是其他类型: {type(data)}")
        else:
            print(f"API请求失败，状态码: {response.status_code}")

        # 连接和响应总结
        print("\n连接和API响应总结:")
        print(f"✅ TCP连接: {tcp_time:.2f}ms")
        if response.status_code == 200:
            print(f"✅ HTTP请求: {http_time:.2f}ms")
            if "models" in data:
                print(f"✅ 模型数量: {len(data['models'])}")
                model_names = [m.get("name", "未知") for m in data["models"]]
                print(f"✅ 可用模型: {', '.join(model_names)}")
            else:
                print(f"❌ 未检测到模型列表")
        else:
            print(f"❌ HTTP请求: {response.status_code}")

    except Exception as e:
        print(f"请求出错: {str(e)}")


if __name__ == "__main__":
    # 添加命令行参数解析
    if len(sys.argv) > 1 and sys.argv[1] == "--configs":
        check_ai_model_configs()
        sys.exit(0)

    # 原有的Ollama API检查代码
    host = "47.119.33.1"
    port = "11435"

    if len(sys.argv) > 1 and sys.argv[1] != "--configs":
        host = sys.argv[1]
    if len(sys.argv) > 2:
        port = sys.argv[2]

    check_ollama_api(host, port)
