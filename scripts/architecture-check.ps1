$ErrorActionPreference = "Stop"
$repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $repo
$matches = rg "shell\s*=\s*True|subprocess\.(run|Popen)\([^\n]*shell\s*=\s*True|dangerouslySetInnerHTML|verify\s*=\s*False" backend/app backend/tests frontend/src --glob "!**/__pycache__/**" --glob "!**/.pytest_cache/**" --glob "!frontend/.next/**" --glob "!frontend/node_modules/**"
if ($LASTEXITCODE -eq 0) {
  Write-Error "Architecture check found forbidden shortcuts:`n$matches"
  exit 1
}
if ($LASTEXITCODE -gt 1) { exit $LASTEXITCODE }
Write-Host "Architecture check passed."
exit 0
