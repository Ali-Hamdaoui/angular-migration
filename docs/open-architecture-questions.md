# Open Architecture Questions

Track questions that are deliberately outside Sprint 0 or require team decisions.
Do not silently implement around them.

| ID | Question | Current Sprint 0 position | Trigger to revisit |
|---|---|---|---|
| OAQ-001 | What production RBAC model controls approvals? | Out of scope; approval identity is a contract field. | Before multi-user or production approval workflows. |
| OAQ-002 | When does the state store move from SQLite to PostgreSQL? | SQLite is single-host MVP only. | Multiple backend instances, distributed workers, or high write concurrency. |
| OAQ-003 | What runtime isolation mechanism is approved for real migrations? | Sprint 0 uses safe mock and version commands only. | Before arbitrary project commands or package installs. |
| OAQ-004 | What artifact retention and encryption policy is required? | Local filesystem artifacts are acceptable for Sprint 0. | Before production or sensitive repository usage. |
| OAQ-005 | Which company-approved browser, visual, security, and quality tools are allowed? | Excluded tools are manual or deferred gates. | Before claiming automated parity, security, or visual assurance. |
