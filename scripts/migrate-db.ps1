$ErrorActionPreference = "Stop"
$backend = (Resolve-Path (Join-Path $PSScriptRoot "..\backend")).Path
Set-Location $backend
python -m alembic -c alembic.ini upgrade heads
if ($LASTEXITCODE -ne 0) { throw "Alembic migration failed." }
python -c "from app.core.config import get_settings; from app.core.database import database_path; print('Migrated database: ' + str(database_path(get_settings().database_url)))"
