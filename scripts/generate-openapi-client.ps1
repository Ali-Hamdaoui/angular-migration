$ErrorActionPreference = "Stop"
$repo = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location (Join-Path $repo "backend")
python -c "import json; from pathlib import Path; from app.main import app; out = Path('..') / 'shared' / 'openapi.json'; out.write_text(json.dumps(app.openapi(), indent=2, sort_keys=True) + '\n', encoding='utf-8')"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host "Generated shared/openapi.json. Keep frontend/src/types/generated/api.ts synchronized before frontend type checks."
