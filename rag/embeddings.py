from langchain_google_genai import GoogleGenerativeAIEmbeddings

from .config import (
    GEMINI_EMBEDDING_MODEL,
    GOOGLE_API_KEY
)


def get_embeddings():

    return GoogleGenerativeAIEmbeddings(
        model=GEMINI_EMBEDDING_MODEL,
        google_api_key=GOOGLE_API_KEY
    )