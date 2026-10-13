import os

import chromadb
from dotenv import load_dotenv
from langchain_chroma import Chroma

from .config import COLLECTION_NAME
from .embeddings import get_embeddings

load_dotenv()


def get_vectorstore():
    """Connect LangChain to the Railway Rules Chroma Cloud collection."""

    required_env = [
        "CHROMA_TENANT",
        "CHROMA_DATABASE",
        "CHROMA_API_KEY",
    ]

    missing = [
        key for key in required_env
        if not os.getenv(key)
    ]

    if missing:
        raise RuntimeError(
            "Missing environment variables: "
            + ", ".join(missing)
        )

    client = chromadb.CloudClient(
        tenant=os.getenv("CHROMA_TENANT"),
        database=os.getenv("CHROMA_DATABASE"),
        api_key=os.getenv("CHROMA_API_KEY"),
    )

    # Use the collection configured in rag/config.py.
    # This should be Railway_Rules_Knowledge.
    vectorstore = Chroma(
        client=client,
        collection_name=COLLECTION_NAME,
        embedding_function=get_embeddings(),
    )

    return vectorstore