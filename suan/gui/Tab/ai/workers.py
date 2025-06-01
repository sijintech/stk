from PySide6.QtCore import QThread, Signal
import ollama
import requests
import os
import time
import traceback
from custom_logger import CustomLogger
from .utils import SENTENCE_TRANSFORMER_AVAILABLE



class RagWorker(QThread):
    """RAG处理工作线程，用于在后台处理PDF和模型加载"""

    progress_signal = Signal(int, str)  # 进度信号(百分比, 消息)
    finished_signal = Signal(object)  # 完成信号(处理后的消息列表)
    error_signal = Signal(str)  # 错误信号

    def __init__(self, pdf_path, question, system_prompt=""):
        super().__init__()
        self.pdf_path = pdf_path
        self.question = question
        self.system_prompt = system_prompt
        self.logger = CustomLogger()
        self.sentence_model = None

    def extract_text_from_pdf(self, pdf_path):
        """从PDF中提取文本，支持进度报告"""
        if not os.path.exists(pdf_path):
            self.logger.error(f"PDF文件不存在: {pdf_path}")
            self.error_signal.emit(f"PDF文件不存在: {pdf_path}")
            return ""

        try:

            import PyPDF2

            text = ""
            with open(pdf_path, "rb") as file:
                reader = PyPDF2.PdfReader(file)
                total_pages = len(reader.pages)


                self.progress_signal.emit(0, f"开始处理PDF文件 ({total_pages}页)...")


                for i, page in enumerate(reader.pages):
                    if self.isInterruptionRequested():
                        self.progress_signal.emit(100, "处理被用户取消")
                        return ""

                    page_text = page.extract_text()
                    text += page_text + "\n\n"


                    progress = int((i + 1) / total_pages * 100)
                    self.progress_signal.emit(
                        progress, f"正在处理PDF: {progress}% ({i+1}/{total_pages}页)"
                    )


                if len(text) > 100000:  # 约10万字符
                    text = text[:100000] + "...(文本已截断)"
                    self.progress_signal.emit(100, "文本过长已截断")

                self.progress_signal.emit(100, "PDF处理完成")
                return text
        except Exception as e:
            self.logger.error(f"提取PDF文本失败: {str(e)}")
            self.error_signal.emit(f"提取PDF文本失败: {str(e)}")
            return ""

    def load_sentence_model(self):
        """加载句子变换器模型"""
        if not SENTENCE_TRANSFORMER_AVAILABLE:
            self.error_signal.emit("sentence-transformers库不可用，无法进行语义搜索")
            return False

        try:
            from sentence_transformers import SentenceTransformer

            self.progress_signal.emit(0, "开始加载语义模型...")
            self.sentence_model = SentenceTransformer("all-MiniLM-L6-v2")
            self.progress_signal.emit(100, "语义模型加载完成")
            return True
        except Exception as e:
            self.logger.error(f"加载sentence-transformer模型失败: {str(e)}")
            self.error_signal.emit(f"加载语义模型失败: {str(e)}")
            return False

    def run(self):
        """线程主函数：处理PDF并准备RAG消息"""
        try:

            self.progress_signal.emit(0, "准备处理PDF...")
            manual_text = self.extract_text_from_pdf(self.pdf_path)

            if not manual_text:
                self.error_signal.emit("未能从PDF中提取文本，RAG处理终止")
                return


            messages = []


            if self.system_prompt:
                messages.append({"role": "system", "content": self.system_prompt})


            max_chunk_size = 8000  # 每块最大字符数
            if len(manual_text) > max_chunk_size:
                self.progress_signal.emit(50, "文本过长，进行分块处理...")

                manual_chunks = [
                    manual_text[i : i + max_chunk_size]
                    for i in range(0, len(manual_text), max_chunk_size)
                ]


                if len(manual_chunks) > 3:
                    manual_chunks = manual_chunks[:3]
                    self.progress_signal.emit(
                        60, f"文本已分为{len(manual_chunks)}块，只使用前3块"
                    )


                rag_prompt = (
                    f"请基于以下软件使用手册内容回答问题。如果手册中没有相关信息，请明确说明。\n\n"
                    f"使用手册内容(节选):\n{manual_chunks[0]}\n\n"
                    f"用户问题: {self.question}"
                )
            else:

                rag_prompt = (
                    f"请基于以下软件使用手册内容回答问题。如果手册中没有相关信息，请明确说明。\n\n"
                    f"使用手册内容:\n{manual_text}\n\n"
                    f"用户问题: {self.question}"
                )

            self.progress_signal.emit(90, "RAG处理完成，准备发送到AI模型")
            messages.append({"role": "user", "content": rag_prompt})


            self.finished_signal.emit(messages)

        except Exception as e:
            self.logger.error(f"RAG处理线程异常: {str(e)}")
            self.error_signal.emit(f"RAG处理失败: {str(e)}\n{traceback.format_exc()}")


class ResponseGenerationWorker(QThread):
    """响应生成工作线程，用于在后台生成AI回复"""

    chunk_signal = Signal(str)  # 文本块信号
    finished_signal = Signal(str)  # 完成信号(完整文本)
    error_signal = Signal(str)  # 错误信号

    def __init__(self, client, model_config, messages):
        super().__init__()
        self.client = client
        self.config = model_config
        self.messages = messages
        self.logger = CustomLogger()
        self.full_response = ""

    def run(self):
        """线程主函数：生成AI响应"""
        try:
            model_type = self.config["type"]  # public/private
            model_name = self.config["model_name"]
            temperature = self.config.get("temperature", 0.7)
            max_tokens = self.config.get("max_tokens", 1000)
            response_timeout = self.config.get("response_timeout", 120)  # 增大超时时间


            if model_type == "public":

                stream = self.client.chat(
                    model=model_name,
                    messages=self.messages,
                    stream=True,
                    options={"num_predict": max_tokens, "temperature": temperature},
                )

                for chunk in stream:
                    if self.isInterruptionRequested():
                        self.chunk_signal.emit("\n\n[用户取消了响应生成]")
                        self.finished_signal.emit(self.full_response)
                        return

                    content = chunk["message"]["content"]
                    self.chunk_signal.emit(content)
                    self.full_response += content


            else:
                headers = self.client["headers"]
                url = self.client["base_url"]
                if not url.startswith("http"):
                    url = f"http://{url}"

                response = requests.post(
                    f"{url}/chat/completions",
                    headers=headers,
                    json={
                        "model": self.client["model"],
                        "messages": self.messages,
                        "temperature": temperature,
                        "max_tokens": max_tokens,
                    },
                    timeout=response_timeout,
                )

                if response.status_code == 200:
                    content = (
                        response.json()
                        .get("choices", [{}])[0]
                        .get("message", {})
                        .get("content", "")
                    )
                    self.chunk_signal.emit(content)
                    self.full_response = content
                else:
                    raise Exception(f"API返回错误: {response.status_code}")


            self.finished_signal.emit(self.full_response)

        except Exception as e:
            error_message = str(e)
            self.logger.error(f"生成响应失败: {error_message}")
            self.error_signal.emit(error_message)
