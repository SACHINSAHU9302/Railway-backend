import os
import hashlib
import re
from pathlib import Path

import chromadb
from dotenv import load_dotenv
from pypdf import PdfReader
from bs4 import BeautifulSoup
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_chroma import Chroma

from .config import COLLECTION_NAME
from .embeddings import get_embeddings


# ==================================================
# 1. ENVIRONMENT AND PATHS
# ==================================================

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")

DOCUMENT_FOLDERS = [
    BASE_DIR / "documents",
    BASE_DIR / "railway_documents",
]

# Use the collection configured in rag/config.py.
# Expected: Railway_Rules_Knowledge
print("Target collection:", COLLECTION_NAME)


# ==================================================
# 2. CHROMA CLOUD CONNECTION
# ==================================================

def get_chroma_client():
    """Create a connection to Chroma Cloud."""

    required_env = [
        "CHROMA_TENANT",
        "CHROMA_DATABASE",
        "CHROMA_API_KEY",
    ]

    missing = [
        key
        for key in required_env
        if not os.getenv(key)
    ]

    if missing:
        raise RuntimeError(
            "Missing environment variables: "
            + ", ".join(missing)
        )

    return chromadb.CloudClient(
        tenant=os.getenv("CHROMA_TENANT"),
        database=os.getenv("CHROMA_DATABASE"),
        api_key=os.getenv("CHROMA_API_KEY"),
    )


def get_vectorstore():
    """
    Connect LangChain to the configured Chroma Cloud collection.

    Gemini embeddings are used for both ingestion and retrieval.
    """

    client = get_chroma_client()

    vectorstore = Chroma(
        client=client,
        collection_name=COLLECTION_NAME,
        embedding_function=get_embeddings(),
    )

    return vectorstore


# ==================================================
# 3. TEXT SPLITTER
# ==================================================

splitter = RecursiveCharacterTextSplitter(
    chunk_size=800,
    chunk_overlap=100,
    separators=["\n\n", "\n", ". ", " ", ""],
)


# ==================================================
# 4. DOCUMENT TEXT EXTRACTION
# ==================================================

def load_txt(file_path):
    """Read a text file."""

    return file_path.read_text(
        encoding="utf-8",
        errors="ignore",
    )


def load_pdf(file_path):
    """Extract text from a PDF."""

    reader = PdfReader(str(file_path))

    pages = []

    for page in reader.pages:
        page_text = page.extract_text() or ""

        if page_text.strip():
            pages.append(page_text)

    return "\n".join(pages)


def load_html(file_path):
    """Extract readable text from an HTML file."""

    html = file_path.read_text(
        encoding="utf-8",
        errors="ignore",
    )

    soup = BeautifulSoup(html, "html.parser")

    for element in soup(
        ["script", "style", "noscript"]
    ):
        element.decompose()

    return soup.get_text(
        separator="\n",
        strip=True,
    )


def extract_text(file_path):
    """Select an extraction method based on file extension."""

    extension = file_path.suffix.lower()

    if extension == ".pdf":
        return load_pdf(file_path)

    if extension in {".html", ".htm"}:
        return load_html(file_path)

    if extension == ".txt":
        return load_txt(file_path)

    return ""


# ==================================================
# 5. DOCUMENT METADATA
# ==================================================

def get_category(file_path):
    """Assign a category based on the filename."""

    name = file_path.stem.lower()
    relative_path = str(
        file_path.relative_to(BASE_DIR)
    ).lower()

    if "luggage" in name:
        return "Luggage Policy"

    if "refund" in name:
        return "Refund & Cancellation"

    if "concession" in name:
        return "Concession Rules"

    if "agent" in name or "terms_conditions" in name:
        return "General Rules"

    if "circular" in name:
        return "Railway Board Circular"

    if "facility" in relative_path:
        return "Station Facilities"

    if "rule" in name or "rules" in name:
        return "General Rules"

    return "Railway Documents"


def get_source_url(file_path):
    """Return a known source URL for recognized local files."""

    name = file_path.name.lower()

    if name == "railway_luggage_rules.html":
        return "https://indianrail.gov.in/luggage_Rule.html"

    if name == "railway_refund_rules.html":
        return "https://indianrail.gov.in/refund_Rules.html"

    return ""


def get_effective_date(file_path):
    """
    Preserve the known date for the legacy refund document.

    Do not assume other documents are current without verification.
    """

    if file_path.name.lower() == "railway_refund_rules.html":
        return "2015-11-12"

    return "unknown"


# ==================================================
# 6. DOCUMENT DISCOVERY AND CHUNKING
# ==================================================

def load_documents():
    """
    Read supported files, skip unusable documents,
    deduplicate identical file contents and create chunks.
    """

    documents = []
    seen_content = set()

    files_scanned = 0
    duplicate_files = 0
    unusable_files = 0
    failed_files = 0

    supported_extensions = {
        ".pdf",
        ".html",
        ".htm",
        ".txt",
    }

    for folder in DOCUMENT_FOLDERS:

        if not folder.exists():
            print("Folder not found:", folder)
            continue

        for file_path in sorted(folder.rglob("*")):

            if not file_path.is_file():
                continue

            if file_path.suffix.lower() not in supported_extensions:
                continue

            files_scanned += 1

            try:
                text = extract_text(file_path)

            except Exception as exc:
                failed_files += 1

                print(
                    f"ERROR reading {file_path.name}: {exc}"
                )
                continue

            normalized_text = re.sub(
                r"\s+",
                " ",
                text,
            ).strip().lower()

            # Skip empty PDFs or files without useful extracted text.
            if len(normalized_text) < 50:
                unusable_files += 1

                print(
                    f"SKIPPED: {file_path.name} "
                    "(no usable extracted text)"
                )
                continue

            # Deduplicate identical full-document contents.
            content_hash = hashlib.sha256(
                normalized_text.encode("utf-8")
            ).hexdigest()

            if content_hash in seen_content:
                duplicate_files += 1

                print(
                    f"DUPLICATE SKIPPED: {file_path.name}"
                )
                continue

            seen_content.add(content_hash)

            relative_source = str(
                file_path.relative_to(BASE_DIR)
            ).replace("\\", "/")

            chunks = splitter.split_text(text)

            category = get_category(file_path)
            source_url = get_source_url(file_path)
            effective_date = get_effective_date(file_path)

            for chunk_index, chunk in enumerate(chunks):

                # Stable chunk ID based on source path and chunk number.
                stable_key = (
                    relative_source
                    + "|"
                    + str(chunk_index)
                )

                document_id = hashlib.sha256(
                    stable_key.encode("utf-8")
                ).hexdigest()

                chunk_hash = hashlib.sha256(
                    chunk.encode("utf-8")
                ).hexdigest()

                documents.append({
                    "id": document_id,
                    "text": chunk,
                    "metadata": {
                        "source": relative_source,
                        "title": file_path.stem,
                        "category": category,
                        "source_url": source_url,
                        "effective_date": effective_date,
                        "last_verified": "unknown",
                        "chunk": chunk_index,
                        "chunk_hash": chunk_hash,
                    },
                })

    print("\n========== DOCUMENT SCAN SUMMARY ==========")
    print("Files scanned:", files_scanned)
    print("Duplicate files skipped:", duplicate_files)
    print("Files without usable text:", unusable_files)
    print("Files with extraction errors:", failed_files)
    print("Chunks prepared:", len(documents))
    print("===========================================\n")

    return documents


# ==================================================
# 7. INGEST DOCUMENTS INTO CHROMA CLOUD
# ==================================================

def ingest_documents():
    """Embed document chunks and store them in Chroma Cloud."""

    documents = load_documents()

    if not documents:
        print("No usable document chunks found.")
        return

    vectorstore = get_vectorstore()

    # Keep IDs stable so rerunning the same ingestion updates
    # existing source/chunk records instead of duplicating them.
    batch_size = 50

    for start in range(0, len(documents), batch_size):

        batch = documents[start:start + batch_size]

        ids = [
            item["id"]
            for item in batch
        ]

        texts = [
            item["text"]
            for item in batch
        ]

        metadatas = [
            item["metadata"]
            for item in batch
        ]

        vectorstore.add_texts(
            texts=texts,
            metadatas=metadatas,
            ids=ids,
        )

        end = start + len(batch)

        print(
            f"Processed chunks {start + 1}-{end} "
            f"of {len(documents)}"
        )

    print("\n========== INGESTION COMPLETE ==========")
    print("Collection:", COLLECTION_NAME)
    print("Chunks processed:", len(documents))

    # Reconnect to the configured collection and verify its count.
    client = get_chroma_client()
    collection = client.get_collection(
        name=COLLECTION_NAME
    )

    print("Total records in collection:", collection.count())
    print("========================================")


# ==================================================
# 8. MAIN
# ==================================================

if __name__ == "__main__":
    ingest_documents()