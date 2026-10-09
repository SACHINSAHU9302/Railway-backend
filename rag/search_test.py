import os
import chromadb
from dotenv import load_dotenv

load_dotenv()

client = chromadb.CloudClient(
    tenant=os.getenv("CHROMA_TENANT"),
    database=os.getenv("CHROMA_DATABASE"),
    api_key=os.getenv("CHROMA_API_KEY"),
)

collection = client.get_or_create_collection(
    name="Railway_Backend"
)

query = "What facilities are available at Bhopal Junction?"

results = collection.query(
    query_texts=[query],
    n_results=2
)

print("\nQuestion:")
print(query)

print("\nRetrieved Documents:")

for i, document in enumerate(results["documents"][0]):
    print(f"\n--- Result {i + 1} ---")
    print(document)

print("\nMetadata:")
print(results["metadatas"][0])