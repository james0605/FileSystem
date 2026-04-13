#!/usr/bin/env bash
set -euo pipefail

RAG_DIR="$(dirname "$(realpath "$0")")"
VENV_PYTHON="$RAG_DIR/.venv/bin/python"

if [ ! -f "$VENV_PYTHON" ]; then
    echo "[ERROR] Virtual environment not found."
    echo "Please run install.sh first."
    exit 1
fi

echo "Scanning docs/ and updating index..."
echo
"$VENV_PYTHON" "$RAG_DIR/sync_docs.py" "$@"
