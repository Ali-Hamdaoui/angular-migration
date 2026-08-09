# Plan: Transformer Angular Update Command Supersession

## Objective

Correct the `angular-update-exact` command definition and post-command routing so that:
1. The invalid `--interactive=false` flag is removed from the authoritative command.
2. Existing template v1 remains as immutable history.
3. A new template v2 (without `--interactive=false`) is added.
4. Planning materializers consume the command catalogue instead of duplicating arguments.
5. Post-command routing terminalizes the step on failure, routes to classification, and enables
   checkpoint-based recovery.
6. A superseding G07 approval is required before retry with corrected arguments.
7. No duplicate active Angular-update attempts are permitted.

## Proven Root Cause

`ng update` (Angular CLI 19.0.0) does not declare an `--interactive` option.
The flag `--interactive=false` originated in the authoritative command catalogue
at `backend/app/domain/command.py:239` and was independently duplicated as
hardcoded arguments in `planning_review_application_service.py:376-385`.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                      COMMAND AUTHORITY (Agent 1)                     │
│                                                                     │
│  domain/command.py           planning_application_service.py        │
│  ┌────────────────────┐     ┌──────────────────────────────────┐    │
│  │ CATALOGUE (v1)     │────→│ _command() reads from CATALOGUE  │    │
│  │   --interactive    │     │ template_version=1 → template_v2 │    │
│  │   =false           │     └──────────────────────────────────┘    │
│  │                    │                                            │
│  │ V2_RENDERER (v2)   │     planning_review_application_service.py │
│  │   (without flag)   │────→│ _rebuild() reads from V2_RENDERER   │
│  └────────────────────┘     └──────────────────────────────────┘    │
│                                                                     │
│  command_registry_service.py                                        │
│  ┌──────────────────────────────────────────┐                      │
│  │ seed_defaults() checks (id, version)     │                      │
│  │ find_registered_template(version=N)      │                      │
│  └──────────────────────────────────────────┘                      │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│                  ROUTING AND RECOVERY (Agent 2)                      │
│                                                                     │
│  transformer_graph.py                                               │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │ _angular_update() → queue w/ next_node="handle_prompt"      │   │
│  │ _handle_prompt():                                            │   │
│  │   ├─ prompt exists → governed prompt flow (unchanged)        │   │
│  │   ├─ success, no prompt → target_inspection (unchanged)      │   │
│  │   └─ failure, no prompt → FAILED step → classify_failure     │   │
│  │ _classify_failure():                                         │   │
│  │   ├─ angular_update failure → restore checkpoint → retry     │   │
│  │   └─ other failures → existing repair flow (unchanged)       │   │
│  │ _restore_angular_update_checkpoint():                        │   │
│  │   → reconstruct from pre_angular_update checkpoint           │   │
│  │   → verify fingerprint                                       │   │
│  │   → route to angular_update or create_superseding_g07        │   │
│  └──────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

## Exact File Map

| File | Ownership | Change Summary |
|------|-----------|---------------|
| `backend/app/domain/command.py` | Agent 1 | Add `ANGULAR_UPDATE_V2_RENDERER` (TransformationCommandDefinition, no `--interactive=false`). Add v2 CommandTemplate (version=2) to templates |
| `backend/app/services/planning_application_service.py` | Agent 1 | `_command()`: use v2 renderer for angular-update-exact, template_version=2 |
| `backend/app/services/planning_review_application_service.py` | Agent 1 | `_rebuild()`: replace hardcoded argument tuple with `V2_RENDERER.render_arguments(...)` |
| `backend/app/services/command_registry_service.py` | Agent 1 | `seed_defaults()`: check (id, version) uniqueness instead of just id |
| `backend/app/orchestration/transformer_graph.py` | Agent 2 | `_handle_prompt()`: terminalize FAILED, route to classify_failure. `_classify_failure()`: add angular_update branch. Add `_restore_angular_update_checkpoint()`, `_is_angular_update_failure()` |
| `backend/app/orchestration/transformer_graph.py:advance()` | Agent 2 | Add superseding G07 routing in `bootstrap_install` to skip completed bootstrap |
| `backend/app/domain/transformation.py` | Agent 2 (minor) | Possibly `TransformationNode` extras for superseding G07 |
| `backend/app/repositories/models/workflow.py` | Neither | No changes needed |
| `backend/app/state/transition_service.py` | Neither | No changes needed |
| `backend/app/services/stage_gate_service.py` | Neither | No changes needed (already supports versioned gates) |

## Interfaces

### Agent 1 → Agent 2 (exported symbols)

```python
# backend/app/domain/command.py
ANGULAR_UPDATE_V2_RENDERER: Final[TransformationCommandDefinition]
#   argument_patterns without "--interactive=false"
#   template_id="tpl-angular-update-exact", command_id="angular-update-exact"
```

### Agent 2 → Agent 1 (consumed behavior)

- Agent 2's `_handle_prompt()` terminalization does not require any symbols from Agent 1.
- Agent 2's recovery routing to `angular_update` does not require v2 knowledge.
- The superseding G07 routing in `advance()` may skip `bootstrap_install` if that step is already PASSED — no Agent 1 dependency.
- Agent 2's checkpoint restoration is independent of command authority.

### Test interface

Agent 2 tests verify step terminalization and routing only — no v2 dependency.
Agent 1 tests verify template versions, seeding, and rendering — no routing dependency.

## Tasks

### Task 1.1 (Agent 1): Add v2 template definition

- `domain/command.py`: Define `ANGULAR_UPDATE_V2_RENDERER` as `TransformationCommandDefinition` with identical metadata except `argument_patterns` omits `--interactive=false`.
- `domain/command.py`: Append v2 `CommandTemplate(version=2, ...)` to `DEFAULT_COMMAND_TEMPLATES`.
- `command_registry_service.py:seed_defaults()`: Change uniqueness check from `tpl.template_id in existing_ids` to `(tpl.template_id, tpl.version) not in existing` — query existing `(id, version)` pairs.

### Task 1.2 (Agent 1): Switch planning to v2

- `planning_application_service.py:_command()`: For `command_id == "angular-update-exact"`, use `ANGULAR_UPDATE_V2_RENDERER.render_arguments(bindings)` and `template_version=2`.

### Task 1.3 (Agent 1): Fix _rebuild() to consume catalogue

- `planning_review_application_service.py:_rebuild()`: Replace lines 372-387:
  ```python
  if changes.target_cli_exact is not None:
      stage_values["target_cli_exact"] = changes.target_cli_exact
      commands = dict(stage_values["commands"])
      definition = ANGULAR_UPDATE_V2_RENDERER  # or TRANSFORMATION_COMMAND_CATALOGUE["angular-update-exact"]
      update = dict(commands["angular_update"][0])
      update["arguments"] = definition.render_arguments({
          "target_cli_exact": changes.target_cli_exact,
          "target_exact": stage.target_exact,
      })
      commands["angular_update"] = (update,)
      stage_values["commands"] = commands
  ```
- Preserve `template_version` from existing stage plan during revision.

### Task 2.1 (Agent 2): Terminalize step and route failure

- `transformer_graph.py:_handle_prompt()`: At lines 346-351, replace `_block()` with:
  ```python
  else:
      step.status = "FAILED"
      step.completed_at = datetime.now(UTC)
      continuation.status = "queued"
      continuation.current_node = "classify_failure"
      continuation.last_error_code = execution.failure_code or "ANGULAR_UPDATE_FAILED"
      continuation.last_error_message = execution.failure_message or "Angular update failed without a governed prompt"
  ```

### Task 2.2 (Agent 2): Add angular_update failure detection

- `transformer_graph.py`: Add `_is_angular_update_failure(session, continuation) -> bool`:
  - Query `StageStepModel` for `angular_update-0` with `status == "FAILED"` in the current stage.

### Task 2.3 (Agent 2): Add checkpoint restoration

- `transformer_graph.py`: Add `_restore_angular_update_checkpoint(session, continuation)`:
  - Query `StageCheckpointModel` for `kind == "pre_angular_update"`, order by `sequence DESC`.
  - Call `self._stage.reconstruct_workspace(...)` with checkpoint path, workspace path, stage root, expected fingerprint.
  - Update binding fingerprint.
  - Return checkpoint id and new fingerprint.

### Task 2.4 (Agent 2): Route in classify_failure

- `transformer_graph.py:_classify_failure()`: Before standard validation logic, add:
  ```python
  if self._is_angular_update_failure(session, continuation):
      if route.value == "environment_transient" and continuation.attempt < continuation.max_attempts:
          # Persist changed-file ledger before restoration
          # Restore checkpoint, verify fingerprint
          self._restore_angular_update_checkpoint(session, continuation)
          continuation.attempt += 1
          # Route to superseding G07 or directly to angular_update
          continuation.current_node = "angular_update"
          continuation.status = "queued"
          ...
      elif route.value == "repairable_source":
          # Checkpoint restoration + repair flow
          ...
      else:
          self._block(...)
      return
  ```

### Task 2.5 (Agent 2): Superseding G07 routing

- `transformer_graph.py:advance()`: In `bootstrap_install` branch, check if `bootstrap_install-0` step is already PASSED. If yes, skip re-execution and route to `verify_bootstrap`.

### Task 2.6 (Agent 2): Duplicate attempt prevention

- No code change needed — `queue_retry_execution()` already enforces:
  - `ACTIVE_COMMAND_EXISTS` check (no pending/queued/running commands).
  - Partial unique index on `(run_id)` WHERE status IN ('queued','pending','running').

## Test Commands

### Agent 1 Tests

```powershell
# Template versioning and seeding
pytest -q backend/tests/test_command_registry_service.py::test_seed_defaults_creates_v1_and_v2_templates
pytest -q backend/tests/test_command_registry_service.py::test_find_registered_template_returns_correct_version
pytest -q backend/tests/test_command_registry_service.py::test_v2_template_omits_interactive_false
pytest -q backend/tests/test_command_registry_service.py::test_seed_defaults_is_idempotent_with_versions

# Planning transformation boundary
pytest -q backend/tests/test_planning_transformation_boundary.py::test_new_plan_uses_v2_template
pytest -q backend/tests/test_planning_transformation_boundary.py::test_planned_angular_update_matches_v2_template
pytest -q backend/tests/test_planning_transformation_boundary.py::test_rebuilt_plan_uses_catalogue_for_arguments
pytest -q backend/tests/test_planning_transformation_boundary.py::test_v1_plan_remains_immutable
pytest -q backend/tests/test_planning_transformation_boundary.py::test_old_g07_rejects_v2_argv

# Plan revision
pytest -q backend/tests/test_planning_review_application_service_s2_f07_i01.py
```

### Agent 2 Tests

```powershell
# Step terminalization
pytest -q backend/tests/test_command_terminal_lifecycle.py::test_angular_update_handle_prompt_marks_step_failed
pytest -q backend/tests/test_command_terminal_lifecycle.py::test_angular_update_handle_prompt_routes_to_classify_failure
pytest -q backend/tests/test_command_terminal_lifecycle.py::test_angular_update_handle_prompt_success_without_prompt_unchanged
pytest -q backend/tests/test_command_terminal_lifecycle.py::test_angular_update_handle_prompt_prompt_path_unchanged

# Checkpoint restoration
pytest -q backend/tests/test_transformer_graph.py::test_angular_update_checkpoint_restoration_success
pytest -q backend/tests/test_transformer_graph.py::test_angular_update_checkpoint_restoration_fingerprint_mismatch

# Vertical/integration
pytest -q backend/tests/test_transformer_bootstrap_vertical.py::test_angular_update_failure_routes_to_classify_in_vertical
```

### Combined Final

```powershell
pytest -q backend/tests/test_command_registry_service.py::test_seed_defaults_creates_v1_and_v2_templates backend/tests/test_command_registry_service.py::test_find_registered_template_returns_correct_version backend/tests/test_command_registry_service.py::test_v2_template_omits_interactive_false backend/tests/test_command_registry_service.py::test_seed_defaults_is_idempotent_with_versions backend/tests/test_planning_transformation_boundary.py::test_new_plan_uses_v2_template backend/tests/test_planning_transformation_boundary.py::test_planned_angular_update_matches_v2_template backend/tests/test_planning_transformation_boundary.py::test_rebuilt_plan_uses_catalogue_for_arguments backend/tests/test_planning_transformation_boundary.py::test_v1_plan_remains_immutable backend/tests/test_planning_transformation_boundary.py::test_old_g07_rejects_v2_argv backend/tests/test_command_terminal_lifecycle.py::test_angular_update_handle_prompt_marks_step_failed backend/tests/test_command_terminal_lifecycle.py::test_angular_update_handle_prompt_routes_to_classify_failure backend/tests/test_command_terminal_lifecycle.py::test_angular_update_handle_prompt_success_without_prompt_unchanged backend/tests/test_command_terminal_lifecycle.py::test_angular_update_handle_prompt_prompt_path_unchanged
```

## Integration Order

1. `fix/transformer-command-authority` (Agent 1) commits first.
2. `fix/transformer-command-routing` (Agent 2) commits second.
3. Cherry-pick Agent 1 → `fix/transformer-angular-update-supersession`.
4. Cherry-pick Agent 2 → `fix/transformer-angular-update-supersession`.

## Rollback/Recovery Invariants

- All changes are backward-compatible: v1 templates remain loadable.
- Existing in-flight runs with v1 plans continue to work (hardcoded `template_version=1` in existing plans means they'll find v1 in DB).
- No Alembic migration required (existing schema already supports multiple template versions).
- G07 checksum binding ensures old G07 cannot authorize v2 arguments.
- Step terminalization (`FAILED`) is safe — only applied on failure-without-prompt, which was previously a dead-end block.
- Checkpoint restoration is atomic (quarantine + replace). Fingerprint verification prevents data loss.
- Duplicate retry prevention is enforced at DB level (unique partial index) and service level (`ACTIVE_COMMAND_EXISTS` check).

## Explicitly Out of Scope

- No fresh migration run creation.
- No modification of live runtime database or artifacts.
- No restart of the current continuation.
- No workspace restoration in the current run.
- No superseding G07 package generation for the current run (manual procedure after code deploy).
- No modification of Planner prompts, schemas, reviewer logic, route generation, migration strategy, or plan semantics.
- No `--force`, `--allow-dirty`, `--legacy-peer-deps`, global `ng`, shell execution, manual lockfile editing, or source mutation.
- No speculative refactoring beyond the defined files.
- No full backend or frontend test suites.
- No network-dependent Angular CLI execution in ordinary tests.
