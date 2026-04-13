# RAG System — Quick Start

> This guide assumes you have already completed the installation. If not, please refer to [SETUP.md](SETUP.md) first.

---

## 1. Add PDF documents

Place your PDFs in the `docs/` folder. Subdirectories are supported for categorization:

```
docs/
├── stm32/
│   └── rm0433.pdf
├── sensors/
│   └── bmp390.pdf
└── some_manual.pdf
```

The subdirectory name becomes the **category** for that document, which can be used to filter search results.

---

## 2. Build the index

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

Example output:
```
[sync] Scanning docs/ ...
[sync] Loading embedding model 'BAAI/bge-base-en-v1.5' ...
  [+] Indexing new: stm32/rm0433.pdf
  [+] Indexing new: sensors/bmp390.pdf
[sync] Done. Added=2, Updated=0, Removed=0, Skipped=0
```

Re-run the same command after adding or modifying PDFs. Unchanged files are skipped automatically.

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

## 3. Run the file watcher (optional)

Automatically detects changes in `docs/` and re-indexes without manual sync:

```bash
python watch_docs.py
```

**Background (Windows — PowerShell):**

```powershell
Start-Process python -ArgumentList "watch_docs.py" `
  -WorkingDirectory (Get-Location) -WindowStyle Hidden
```

**Background (macOS / Linux):**

```bash
nohup python watch_docs.py > watch.log 2>&1 &
```

---

## 4. Search in Copilot Chat

### Search all documents

```
/rag how does the SPI interface work
```

### Filter by category (subdirectory name)

```
/rag category:stm32 what is the maximum clock speed
```

### Filter by specific file

```
/rag source:stm32/rm0433.pdf describe pin PA0
```

### Filter by both category and source

```
/rag category:sensors source:sensors/bmp390.pdf ODR register settings
```

### List indexed documents

```
what documents are available
```

---

## Response format

Each answer includes source citations:

```
SPI clock speed can reach up to 50 MHz in master mode [stm32/rm0433.pdf, Page 23].

| Register | Bit | Description     |
|----------|-----|-----------------|
| SPI_CR1  | BR  | Baud rate ctrl  |
```

If the information is not found in the indexed documents, Copilot will explicitly reply:

> "This information was not found in the indexed documents."

---

## Quick reference

| Action | Command |
|--------|---------|
| Initial / incremental index | `python sync_docs.py` |
| Force re-index all documents | `python sync_docs.py --force` |
| Start file watcher | `python watch_docs.py` |
| Test MCP server manually | `python datasheet_mcp.py` |
