from rag.vectorstore import get_vectorstore
from rag.config import COLLECTION_NAME

try:
    print("Connecting to Chroma Cloud...")

    vectorstore = get_vectorstore()

    print("\nCollection Name:", COLLECTION_NAME)

    collection = vectorstore._collection

    print("Total Documents:", collection.count())

    question = "Where is the waiting room at Bhopal Junction?"

    print("\nSearching:", question)

    results = vectorstore.similarity_search(
        question,
        k=3
    )

    print("\n========== SEARCH RESULTS ==========")

    if not results:
        print("No documents found.")

    for i, doc in enumerate(results, start=1):
        print(f"\nResult {i}")
        print("Content:", doc.page_content)
        print("Metadata:", doc.metadata)

except Exception as e:
    print("\nERROR:", str(e))