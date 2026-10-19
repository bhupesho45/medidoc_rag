import os
from pathlib import Path


PROJECT_DIRECTORY = Path(__file__).resolve().parent
DATA_DIRECTORY = Path(
    os.getenv("MEDICALDOC_DATA_DIR") or PROJECT_DIRECTORY
).expanduser().resolve()
UPLOAD_DIRECTORY = DATA_DIRECTORY / "data" / "uploads"
CHROMA_DIRECTORY = DATA_DIRECTORY / "chroma_db"
