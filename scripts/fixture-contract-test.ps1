$ErrorActionPreference = "Stop"
$repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location (Join-Path $repo "backend")
$pytestArgs = @()
if ($env:AMF_PYTEST_BASETEMP) {
  $pytestArgs += @("--basetemp", $env:AMF_PYTEST_BASETEMP)
}
python -m pytest @pytestArgs tests/test_angular18_fixture.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
