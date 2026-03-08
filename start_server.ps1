$ErrorActionPreference = 'Stop'
Set-Location -Path $PSScriptRoot
if (-not (Test-Path '.venv\Scripts\python.exe')) { throw 'Virtual environment not found at .venv\Scripts\python.exe' }
& '.venv\Scripts\python.exe' 'app.py'
