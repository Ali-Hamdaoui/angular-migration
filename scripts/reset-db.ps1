param([switch]$ConfirmReset)
$ErrorActionPreference = "Stop"
$backend = Resolve-Path (Join-Path $PSScriptRoot "..\backend")
$db = Join-Path $backend ".migration-factory\migration-factory.db"
if (-not $ConfirmReset) { throw "Refusing to reset the database without -ConfirmReset." }
if (Test-Path $db) { Remove-Item -LiteralPath $db -Force }
Set-Location $backend
alembic upgrade head