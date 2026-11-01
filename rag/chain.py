import logging
from .database import get_station_answer
from .retriever import get_retriever
from .llm import get_llm
from .prompt import create_prompt


# ============================================================
# LOGGER CONFIGURATION
# ============================================================

logger = logging.getLogger(__name__)


# ============================================================
# HELPER FUNCTION: CONVERT RESPONSE INTO TEXT
# ============================================================

def extract_answer_text(content):

    # Normal string response
    if isinstance(content, str):
        return content.strip()

    # Gemini content blocks
    if isinstance(content, list):

        text_parts = []

        for item in content:

            if isinstance(item, str):
                text_parts.append(item)

            elif isinstance(item, dict):

                if item.get("type") == "text":
                    text_parts.append(
                        item.get("text", "")
                    )

        return "\n".join(text_parts).strip()

    # Other response formats
    return str(content).strip()


# ============================================================
# HELPER FUNCTION: EXTRACT DOCUMENT SOURCES
# ============================================================

def extract_sources(documents):

    sources = []
    seen_sources = set()

    for doc in documents:

        metadata = doc.metadata or {}

        source = metadata.get("source", "")

        if not source:
            continue

        source = str(source)

        if source in seen_sources:
            continue

        seen_sources.add(source)

        sources.append({

            "source": source,

            "title": str(
                metadata.get("title", "")
            ),

            "category": str(
                metadata.get("category", "")
            ),

            "source_url": str(
                metadata.get("source_url", "")
            ),

            "effective_date": str(
                metadata.get("effective_date", "unknown")
            ),

        })

    return sources


# ============================================================
# MAIN RAG FUNCTION
# ============================================================

def ask_rag(question):

    # --------------------------------------------------------
    # 1. VALIDATE QUESTION
    # --------------------------------------------------------

    if not isinstance(question, str) or not question.strip():

        return {
            "answer": "Please enter a valid question.",
            "sources": [],
        }

    question = question.strip()

    try:

        logger.info("====================================")
        logger.info("RAILVISION RAG STARTED")
        logger.info("QUESTION: %s", question)

        # =========================================
        # CHECK DJANGO DATABASE FIRST
        # =========================================

        database_answer = get_station_answer(question)

        if database_answer:

            logger.info("Answer generated using Django database.")

            return {
                "answer": database_answer,
                "sources": [
                    {
                        "source": "Django Station Database",
                        "title": "Station, Platform and Facility Records",
                        "category": "Station Information",
                        "source_url": "",
                        "effective_date": "Database records",
                    }
                ],
            }

        # =========================================
        # EXISTING CHROMA RAG CODE
        # =========================================

        # ----------------------------------------------------
        # 2. GET RETRIEVER
        # ----------------------------------------------------

        retriever = get_retriever()

        if retriever is None:
            raise ValueError("Retriever initialization failed.")

        # ----------------------------------------------------
        # 3. RETRIEVE RELEVANT DOCUMENTS
        # ----------------------------------------------------

        documents = retriever.invoke(question)

        logger.info(
            "RETRIEVED DOCUMENT COUNT: %s",
            len(documents)
        )

        # ----------------------------------------------------
        # 4. DEBUG RETRIEVED DOCUMENTS
        # ----------------------------------------------------

        for index, doc in enumerate(documents):

            logger.info(
                "DOCUMENT NUMBER: %s",
                index + 1
            )

            logger.info(
                "DOCUMENT CONTENT: %s",
                doc.page_content
            )

            logger.info(
                "DOCUMENT METADATA: %s",
                doc.metadata
            )

        # ----------------------------------------------------
        # 5. HANDLE NO DOCUMENTS
        # ----------------------------------------------------

        if not documents:

            logger.warning(
                "No relevant documents found."
            )

            return {
                "answer": (
                    "I could not find this information "
                    "in the RailVision knowledge base."
                ),
                "sources": [],
            }

        # ----------------------------------------------------
        # 6. PREPARE CONTEXT
        # ----------------------------------------------------

        context_parts = []

        for doc in documents:

            if doc.page_content:

                context_parts.append(
                    doc.page_content
                )

        context = "\n\n".join(context_parts)

        # ----------------------------------------------------
        # 7. EXTRACT SOURCES
        # ----------------------------------------------------

        sources = extract_sources(documents)

        # ----------------------------------------------------
        # 8. VALIDATE CONTEXT
        # ----------------------------------------------------

        if not context.strip():

            logger.warning(
                "Retrieved documents have empty content."
            )

            return {
                "answer": (
                    "Retrieved documents contain no readable content."
                ),
                "sources": sources,
            }

        logger.info(
            "CONTEXT LENGTH: %s",
            len(context)
        )

        # ----------------------------------------------------
        # 9. CREATE PROMPT
        # ----------------------------------------------------

        prompt = create_prompt(
            question,
            context
        )

        # ----------------------------------------------------
        # 10. GET GEMINI LLM
        # ----------------------------------------------------

        llm = get_llm()

        if llm is None:
            raise ValueError("LLM initialization failed.")

        # ----------------------------------------------------
        # 11. GENERATE ANSWER
        # ----------------------------------------------------

        response = llm.invoke(prompt)

        # ----------------------------------------------------
        # 12. EXTRACT ANSWER
        # ----------------------------------------------------

        answer = extract_answer_text(
            response.content
        )

        if not answer:

            answer = (
                "I could not generate an answer. "
                "Please try again."
            )

        # ----------------------------------------------------
        # 13. FINAL DEBUG
        # ----------------------------------------------------

        logger.info(
            "GENERATED ANSWER: %s",
            answer
        )

        logger.info(
            "SOURCE COUNT: %s",
            len(sources)
        )

        logger.info("RAILVISION RAG COMPLETED")
        logger.info("====================================")

        # ----------------------------------------------------
        # 14. RETURN FINAL RESULT
        # ----------------------------------------------------

        return {

            "answer": answer,

            "sources": sources,

        }

    # --------------------------------------------------------
    # 15. ERROR HANDLING
    # --------------------------------------------------------

    except Exception:

        logger.exception(
            "RailVision RAG processing failed."
        )

        raise