# Controlled Dependency Change Design

## Goal

Allow a G10-approved repair to change `package.json`, regenerate the root npm
lockfile through the governed command path, verify that no other workspace
content changed, and continue to `npm-ci-final` with durable evidence.

This design applies only to newly generated stage plans and stage plans that
receive explicit G06 reapproval. It never adds command authority to an already
accepted immutable plan.

## Existing authority boundary

`CommandPolicyEngineService` authorizes only commands whose exact command,
template, arguments, workspace alias, runtime profile, network profile, and
timeout appear in the approved `StageExecutionPlan`. `CommandExecutorService`
then reconstructs execution exclusively from that authorization.

The preserved in-flight continuation is bound to an older G06-approved plan
that lacks lockfile-generation authority. `ensure_created_in_session()` does
not support rebinding an existing continuation to a different plan payload.
That continuation therefore remains blocked with
`STAGE_PLAN_COMMAND_AUTHORITY_MISSING`; its plan checksum, repair evidence, and
checkpoint lineage are not mutated.

## Planned command authority

Add a deterministic command definition and default registered template:

- group: `lockfile_generation`
- command ID: `npm-lockfile-generate`
- executable: `npm`
- arguments:
  - `install`
  - `--package-lock-only`
  - `--ignore-scripts`
  - `--no-audit`
  - `--no-fund`
- shell: `false`
- workspace: the stage plan's bound `STAGE_WORKSPACE_*` alias
- runtime: the stage's resolved execution profile and checksum
- network: the existing approved-registry network profile

Newly generated or explicitly reapproved stage plans include exactly one
reference in `commands.lockfile_generation`. Because the command reference is
part of the serialized plan, the existing plan checksum binds its complete
authority. No package name or version is supplied on the command line;
G10-approved `package.json` is the dependency authority.

No dependency-tree compatibility flags are added by default. A future stage
profile that requires one must bind the same flag explicitly into both
`lockfile_generation` and `final_install`; this design adds no implicit flag
propagation.

## Proposal contract

The proposer prompt states all of the following:

- every `package.json` change uses `proposal_format=operations`;
- its operation is `dependency_change`;
- `old_text` and `new_text` are required;
- ordinary operations and unified diffs cannot change `package.json`;
- lockfiles are never patched directly.

Semantic validation remains authoritative even if provider output violates the
prompt. It rejects:

- `dependency_change` outside root `package.json`;
- any other operation targeting root `package.json`;
- any unified diff touching root `package.json`;
- every direct `package-lock.json` or shrinkwrap patch;
- dependency changes when the accepted stage plan does not contain the exact
  registered `lockfile_generation` command, using
  `STAGE_PLAN_COMMAND_AUTHORITY_MISSING`.

The proposal binder continues to derive `preimage_sha256` from the bound stage
workspace. `dependency_change` is explicitly applied as one exact text
replacement; it is not handled by a generic unknown-operation fallback.

Proposer, Reviewer, and G10 creation remain read-only.

## Post-G10 orchestration

Ordinary repairs retain the existing path:

```text
G10 approval -> apply repair -> repair revalidation -> npm-ci-final
```

Approved dependency repairs use:

```text
G10 approval
  -> apply dependency_change to package.json
  -> lockfile_generation
  -> verify lockfile-generation evidence and workspace mutation scope
  -> repair revalidation
  -> npm-ci-final
```

The patch application service never starts npm. After applying an approved
dependency operation, the graph queues the checksum-bound
`lockfile_generation` command through `StageExecutionApplicationService`, which
uses `CommandPolicyEngineService` and `CommandExecutorService`. The continuation
waits for durable terminal command evidence before verification.

## Verification contract

Before queueing the command, persist on the command execution:

- approved post-patch `package.json` SHA-256;
- pre-command root `package-lock.json` SHA-256 or an explicit missing marker;
- a canonical workspace fingerprint excluding only root `package-lock.json`.

That exclusion is path-specific. Nested lockfiles, `node_modules`, source files,
configuration files, and every other workspace file remain covered.

After terminal execution, verification requires:

1. command status `succeeded` and exit code zero;
2. finalized command log, stdout, stderr, result, and manifest evidence as
   provided by the existing executor;
3. byte-identical `package.json` checksum;
4. an unchanged workspace-excluding-root-lockfile fingerprint;
5. an existing, UTF-8 JSON root `package-lock.json`;
6. a post-command lockfile checksum;
7. root dependency synchronization verified by the existing
   `PackageMetadataInspector` and `LockfilePrequalificationService`;
8. no blocker from lockfile parsing or dependency agreement.

Failure blocks the continuation and does not queue `npm-ci-final`. Unexpected
mutation uses a specific mutation error; package mutation, missing lockfile,
invalid lockfile, and unsynchronized lockfile retain distinct reasons.

On success, update the active workspace binding to the complete post-command
stage fingerprint and continue to repair revalidation. `npm-ci-final` remains a
separate checksum-bound command and runs afterward.

## Durable evidence

The existing command execution and authorization models persist:

- command ID, executable, argv, shell mode, and workspace alias;
- execution profile ID and resolved runtime checksum;
- authorization and execution correlation IDs;
- exit code and terminal status;
- stdout, stderr, command-log, result, and execution-manifest artifact IDs and
  checksums.

Add one immutable lockfile-generation verification artifact linked to the
execution and stage step. It contains only bounded authoritative metadata:

- execution and correlation IDs;
- stage-plan checksum;
- package checksum before and after;
- lockfile checksum before and after;
- workspace-excluding-lockfile fingerprint before and after;
- command artifact IDs and checksums;
- synchronization status and safe blocker codes.

No package contents, lockfile contents, source contents, prompts, or secrets are
included.

## Failure behavior

- `STAGE_PLAN_COMMAND_AUTHORITY_MISSING`: accepted plan lacks the exact command.
- `LOCKFILE_GENERATION_COMMAND_FAILED`: command did not complete successfully.
- `LOCKFILE_GENERATION_EVIDENCE_MISSING`: terminal command artifacts incomplete.
- `LOCKFILE_GENERATION_PACKAGE_MUTATED`: `package.json` changed during npm.
- `LOCKFILE_GENERATION_WORKSPACE_MUTATED`: anything except root lockfile changed.
- `LOCKFILE_GENERATION_OUTPUT_MISSING`: root `package-lock.json` absent.
- `LOCKFILE_GENERATION_OUTPUT_INVALID`: lockfile is not valid supported JSON.
- `LOCKFILE_GENERATION_UNSYNCHRONIZED`: root dependency agreement failed.

Every failure leaves `npm-ci-final` unqueued and preserves command output and
verification evidence available at the point of failure.

## Focused tests

Tests cover:

- generated plan contains the exact registered command and checksum binding;
- an older accepted plan remains immutable and blocks dependency proposals;
- unified diffs and ordinary operations cannot touch `package.json`;
- proposal, review, and G10 creation do not execute commands or mutate files;
- `dependency_change` applies one exact approved replacement;
- lockfile generation is queued only after G10-approved apply and before
  `npm-ci-final`;
- package mutation and unexpected workspace mutation are rejected;
- missing and invalid lockfiles are rejected;
- lockfile/package synchronization is required;
- successful verification records evidence and continues to
  `npm-ci-final` through repair revalidation.

Only focused tests for these boundaries are run; the full suite is outside this
change.

## Non-goals

- no in-place mutation of accepted plans;
- no automatic rebinding of existing continuations;
- no migration restart or preserved-database access;
- no direct lockfile patching;
- no shell execution;
- no package-specific command arguments;
- no frontend or database-schema changes;
- no general redesign of validation or stage execution.
