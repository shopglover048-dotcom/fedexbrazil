@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo Virtual environment not found at .venv\Scripts\python.exe
  exit /b 1
)
.venv\Scripts\python.exe app.py
