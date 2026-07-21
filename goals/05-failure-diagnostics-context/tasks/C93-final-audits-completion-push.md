# Final Audits, Completion, and Push

Run the two independent final auditors concurrently, fix/revalidate major findings, validate completion evidence, commit, and push only the assigned branch when branch_ready is true.

Follow root `AGENTS.md` and shared completion standards.

## V3 completion semantics

- Validate against `goal_completion.schema.json` V3 and record the goal-package SHA-256.
- Record human product sign-off separately from agent manual validation.
- Normal goals use honest `branch_ready`/`integration_verified` fields.
- Goal 10 Phase A uses `completion_level=harness_ready`, `jira_complete=false`; only integrated Phase B may set `jira_complete=true`.
