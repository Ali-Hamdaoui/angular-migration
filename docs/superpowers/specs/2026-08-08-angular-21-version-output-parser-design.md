# Angular 21 Version Output Parser Design

## Goal

Allow the existing four-source Angular version verifier to recognize Angular 21's padded `ng version` header labels without weakening any version or evidence checks.

## Proven failure

`AngularTransformationEvidenceService.build()` currently asks `_line_version()` to find the literal prefixes `Angular:` and `Angular CLI:`. Angular 20 emits those compact labels, while Angular 21 pads labels before the colon. A local reproduction against this checkout therefore raises `TARGET_VERSION_MISMATCH` with `cli.ng_version=missing, core.ng_version=missing` even when `package.json`, `package-lock.json`, installed package metadata, and the displayed CLI versions all agree on Angular 21.

The version command has already succeeded before `TransformerWorkflow._version_verify()` invokes this parser. The defect is post-command interpretation, not dependency installation or workflow execution.

## Selected approach

Keep the current human-readable command protocol and make only its label matcher whitespace-tolerant:

- Call `_line_version()` with semantic labels `Angular` and `Angular CLI`, excluding the colon.
- Escape each label and match it at the beginning of a line with optional leading whitespace and optional whitespace before a required colon: `^\s*<escaped label>\s*:`.
- Continue extracting the semantic version with the existing `_version()` helper.

The anchored, escaped pattern accepts both `Angular: 20.3.0` and `Angular           : 21.0.0`. Requiring the colon prevents partial-label matches, so the `Angular` matcher does not accept the `Angular CLI` line.

## Components and data flow

Only `backend/app/services/angular_transformation_evidence_service.py` changes in production. `TransformerWorkflow` continues concatenating persisted `angular-version-verify` log chunks and passes that text into `AngularTransformationEvidenceService.build()`. The service continues building the same core and CLI source maps, enforcing the same target-major and resolved-version agreement rules, and raising the same evidence errors for missing or inconsistent sources.

No command definitions, command registry entries, stage plans, continuation state, artifacts, gates, database models, or frontend contracts change.

## Error handling and safety

Malformed output, absent labels, labels without a colon, missing files, and version disagreements continue to fail closed through the existing errors. The repair does not accept `None`, remove the fourth evidence source, bypass G08, alter fingerprints, or mutate a blocked run.

## Test design

Add one regression test to `backend/tests/test_angular_transformation_evidence.py` that supplies coherent Angular 21 package sources plus padded Angular 21 CLI headers. Write and run this test before changing production code; it must fail with the current two missing `ng_version` sources. After the parser change, assert that verification succeeds and both parsed CLI-derived values equal `21.0.0`.

Then run:

- the complete Angular transformation evidence test file, proving compact and padded formats plus mismatch rejection;
- the directly affected Transformer bootstrap vertical test file, proving the surrounding G08 path remains intact;
- Ruff on the two changed Python files;
- Python bytecode compilation for the changed production module;
- `git diff --check` and a final diff/status review.

The known v2/v3 command-template test failures are pre-existing and outside this repair.

## Explicitly out of scope

- Switching `angular-version-verify` to `ng version --json`.
- Changing version exactness or compatibility catalogue policy.
- Reconciling v2/v3 command-template tests.
- Resolving the `--allow-dirty` policy contradiction.
- Adding new diagnostics or modifying failure classification.
- Restarting services or resuming `run-85c6be6f4382`; that run is absent from this machine's operational database.
