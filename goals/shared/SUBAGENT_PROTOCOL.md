# Subagent Protocol V3

Every Jira task has three mandatory runs and a conditional correction loop:

1. **Planner (read-only):** inspect the live branch and produce exact reuse/gap/file/test/risk/acceptance mapping.
2. **Implementer (sole writer):** implement only the approved bounded task and tests.
3. **Strict reviewer (read-only and independent):** return `PASS`, `FAIL`, or `BLOCKED` with criterion IDs and file/line evidence.
4. **Fixer (conditional):** run only after reviewer `FAIL`; apply only approved findings.
5. **Re-reviewer (conditional):** run only after fixes; repeat until `PASS` or structured blocker.

A first-pass reviewer `PASS` ends the task cycle; do not waste a fixer/re-review run. Reviewer and implementer must be distinct subagent invocations. The reviewer never edits code. One writer is active in a worktree at a time.

## Mandatory context pack

The parent passes goal/task/Jira IDs, worktree path, branch and locked base SHA, root rules, exact task contract, relevant frozen schemas, owned/shared/forbidden files, current-state findings, acceptance IDs, required commands, and output schema. Delegated agents do not inherit the parent conversation.

## Final auditors

After automated/manual green and as-built documentation, run two read-only final auditors concurrently: architecture/contract/security and runtime/product/frontend/documentation. Any blocker, critical, or major finding returns to correction and revalidation.
