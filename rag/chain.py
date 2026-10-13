from .retriever import get_retriever
from .llm import get_llm
from .prompt import create_prompt


def ask_rag(question):
    question = question.strip()

    # Validate the question
    if not question:
        return {
            "answer": "Please enter a question.",
            "sources": [],
        }

    # Retrieve relevant documents from Chroma Cloud
    retriever = get_retriever()
    documents = retriever.invoke(question)

    # Handle missing documents
    if not documents:
        return {
            "answer": (
                "I could not find this information "
                "in the RailVision knowledge base."
            ),
            "sources": [],
        }

    # Prepare context and collect source information
    context_parts = []
    sources = []
    seen_sources = set()

    for doc in documents:
        context_parts.append(doc.page_content)

        metadata = doc.metadata or {}
        source = metadata.get("source", "")

        if source and source not in seen_sources:
            seen_sources.add(source)

            sources.append({
                "source": source,
                "title": metadata.get("title", ""),
                "category": metadata.get("category", ""),
                "source_url": metadata.get("source_url", ""),
                "effective_date": metadata.get(
                    "effective_date", "unknown"
                ),
            })

    # Combine retrieved documents into context
    context = "\n\n".join(context_parts)

    # Create prompt and generate the answer
    prompt = create_prompt(question, context)
    response = get_llm().invoke(prompt)

    answer = response.content

    # Convert Gemini content blocks into plain text
    if isinstance(answer, list):
        text_parts = []

        for item in answer:
            if isinstance(item, dict) and item.get("type") == "text":
                text_parts.append(item.get("text", ""))

        answer = "\n".join(text_parts)

    # Ensure answer is a string
    if not isinstance(answer, str):
        answer = str(answer)

    # Return answer and source documents
    return {
        "answer": answer,
        "sources": sources,
    }