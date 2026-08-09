import sqlite3

db = r"C:\Users\abdelilah.mortaki\AppData\Local\AngularMigrationControlTower-Fresh-20260807-C\control-tower.db"
run_id = "run-a2a348a950bb"
stage_id = "angular-20-to-21--1269ed5e61c08196"

c = sqlite3.connect(db)
c.row_factory = sqlite3.Row

def dump(title, sql, args=()):
    print("\n" + "="*90)
    print(title)
    print("="*90)
    try:
        rows = c.execute(sql, args).fetchall()
        for r in rows:
            print(dict(r))
    except Exception as e:
        print("ERROR:", e)

dump(
    "CONTINUATION",
    """
    SELECT *
    FROM transformation_continuations
    WHERE run_id=?
    ORDER BY created_at DESC
    LIMIT 5
    """,
    (run_id,)
)

dump(
    "WORKSPACE BINDINGS",
    """
    SELECT *
    FROM stage_workspace_bindings
    WHERE run_id=? AND stage_id=?
    ORDER BY created_at
    """,
    (run_id, stage_id)
)

dump(
    "REPAIR ATTEMPTS",
    """
    SELECT *
    FROM repair_attempts
    WHERE run_id=? AND stage_id=?
    ORDER BY created_at
    """,
    (run_id, stage_id)
)

dump(
    "COMMANDS AFTER ANGULAR 20->21 START",
    """
    SELECT id,idempotency_key,command_id,status,arguments,
           requested_at,started_at,finished_at,
           failure_code,failure_message,
           start_fingerprint,end_fingerprint
    FROM command_executions
    WHERE run_id=? AND stage_id=?
    ORDER BY requested_at
    """,
    (run_id, stage_id)
)

dump(
    "LATEST 50 WORKFLOW EVENTS",
    """
    SELECT sequence,event_type,reason,payload,occurred_at
    FROM workflow_events
    WHERE run_id=?
    ORDER BY sequence DESC
    LIMIT 50
    """,
    (run_id,)
)

c.close()
