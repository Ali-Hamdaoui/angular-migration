$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..\backend")
python -m uvicorn app.main:app --reload