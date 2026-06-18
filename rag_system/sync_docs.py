"""
sync_docs.py - Document indexing & sync script for local RAG system.

Recursively scans docs/ for PDF and XLSX files and tech_notes/ for Markdown
files, computes MD5 hashes to detect changes, and maintains a ChromaDB vector
store with chunked embeddings.
"""

import hashlib
import json
import os
import sys
from datetime import datetime
from pathlib import Path

import chromadb
import fitz  # PyMuPDF
from chromadb.utils import embedding_functions
from sentence_transformers import SentenceTransformer

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).parent.resolve()
DOCS_DIR = BASE_DIR / "docs"
NOTES_DIR = BASE_DIR.parent / "tech_notes"
CHROMA_DIR = BASE_DIR / "chroma_db"
REGISTRY_PATH = BASE_DIR / "doc_registry.json"

# ---------------------------------------------------------------------------
# Chunking parameters
# ---------------------------------------------------------------------------
CHUNK_SIZE = 800
CHUNK_OVERLAP = 200

# ---------------------------------------------------------------------------
# Embedding model
# ---------------------------------------------------------------------------
EMBED_MODEL_NAME = "BAAI/bge-base-en-v1.5"
COLLECTION_NAME = "documents"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def md5_file(path: Path) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def load_registry() -> dict:
    if REGISTRY_PATH.exists():
        with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_registry(registry: dict) -> None:
    with open(REGISTRY_PATH, "w", encoding="utf-8") as f:
        json.dump(registry, f, indent=2, ensure_ascii=False)


def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Split text into overlapping chunks."""
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(text):
            break
        start = end - overlap
    return chunks


def _toc_sections(doc, toc: list) -> list[tuple[str, str, int]]:
    """
    Use PDF TOC/bookmarks to split into sections.
    Returns list of (section_path, text, start_page_1indexed).
    Only uses top 3 TOC levels to avoid over-fragmentation.
    """
    n_pages = len(doc)
    filtered = [(lvl, title, max(pg, 1)) for lvl, title, pg in toc if lvl <= 3]
    if not filtered:
        return []

    results = []
    for i, (level, title, start_pg) in enumerate(filtered):
        # End page = start of next entry, or end of document
        end_pg = filtered[i + 1][2] if i + 1 < len(filtered) else n_pages + 1

        # Build section path by tracking heading hierarchy
        heading_stack: dict[int, str] = {}
        for lvl, t, pg in filtered[: i + 1]:
            # Clear deeper levels when a shallower heading appears
            for l in [k for k in heading_stack if k > lvl]:
                del heading_stack[l]
            heading_stack[lvl] = t
        section_path = " > ".join(heading_stack[l] for l in sorted(heading_stack))

        # Extract text from [start_pg, end_pg)
        text_parts = []
        for pg_num in range(start_pg - 1, min(end_pg - 1, n_pages)):
            text = doc[pg_num].get_text("text")
            if text.strip():
                text_parts.append(text)

        text = "\n".join(text_parts).strip()
        if text:
            results.append((section_path, text, start_pg))

    return results


def _fontsize_sections(doc) -> list[tuple[str, str, int]]:
    """
    Detect headings by font size when no TOC is available.
    Returns list of (heading_text, body_text, start_page_1indexed).
    """
    from collections import Counter

    # Determine body font size (most common)
    all_sizes: list[int] = []
    for page in doc:
        for block in page.get_text("dict")["blocks"]:
            if block.get("type") != 0:
                continue
            for line in block["lines"]:
                for span in line["spans"]:
                    all_sizes.append(round(span["size"]))

    if not all_sizes:
        return []

    body_size = Counter(all_sizes).most_common(1)[0][0]
    heading_threshold = body_size * 1.2

    sections: list[tuple[str, str, int]] = []
    current_header = ""
    current_body: list[str] = []
    current_start = 1

    for page_num, page in enumerate(doc):
        for block in page.get_text("dict")["blocks"]:
            if block.get("type") != 0:
                continue

            block_text = ""
            is_heading = False
            for line in block["lines"]:
                for span in line["spans"]:
                    if span["size"] >= heading_threshold and len(span["text"].strip()) < 150:
                        is_heading = True
                    block_text += span["text"]

            block_text = block_text.strip()
            if not block_text:
                continue

            if is_heading:
                if current_body:
                    sections.append((current_header, "\n".join(current_body).strip(), current_start))
                current_header = block_text[:200]
                current_body = []
                current_start = page_num + 1
            else:
                current_body.append(block_text)

    if current_body:
        sections.append((current_header, "\n".join(current_body).strip(), current_start))

    return [(h, t, p) for h, t, p in sections if t.strip()]


def extract_sections_pdf(pdf_path: Path) -> list[tuple[str, str, int]]:
    """
    Extract structured sections from a PDF.
    Returns list of (section_path, text, start_page_1indexed).

    Strategy (in order):
      1. TOC/bookmarks  — best for official datasheets with outline
      2. Font-size detection — fallback for PDFs without TOC
      3. Page-by-page  — last resort
    """
    doc = fitz.open(str(pdf_path))
    try:
        toc = doc.get_toc()
        if toc:
            sections = _toc_sections(doc, toc)
            if sections:
                return sections

        sections = _fontsize_sections(doc)
        if sections:
            return sections

        # Page-by-page fallback
        fallback = []
        for page_num in range(len(doc)):
            text = doc[page_num].get_text("text").strip()
            if text:
                fallback.append((f"Page {page_num + 1}", text, page_num + 1))
        return fallback
    finally:
        doc.close()


def extract_sections_xlsx(xlsx_path: Path) -> list[tuple[str, str, int]]:
    """
    Extract one section per worksheet from an .xlsx workbook.
    Returns list of (sheet_name, text, sheet_number_1indexed).

    Each non-empty row is serialized as 'cell | cell | cell' so that
    tabular relationships survive into the embedded text.

    Notes / limitations:
      - Only visible worksheets are indexed; hidden/very-hidden helper
        sheets are skipped so their scratch data does not pollute search.
      - data_only=True reads Excel's cached cell values. For workbooks
        generated programmatically (pandas/xlsxwriter) and never opened
        in Excel, formula cells have no cached value and read as None,
        i.e. formula-only rows are dropped. A warning is printed when a
        visible sheet yields no text so this case is at least visible.
    """
    import openpyxl

    wb = openpyxl.load_workbook(str(xlsx_path), read_only=True, data_only=True)
    sections: list[tuple[str, str, int]] = []
    try:
        sheet_idx = 0
        for ws in wb.worksheets:
            if ws.sheet_state != "visible":
                continue
            sheet_idx += 1
            rows_text: list[str] = []
            for row in ws.iter_rows(values_only=True):
                cells = [str(c).strip() for c in row if c is not None and str(c).strip()]
                if cells:
                    rows_text.append(" | ".join(cells))
            text = "\n".join(rows_text).strip()
            if text:
                sections.append((ws.title, text, sheet_idx))
            else:
                print(
                    f"  [!] {xlsx_path.name}: visible sheet '{ws.title}' yielded no "
                    f"text (empty, or formula-only with no cached values)."
                )
    finally:
        wb.close()
    return sections


def relative_source(pdf_path: Path) -> str:
    """Return POSIX relative path from docs/, e.g. 'dir1/A.pdf'."""
    return pdf_path.relative_to(DOCS_DIR).as_posix()


def relative_note_source(md_path: Path) -> str:
    """Return POSIX relative path prefixed with 'notes/', e.g. 'notes/claude-code/foo.md'."""
    return "notes/" + md_path.relative_to(NOTES_DIR).as_posix()


def extract_sections(md_path: Path) -> list[tuple[str, str]]:
    """Parse a Markdown file into (section_header, text) tuples split by ## headings."""
    content = md_path.read_text(encoding="utf-8")
    sections: list[tuple[str, str]] = []
    current_header = ""
    current_lines: list[str] = []

    for line in content.splitlines():
        if line.startswith("## "):
            if current_lines:
                sections.append((current_header, "\n".join(current_lines).strip()))
            current_header = line[3:].strip()
            current_lines = []
        else:
            current_lines.append(line)

    if current_lines:
        sections.append((current_header, "\n".join(current_lines).strip()))

    return [(h, t) for h, t in sections if t.strip()]


def chunk_ids_for_source(source: str, collection) -> list[str]:
    """Retrieve all chunk IDs stored for a given source."""
    results = collection.get(where={"source": source}, include=[])
    return results["ids"]


# ---------------------------------------------------------------------------
# Core operations
# ---------------------------------------------------------------------------

def index_note(md_path: Path, collection, model: SentenceTransformer) -> int:
    """Chunk and embed a Markdown note, storing results in ChromaDB. Returns chunk count."""
    source = relative_note_source(md_path)
    filename = md_path.name
    category = md_path.parent.name if md_path.parent != NOTES_DIR else ""

    sections = extract_sections(md_path)
    all_ids, all_embeddings, all_documents, all_metadatas = [], [], [], []

    for section_idx, (header, text) in enumerate(sections):
        chunks = chunk_text(text)
        for chunk_idx, chunk in enumerate(chunks):
            chunk_id = f"{source}::s{section_idx}::c{chunk_idx}"
            # Prepend header so each chunk carries its section context
            enriched = f"{header}\n\n{chunk}" if header else chunk
            embedding = model.encode(enriched, normalize_embeddings=True).tolist()
            all_ids.append(chunk_id)
            all_embeddings.append(embedding)
            all_documents.append(enriched)
            all_metadatas.append(
                {
                    "source": source,
                    "filename": filename,
                    "category": category,
                    "section": header,
                    "doc_type": "note",
                }
            )

    if all_ids:
        batch = 512
        for i in range(0, len(all_ids), batch):
            collection.upsert(
                ids=all_ids[i : i + batch],
                embeddings=all_embeddings[i : i + batch],
                documents=all_documents[i : i + batch],
                metadatas=all_metadatas[i : i + batch],
            )

    return len(all_ids)


def index_document(pdf_path: Path, collection, model: SentenceTransformer) -> int:
    """Chunk and embed a PDF using structure-based chunking. Returns chunk count."""
    source = relative_source(pdf_path)
    filename = pdf_path.name
    category = pdf_path.parent.name if pdf_path.parent != DOCS_DIR else ""

    sections = extract_sections_pdf(pdf_path)
    all_ids, all_embeddings, all_documents, all_metadatas = [], [], [], []

    for section_idx, (section_path, text, start_page) in enumerate(sections):
        chunks = chunk_text(text)
        for chunk_idx, chunk in enumerate(chunks):
            chunk_id = f"{source}::s{section_idx}::c{chunk_idx}"
            # Prepend section path so each chunk carries its structural context
            enriched = f"{section_path}\n\n{chunk}" if section_path else chunk
            embedding = model.encode(enriched, normalize_embeddings=True).tolist()
            all_ids.append(chunk_id)
            all_embeddings.append(embedding)
            all_documents.append(enriched)
            all_metadatas.append(
                {
                    "source": source,
                    "filename": filename,
                    "category": category,
                    "section": section_path,
                    "page": start_page,
                    "doc_type": "pdf",
                }
            )

    if all_ids:
        # Upsert in batches of 512 to avoid request-size limits
        batch = 512
        for i in range(0, len(all_ids), batch):
            collection.upsert(
                ids=all_ids[i : i + batch],
                embeddings=all_embeddings[i : i + batch],
                documents=all_documents[i : i + batch],
                metadatas=all_metadatas[i : i + batch],
            )

    return len(all_ids)


def index_spreadsheet(xlsx_path: Path, collection, model: SentenceTransformer) -> int:
    """Chunk and embed an .xlsx workbook, one section per sheet. Returns chunk count."""
    source = relative_source(xlsx_path)
    filename = xlsx_path.name
    category = xlsx_path.parent.name if xlsx_path.parent != DOCS_DIR else ""

    sections = extract_sections_xlsx(xlsx_path)
    all_ids, all_embeddings, all_documents, all_metadatas = [], [], [], []

    for section_idx, (sheet_name, text, sheet_number) in enumerate(sections):
        chunks = chunk_text(text)
        for chunk_idx, chunk in enumerate(chunks):
            chunk_id = f"{source}::s{section_idx}::c{chunk_idx}"
            # Prepend sheet name so each chunk carries its worksheet context
            enriched = f"{sheet_name}\n\n{chunk}" if sheet_name else chunk
            embedding = model.encode(enriched, normalize_embeddings=True).tolist()
            all_ids.append(chunk_id)
            all_embeddings.append(embedding)
            all_documents.append(enriched)
            all_metadatas.append(
                {
                    "source": source,
                    "filename": filename,
                    "category": category,
                    "section": sheet_name,
                    "page": sheet_number,
                    "doc_type": "xlsx",
                }
            )

    if all_ids:
        batch = 512
        for i in range(0, len(all_ids), batch):
            collection.upsert(
                ids=all_ids[i : i + batch],
                embeddings=all_embeddings[i : i + batch],
                documents=all_documents[i : i + batch],
                metadatas=all_metadatas[i : i + batch],
            )

    return len(all_ids)


def remove_document(source: str, collection) -> int:
    """Delete all chunks for a given source from ChromaDB. Returns count removed."""
    ids = chunk_ids_for_source(source, collection)
    if ids:
        collection.delete(ids=ids)
    return len(ids)


# ---------------------------------------------------------------------------
# Main sync logic
# ---------------------------------------------------------------------------

def pick_indexer(source: str, file_path: Path):
    """Select the indexing function based on source location and file type."""
    if source.startswith("notes/"):
        return index_note
    if file_path.suffix.lower() == ".xlsx":
        return index_spreadsheet
    return index_document


def sync(force: bool = False) -> None:
    print(f"[sync] Scanning {DOCS_DIR} (PDFs, XLSX) and {NOTES_DIR} (Markdown notes) ...")

    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    NOTES_DIR.mkdir(parents=True, exist_ok=True)
    CHROMA_DIR.mkdir(parents=True, exist_ok=True)

    # Load model
    print(f"[sync] Loading embedding model '{EMBED_MODEL_NAME}' ...")
    model = SentenceTransformer(EMBED_MODEL_NAME)

    # Connect to ChromaDB
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    collection = client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )

    registry = load_registry()
    disk_files: dict[str, Path] = {}

    # Collect PDFs and spreadsheets from docs/ (skip Excel temp lock files "~$...")
    for doc_path in sorted(DOCS_DIR.rglob("*")):
        if doc_path.name.startswith("~$"):
            continue
        if doc_path.suffix.lower() in (".pdf", ".xlsx"):
            disk_files[relative_source(doc_path)] = doc_path

    # Collect Markdown notes
    for md_path in sorted(NOTES_DIR.rglob("*.md")):
        src = relative_note_source(md_path)
        disk_files[src] = md_path

    added = removed = updated = skipped = 0

    # --- Add / update ---
    for source, file_path in disk_files.items():
        current_hash = md5_file(file_path)
        entry = registry.get(source)
        indexer = pick_indexer(source, file_path)

        if entry is None:
            print(f"  [+] Indexing new: {source}")
            chunk_count = indexer(file_path, collection, model)
            registry[source] = {
                "hash": current_hash,
                "chunk_count": chunk_count,
                "indexed_at": datetime.utcnow().isoformat(),
            }
            added += 1

        elif force or entry.get("hash") != current_hash:
            print(f"  [~] Re-indexing modified: {source}")
            remove_document(source, collection)
            chunk_count = indexer(file_path, collection, model)
            registry[source] = {
                "hash": current_hash,
                "chunk_count": chunk_count,
                "indexed_at": datetime.utcnow().isoformat(),
            }
            updated += 1

        else:
            skipped += 1

    # --- Remove stale entries ---
    for source in list(registry.keys()):
        if source not in disk_files:
            print(f"  [-] Removing deleted: {source}")
            remove_document(source, collection)
            del registry[source]
            removed += 1

    save_registry(registry)

    pdf_count = sum(1 for s in registry if s.lower().endswith(".pdf"))
    xlsx_count = sum(1 for s in registry if s.lower().endswith(".xlsx"))
    note_count = sum(1 for s in registry if s.startswith("notes/"))
    print(
        f"\n[sync] Done. "
        f"Added={added}, Updated={updated}, Removed={removed}, Skipped={skipped}"
    )
    print(f"[sync] Indexed: {pdf_count} PDFs, {xlsx_count} spreadsheets, {note_count} Markdown notes")


if __name__ == "__main__":
    force = "--force" in sys.argv
    sync(force=force)
