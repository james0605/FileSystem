"""
datasheet_mcp.py - MCP server exposing RAG search tools via FastMCP.

Tools:
  search_documents(query, n_results, source, category)
  list_documents()
"""

import json
from pathlib import Path
from typing import Optional

import chromadb
from fastmcp import FastMCP
from sentence_transformers import SentenceTransformer

# ---------------------------------------------------------------------------
# Paths & constants
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).parent.resolve()
CHROMA_DIR = BASE_DIR / "chroma_db"
REGISTRY_PATH = BASE_DIR / "doc_registry.json"
EMBED_MODEL_NAME = "BAAI/bge-base-en-v1.5"
COLLECTION_NAME = "documents"

# ---------------------------------------------------------------------------
# Lazy-loaded singletons
# ---------------------------------------------------------------------------
_model: Optional[SentenceTransformer] = None
_collection = None


def _get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        _model = SentenceTransformer(EMBED_MODEL_NAME)
    return _model


def _get_collection():
    global _collection
    if _collection is None:
        CHROMA_DIR.mkdir(parents=True, exist_ok=True)
        client = chromadb.PersistentClient(path=str(CHROMA_DIR))
        _collection = client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
    return _collection


def _load_registry() -> dict:
    if REGISTRY_PATH.exists():
        with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


# ---------------------------------------------------------------------------
# MCP server
# ---------------------------------------------------------------------------
mcp = FastMCP(
    name="datasheet-rag",
    instructions=(
        "Local RAG server for technical datasheets (PDFs) and tech notes (Markdown). "
        "Use search_documents to retrieve relevant passages from both sources, "
        "filter by doc_type='pdf' or doc_type='note' to narrow results, "
        "and list_documents to see what is indexed."
    ),
)


@mcp.tool()
def search_documents(
    query: str,
    n_results: int = 5,
    source: Optional[str] = None,
    category: Optional[str] = None,
    doc_type: Optional[str] = None,
) -> str:
    """
    Search indexed technical documents and notes using semantic similarity.

    Args:
        query: Natural-language search string.
        n_results: Number of top results to return (default 5).
        source: Optional filter by relative file path, e.g. "dir1/A.pdf" or "notes/git/foo.md".
        category: Optional filter by category name, e.g. "TC4Dx" or "claude-code".
        doc_type: Optional filter by type: "pdf" for datasheets, "note" for tech notes.

    Returns:
        Formatted string with matching passages, source paths, and location info.
    """
    model = _get_model()
    collection = _get_collection()

    query_embedding = model.encode(query, normalize_embeddings=True).tolist()

    # Build ChromaDB where-filter
    filters = []
    if source:
        filters.append({"source": source})
    if category:
        filters.append({"category": category})
    if doc_type:
        filters.append({"doc_type": doc_type})

    where: Optional[dict] = None
    if len(filters) == 1:
        where = filters[0]
    elif len(filters) > 1:
        where = {"$and": filters}

    query_kwargs = dict(
        query_embeddings=[query_embedding],
        n_results=n_results,
        include=["documents", "metadatas", "distances"],
    )
    if where:
        query_kwargs["where"] = where

    results = collection.query(**query_kwargs)

    documents = results.get("documents", [[]])[0]
    metadatas = results.get("metadatas", [[]])[0]
    distances = results.get("distances", [[]])[0]

    if not documents:
        return "No results found in indexed documents."

    lines = [f"Search results for: \"{query}\"\n"]
    for rank, (doc, meta, dist) in enumerate(zip(documents, metadatas, distances), 1):
        src = meta.get("source", "unknown")
        dtype = meta.get("doc_type", "pdf")
        score = round(1 - dist, 4)  # cosine similarity
        if dtype == "note":
            section = meta.get("section", "")
            location = f"Section: {section}" if section else "Note"
        else:
            page = meta.get("page", "?")
            location = f"Page {page}"
        lines.append(f"--- Result {rank} | [{src}] | {location} | similarity={score} ---")
        lines.append(doc.strip())
        lines.append("")

    return "\n".join(lines)


@mcp.tool()
def list_documents() -> str:
    """
    List all indexed documents and notes grouped by type and category.

    Returns:
        Formatted string showing PDFs and tech notes separately,
        with chunk count and last indexed date for each entry.
    """
    registry = _load_registry()

    if not registry:
        return "No documents are currently indexed."

    pdfs = {s: i for s, i in registry.items() if not s.startswith("notes/")}
    notes = {s: i for s, i in registry.items() if s.startswith("notes/")}

    lines = [f"Indexed documents ({len(registry)} total: {len(pdfs)} PDFs, {len(notes)} notes)\n"]

    # PDFs grouped by subdirectory
    if pdfs:
        lines.append("=== PDFs ===")
        grouped: dict[str, list] = {}
        for source, info in sorted(pdfs.items()):
            parts = source.split("/")
            cat = parts[0] if len(parts) > 1 else "(root)"
            grouped.setdefault(cat, []).append((source, info))
        for cat in sorted(grouped):
            lines.append(f"[{cat}]")
            for source, info in grouped[cat]:
                chunk_count = info.get("chunk_count", "?")
                indexed_at = info.get("indexed_at", "?")[:19].replace("T", " ")
                lines.append(f"  {source}  ({chunk_count} chunks, indexed {indexed_at})")
        lines.append("")

    # Tech notes grouped by category
    if notes:
        lines.append("=== Tech Notes ===")
        grouped_notes: dict[str, list] = {}
        for source, info in sorted(notes.items()):
            # source format: notes/<category>/<file>.md
            parts = source.split("/")
            cat = parts[1] if len(parts) > 2 else "(root)"
            grouped_notes.setdefault(cat, []).append((source, info))
        for cat in sorted(grouped_notes):
            lines.append(f"[{cat}]")
            for source, info in grouped_notes[cat]:
                chunk_count = info.get("chunk_count", "?")
                indexed_at = info.get("indexed_at", "?")[:19].replace("T", " ")
                lines.append(f"  {source}  ({chunk_count} chunks, indexed {indexed_at})")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    mcp.run()
