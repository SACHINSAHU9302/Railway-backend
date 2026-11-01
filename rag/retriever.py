from .vectorstore import get_vectorstore
from .config import TOP_K


def get_retriever():

    vectorstore = get_vectorstore()

    retriever = vectorstore.as_retriever(
        search_type="mmr",
        search_kwargs={
            "k": TOP_K,
            "fetch_k": 20,
            "lambda_mult": 0.7
        }
    )

    return retriever