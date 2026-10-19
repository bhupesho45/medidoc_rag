import re

from langchain_core.documents import Document


_CONTROL_CHARACTERS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_HORIZONTAL_WHITESPACE = re.compile(r"[ \t]+")
_EXCESS_BLANK_LINES = re.compile(r"\n{3,}")


def clean_text(text: str) -> str:
    """Normalize extracted text while preserving paragraph and line breaks."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _CONTROL_CHARACTERS.sub("", text)
    text = _HORIZONTAL_WHITESPACE.sub(" ", text)
    text = _EXCESS_BLANK_LINES.sub("\n\n", text)
    return text.strip()


def clean_documents(documents: list[Document]) -> list[Document]:
    """Clean page documents and omit pages without usable text."""
    cleaned: list[Document] = []
    for document in documents:
        page_content = clean_text(document.page_content)
        if page_content:
            cleaned.append(
                Document(
                    page_content=page_content,
                    metadata=document.metadata.copy(),
                )
            )
    return cleaned
