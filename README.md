# Local RAG System for Technical Documents

A fully local, offline Retrieval-Augmented Generation (RAG) system for technical
datasheets, spreadsheets, and engineering notes. Index your **PDFs**, **Excel
workbooks**, and **Markdown notes**, then query them with source-cited answers
directly inside **VS Code Copilot Chat** or **Claude Code** — no cloud, no data
leaves your machine.

## Features

- **Multi-format ingestion** — PDF datasheets, XLSX spreadsheets, and Markdown
  tech notes, all searchable from one index.
- **100% local** — embeddings (`BAAI/bge-base-en-v1.5`) and the ChromaDB vector
  store run on your machine; documents never leave it.
- **MCP integration** — exposes a `datasheet-rag` MCP server consumed by VS Code
  Copilot Chat and Claude Code (`/rag`).
- **Incremental sync** — MD5 hashing skips unchanged files; an optional file
  watcher re-indexes on the fly.
- **Filtered search** — narrow results by category (subfolder), source file, or
  document type (`pdf` / `xlsx` / `note`).
- **Source citations** — every answer cites the file and page/sheet/section it
  came from.

## Repository layout

```
FileSystem/
├── README.md                ← you are here
├── rag_system/              ← the RAG engine
│   ├── docs/                ← put your PDF / XLSX files here (subfolders = categories)
│   │   └── example1/
│   ├── tech_notes/  →  ../tech_notes   (indexed from the repo root, see below)
│   ├── sync_docs.py         ← build / update the index
│   ├── watch_docs.py        ← optional auto-indexing file watcher
│   ├── datasheet_mcp.py     ← MCP server (search_documents, list_documents)
│   ├── install.bat / .sh    ← one-click setup
│   ├── index.bat / .sh      ← convenience wrappers around sync_docs.py
│   ├── requirements.txt
│   ├── chroma_db/           ← auto-generated vector store (git-ignored)
│   └── doc_registry.json    ← auto-generated index cache (git-ignored)
└── tech_notes/              ← your Markdown notes (git-ignored; indexed by RAG)
    └── example1/
```

> Your actual documents and notes are **git-ignored** — only the empty
> `example1/` placeholder structure is tracked. Nothing confidential is committed.

## Prerequisites

- Python 3.10+
- *(Optional)* Tesseract OCR — only for scanned/image-based PDFs. PyMuPDF reads
  text from most PDFs without it; install Tesseract only if `sync_docs.py`
  reports empty text for a document (`winget install UB-Mannheim.TesseractOCR`
  on Windows, `brew install tesseract` on macOS, `apt install tesseract-ocr` on
  Linux).

## Quick start

All commands run from the `rag_system/` directory.

### 1. Install

**Windows:**
```bat
cd rag_system
install.bat
```

**Linux / macOS:**
```bash
cd rag_system
chmod +x install.sh
./install.sh
```

The installer creates a `.venv`, installs dependencies, wires up the VS Code MCP
config, and registers the RAG root for Claude Code's `/rag`. The embedding model
(`BAAI/bge-base-en-v1.5`, ~440 MB) downloads automatically on first run.

<details>
<summary>Manual install</summary>

```bash
cd rag_system
python -m venv .venv
# Windows:        .venv\Scripts\activate
# macOS / Linux:  source .venv/bin/activate
pip install -r requirements.txt
```
</details>

### 2. Add your documents

- Drop **PDFs** and **XLSX** files into `rag_system/docs/`.
- Write **Markdown notes** into `tech_notes/` (at the repo root).

Subdirectory names become the **category** used for filtered search:

```
docs/
├── stm32/rm0433.pdf          → category "stm32"
└── sensors/bmp390.pdf        → category "sensors"
```

### 3. Build the index

```bash
# Windows:        index.bat        (index.bat --force to rebuild all)
# Linux / macOS:  ./index.sh       (./index.sh --force)
# Manual:         python sync_docs.py [--force]
```

Re-run after adding or editing files — unchanged files are skipped via hash
comparison. Or run the watcher to auto-index changes:

```bash
python watch_docs.py
```

### 4. Query

In **VS Code Copilot Chat** or **Claude Code**:

```
/rag how does the SPI interface work
/rag category:stm32 what is the maximum clock speed
/rag source:sensors/bmp390.pdf ODR register settings
```

Ask *"what documents are available"* to list everything indexed.

## Supported formats & filters

| Format   | `doc_type` | Indexed as                          | Location reported |
|----------|------------|-------------------------------------|-------------------|
| PDF      | `pdf`      | one section per detected heading    | `Page N`          |
| XLSX     | `xlsx`     | one section per **visible** sheet; rows serialized as `cell \| cell` | `Sheet: <name>` |
| Markdown | `note`     | one section per heading             | `Section: <name>` |

Filter searches by `category:`, `source:`, or document type. Example:

```
/rag doc_type:xlsx FRU device ID board info area
```

> **XLSX note:** hidden worksheets and Excel temp lock files (`~$...`) are
> skipped. Cell values are read via `data_only=True`, so formula-only cells with
> no cached value (e.g. workbooks generated programmatically and never opened in
> Excel) are not indexed.

## How it works

1. `sync_docs.py` scans `docs/` (PDF, XLSX) and `tech_notes/` (Markdown).
2. Each file is split into sections, then chunked and embedded with
   `BAAI/bge-base-en-v1.5`.
3. Chunks are upserted into a local ChromaDB collection (`documents`).
4. `datasheet_mcp.py` exposes `search_documents` and `list_documents` over MCP;
   Copilot / Claude Code call these to retrieve passages and cite sources.

## A note on tech_notes

`tech_notes/` holds your own engineering notes and is indexed alongside the
datasheets. Because the embedding model is **English-only**
(`bge-base-en-v1.5`), write notes in **English** for consistent retrieval
quality.

## VS Code MCP configuration

VS Code loads the MCP server from `rag_system/.vscode/mcp.json` (already
included). On macOS / Linux, replace `Scripts/python.exe` with `bin/python`:

```json
{
  "servers": {
    "datasheet-rag": {
      "type": "stdio",
      "command": "${workspaceFolder}/rag_system/.venv/Scripts/python.exe",
      "args": ["${workspaceFolder}/rag_system/datasheet_mcp.py"],
      "env": {}
    }
  }
}
```

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Empty search results | Run `python sync_docs.py` to (re)index |
| PDF indexed with 0 chunks | Image-based PDF; install Tesseract and use a PyMuPDF OCR pipeline |
| XLSX sheet yields no text | Sheet is empty or formula-only with no cached values (see XLSX note) |
| `chromadb` / `fastmcp` import error | `pip install -r requirements.txt` inside the activated `.venv` |
| MCP server not starting | Run `python datasheet_mcp.py` manually to see the error; check Python is on PATH |

## Quick reference

| Action | Command |
|--------|---------|
| Initial / incremental index | `python sync_docs.py` |
| Force re-index everything | `python sync_docs.py --force` |
| Start file watcher | `python watch_docs.py` |
| Test MCP server manually | `python datasheet_mcp.py` |
