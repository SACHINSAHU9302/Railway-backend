    import os
    import hashlib
    import re
    from pathlib import Path
    from datetime import date
    from collections import defaultdict

    import chromadb
    from dotenv import load_dotenv
    from pypdf import PdfReader
    from bs4 import BeautifulSoup
    from langchain_text_splitters import RecursiveCharacterTextSplitter


    # --------------------------------------------------
    # 1. Environment and paths
    # --------------------------------------------------

    load_dotenv()

    BASE_DIR = Path(__file__).resolve().parent.parent

    DOCUMENT_FOLDERS = [
        BASE_DIR / "documents",
        BASE_DIR / "railway_documents",
    ]

    COLLECTION_NAME = "Railway_Backend"


    # --------------------------------------------------
    # 2. Chroma Cloud connection
    # --------------------------------------------------

    required_env = [
        "CHROMA_TENANT",
        "CHROMA_DATABASE",
        "CHROMA_API_KEY",
    ]

    missing = [
        key for key in required_env
        if not os.getenv(key)
    ]

    if missing:
        raise RuntimeError(
            "Missing Chroma environment variables: "
            + ", ".join(missing)
        )

    client = chromadb.CloudClient(
        tenant=os.getenv("CHROMA_TENANT"),
        database=os.getenv("CHROMA_DATABASE"),
        api_key=os.getenv("CHROMA_API_KEY"),
    )

    collection = client.get_or_create_collection(
        name=COLLECTION_NAME
    )


    # --------------------------------------------------
    # 3. Text splitting
    # --------------------------------------------------

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=800,
        chunk_overlap=100,
    )


    # --------------------------------------------------
    # 4. Extract text from documents
    # --------------------------------------------------

    def load_txt(file_path):
        return file_path.read_text(
            encoding="utf-8",
            errors="ignore",
        )


    def load_pdf(file_path):
        reader = PdfReader(str(file_path))

        pages = []

        for page in reader.pages:
            text = page.extract_text() or ""

            if text.strip():
                pages.append(text)

        return "\n".join(pages)


    def load_html(file_path):
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
        suffix = file_path.suffix.lower()

        if suffix == ".pdf":
            return load_pdf(file_path)

        if suffix in {".html", ".htm"}:
            return load_html(file_path)

        if suffix == ".txt":
            return load_txt(file_path)

        return ""


    # --------------------------------------------------
    # 5. Document metadata
    # --------------------------------------------------

    def get_category(file_path):
        name = file_path.stem.lower()
        relative = str(file_path.relative_to(BASE_DIR)).lower()

        if "luggage" in name:
            return "Luggage Policy"

        if "refund" in name:
            return "Refund & Cancellation"

        if "concession" in name:
            return "Divyangjan & Senior Citizen"

        if "agent" in name or "terms_conditions" in name:
            return "General Rules"

        if "circular" in name:
            return "Railway Board Circular"

        if "rule" in name or "rules" in name:
            return "General Rules"

        if "facility" in relative:
            return "Station Facilities"

        return "Railway Documents"


    def get_source_url(file_path):
        """
        Return a source URL only when it is known.
        A local filename is not treated as proof of origin.
        """
        name = file_path.name.lower()

        if name == "railway_luggage_rules.html":
            return "https://indianrail.gov.in/luggage_Rule.html"

        if name == "railway_refund_rules.html":
            return "https://indianrail.gov.in/refund_Rules.html"

        return ""


    def get_effective_date(file_path):
        """
        Keep a known effective date for the legacy refund page.
        Do not guess dates for other documents.
        """
        if file_path.name.lower() == "railway_refund_rules.html":
            return "2015-11-12"

        return "unknown"


    # --------------------------------------------------
    # 6. Collect and deduplicate document chunks
    # --------------------------------------------------

    def load_documents():
        documents = []
        seen_content = set()

        file_count = 0
        duplicate_count = 0
        empty_count = 0

        for folder in DOCUMENT_FOLDERS:

            if not folder.exists():
                continue

            for file_path in sorted(folder.rglob("*")):

                if not file_path.is_file():
                    continue

                if file_path.suffix.lower() not in {
                    ".pdf", ".html", ".htm", ".txt"
                }:
                    continue

                # Do not read the same physical file twice
                file_count += 1

                try:
                    text = extract_text(file_path)
                except Exception as exc:
                    print(f"ERROR reading {file_path.name}: {exc}")
                    continue

                normalized = re.sub(
                    r"\s+",
                    " ",
                    text,
                ).strip().lower()

                if len(normalized) < 50:
                    empty_count += 1
                    print(
                        f"SKIPPED: {file_path.name} "
                        "(no usable text)"
                    )
                    continue

                # Skip identical content even if filenames differ
                content_hash = hashlib.sha256(
                    normalized.encode("utf-8")
                ).hexdigest()

                if content_hash in seen_content:
                    duplicate_count += 1
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

                    chunk_hash = hashlib.sha256(
                        chunk.encode("utf-8")
                    ).hexdigest()

                    documents.append({
                        "text": chunk,
                        "source": relative_source,
                        "title": file_path.stem,
                        "category": category,
                        "source_url": source_url,
                        "effective_date": effective_date,
                        "last_verified": "unknown",
                        "chunk": chunk_index,
                        "chunk_hash": chunk_hash,
                    })

        print("\nDocument scan summary")
        print("---------------------")
        print("Files scanned:", file_count)
        print("Duplicate files skipped:", duplicate_count)
        print("Files without usable text:", empty_count)
        print("Chunks prepared:", len(documents))

        return documents


    # --------------------------------------------------
    # 7. Ingest into Chroma Cloud
    # --------------------------------------------------

    def ingest_documents():
        documents = load_documents()

        if not documents:
            print("No usable document chunks found.")
            return

        # Stable IDs allow safe reruns of the same source/chunk.
        # Existing records from unrelated sources are not deleted.
        ids = []
        texts = []
        metadatas = []

        for document in documents:

            stable_key = (
                document["source"]
                + "|"
                + str(document["chunk"])
            )

            document_id = hashlib.sha256(
                stable_key.encode("utf-8")
            ).hexdigest()

            ids.append(document_id)
            texts.append(document["text"])

            metadatas.append({
                "source": document["source"],
                "title": document["title"],
                "category": document["category"],
                "source_url": document["source_url"],
                "effective_date": document["effective_date"],
                "last_verified": document["last_verified"],
                "chunk": document["chunk"],
                "chunk_hash": document["chunk_hash"],
            })

        # Upsert updates records with the same IDs.
        # It does not clear the collection.
        batch_size = 100

        for start in range(0, len(ids), batch_size):

            end = start + batch_size

            collection.upsert(
                ids=ids[start:end],
                documents=texts[start:end],
                metadatas=metadatas[start:end],
            )

            print(
                f"Uploaded chunks {start + 1} "
                f"to {min(end, len(ids))}"
            )

        print("\nIngestion completed.")
        print("Collection:", collection.name)
        print("Total records currently in collection:", collection.count())


    if __name__ == "__main__":
        ingest_documents()