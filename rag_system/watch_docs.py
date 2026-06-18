"""
watch_docs.py - File watcher for automatic RAG indexing.

Monitors docs/ (PDFs, XLSX) and tech_notes/ (Markdown) recursively.
On file add/modify/delete it updates ChromaDB and doc_registry.json
without restarting the process.
"""

import sys
import time
from datetime import datetime
from pathlib import Path

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

# ---------------------------------------------------------------------------
# Re-use helpers from sync_docs
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).parent.resolve()
sys.path.insert(0, str(BASE_DIR))

import chromadb
from sentence_transformers import SentenceTransformer

from sync_docs import (
    CHROMA_DIR,
    COLLECTION_NAME,
    DOCS_DIR,
    NOTES_DIR,
    EMBED_MODEL_NAME,
    chunk_ids_for_source,
    index_document,
    index_note,
    index_spreadsheet,
    load_registry,
    md5_file,
    relative_source,
    relative_note_source,
    remove_document,
    save_registry,
)


# ---------------------------------------------------------------------------
# Shared state (loaded once at startup)
# ---------------------------------------------------------------------------

def _load_shared():
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    NOTES_DIR.mkdir(parents=True, exist_ok=True)
    CHROMA_DIR.mkdir(parents=True, exist_ok=True)
    print(f"[watch] Loading embedding model '{EMBED_MODEL_NAME}' ...")
    model = SentenceTransformer(EMBED_MODEL_NAME)
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    collection = client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )
    return model, collection


# ---------------------------------------------------------------------------
# Event handler
# ---------------------------------------------------------------------------

class DocEventHandler(FileSystemEventHandler):
    def __init__(self, model: SentenceTransformer, collection):
        super().__init__()
        self.model = model
        self.collection = collection

    @staticmethod
    def _is_pdf(path: str) -> bool:
        return path.lower().endswith(".pdf")

    @staticmethod
    def _is_md(path: str) -> bool:
        return path.lower().endswith(".md")

    @staticmethod
    def _is_xlsx(path: str) -> bool:
        # Ignore Excel temp lock files like "~$Book.xlsx"
        return path.lower().endswith(".xlsx") and not Path(path).name.startswith("~$")

    def _source_and_indexer(self, path: Path):
        """Return (source_key, index_fn) based on file type and location."""
        if self._is_pdf(str(path)):
            return relative_source(path), index_document
        if self._is_xlsx(str(path)):
            return relative_source(path), index_spreadsheet
        if self._is_md(str(path)):
            return relative_note_source(path), index_note
        return None, None

    def on_created(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        file_path = Path(event.src_path)
        source, indexer = self._source_and_indexer(file_path)
        if source is None or not file_path.exists():
            return
        print(f"[{self._ts()}] [+] New file detected: {source}")
        registry = load_registry()
        chunk_count = indexer(file_path, self.collection, self.model)
        registry[source] = {
            "hash": md5_file(file_path),
            "chunk_count": chunk_count,
            "indexed_at": datetime.utcnow().isoformat(),
        }
        save_registry(registry)
        print(f"[{self._ts()}]     Indexed {chunk_count} chunks.")

    def on_modified(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        file_path = Path(event.src_path)
        source, indexer = self._source_and_indexer(file_path)
        if source is None or not file_path.exists():
            return
        registry = load_registry()
        current_hash = md5_file(file_path)
        entry = registry.get(source)
        if entry and entry.get("hash") == current_hash:
            return  # spurious modify event, content unchanged
        print(f"[{self._ts()}] [~] File modified: {source}")
        remove_document(source, self.collection)
        chunk_count = indexer(file_path, self.collection, self.model)
        registry[source] = {
            "hash": current_hash,
            "chunk_count": chunk_count,
            "indexed_at": datetime.utcnow().isoformat(),
        }
        save_registry(registry)
        print(f"[{self._ts()}]     Re-indexed {chunk_count} chunks.")

    def on_deleted(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        file_path = Path(event.src_path)
        source, _ = self._source_and_indexer(file_path)
        if source is None:
            return
        print(f"[{self._ts()}] [-] File deleted: {source}")
        removed = remove_document(source, self.collection)
        registry = load_registry()
        registry.pop(source, None)
        save_registry(registry)
        print(f"[{self._ts()}]     Removed {removed} chunks.")

    def on_moved(self, event: FileSystemEvent) -> None:
        """Treat a move as delete-old + create-new."""
        if event.is_directory:
            return
        # Delete old
        old_path = Path(event.src_path)
        old_source, _ = self._source_and_indexer(old_path)
        if old_source:
            removed = remove_document(old_source, self.collection)
            registry = load_registry()
            registry.pop(old_source, None)
            save_registry(registry)
            print(f"[{self._ts()}] [mv] Removed old: {old_source} ({removed} chunks)")
        # Index new
        new_path = Path(event.dest_path)
        new_source, indexer = self._source_and_indexer(new_path)
        if new_source and indexer and new_path.exists():
            registry = load_registry()
            chunk_count = indexer(new_path, self.collection, self.model)
            registry[new_source] = {
                "hash": md5_file(new_path),
                "chunk_count": chunk_count,
                "indexed_at": datetime.utcnow().isoformat(),
            }
            save_registry(registry)
            print(f"[{self._ts()}] [mv] Indexed new:  {new_source} ({chunk_count} chunks)")

    @staticmethod
    def _ts() -> str:
        return datetime.now().strftime("%H:%M:%S")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    model, collection = _load_shared()
    event_handler = DocEventHandler(model=model, collection=collection)
    observer = Observer()
    observer.schedule(event_handler, str(DOCS_DIR), recursive=True)
    observer.schedule(event_handler, str(NOTES_DIR), recursive=True)
    observer.start()
    print(f"[watch] Watching {DOCS_DIR} and {NOTES_DIR} (recursive). Press Ctrl+C to stop.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()
    print("[watch] Stopped.")


if __name__ == "__main__":
    main()
