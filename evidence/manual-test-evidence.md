# Manual Runtime Test Evidence — G02 Stage Workspace Bootstrap

## Environment

| Item | Value |
|------|-------|
| Worktree | `/home/ubuntu/amfa-worktrees/02-stage-workspace-bootstrap` |
| Runtime root | `/home/ubuntu/amfa-runtime/02-stage-workspace-bootstrap` |
| Backend | `http://127.0.0.1:8302` |
| Frontend | `http://127.0.0.1:3302` |

## Cases Executed

### MT-001: S3-F05 Authoritative Scenario (Stage Sandbox Prep + G07)

**Preconditions:** Authenticated reviewer/operator, valid run with snapshot created.

**Steps:**
1. Launch backend + frontend
2. Navigate to stage preparation page
3. Trigger stage preparation
4. Observe progress through PREPARING → PLAN_LOCKED → WAITING_APPROVAL states
5. Submit G07 approval with comment
6. Observe SANDBOX_READY state
7. Verify artifacts are registered (copy report, fingerprints, verification)

**Expected result:** Stage sandbox created, G07 approved, evidence artifacts finalized.

**Negative test:** Submit with stale state_version → expect 409 error.

### MT-002: S3-F06 Authoritative Scenario (Bootstrap Install)

**Preconditions:** G07 approved, sandbox ready.

**Steps:**
1. Navigate to bootstrap install step
2. Trigger bootstrap install
3. Observe install progress
4. Verify command execution record created
5. Verify pre/post workspace fingerprints

**Expected result:** Bootstrap install step runs (or is authorized).

**Negative test:** Trigger before G07 approval → expect 409 error.

### MT-900: Capability Integrated Happy Path

**Preconditions:** Valid run, source snapshot, G02 approved.

**Steps:**
1. Full flow: prepare stage → create sandbox → G07 approve → bootstrap install
2. Verify all events emitted at each stage
3. Verify artifact chain complete

**Expected result:** End-to-end integration works.

### MT-910: Stale/Idempotency/Reconnect/Restart

**Steps:**
1. Submit request with old state_version → expect STALE_STATE_VERSION
2. Submit same idempotency_key twice → second returns original result (idempotent)
3. Simulate backend restart → verify state recovery

### MT-920: Security/Accessibility/Observability

**Steps:**
1. Submit with unauthorized actor → expect authorization failure
2. Verify no absolute paths in API responses
3. Check screen reader labels on controls
4. Verify correlation IDs in error responses
