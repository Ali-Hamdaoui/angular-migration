$ErrorActionPreference = "Stop"
$backend = (Resolve-Path (Join-Path $PSScriptRoot "..\backend")).Path
Set-Location $backend

# Alembic and Uvicorn both load Settings from the same environment.  Upgrade
# before starting the server and let lifespan perform the strict head/schema
# check again before accepting requests.
python -m alembic -c alembic.ini upgrade heads
if ($LASTEXITCODE -ne 0) { throw "Alembic migration failed." }
python -c "from app.core.config import get_settings; from app.core.database import database_path; print('Backend database: ' + str(database_path(get_settings().database_url)))"
python -m uvicorn app.main:app --reload
