@echo off
setlocal
chcp 65001 >nul

set "RAG_DIR=%~dp0"
if "%RAG_DIR:~-1%"=="\" set "RAG_DIR=%RAG_DIR:~0,-1%"

set "VENV_PYTHON=%RAG_DIR%\.venv\Scripts\python.exe"

if not exist "%VENV_PYTHON%" (
    echo [ERROR] Virtual environment not found.
    echo Please run install.bat first.
    pause
    exit /b 1
)

echo Scanning docs\ and updating index...
echo.
"%VENV_PYTHON%" "%RAG_DIR%\sync_docs.py" %*
echo.
pause
