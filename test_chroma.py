import os
from importlib import import_module

try:
    load_dotenv = import_module("dotenv").load_dotenv
except ModuleNotFoundError as exc:
    if exc.name != "dotenv":
        raise
    raise ModuleNotFoundError(
        "python-dotenv is not installed. Install it with: python -m pip install python-dotenv"
    ) from exc
try:
    chromadb = import_module("chromadb")
except ModuleNotFoundError as exc:
    if exc.name != "chromadb":
        raise
    raise ModuleNotFoundError(
        "chromadb is not installed. Install it with: python -m pip install chromadb"
    ) from exc

load_dotenv()

client = chromadb.CloudClient(
    tenant=os.getenv("CHROMA_TENANT"),
    database=os.getenv("CHROMA_DATABASE"),
    api_key=os.getenv("CHROMA_API_KEY"),
)

collection = client.get_or_create_collection(
    name="Railway_Backend"
)

collection.add(
    ids=["test-001"],
    documents=[
        "Bhopal Junction railway station provides passenger facilities such as waiting rooms, ticket counters, food facilities and platforms."
    ],
    metadatas=[
        {
            "source": "test",
            "type": "station_information"
        }
    ]
)

print("Collection created successfully!")
print("Collection name:", collection.name)

results = collection.get()

print("\nStored documents:")
print(results)