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
    for row in c.execute(sql, args).fetchall():
        print(dict(row))

dump(
    "CURRENT CONTINUATION",
    """
    SELECT id,status,current_node,state_version,last_error_code,last_error_message,
           waiting_execution_id,updated_at
    FROM transformation_continuations
    WHERE run_id=?
    ORDER BY created_at DESC
    LIMIT 1
    """,
    (run_id,)
)

dump(
    "REPAIR ATTEMPTS",
    """
    SELECT id,attempt_number,status,pre_fingerprint,post_fingerprint,
           checkpoint_id,failure_evidence_artifact_id,
           proposal_artifact_id,review_artifact_id,updated_at
    FROM repair_attempts
    WHERE run_id=? AND stage_id=?
    ORDER BY attempt_number
    """,
    (run_id, stage_id)
)

dump(
    "ACTIVE BINDING",
    """
    SELECT id,workspace_path,workspace_fingerprint,last_verified_fingerprint,
           last_verified_at,fingerprint_profile_id
    FROM stage_workspace_bindings
    WHERE run_id=? AND stage_id=? AND active=1
    """,
    (run_id, stage_id)
)

dump(
    "TIMED OUT RETRY",
    """
    SELECT id,status,failure_code,reconstruction_required,
           timeout_seconds,operation_kind,checkpoint_id,
           parent_execution_id,idempotency_key
    FROM command_executions
    WHERE id='exec-9f91707ade55'
    """
)

dump(
    "EVENTS 429+",
    """
    SELECT sequence,event_type,reason,payload,occurred_at
    FROM workflow_events
    WHERE run_id=? AND sequence >= 429
    ORDER BY sequence
    """,
    (run_id,)
)

c.close()
