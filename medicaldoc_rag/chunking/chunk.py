from uuid import NAMESPACE_URL, uuid5

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter


PARENT_CHUNK_SIZE = 1000
PARENT_CHUNK_OVERLAP = 100
CHILD_CHUNK_SIZE = 200
CHILD_CHUNK_OVERLAP = 40


def create_parent_child_chunks(
    documents: list[Document],
    parent_chunk_size: int = PARENT_CHUNK_SIZE,
    parent_chunk_overlap: int = PARENT_CHUNK_OVERLAP,
    child_chunk_size: int = CHILD_CHUNK_SIZE,
    child_chunk_overlap: int = CHILD_CHUNK_OVERLAP,
) -> tuple[list[Document], list[Document]]:
    """Split page documents into parent chunks and retrievable child chunks."""
    _validate_chunk_settings(parent_chunk_size, parent_chunk_overlap)
    _validate_chunk_settings(child_chunk_size, child_chunk_overlap)
    if child_chunk_size > parent_chunk_size:
        raise ValueError("Child chunk size cannot exceed parent chunk size")

    parent_splitter = RecursiveCharacterTextSplitter(
        chunk_size=parent_chunk_size,
        chunk_overlap=parent_chunk_overlap,
        add_start_index=True,
    )
    child_splitter = RecursiveCharacterTextSplitter(
        chunk_size=child_chunk_size,
        chunk_overlap=child_chunk_overlap,
        add_start_index=True,
    )

    parent_documents: list[Document] = []
    child_documents: list[Document] = []
    for document in documents:
        source_id = document.metadata.get(
            "document_id", document.metadata.get("source", "document")
        )
        for parent_index, parent in enumerate(
            parent_splitter.split_documents([document])
        ):
            parent_id = str(
                uuid5(
                    NAMESPACE_URL,
                    "medicaldoc-rag:parent:"
                    f"{source_id}:{document.metadata.get('page', 0)}:"
                    f"{parent.metadata['start_index']}:{parent_index}",
                )
            )
            parent.metadata.update(
                {
                    "parent_id": parent_id,
                    "chunk_type": "parent",
                }
            )
            parent_documents.append(parent)

            for child_index, child in enumerate(
                child_splitter.split_documents([parent])
            ):
                child_id = str(
                    uuid5(
                        NAMESPACE_URL,
                        f"medicaldoc-rag:child:{parent_id}:{child_index}:"
                        f"{child.metadata['start_index']}",
                    )
                )
                child.metadata.update(
                    {
                        "parent_id": parent_id,
                        "child_id": child_id,
                        "chunk_type": "child",
                    }
                )
                child_documents.append(child)

    return parent_documents, child_documents


def _validate_chunk_settings(chunk_size: int, chunk_overlap: int) -> None:
    if chunk_size <= 0:
        raise ValueError("Chunk size must be greater than zero")
    if chunk_overlap < 0 or chunk_overlap >= chunk_size:
        raise ValueError("Chunk overlap must be non-negative and smaller than size")
