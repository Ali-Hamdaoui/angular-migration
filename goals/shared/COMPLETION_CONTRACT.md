# Completion Contract V3

## Normal goals G01–G09

A goal is `branch_ready` only when every branch-owned Jira task and criterion has planner/implementation/reviewer PASS evidence; conditional fix/re-review evidence exists for every failed first review; automated and manual validation pass; as-built documentation matches the final head; both final auditors pass; shared-file/database/contract changes are recorded; no blocker/critical/major finding remains; intended files are committed; and the worktree is clean.

Missing integrated upstream implementations must be represented honestly by frozen consuming ports/fakes and `blocked_integrated_criteria`; they do not become production fallbacks. `jira_complete` is true only when the Jira acceptance criteria have genuinely been exercised at the required scope.

## Goal 10

Goal 10 has two phases:

- **Phase A / `harness_ready`:** from base branch `goal`, implement and validate external fixture generators, acceptance-suite orchestration, evidence collection, safe subprocess/cancel/restart harnesses, and contract tests. The branch may be pushed. AMFA-225 remains incomplete; `jira_complete=false`, `integration_verified=false`, and integrated criteria are listed.
- **Phase B / `integration_verified`:** after G01–G09 and Sprint 2 prerequisites are integrated, run the complete production-API Angular 18.0.x and 18.2.x proof through 19/20/21, repair, environment blocker, cancellation, restart, final assurance, delivery, report, unchanged source, and human product sign-off. Only then set `jira_complete=true`.

All goals validate `evidence/completion.json` against `shared/contracts/goal_completion.schema.json` and record the V3 package checksum.
