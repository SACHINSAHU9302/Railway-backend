import os
from pathlib import Path

import chromadb
from dotenv import load_dotenv
from pypdf import PdfReader
from langchain_text_splitters import RecursiveCharacterTextSplitter


# Load environment variables
load_dotenv()

# Project paths
BASE_DIR = Path(__file__).resolve().parent.parent
DOCUMENTS_DIR = BASE_DIR / "documents"

# Chroma Cloud connection
client = chromadb.CloudClient(
    tenant=os.getenv("CHROMA_TENANT"),
    database=os.getenv("CHROMA_DATABASE"),
    api_key=os.getenv("CHROMA_API_KEY"),
)

# Existing Chroma collection
collection = client.get_or_create_collection(
    name="Railway_Backend"
)

# Text splitter
splitter = RecursiveCharacterTextSplitter(
    chunk_size=800,
    chunk_overlap=100,
)


def load_txt(file_path):
    """Load TXT file."""
    return file_path.read_text(encoding="utf-8")


def load_pdf(file_path):
    """Load PDF file."""
    reader = PdfReader(str(file_path))

    pages = []

    for page in reader.pages:
        text = page.extract_text()

        if text:
            pages.append(text)

    return "\n".join(pages)


def load_documents():
    """Load all TXT and PDF documents."""

    documents = []

    for file_path in DOCUMENTS_DIR.rglob("*"):

        if file_path.suffix.lower() == ".txt":
            text = load_txt(file_path)

        elif file_path.suffix.lower() == ".pdf":
            text = load_pdf(file_path)

        else:
            continue

        if not text.strip():
            continue

        chunks = splitter.split_text(text)

        for index, chunk in enumerate(chunks):

            documents.append({
                "text": chunk,
                "source": str(file_path.relative_to(BASE_DIR)),
                "chunk": index,
            })

    return documents


def ingest_documents():

    documents = load_documents()

    if not documents:
        print("No TXT or PDF documents found.")
        return

    print(f"Found {len(documents)} chunks.")

    ids = []
    texts = []
    metadatas = []

    for index, document in enumerate(documents):

        ids.append(
            f"{document['source']}-{document['chunk']}-{index}"
        )

        texts.append(document["text"])

        metadatas.append({
            "source": document["source"],
            "chunk": document["chunk"],
        })

    collection.upsert(
        ids=ids,
        documents=texts,
        metadatas=metadatas,
    )

    print("Documents successfully added to Chroma Cloud!")
    print("Collection:", collection.name)
    print("Total documents:", collection.count())


if __name__ == "__main__":
    ingest_documents()