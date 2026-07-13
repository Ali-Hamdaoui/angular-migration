$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..\frontend")
npm run test