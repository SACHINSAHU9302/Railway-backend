import os

import chromadb
from dotenv import load_dotenv
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from langchain_google_genai import ChatGoogleGenerativeAI

load_dotenv()


# -----------------------------
# Chroma Cloud
# -----------------------------

chroma_client = chromadb.CloudClient(
    tenant=os.getenv("CHROMA_TENANT"),
    database=os.getenv("CHROMA_DATABASE"),
    api_key=os.getenv("CHROMA_API_KEY"),
)

collection = chroma_client.get_or_create_collection(
    name="Railway_Backend"
)


# -----------------------------
# Gemini
# -----------------------------

llm = ChatGoogleGenerativeAI(
    model="gemini-3.8-flash",
    google_api_key=os.getenv("GOOGLE_API_KEY"),
)


# -----------------------------
# RAG API
# -----------------------------

@csrf_exempt
def rag_query(request):

    if request.method != "POST":
        return JsonResponse(
            {
                "error": "Only POST method is allowed."
            },
            status=405,
        )

    try:
        import json

        data = json.loads(request.body)

        question = data.get("question", "").strip()

        if not question:
            return JsonResponse(
                {
                    "error": "Question is required."
                },
                status=400,
            )

        # Search Chroma
        results = collection.query(
            query_texts=[question],
            n_results=3,
        )

        documents = results.get("documents", [[]])[0]

        if not documents:
            return JsonResponse(
                {
                    "answer": "Sorry, I could not find relevant railway information."
                }
            )

        # Build context
        context = "\n\n".join(documents)

        # Prompt Gemini
        prompt = f"""
You are RailVision AI, an intelligent railway station
navigation and assistance assistant.

Answer the user's question using ONLY the information
provided in the context.

Do not invent or assume information.

If the answer is not available in the context,
say that the information is not available in the
Railway knowledge base.

Context:
{context}

User Question:
{question}

Give a clear and concise answer.
"""

        # Gemini
        response = llm.invoke(prompt)

        # Extract clean text
        if isinstance(response.content, list):
            answer_parts = []

            for item in response.content:
                if isinstance(item, dict) and item.get("type") == "text":
                    answer_parts.append(item.get("text", ""))

            answer = "\n".join(answer_parts)

        else:
            answer = response.content

        return JsonResponse(
            {
                "success": True,
                "question": question,
                "answer": answer,
            }
        )

    except json.JSONDecodeError:
        return JsonResponse(
            {
                "error": "Invalid JSON."
            },
            status=400,
        )

    except Exception as e:
        return JsonResponse(
            {
                "error": str(e)
            },
            status=500,
        )