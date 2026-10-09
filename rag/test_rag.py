from .chain import ask_rag


question = (
    "What facilities are available "
    "at a railway station?"
)


result = ask_rag(
    question
)


print("\nANSWER:")
print(result["answer"])


print("\nSOURCES:")

for source in result["sources"]:

    print(source)