from pathlib import Path

from langchain_community.document_loaders import (
    PyPDFLoader,
    TextLoader
)


DOCUMENTS_DIR = Path("documents")


def load_documents():

    documents = []

    for file_path in DOCUMENTS_DIR.rglob("*"):

        if not file_path.is_file():
            continue

        suffix = file_path.suffix.lower()

        try:

            if suffix == ".pdf":

                loader = PyPDFLoader(
                    str(file_path)
                )

                docs = loader.load()

            elif suffix == ".txt":

                loader = TextLoader(
                    str(file_path),
                    encoding="utf-8"
                )

                docs = loader.load()

            else:

                continue

            for doc in docs:

                doc.metadata["source"] = str(
                    file_path
                )

            documents.extend(docs)

        except Exception as e:

            print(
                f"Error loading {file_path}: {e}"
            )

    return documents