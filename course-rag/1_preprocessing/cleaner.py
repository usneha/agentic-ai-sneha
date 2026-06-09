import re

LOW_VALUE_PHRASES = {
    "before we get started",
    "agenda",
    "thank you",
    "questions",
    "q&a",
    "welcome",
    "introduction",
}


def normalize_text(text: str) -> str:
    text = text or ""
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def is_useful_document(doc: dict, min_chars: int = 40) -> bool:
    text = normalize_text(doc.get("content", ""))
    lower_text = text.lower().strip(" .…!?-:")

    if len(text) < min_chars:
        return False

    if lower_text in LOW_VALUE_PHRASES:
        return False

    return True


def clean_documents(docs: list[dict]) -> list[dict]:
    cleaned = []

    for doc in docs:
        text = normalize_text(doc.get("content", ""))

        if not is_useful_document(doc):
            continue

        doc["content"] = text
        cleaned.append(doc)

    return cleaned
