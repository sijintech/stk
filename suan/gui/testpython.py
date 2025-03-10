import ollama
from transformers import pipeline
import fitz  # PyMuPDF

# Load the distilled model
model = ollama.load_model('deepseek_r1_distilled')

# Initialize the RAG pipeline
rag_pipeline = pipeline('rag-token', model=model)


# Function to extract text from a PDF
def extract_text_from_pdf(pdf_path):
    doc = fitz.open(pdf_path)
    text = ""
    for page_num in range(len(doc)):
        page = doc.load_page(page_num)
        text += page.get_text()
    return text


# Function to train the model with a specific software manual
def train_with_manual(manual_path):
    manual_text = extract_text_from_pdf(manual_path)
    # Assuming the manual is in plain text format
    rag_pipeline.add_documents([manual_text])


# Function to answer questions about the software
def answer_question(question):
    return rag_pipeline(question)


# Example usage
if __name__ == "__main__":
    manual_path = 'maxkb.pdf'
    train_with_manual(manual_path)

    question = "How do I install the software?"
    answer = answer_question(question)
    print(answer)
