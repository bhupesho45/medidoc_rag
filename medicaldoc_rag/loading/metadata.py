from pathlib import Path
from uuid import NAMESPACE_URL, uuid5


def build_page_metadata(
    source_path: str | Path,
    page_number: int,
    project_root: str | Path,
) -> dict[str, str | int]:
    """Build stable source, page, and document identifiers for a PDF page."""
    source_file = Path(source_path).resolve()
    root = Path(project_root).resolve()
    try:
        source = source_file.relative_to(root).as_posix()
    except ValueError:
        source = source_file.name

    document_id = str(uuid5(NAMESPACE_URL, f"medicaldoc-rag:{source}"))
    return {
        "source": source,
        "page": page_number,
        "document_id": document_id,
    }
