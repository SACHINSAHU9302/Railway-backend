from .retriever import get_retriever


def test():

    retriever = get_retriever()

    query = "What facilities are available at railway stations?"

    documents = retriever.invoke(
        query
    )

    print(
        "\nRetrieved Documents:\n"
    )

    for i, doc in enumerate(
        documents,
        start=1
    ):

        print(
            f"\n--- Result {i} ---"
        )

        print(
            doc.page_content
        )

        print(
            "Source:",
            doc.metadata.get(
                "source"
            )
        )


if __name__ == "__main__":

    test()