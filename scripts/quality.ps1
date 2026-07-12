$ErrorActionPreference = "Stop"
$repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

function Invoke-Script($Path) {
  & $Path
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

function Invoke-Native([string]$WorkingDirectory, [string]$File, [string[]]$Arguments) {
  Push-Location $WorkingDirectory
  try {
    & $File @Arguments
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
  } finally {
    Pop-Location
  }
}

Invoke-Script (Join-Path $PSScriptRoot "generate-openapi-client.ps1")
Invoke-Script (Join-Path $PSScriptRoot "backend-static-check.ps1")
Invoke-Script (Join-Path $PSScriptRoot "test-backend.ps1")
Invoke-Native (Join-Path $repo "frontend") "npm" @("run", "typecheck")
Invoke-Native (Join-Path $repo "frontend") "npm" @("run", "test")
Invoke-Native (Join-Path $repo "frontend") "npm" @("run", "build")
Invoke-Script (Join-Path $PSScriptRoot "artifact-integrity-test.ps1")
Invoke-Script (Join-Path $PSScriptRoot "fixture-contract-test.ps1")
Invoke-Script (Join-Path $PSScriptRoot "architecture-check.ps1")
Write-Host "Sprint 0 quality gates passed."
