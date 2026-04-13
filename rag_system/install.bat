@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul

echo ============================================
echo   RAG System Installer
echo ============================================
echo.

:: ---------------------------------------------------------------------------
:: 1. Locate this script's directory (works regardless of where user runs it)
:: ---------------------------------------------------------------------------
set "RAG_DIR=%~dp0"
:: Remove trailing backslash
if "%RAG_DIR:~-1%"=="\" set "RAG_DIR=%RAG_DIR:~0,-1%"

echo [1/5] RAG system directory: %RAG_DIR%
echo.

:: ---------------------------------------------------------------------------
:: 2. Find a usable Python (skip MSYS2)
:: ---------------------------------------------------------------------------
echo [2/5] Checking Python...

set "PYTHON="

:: Try py launcher first
py -3 --version >nul 2>&1
if %errorlevel%==0 (
    for /f "tokens=*" %%i in ('py -3 -c "import sys; print(sys.executable)"') do set "PYTHON=%%i"
)

:: If py launcher not found, try python but skip MSYS2
if not defined PYTHON (
    for /f "tokens=*" %%i in ('where python 2^>nul') do (
        if not defined PYTHON (
            echo %%i | findstr /i "msys64\ucrt64" >nul
            if errorlevel 1 (
                set "PYTHON=%%i"
            )
        )
    )
)

if not defined PYTHON (
    echo.
    echo [ERROR] No suitable Python found.
    echo Please install Python 3.10+ from https://www.python.org/downloads/
    echo Make sure to check "Add Python to PATH" during installation.
    echo.
    pause
    exit /b 1
)

echo Found Python: %PYTHON%
"%PYTHON%" --version
echo.

:: ---------------------------------------------------------------------------
:: 3. Create virtual environment
:: ---------------------------------------------------------------------------
echo [3/5] Setting up virtual environment...

set "VENV_DIR=%RAG_DIR%\.venv"

if exist "%VENV_DIR%\Scripts\python.exe" (
    echo Virtual environment already exists, skipping creation.
) else (
    echo Creating .venv ...
    "%PYTHON%" -m venv "%VENV_DIR%"
    if errorlevel 1 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
    echo Done.
)

set "VENV_PYTHON=%VENV_DIR%\Scripts\python.exe"
set "VENV_PIP=%VENV_DIR%\Scripts\pip.exe"
echo.

:: ---------------------------------------------------------------------------
:: 4. Install dependencies
:: ---------------------------------------------------------------------------
echo [4/5] Installing dependencies (this may take a few minutes)...
echo       The embedding model (~440 MB) will download on first use.
echo.

"%VENV_PIP%" install --upgrade pip --quiet
"%VENV_PIP%" install -r "%RAG_DIR%\requirements.txt"

if errorlevel 1 (
    echo [ERROR] Failed to install dependencies.
    pause
    exit /b 1
)
echo.
echo Dependencies installed.
echo.

:: ---------------------------------------------------------------------------
:: 5. Update VS Code user settings
:: ---------------------------------------------------------------------------
echo [5/5] Configuring VS Code MCP settings...

set "SETTINGS_DIR=%APPDATA%\Code\User"
set "SETTINGS_FILE=%SETTINGS_DIR%\settings.json"

:: Write temp Python script line-by-line (avoids cmd ^ continuation fragility)
set "TMP_PY=%TEMP%\rag_vscode_setup.py"
echo import json, pathlib > "%TMP_PY%"
echo p = pathlib.Path^(r'%SETTINGS_FILE%'^) >> "%TMP_PY%"
echo s = json.loads^(p.read_text^(encoding='utf-8'^)^) if p.exists^(^) else {} >> "%TMP_PY%"
echo s['chat.mcp.enabled'] = True >> "%TMP_PY%"
echo srv = {'type': 'stdio', 'command': r'%VENV_PYTHON%', 'args': [r'%RAG_DIR%\datasheet_mcp.py']} >> "%TMP_PY%"
echo s.setdefault^('mcp', {}^).setdefault^('servers', {}^)['datasheet-rag'] = srv >> "%TMP_PY%"
echo instr_file = r'%RAG_DIR%\.github\copilot-instructions.md' >> "%TMP_PY%"
echo s['github.copilot.chat.codeGeneration.instructions'] = [{'file': instr_file}] >> "%TMP_PY%"
echo p.parent.mkdir^(parents=True, exist_ok=True^) >> "%TMP_PY%"
echo p.write_text^(json.dumps^(s, indent=4, ensure_ascii=False^), encoding='utf-8'^) >> "%TMP_PY%"
echo print^('VS Code settings updated.'^) >> "%TMP_PY%"
"%VENV_PYTHON%" "%TMP_PY%"

if errorlevel 1 (
    echo.
    echo [WARNING] Could not update VS Code settings automatically.
    echo Please add the following to your VS Code User Settings manually:
    echo.
    echo   "chat.mcp.enabled": true,
    echo   "mcp": {
    echo     "servers": {
    echo       "datasheet-rag": {
    echo         "type": "stdio",
    echo         "command": "%VENV_PYTHON%",
    echo         "args": ["%RAG_DIR%\datasheet_mcp.py"]
    echo       }
    echo     }
    echo   },
    echo   "github.copilot.chat.codeGeneration.instructions": [
    echo     { "file": "%RAG_DIR%\.github\copilot-instructions.md" }
    echo   ]
    echo.
)
del "%TMP_PY%" >nul 2>&1

:: ---------------------------------------------------------------------------
:: 6. Save RAG root path to Claude Code config
:: ---------------------------------------------------------------------------
echo [6/6] Saving RAG root path to Claude Code config...

set "TMP_PY=%TEMP%\rag_claude_config.py"
echo import json, pathlib > "%TMP_PY%"
echo cfg = pathlib.Path.home^(^) / '.claude' / 'rag_config.json' >> "%TMP_PY%"
echo cfg.parent.mkdir^(parents=True, exist_ok=True^) >> "%TMP_PY%"
echo data = json.loads^(cfg.read_text^(encoding='utf-8'^)^) if cfg.exists^(^) else {} >> "%TMP_PY%"
echo data['rag_root'] = r'%RAG_DIR%' >> "%TMP_PY%"
echo cfg.write_text^(json.dumps^(data, indent=2, ensure_ascii=False^), encoding='utf-8'^) >> "%TMP_PY%"
echo print^('Saved rag_root =', r'%RAG_DIR%'^) >> "%TMP_PY%"
"%VENV_PYTHON%" "%TMP_PY%"
del "%TMP_PY%" >nul 2>&1

if errorlevel 1 (
    echo [WARNING] Could not write rag_config.json. Claude /rag skill may prompt for path on first use.
) else (
    echo Claude Code rag_config.json updated.
)

:: ---------------------------------------------------------------------------
:: Done
:: ---------------------------------------------------------------------------
echo.
echo ============================================
echo   Installation Complete!
echo ============================================
echo.
echo Next steps:
echo.
echo   1. Place your PDF files in:
echo      %RAG_DIR%\docs\
echo      (Subdirectories are supported, e.g. docs\stm32\, docs\sensors\)
echo.
echo   2. Run initial indexing:
echo      %RAG_DIR%\index.bat
echo.
echo   3. Restart VS Code
echo.
echo   4. In Copilot Chat, type:
echo      /rag how does the SPI interface work
echo.
pause
