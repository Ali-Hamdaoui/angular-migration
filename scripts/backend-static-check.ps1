$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..\backend")
python -m compileall -q app tests
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
