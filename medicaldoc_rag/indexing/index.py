from dataclasses import dataclass
from pathlib import Path

import chromadb
from langchain_core.documents import Document

from medicaldoc_rag.config import CHROMA_DIRECTORY

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PARENT_COLLECTION_NAME = "medicaldoc_parents"
CHILD_COLLECTION_NAME = "medicaldoc_children"


@dataclass(frozen=True)
class IndexingResult:
    parent_count: int
    child_count: int
    parent_collection: str
    child_collection: str
    persist_directory: Path


def store_parent_child_chunks(
    parents: list[Document],
    children: list[Document],
    persist_directory: str | Path = CHROMA_DIRECTORY,
) -> IndexingResult:
    """Embed and persist parent and child chunks in separate Chroma collections."""
    if not parents or not children:
        raise ValueError("Both parent and child chunks are required for indexing")

    parent_ids = [document.metadata["parent_id"] for document in parents]
    child_ids = [document.metadata["child_id"] for document in children]
    if len(parent_ids) != len(set(parent_ids)):
        raise ValueError("Parent chunk IDs must be unique")
    if len(child_ids) != len(set(child_ids)):
        raise ValueError("Child chunk IDs must be unique")

    parent_id_set = set(parent_ids)
    if any(document.metadata["parent_id"] not in parent_id_set for document in children):
        raise ValueError("Every child chunk must reference a supplied parent")

    directory = Path(persist_directory).resolve()
    client = chromadb.PersistentClient(path=str(directory))
    existing_collections = {item.name for item in client.list_collections()}
    for collection_name in (PARENT_COLLECTION_NAME, CHILD_COLLECTION_NAME):
        if collection_name in existing_collections:
            client.delete_collection(collection_name)
    parent_collection = client.create_collection(PARENT_COLLECTION_NAME)
    child_collection = client.create_collection(CHILD_COLLECTION_NAME)

    _upsert_documents(parent_collection, parents, parent_ids)
    _upsert_documents(child_collection, children, child_ids)

    return IndexingResult(
        parent_count=len(parents),
        child_count=len(children),
        parent_collection=PARENT_COLLECTION_NAME,
        child_collection=CHILD_COLLECTION_NAME,
        persist_directory=directory,
    )


def _upsert_documents(
    collection: chromadb.Collection,
    documents: list[Document],
    ids: list[str],
) -> None:
    collection.upsert(
        ids=ids,
        documents=[document.page_content for document in documents],
        metadatas=[document.metadata for document in documents],
    )
