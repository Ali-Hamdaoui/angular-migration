# Task 2 Report: backend repair authority binding

Implemented on base `297a124eb26b7bd222bd2cd35b027dd914b6fff5` as commit `6aa63819b525b24a597248a76dd36fbeedde58c8`.

The service now injects evidence/context checksums from backend attempt context, normalizes paths, derives operation preimages from the workspace, derives operation/unified-diff touched files, allowlists `build`/`test`/`lint` validation targets, binds review to the immutable active proposal checksum, preserves v1 persisted artifacts, adds attempt lineage to artifact envelopes, and links failure artifacts to invocation evidence. No stale-state or concurrency behavior was changed.

TDD evidence: the initial binding selectors failed on noncanonical paths and unknown targets; an immutable active-proposal mutation also failed before the fix. The final exact focused run passed `20 passed in 19.11s` (staged-tree rerun `20 passed in 20.82s`). Ruff and `py_compile` passed on changed Python files. No services, Azure, migration, preserved-run action, frontend edit, or full suite was performed.

## Task 2 fix round 1

The review-found failure-link regression is covered by `test_failed_replay_retains_all_immutable_failure_artifact_links`; `_persist_failure` now preserves prior invocation artifact IDs and checksums while deduplicating IDs. The unified-diff binder now consumes paired `---`/`+++` headers together, validates every non-`/dev/null` path through `_safe_path`, and rejects unpaired header lines. The pre-existing test additions also cover forbidden old-header paths, malformed header-only diffs, canonical touched files, and the no-success-artifact path.

TDD evidence: the focused pre-fix run was red with 2 failures in valid unified-diff binding. The post-fix Task 2 run passed `13 passed, 25 deselected in 11.33s`; the narrower regression run passed `8 passed, 29 deselected in 6.24s`. Ruff and `py_compile` passed. No frontend, preserved-run, stale-state, concurrency, service, Azure, migration, or full-suite action was performed.
