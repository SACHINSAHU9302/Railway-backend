from langchain_chroma import Chroma

from .config import (
    CHROMA_PERSIST_DIRECTORY,
    COLLECTION_NAME
)

from .embeddings import get_embeddings

def get_vectorstore():

    embeddings = get_embeddings()

    vectorstore = Chroma(
        collection_name=COLLECTION_NAME,
        embedding_function=embeddings,
        persist_directory=CHROMA_PERSIST_DIRECTORY
    )
    
    return vectorstore