$runId="run-3d0b72aa559d"
$db="C:\Users\abdelilah.mortaki\Desktop\migration-lab\real-e2e-11-21-v21-r9\app-data\control-tower.db"

Write-Host "=== RUN POLICY ==="
@"
import json, sqlite3
db=r'$db'
run='$runId'
c=sqlite3.connect(db).cursor()

r=c.execute("""
SELECT id,status,run_phase,run_policy_snapshot
FROM migration_runs WHERE id=?
""",(run,)).fetchone()

print(r[0])
print(r[1], r[2])
print(json.dumps(json.loads(r[3]),indent=2))

print("\n=== G06 GATE ===")
for x in c.execute("""
SELECT gate_id,status,decision,stale_reason,created_at,updated_at
FROM g06_approvals
WHERE run_id=?
ORDER BY created_at
""",(run,)):
    print(x)

print("\n=== EVENTS G06 WINDOW ===")
for x in c.execute("""
SELECT event_type,reason,occurred_at
FROM workflow_events
WHERE run_id=?
AND occurred_at >= '2026-08-23 18:45:00'
AND occurred_at <= '2026-08-23 18:46:30'
ORDER BY occurred_at
""",(run,)):
    print(x)

print("\n=== PLANS ===")
for x in c.execute("""
SELECT id,version,status,checksum,state_version,created_at
FROM migration_plans
WHERE run_id=?
ORDER BY created_at
""",(run,)):
    print(x)
"@ | .\.venv\Scripts\python.exe -