from .vectorstore import get_vectorstore
from .config import TOP_K


def get_retriever():

    vectorstore = get_vectorstore()

    retriever = vectorstore.as_retriever(
        search_type="similarity",
        search_kwargs={
            "k": TOP_K
        }
    )

    return retriever