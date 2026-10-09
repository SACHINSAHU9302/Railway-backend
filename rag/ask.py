import os

import chromadb
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI

load_dotenv()


# -----------------------------
# Chroma Cloud
# -----------------------------

client = chromadb.CloudClient(
    tenant=os.getenv("CHROMA_TENANT"),
    database=os.getenv("CHROMA_DATABASE"),
    api_key=os.getenv("CHROMA_API_KEY"),
)

collection = client.get_or_create_collection(
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
# Ask Question
# -----------------------------

question = "What facilities are available at Bhopal Junction?"


# Search Chroma
results = collection.query(
    query_texts=[question],
    n_results=2,
)


# Build context
documents = results["documents"][0]

context = "\n\n".join(documents)


# Prompt Gemini
prompt = f"""
You are RailVision AI, an intelligent railway station
navigation and assistance assistant.

Answer the user's question using ONLY the information
provided in the context.

If the answer is not available in the context,
say that the information is not available.

Context:
{context}

User Question:
{question}

Give a clear and concise answer.
"""


# Generate answer
response = llm.invoke(prompt)



print("Question:")
print(question)

print("\nAI Answer:")

if isinstance(response.content, list):
    for item in response.content:
        if isinstance(item, dict) and item.get("type") == "text":
            print(item.get("text", ""))
else:
    print(response.content)

