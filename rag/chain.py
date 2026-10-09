from .retriever import get_retriever
from .llm import get_llm
from .prompt import create_prompt


def ask_rag(question):

    retriever = get_retriever()

    documents = retriever.invoke(
        question
    )

    if not documents:

        return {
            "answer": (
                "I could not find this information "
                "in the RailVision knowledge base."
            ),
            "sources": []
        }

    context_parts = []

    sources = []

    for doc in documents:

        context_parts.append(
            doc.page_content
        )

        source = doc.metadata.get(
            "source"
        )

        if source:
            sources.append(
                source
            )

    context = "\n\n".join(
        context_parts
    )

    prompt = create_prompt(
        question,
        context
    )

    llm = get_llm()

    response = llm.invoke(
        prompt
    )

    answer = response.content

    return {
        "answer": answer,
        "sources": list(
            set(sources)
        )
    }