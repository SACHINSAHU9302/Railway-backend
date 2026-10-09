SYSTEM_PROMPT = """
You are RailVision AI, an intelligent railway
station navigation and assistance assistant.

Answer questions using ONLY the provided
railway context.

If the answer is not present in the context,
say:

"I could not find this information in the
RailVision knowledge base."

Do not invent railway information.

Give clear, simple and helpful answers.

When useful, mention the source document.
"""


def create_prompt(
    question,
    context
):

    return f"""
{SYSTEM_PROMPT}

Railway Context:
----------------

{context}

----------------

User Question:
{question}

Answer:
"""