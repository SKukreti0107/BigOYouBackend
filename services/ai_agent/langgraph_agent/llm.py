from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI

load_dotenv()

base_llm = ChatGoogleGenerativeAI(
    model="gemini-3.1-flash-lite",
)
