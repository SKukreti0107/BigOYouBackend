# from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq
from dotenv import load_dotenv

load_dotenv()

# llm = ChatGoogleGenerativeAI(
#     model = "gemma-3-27b-it",
#     # thinking_level ="low"
# )


llm = ChatGroq(
    model="llama-3.3-70b-versatile",
    # model="meta-llama/llama-4-scout-17b-16e-instruct"
)