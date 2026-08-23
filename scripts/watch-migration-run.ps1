$runId = "run-3d0b72aa559d"
$db = "C:\Users\abdelilah.mortaki\Desktop\migration-lab\real-e2e-11-21-v21-r9\app-data\control-tower.db"
$intervalSeconds = 20

Write-Host "Watching migration run $runId every ${intervalSeconds}s (Ctrl+C to stop)..."
Write-Host ""

while ($true) {
    $block = @"
import sqlite3
from datetime import datetime

db = r'$db'
run = '$runId'
c = sqlite3.connect(db)
cur = c.cursor()

def fmt(ts):
    if not ts:
        return ""
    try:
        return datetime.fromisoformat(ts).strftime("%H:%M:%S")
    except Exception:
        return str(ts)

row = cur.execute(
    "SELECT id,status,run_phase,updated_at FROM migration_runs WHERE id=?", (run,)
).fetchone()
print("=" * 50)
print("TIME:  ", datetime.now().strftime("%H:%M:%S"))
if not row:
    print("RUN NOT FOUND:", run)
    raise SystemExit(0)
print("RUN:   ", row[0])
print("STATUS:", row[1])
print("PHASE: ", row[2])

print()
print("GATES:")
for gate in ("G05", "G06"):
    r = cur.execute(
        "SELECT status,decision,stale_reason FROM " + gate.lower() + "_approvals "
        "WHERE run_id=? ORDER BY created_at DESC LIMIT 1", (run,)
    ).fetchone()
    if r:
        print(f"  {gate}: {r[0]}" + (f"  decision={r[1]}" if r[1] else "") + (f"  stale={r[2]}" if r[2] else ""))
    else:
        print(f"  {gate}: (none)")
g7 = cur.execute(
    "SELECT status,gate_version FROM stage_gate_packages WHERE run_id=? AND gate_id='G07' "
    "ORDER BY gate_version DESC LIMIT 1", (run,)
).fetchone()
g7d = cur.execute(
    "SELECT decision,accepted,actor FROM stage_gate_decisions WHERE run_id=? AND gate_id='G07' "
    "ORDER BY created_at DESC LIMIT 1", (run,)
).fetchone()
if g7:
    print(f"  G07: package={g7[0]} v{g7[1]}" + (f"  decision={g7d[0]} accepted={g7d[1]} actor={g7d[2]}" if g7d else ""))
else:
    print("  G07: (none)")

print()
print("STAGE:")
stage = cur.execute(
    "SELECT id,status,started_at,completed_at FROM migration_stages WHERE run_id=? ORDER BY stage_order", (run,)
).fetchone()
if stage:
    print("  name:   ", stage[0])
    print("  status: ", stage[1])
else:
    print("  (none)")
cont = cur.execute(
    "SELECT status,current_node,worker_id,last_error_code FROM transformation_continuations WHERE run_id=?", (run,)
).fetchone()
if cont:
    print("  node:      ", cont[1])
    print("  cont state:", cont[0], ("worker=" + cont[2] if cont[2] else "") + ("  error=" + (cont[3] or "") if cont[3] else ""))

print()
print("RUNTIME BINDINGS:")
found = False
for kind in ("node", "npm", "npx"):
    r = cur.execute(
        "SELECT version_exact,resolved_path,status FROM stage_runtime_bindings "
        "WHERE run_id=? AND kind=? ORDER BY created_at DESC LIMIT 1", (run, kind)
    ).fetchone()
    if r:
        found = True
        print(f"  {kind}: {r[0]}  [{r[2]}]")
        print(f"        {r[1]}")
if not found:
    print("  (none)")

print()
print("LATEST COMMANDS:")
for r in cur.execute(
    "SELECT command_id,status,exit_code,started_at,finished_at FROM command_executions "
    "WHERE run_id=? ORDER BY COALESCE(started_at,requested_at) DESC LIMIT 3", (run,)
):
    print(f"  {r[0]}: {r[1]} exit={r[2] if r[2] is not None else '-'} started={fmt(r[3])} finished={fmt(r[4])}")

print()
print("LATEST EVENTS:")
for r in cur.execute(
    "SELECT occurred_at,event_type,reason FROM workflow_events WHERE run_id=? "
    "ORDER BY occurred_at DESC LIMIT 10", (run,)
):
    print(f"  {fmt(r[0])}  {r[1]}  {r[2]}")

terminal = {"COMPLETED", "FAILED", "CANCELLED", "TIMED_OUT", "CLEANUP_FAILED"}
if row[1] in terminal:
    print()
    print("TERMINAL STATE:", row[1])
print("=" * 50)
"@
    $out = $block | & ".\.venv\Scripts\python.exe" - 2>&1
    if ($LASTEXITCODE -ne 0) { Write-Host $out; Write-Host "python error, stopping."; break }
    $out | ForEach-Object { Write-Host $_ }
    if ($out -match "TERMINAL STATE") { Write-Host "Run reached terminal state. Stopping."; break }
    Start-Sleep -Seconds $intervalSeconds
}