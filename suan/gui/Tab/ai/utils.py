import os
import json
import time
import psutil
import requests
from custom_logger import CustomLogger

logger = CustomLogger()


SENTENCE_TRANSFORMER_AVAILABLE = False
SENTENCE_TRANSFORMER_ERROR = None


try:

    import torch
    from sentence_transformers import SentenceTransformer, util

    SENTENCE_TRANSFORMER_AVAILABLE = True

except Exception as e:
    import traceback

    error_message = str(e)
    error_traceback = traceback.format_exc()
    SENTENCE_TRANSFORMER_ERROR = error_message


    logger.error(f"无法导入sentence_transformers库: {error_message}")
    logger.debug(f"详细错误: {error_traceback}")


    if "LRScheduler" in error_message or "cached_download" in error_message:
        logger.error(
            "检测到版本不兼容问题。请按照以下步骤解决：\n"
            "1. 卸载现有包：\n"
            "   pip uninstall torch transformers sentence-transformers huggingface_hub\n"
            "2. 安装兼容版本：\n"
            "   pip install torch==1.13.1\n"
            "   pip install transformers==4.30.2\n"
            "   pip install sentence-transformers==2.2.2\n"
            "   pip install huggingface_hub==0.12.0"
        )


def get_config_path():
    """获取配置文件路径"""
    return os.path.join(os.path.expanduser("~"), ".stk", "ai_models.json")


def ensure_config_dir():
    """确保配置目录存在"""
    config_dir = os.path.dirname(get_config_path())
    os.makedirs(config_dir, exist_ok=True)
    return config_dir


def get_log_dir():
    """获取日志目录"""
    log_dir = os.path.join(os.path.expanduser("~"), ".stk", "logs")
    os.makedirs(log_dir, exist_ok=True)
    return log_dir


def log_query(config, question, response, response_time):
    """记录查询日志"""
    try:
        log_file = os.path.join(get_log_dir(), "chat_queries.log")
        with open(log_file, "a", encoding="utf-8") as f:
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
            model_info = f"{config['name']} ({config['model_name']})"
            log_entry = f"[{timestamp}] 模型: {model_info}\n问: {question}\n答: {response}\n响应时间: {response_time}ms\n{'='*50}\n"
            f.write(log_entry)
        return True
    except Exception as e:
        logger.error(f"记录查询日志时出错: {str(e)}")
        return False


def check_memory_usage():
    """检查系统内存使用情况，返回可用内存(GB)和使用率"""
    try:
        mem = psutil.virtual_memory()
        available_gb = mem.available / (1024**3)
        return available_gb, mem.percent
    except Exception as e:
        logger.error(f"检查内存使用时出错: {str(e)}")
        return None, None


def estimate_model_memory_requirement(model_name):
    """根据模型名称估计内存需求(GB)"""
    memory_requirement = 1.0  # 默认需求


    model_name_lower = model_name.lower()
    if any(s in model_name_lower for s in ["1.5b", "1b", "small"]):
        memory_requirement = 1.2
    elif any(s in model_name_lower for s in ["7b", "7B", "medium"]):
        memory_requirement = 4.0
    elif any(s in model_name_lower for s in ["13b", "13B", "large"]):
        memory_requirement = 8.0
    elif any(s in model_name_lower for s in ["30b", "30B", "huge", "70b", "70B"]):
        memory_requirement = 16.0

    return memory_requirement


def is_sentence_transformer_available():
    """检查句子变换器库是否可用"""

    return SENTENCE_TRANSFORMER_AVAILABLE, SENTENCE_TRANSFORMER_ERROR


def connect_to_ollama(host, port):
    """连接到Ollama服务，返回客户端和可用模型列表"""
    try:
        import ollama


        client = ollama.Client(host=f"http://{host}:{port}")


        models_info = client.list()
        model_names = []

        if isinstance(models_info, dict) and "models" in models_info:
            for model in models_info.get("models", []):
                if isinstance(model, dict) and "name" in model:
                    model_names.append(model["name"])

        return client, model_names, None
    except Exception as e:
        return None, [], str(e)


def validate_ollama_connection(host, port):
    """验证到Ollama服务的连接，返回详细信息"""
    results = {
        "tcp_connection": False,
        "api_connection": False,
        "available_models": [],
        "errors": [],
    }

    try:

        import socket

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(3)
        sock.connect((host, int(port)))
        sock.close()
        results["tcp_connection"] = True


        response = requests.get(f"http://{host}:{port}/api/tags", timeout=5)
        if response.status_code == 200:
            results["api_connection"] = True
            data = response.json()
            if "models" in data:
                results["available_models"] = [
                    model["name"] for model in data["models"]
                ]
    except Exception as e:
        results["errors"].append(str(e))

    return results
