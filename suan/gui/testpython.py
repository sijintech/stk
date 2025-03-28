import ollama

# from ollama import chat
from sentence_transformers import SentenceTransformer, util
import PyPDF2
import requests


host = "47.119.33.1"  # 更新为远程服务器IP
port = "11435"
client = ollama.Client(host=f"http://{host}:{port}")


# 从 PDF 中提取文本的函数
def extract_text_from_pdf(pdf_path):
    text = ""
    with open(pdf_path, "rb") as file:
        reader = PyPDF2.PdfReader(file)
        for page in reader.pages:
            text += page.extract_text()
    return text


# # 使用特定软件手册训练模型的函数
# def train_with_manual(manual_path):
#     manual_text = extract_text_from_pdf(manual_path)
#     # 假设手册是纯文本格式
#     embeddings = sentence_model.encode([manual_text], convert_to_tensor=True)
#     return embeddings


# 使用 RAG 技术回答关于软件的问题的函数
def answer_question_by_rag(question, manual_text):
    # 初始化 SentenceTransformer 模型
    sentence_model = SentenceTransformer("all-MiniLM-L6-v2")
    # 检索（Retrieval）：从手册中检索相关信息
    question_embedding = sentence_model.encode(question, convert_to_tensor=True)
    manual_embeddings = sentence_model.encode([manual_text], convert_to_tensor=True)
    scores = util.pytorch_cos_sim(question_embedding, manual_embeddings)[0]
    best_score_idx = scores.argmax().item()
    relevant_context = manual_text

    # 增强（Augmented）：将检索到的信息作为上下文
    # 生成（Generation）：基于上下文生成回答
    response = client.generate(
        model="deepseek-r1:1.5b",
        prompt="现在有软件相关信息为："
        + relevant_context
        + "请根据上面信息回答问题："
        + question,
    )
    # response = model.generate(question, context=relevant_context)
    return response


def answer_question(question, manual_text, is_direct):
    if is_direct:
        response = answer_question_direct(question, manual_text)
    else:
        response = answer_question_by_rag(question, manual_text)
    return response


def answer_question_direct(question, manual_text):

    # response =ollama.generate(model='deepseek-r1:1.5b', prompt='现在有软件相关信息为：'+manual_text+'请根据上面信息回答问题：'+question)
    # response = model.generate(question, context=relevant_context)
    stream = client.chat(
        model="deepseek-r1:1.5b",
        messages=[
            {
                "role": "user",
                "content": "现在有软件相关信息为："
                + manual_text
                + "请根据上面信息回答问题："
                + question,
            }
        ],
        stream=True,
    )
    return stream


def is_install_model(model_name):
    try:
        # 首先检查服务器是否可达
        response = requests.get(f"http://{host}:{port}/api/tags")
        if response.status_code != 200:
            print(f"无法连接到Ollama服务器: {response.status_code}")
            return False

        # 然后检查模型
        installed_models = client.list()
        print(installed_models)
        model_names = [model["name"] for model in installed_models["models"]]
        if model_name in model_names:
            return True
        else:
            print(f"未找到模型: {model_name}")
            return False
    except Exception as e:
        print(f"连接到Ollama服务器时出错: {str(e)}")
        return False


# 示例用法
if __name__ == "__main__":
    is_install_model("deepseek-r1:1.5b")
    manual_path = "sijin.pdf"
    # 使用手册训练模型
    manual_text = extract_text_from_pdf(manual_path)

    question = "详细介绍怎么开发者使用这个许可证系统?"
    # 使用训练好的模型回答问题
    stream = answer_question(question, manual_text, True)
    # print(answer)
    # from ollama import chat
    # from sentence_transformers import SentenceTransformer, util
    # import PyPDF2

    # stream = chat(
    #     model='deepseek-r1:1.5b',
    #     messages=[{'role': 'user', 'content': '你是谁？'}],
    #     stream=True,
    # )

    # 逐块打印响应内容
    for chunk in stream:
        print(chunk["message"]["content"], end="", flush=True)
