#!/usr/bin/env bash
set -euo pipefail

echo "============================================"
echo "  RAG System Installer"
echo "============================================"
echo

# ---------------------------------------------------------------------------
# 1. Locate this script's directory (works regardless of where user runs it)
# ---------------------------------------------------------------------------
RAG_DIR="$(dirname "$(realpath "$0")")"
echo "[1/6] RAG system directory: $RAG_DIR"
echo

# ---------------------------------------------------------------------------
# 2. Find a usable Python 3
# ---------------------------------------------------------------------------
echo "[2/6] Checking Python..."

PYTHON=""

if command -v python3 &>/dev/null; then
    PYTHON="$(command -v python3)"
elif command -v python &>/dev/null; then
    # Verify it's Python 3
    if python -c "import sys; assert sys.version_info.major == 3" &>/dev/null; then
        PYTHON="$(command -v python)"
    fi
fi

if [ -z "$PYTHON" ]; then
    echo
    echo "[ERROR] No suitable Python 3 found."
    echo "Please install Python 3.10+ via your package manager:"
    echo "  Ubuntu/Debian: sudo apt install python3 python3-venv"
    echo "  Fedora:        sudo dnf install python3"
    echo "  macOS:         brew install python"
    echo
    exit 1
fi

echo "Found Python: $PYTHON"
"$PYTHON" --version
echo

# ---------------------------------------------------------------------------
# 3. Create virtual environment
# ---------------------------------------------------------------------------
echo "[3/6] Setting up virtual environment..."

VENV_DIR="$RAG_DIR/.venv"

if [ -f "$VENV_DIR/bin/python" ]; then
    echo "Virtual environment already exists, skipping creation."
else
    echo "Creating .venv ..."
    "$PYTHON" -m venv "$VENV_DIR"
    echo "Done."
fi

VENV_PYTHON="$VENV_DIR/bin/python"
VENV_PIP="$VENV_DIR/bin/pip"
echo

# ---------------------------------------------------------------------------
# 4. Install dependencies
# ---------------------------------------------------------------------------
echo "[4/6] Installing dependencies (this may take a few minutes)..."
echo "      The embedding model (~440 MB) will download on first use."
echo

"$VENV_PIP" install --upgrade pip --quiet
"$VENV_PIP" install -r "$RAG_DIR/requirements.txt"

echo
echo "Dependencies installed."
echo

# ---------------------------------------------------------------------------
# 5. Update VS Code user settings
# ---------------------------------------------------------------------------
echo "[5/6] Configuring VS Code MCP settings..."

# Detect VS Code settings path (Linux vs macOS)
if [ -d "$HOME/.config/Code/User" ]; then
    SETTINGS_FILE="$HOME/.config/Code/User/settings.json"
elif [ -d "$HOME/Library/Application Support/Code/User" ]; then
    SETTINGS_FILE="$HOME/Library/Application Support/Code/User/settings.json"
else
    SETTINGS_FILE="$HOME/.config/Code/User/settings.json"
fi

"$VENV_PYTHON" - <<EOF
import json, pathlib

p = pathlib.Path("""$SETTINGS_FILE""")
s = json.loads(p.read_text(encoding='utf-8')) if p.exists() else {}

s['chat.mcp.enabled'] = True
s.setdefault('mcp', {}).setdefault('servers', {})['datasheet-rag'] = {
    'type': 'stdio',
    'command': """$VENV_PYTHON""",
    'args': ["""$RAG_DIR/datasheet_mcp.py"""]
}

instr_file = """$RAG_DIR/.github/copilot-instructions.md"""
s['github.copilot.chat.codeGeneration.instructions'] = [{'file': instr_file}]

p.parent.mkdir(parents=True, exist_ok=True)
p.write_text(json.dumps(s, indent=4, ensure_ascii=False), encoding='utf-8')
print('VS Code settings updated.')
EOF

if [ $? -ne 0 ]; then
    echo
    echo "[WARNING] Could not update VS Code settings automatically."
    echo "Please add the following to your VS Code User Settings manually:"
    echo
    echo '  "chat.mcp.enabled": true,'
    echo '  "mcp": {'
    echo '    "servers": {'
    echo '      "datasheet-rag": {'
    echo '        "type": "stdio",'
    echo "        \"command\": \"$VENV_PYTHON\","
    echo "        \"args\": [\"$RAG_DIR/datasheet_mcp.py\"]"
    echo '      }'
    echo '    }'
    echo '  },'
    echo '  "github.copilot.chat.codeGeneration.instructions": ['
    echo "    { \"file\": \"$RAG_DIR/.github/copilot-instructions.md\" }"
    echo '  ]'
    echo
fi

# ---------------------------------------------------------------------------
# 6. Save RAG root path to Claude Code config
# ---------------------------------------------------------------------------
echo "[6/6] Saving RAG root path to Claude Code config..."

"$VENV_PYTHON" - <<EOF
import json, pathlib

cfg = pathlib.Path.home() / '.claude' / 'rag_config.json'
cfg.parent.mkdir(parents=True, exist_ok=True)
data = json.loads(cfg.read_text(encoding='utf-8')) if cfg.exists() else {}
data['rag_root'] = """$RAG_DIR"""
cfg.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')
print(f'Saved rag_root = $RAG_DIR')
EOF

if [ $? -ne 0 ]; then
    echo "[WARNING] Could not write rag_config.json. Claude /rag skill may prompt for path on first use."
else
    echo "Claude Code rag_config.json updated."
fi

# ---------------------------------------------------------------------------
# Done
# ---------------------------------------------------------------------------
echo
echo "============================================"
echo "  Installation Complete!"
echo "============================================"
echo
echo "Next steps:"
echo
echo "  1. Place your PDF files in:"
echo "     $RAG_DIR/docs/"
echo "     (Subdirectories are supported, e.g. docs/stm32/, docs/sensors/)"
echo
echo "  2. Run initial indexing:"
echo "     $RAG_DIR/index.sh"
echo
echo "  3. Restart VS Code"
echo
echo "  4. In Copilot Chat, type:"
echo "     /rag how does the SPI interface work"
echo
