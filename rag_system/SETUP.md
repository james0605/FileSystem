# RAG System — Setup Guide

## Prerequisites

- Python 3.10+
- (Optional) Tesseract OCR — only needed for scanned/image-based PDFs

### Install Tesseract (optional, for scanned PDFs)

**Windows:**
```
winget install UB-Mannheim.TesseractOCR
# or download from https://github.com/UB-Mannheim/tesseract/wiki
# Add to PATH: C:\Program Files\Tesseract-OCR
```

**macOS:**
```bash
brew install tesseract
```

**Linux (Debian/Ubuntu):**
```bash
sudo apt install tesseract-ocr
```

> Note: PyMuPDF can extract text from most PDFs without Tesseract.
> Tesseract is only needed if `sync_docs.py` reports empty text for a document.

---

## Installation

### One-click Installation (Recommended)

**Windows:**
```
install.bat
```

**Linux / macOS:**
```bash
chmod +x install.sh
./install.sh
```

The installer automatically performs the following steps:
1. Locate a suitable Python 3
2. Create a `.venv` virtual environment
3. Install all dependencies from `requirements.txt`
4. Update VS Code `settings.json` (MCP server path + Copilot instructions)
5. Save the RAG root path to `~/.claude/rag_config.json` (for Claude Code `/rag`)

---

### Manual Installation

**Windows (cmd / PowerShell):**
```bash
cd rag_system

# Create .venv
python -m venv .venv

# Activate (PowerShell)
.venv\Scripts\Activate.ps1

# Activate (cmd)
.venv\Scripts\activate.bat

# Install dependencies
pip install -r requirements.txt
```

**macOS / Linux:**
```bash
cd rag_system

# Create .venv
python3 -m venv .venv

# Activate
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

> You need to activate `.venv` each time you open a new terminal.
> When activated, `(.venv)` will appear at the start of your prompt.

The embedding model (`BAAI/bge-base-en-v1.5`, ~440 MB) downloads automatically
from Hugging Face on the first run of `sync_docs.py` or `datasheet_mcp.py`.

---

## Directory layout

```
rag_system/
├── docs/                  ← Place your PDF files here (subdirectories supported)
│   ├── stm32/
│   │   └── rm0433.pdf
│   └── sensors/
│       └── bmp390.pdf
├── chroma_db/             ← Auto-created; do not edit manually
├── doc_registry.json      ← Auto-created; tracks indexed files
├── sync_docs.py
├── watch_docs.py
├── datasheet_mcp.py
└── requirements.txt
```

---

## Initial indexing

After placing PDFs in `docs/` (or any subdirectory), run:

**Windows:**
```
index.bat
```

**Linux / macOS:**
```bash
./index.sh
```

**Manual:**
```bash
python sync_docs.py
```

To force re-index all documents (ignoring hash cache):

```bash
# Windows
index.bat --force

# Linux / macOS
./index.sh --force

# Manual
python sync_docs.py --force
```

---

## Running the file watcher (background process)

The watcher automatically indexes new/modified/deleted PDFs without manual sync.

**Foreground (development):**
```bash
python watch_docs.py
```

**Background (Windows — PowerShell):**
```powershell
Start-Process python -ArgumentList "watch_docs.py" -WorkingDirectory (Get-Location) -WindowStyle Hidden
```

**Background (macOS/Linux):**
```bash
nohup python watch_docs.py > watch.log 2>&1 &
```

---

## VS Code MCP configuration

VS Code manages MCP servers through a workspace-level `.vscode/mcp.json` file, **not** through `settings.json`. This file is already included in the project.

The installer (`install.bat` / `install.sh`) automatically updates `settings.json` with:
- Copilot code generation instructions pointing to this RAG system
- `chat.mcp.access: "all"` to enable MCP access in Copilot Chat

The `.vscode/mcp.json` configures the MCP server itself:

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

> On macOS / Linux, replace `Scripts/python.exe` with `bin/python`.

> The MCP server starts automatically when VS Code Copilot needs it.
> It stays running as long as the Copilot session is active.

---

## Usage in Copilot Chat

| Intent | Example |
|--------|---------|
| Search all docs | `/rag how does the SPI interface work` |
| Filter by category | `/rag category:stm32 what is the clock speed` |
| Filter by file | `/rag source:stm32/rm0433.pdf pin PA0 description` |
| List indexed docs | ask "what documents are available" |

---

## Troubleshooting

| Problem | Solution |
|---------|---------|
| Empty search results | Run `python sync_docs.py` to index PDFs |
| PDF shows 0 chunks | PDF may be image-based; install Tesseract and use a PyMuPDF OCR pipeline |
| `chromadb` import error | `pip install chromadb>=0.5.0` |
| `fastmcp` not found | `pip install fastmcp>=2.0.0` |
| MCP server not starting | Check Python is on PATH; run `python datasheet_mcp.py` manually to see errors |
