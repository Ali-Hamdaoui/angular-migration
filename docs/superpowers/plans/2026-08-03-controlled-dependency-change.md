# Controlled Dependency Change Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Safely apply a G10-approved `package.json` dependency repair, regenerate and verify the root npm lockfile through checksum-bound command authority, then continue to `npm-ci-final`.

**Architecture:** Add `lockfile_generation` to newly generated stage plans and run it through the existing stage command authorization/executor path. A focused `LockfileGenerationRunner` owns prequalification, crash-safe queue/recovery, exact mutation verification, CAS binding update, immutable verification evidence, and resume; ordinary repair and validation paths remain unchanged.

**Tech Stack:** Python 3.12, Pydantic, SQLAlchemy, pytest, existing LocalFilesystemArtifactStore, CommandPolicyEngineService, StageExecutionApplicationService, and CommandExecutorService.

## Global Constraints

- Command ID is exactly `npm-lockfile-generate`.
- Executable is exactly `npm`.
- Arguments are exactly `install --package-lock-only --ignore-scripts --no-audit --no-fund`.
- Execute with `shell=False` in the authoritative bound stage workspace and resolved checksum-bound runtime profile.
- Never inject the command into an accepted immutable stage plan.
- Missing authority blocks with `STAGE_PLAN_COMMAND_AUTHORITY_MISSING`.
- The preserved in-flight continuation remains blocked and is not rebound or advertised as restartable.
- Proposer, Reviewer, and G10 creation remain non-mutating.
- Execute only after approved `dependency_change` application and before `npm-ci-final`.
- Direct `package-lock.json` and npm shrinkwrap patches remain forbidden.
- Root `npm-shrinkwrap.json` blocks execution before queueing.
- No frontend, migrations, preserved-database access, unrestricted shell, implicit dependency flags, or unrelated workflow redesign.

## File map

- Modify `backend/app/domain/command.py`: registered deterministic command definition.
- Modify `backend/app/domain/planning.py`: require the `lockfile_generation` command group in new stage contracts.
- Modify `backend/app/services/planning_application_service.py`: emit the checksum-bound command reference.
- Modify `backend/app/llm_gateway/azure_gateway.py`: package-specific proposer instructions.
- Modify `backend/app/services/repair_application_service.py`: reject forbidden package paths and verify exact accepted-plan authority.
- Modify `backend/app/services/patch_apply_service.py`: explicitly apply `dependency_change`.
- Create `backend/app/services/lockfile_generation_runner.py`: queue, recover, verify, persist evidence, CAS-update binding, and resume.
- Modify `backend/app/orchestration/transformer_graph.py`: route dependency repairs through the runner after apply.
- Modify focused tests listed per task; no schema files or migrations change.

---

### Task 1: Register and checksum-bind lockfile-generation authority

**Files:**
- Modify: `backend/app/domain/command.py:252-294`
- Modify: `backend/app/domain/planning.py:151-184`
- Modify: `backend/app/services/planning_application_service.py:76-115`
- Test: `backend/tests/test_planning_application_service_s2_f06_i01.py`
- Test: `backend/tests/test_planning_transformation_boundary.py`
- Test: `backend/tests/test_command_executor_services.py`

**Interfaces:**
- Produces: `StageExecutionPlan.commands["lockfile_generation"]` containing one `CommandTemplateReference` for `npm-lockfile-generate`.
- Produces: default registry template `tpl-npm-lockfile-generate`, version 1.
- Consumes: existing request execution-profile checksum and stage workspace alias.

- [ ] **Step 1: Write failing authority tests**

Add assertions equivalent to:

```python
reference = plan.commands["lockfile_generation"][0]
assert reference.command_id == "npm-lockfile-generate"
assert reference.template_id == "tpl-npm-lockfile-generate"
assert reference.executable == "npm"
assert reference.arguments == (
    "install", "--package-lock-only", "--ignore-scripts", "--no-audit", "--no-fund",
)
assert reference.shell is False
assert reference.runtime_profile_checksum == request.execution_profile_checksum
assert "npm-lockfile-generate" in {item.command_id for item in DEFAULT_COMMAND_TEMPLATES}
```

Also construct an existing serialized plan without `lockfile_generation`, verify its checksum and JSON remain unchanged, and verify no helper mutates it in place.

- [ ] **Step 2: Run tests and verify RED**

Run:

```powershell
backend/.venv/Scripts/python.exe -m pytest backend/tests/test_planning_application_service_s2_f06_i01.py backend/tests/test_planning_transformation_boundary.py backend/tests/test_command_executor_services.py -q
```

Expected: failures for missing command group/template.

- [ ] **Step 3: Implement the minimal command and plan group**

Add to `TRANSFORMATION_COMMAND_CATALOGUE`:

```python
"npm-lockfile-generate": TransformationCommandDefinition(
    command_id="npm-lockfile-generate",
    template_id="tpl-npm-lockfile-generate",
    executable="npm",
    argument_patterns=(
        "install", "--package-lock-only", "--ignore-scripts", "--no-audit", "--no-fund",
    ),
    executable_aliases=("npm.cmd",),
    timeout_seconds=3600,
    network_profile="approved-registries-only",
    allowed_env_vars=("NODE_OPTIONS", "NPM_CONFIG_CACHE"),
    max_output_bytes=5_000_000,
    description="Regenerate the approved npm lockfile without lifecycle scripts",
),
```

Add `lockfile_generation` to the complete StageExecutionPlan command set and create it with:

```python
"lockfile_generation": (self._command("npm-lockfile-generate", request),),
```

Do not add any compatibility flags or legacy-plan mutation.

- [ ] **Step 4: Run tests and verify GREEN**

Run the Step 2 command. Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add backend/app/domain/command.py backend/app/domain/planning.py backend/app/services/planning_application_service.py backend/tests/test_planning_application_service_s2_f06_i01.py backend/tests/test_planning_transformation_boundary.py backend/tests/test_command_executor_services.py
git commit -m "feat(transformer): plan lockfile generation authority"
```

### Task 2: Align proposal contract and fail closed on missing plan authority

**Files:**
- Modify: `backend/app/llm_gateway/azure_gateway.py:136`
- Modify: `backend/app/services/repair_application_service.py:434-477,593-666,668-792`
- Test: `backend/tests/test_repair_application_service.py`
- Test: `backend/tests/test_repair_provider_schema_policy.py`

**Interfaces:**
- Consumes: checksum-bound `context["stage_plan_commands"]` copied from the loaded `StageExecutionPlanModel.stage_plan`.
- Produces: `context["has_dependency_change"]: bool` in the validated proposal payload only through operation inspection; no workspace mutation.
- Error: `STAGE_PLAN_COMMAND_AUTHORITY_MISSING` when the exact reference is absent or mismatched.

- [ ] **Step 1: Write failing proposal tests**

Cover:

```python
with pytest.raises(RepairApplicationError) as error:
    service._bind_proposal_candidate(unified_diff_touching_package_json, context)
assert error.value.code == "REPAIR_DEPENDENCY_OPERATION_REQUIRED"

with pytest.raises(RepairApplicationError) as error:
    service.validate_proposal(valid_dependency_change, context_without_command)
assert error.value.code == "STAGE_PLAN_COMMAND_AUTHORITY_MISSING"

assert service.validate_proposal(valid_dependency_change, context_with_exact_command)
```

Assert ordinary operations touching `package.json`, dependency operations outside it, and all direct `package-lock.json`/`npm-shrinkwrap.json` paths remain rejected. Assert proposal and review calls do not alter workspace bytes.

- [ ] **Step 2: Run tests and verify RED**

```powershell
backend/.venv/Scripts/python.exe -m pytest backend/tests/test_repair_application_service.py backend/tests/test_repair_provider_schema_policy.py -q
```

Expected: unified-diff package test passes unexpectedly or missing-authority test reports the old unconditional error.

- [ ] **Step 3: Implement exact authority validation**

Expose only the loaded command map in `_attempt_context`:

```python
"stage_plan_commands": dict((stage_plan.stage_plan or {}).get("commands") or {}),
```

Add a constant exact shape derived from the registered catalogue definition, then verify one reference in `lockfile_generation` matches command ID, template ID/version, executable, argv, workspace alias, network profile, runtime checksum, timeout, and `shell=False`. Do not mutate the plan.

Reject root `package.json` from `_unified_diff_touched_files()` because unified diffs have no controlled dependency discriminator. Replace the unconditional `REPAIR_DEPENDENCY_COMMAND_MISSING` branch with exact authority verification and `STAGE_PLAN_COMMAND_AUTHORITY_MISSING`.

Update the proposer prompt to state:

```text
Every package.json change must use proposal_format "operations" and operation
"dependency_change" with non-null old_text and new_text. Ordinary operations
and unified diffs must not modify package.json. Never patch package-lock.json or
npm-shrinkwrap.json directly.
```

- [ ] **Step 4: Run tests and verify GREEN**

Run the Step 2 command. Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add backend/app/llm_gateway/azure_gateway.py backend/app/services/repair_application_service.py backend/tests/test_repair_application_service.py backend/tests/test_repair_provider_schema_policy.py
git commit -m "fix(transformer): enforce dependency proposal authority"
```

### Task 3: Explicitly apply approved dependency changes

**Files:**
- Modify: `backend/app/services/patch_apply_service.py:338-372`
- Test: `backend/tests/test_patch_apply_service.py`

**Interfaces:**
- Consumes: validated `dependency_change` with `path="package.json"`, exact `preimage_sha256`, `old_text`, and `new_text`.
- Produces: the same prepared/applied ledger shape as `replace_text`, with operation identity preserved in the approved proposal.

- [ ] **Step 1: Write failing apply tests**

Add a successful `dependency_change` test and an unknown-operation rejection test:

```python
result = service.apply(proposal=dependency_proposal, ...)
assert json.loads((workspace / "package.json").read_text())["dependencies"]["x"] == "2.0.0"
assert not command_gateway.calls

with pytest.raises(RepairApplicationError) as error:
    service._prepare_operations([{"operation": "unknown", ...}], workspace)
assert error.value.code == "REPAIR_OPERATION_INVALID"
```

- [ ] **Step 2: Run test and verify RED**

```powershell
backend/.venv/Scripts/python.exe -m pytest backend/tests/test_patch_apply_service.py -q
```

Expected: unknown operation currently falls through as replacement; explicit dependency branch is absent.

- [ ] **Step 3: Implement explicit operation dispatch**

Use explicit branches:

```python
if action in {"replace_text", "dependency_change"}:
    # exact one-occurrence replacement
elif action == "delete_text_file":
    ...
else:
    raise RepairApplicationError("REPAIR_OPERATION_INVALID", "Repair operation is unsupported")
```

Do not execute npm or touch lockfiles in this service.

- [ ] **Step 4: Run test and verify GREEN**

Run the Step 2 command. Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add backend/app/services/patch_apply_service.py backend/tests/test_patch_apply_service.py
git commit -m "fix(transformer): apply dependency changes explicitly"
```

### Task 4: Build crash-safe lockfile-generation runner and evidence

**Files:**
- Create: `backend/app/services/lockfile_generation_runner.py`
- Test: `backend/tests/test_lockfile_generation_runner.py`

**Interfaces:**
- Class: `LockfileGenerationRunner(stage_execution=None, now_provider=None)`.
- Method: `advance(session, continuation, *, next_node: str) -> str` returning `queued`, `waiting`, `passed`, or raising `LockfileGenerationError(code, message)`.
- Uses stage step `lockfile_generation-0` and idempotency key `"{continuation.id}:lockfile-generation"`.

- [ ] **Step 1: Write failing prequalification and queue tests**

Cover exact authority, shrinkwrap, phase names, and single queue behavior:

```python
assert runner.advance(session, continuation, next_node="repair_revalidate") == "queued"
execution = session.get(CommandExecutionModel, step.execution_id)
assert execution.command_id == "npm-lockfile-generate"
assert execution.start_fingerprint == {
    "post_apply_pre_command_package_json_sha256": expected_package,
    "post_apply_pre_command_package_lock_sha256": expected_lock_or_missing,
    "post_apply_pre_command_workspace_excluding_root_lockfile_fingerprint": expected_workspace,
    "post_apply_pre_command_binding_fingerprint": expected_binding,
}

assert runner.advance(session, continuation, next_node="repair_revalidate") == "waiting"
assert one_execution_exists()
```

With root `npm-shrinkwrap.json`, expect `LOCKFILE_GENERATION_SHRINKWRAP_PRESENT` and zero command executions.

- [ ] **Step 2: Run tests and verify RED**

```powershell
backend/.venv/Scripts/python.exe -m pytest backend/tests/test_lockfile_generation_runner.py -q
```

Expected: import failure because the runner does not exist.

- [ ] **Step 3: Implement queue and crash recovery**

Reuse `StageExecutionApplicationService._authorize_and_queue_first_command()` with group `lockfile_generation`. Before queueing, compute SHA-256 using a helper that returns `"missing"` for absent files and a canonical manifest fingerprint excluding only relative path `package-lock.json`.

Persist the four explicitly named pre-command values in `CommandExecutionModel.start_fingerprint`. Set the step execution ID before moving the continuation to `waiting_command`. On replay:

- existing nonterminal execution: wait on the same ID;
- terminal failure/interruption: fail without queueing another command;
- succeeded, unverified execution: continue verification;
- passed step plus linked verification artifact: idempotently resume without rewriting evidence.

The unique command execution idempotency key and existing step execution link prevent duplicate queueing.

- [ ] **Step 4: Write failing terminal verification tests**

Cover:

- package mutation;
- any non-root-lockfile workspace mutation, including `node_modules`;
- missing lockfile;
- invalid JSON lockfile;
- unsynchronized lockfile;
- incomplete command artifacts;
- successful verification;
- replay after verification does not duplicate the artifact or CAS update.

Assert exact post-command names:

```python
assert execution.end_fingerprint == {
    "post_command_package_json_sha256": expected_package,
    "post_command_package_lock_sha256": expected_lock,
    "post_command_workspace_excluding_root_lockfile_fingerprint": expected_workspace,
    "post_command_binding_fingerprint": expected_binding,
}
```

- [ ] **Step 5: Run verification tests and verify RED**

Run the Step 2 command. Expected: failures for missing verification behavior.

- [ ] **Step 6: Implement verification, evidence, and authoritative CAS**

Use `PackageMetadataInspector` and `LockfilePrequalificationService` for parseability and root dependency agreement. Write one immutable JSON artifact containing the approved safe metadata from the design.

Register `ArtifactMetadataModel` with:

```python
execution_id=execution.id
owner_reference=f"{execution.id}:lockfile-generation-verification"
correlation_id=execution.correlation_id
```

Append its ID idempotently to both existing arrays:

```python
execution.artifact_ids = list(dict.fromkeys([*(execution.artifact_ids or []), artifact_id]))
step.artifact_ids = list(dict.fromkeys([*(step.artifact_ids or []), artifact_id]))
```

This proves durable linkage without a schema change: `ArtifactMetadataModel.execution_id`, `owner_reference`, and `correlation_id`; `CommandExecutionModel.artifact_ids`; and `StageStepModel.execution_id/artifact_ids` already exist.

In the same database transaction, CAS-update `StageWorkspaceBindingModel` using ID, run, stage, active flag, workspace path, and expected `post_apply_pre_command_binding_fingerprint`. Set the complete post-command stage fingerprint. If CAS misses, accept only an exact idempotent replay where the binding already equals the recorded post-command fingerprint and the same verification artifact is linked; otherwise raise `LOCKFILE_GENERATION_BINDING_STALE`.

Set `execution.end_fingerprint`, mark the step passed, persist verification metadata/linkage, update the binding, and queue `next_node` atomically. Artifact-file creation before this transaction is recovered by checking existing metadata/owner linkage and validating content checksum before reuse.

- [ ] **Step 7: Run tests and verify GREEN**

Run the Step 2 command. Expected: PASS.

- [ ] **Step 8: Commit**

```powershell
git add backend/app/services/lockfile_generation_runner.py backend/tests/test_lockfile_generation_runner.py
git commit -m "feat(transformer): verify governed lockfile generation"
```

### Task 5: Route approved dependency repairs through the runner

**Files:**
- Modify: `backend/app/orchestration/transformer_graph.py:150-205,1887-1943`
- Test: `backend/tests/test_transformer_repair_failure_governance.py`

**Interfaces:**
- Consumes: persisted approved proposal artifact and operation list.
- Produces: graph node `lockfile_generation` between successful dependency apply and `repair_revalidate`.
- Uses: `LockfileGenerationRunner.advance(..., next_node="repair_revalidate")`.

- [ ] **Step 1: Write failing orchestration tests**

Cover:

```text
proposal/review/G10 creation -> no workspace or command mutation
approved ordinary repair apply -> repair_revalidate
approved dependency apply -> lockfile_generation
lockfile_generation queued/waiting -> no npm-ci-final
verified lockfile_generation -> repair_revalidate -> npm-ci-final
```

Simulate restart after apply commit, after command queue, after terminal command, and after verification commit. Assert the package operation is applied once, one command execution exists, one verification artifact exists, and the continuation resumes from durable state.

- [ ] **Step 2: Run test and verify RED**

```powershell
backend/.venv/Scripts/python.exe -m pytest backend/tests/test_transformer_repair_failure_governance.py -q
```

Expected: dependency apply currently queues `repair_revalidate` directly and the node is unsupported.

- [ ] **Step 3: Implement minimal graph routing**

Register the new node in `advance()`. After successful apply persistence, inspect the already checksum-bound proposal artifact:

```python
has_dependency_change = any(
    item.get("operation") == "dependency_change"
    for item in proposal.get("operations") or []
)
self._queue(continuation, "lockfile_generation" if has_dependency_change else "repair_revalidate")
```

Add `_lockfile_generation()` that delegates to the runner and maps `LockfileGenerationError` through the existing `_block()` path. Do not call the runner from proposal, review, G10, or patch apply.

Preserve existing apply ledger/reconstruction behavior: a crash before apply commit reconstructs from the checkpoint; a committed `attempt.status="applied"` never re-enters patch mutation and resumes at the persisted next node.

- [ ] **Step 4: Run test and verify GREEN**

Run the Step 2 command. Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add backend/app/orchestration/transformer_graph.py backend/tests/test_transformer_repair_failure_governance.py
git commit -m "feat(transformer): orchestrate lockfile generation after G10"
```

### Task 6: Focused integration verification and final review

**Files:**
- Review all files changed in Tasks 1-5.
- No new production files beyond `lockfile_generation_runner.py`.

**Interfaces:**
- Verifies the complete contract from stage-plan generation through post-command resume.

- [ ] **Step 1: Run focused tests**

```powershell
backend/.venv/Scripts/python.exe -m pytest backend/tests/test_planning_application_service_s2_f06_i01.py backend/tests/test_planning_transformation_boundary.py backend/tests/test_command_executor_services.py backend/tests/test_repair_provider_schema_policy.py backend/tests/test_repair_application_service.py backend/tests/test_patch_apply_service.py backend/tests/test_lockfile_generation_runner.py backend/tests/test_transformer_repair_failure_governance.py -q
```

Expected: PASS. Do not run the full suite.

- [ ] **Step 2: Compile changed Python files**

```powershell
backend/.venv/Scripts/python.exe -m py_compile backend/app/domain/command.py backend/app/domain/planning.py backend/app/services/planning_application_service.py backend/app/llm_gateway/azure_gateway.py backend/app/services/repair_application_service.py backend/app/services/patch_apply_service.py backend/app/services/lockfile_generation_runner.py backend/app/orchestration/transformer_graph.py
```

Expected: exit code 0.

- [ ] **Step 3: Verify diff hygiene**

```powershell
git diff --check
git status --short
```

Expected: no whitespace errors; only scoped backend/tests/docs changes.

- [ ] **Step 4: Perform one read-only review**

Inspect `git diff HEAD~5..HEAD` and verify:

- no command can run before approved apply;
- no legacy plan mutation or continuation rebinding;
- exact command authority and ordering;
- exact mutation checks and phase checksum names;
- CAS predicates and idempotent replay;
- verification artifact linked through existing columns;
- no frontend, migration, database, runtime, or unrelated changes.

- [ ] **Step 5: Commit any review-only corrections, then report final SHA**

If corrections are needed, repeat their focused RED/GREEN check and commit only those corrections. Otherwise report the latest implementation commit SHA and the earlier design/plan commits.
