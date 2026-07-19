# Runtime Isolation

Each goal uses a unique external root:

```text
/home/ubuntu/amfa-runtime/<goal>/
├── database/amfa.db
├── artifacts/
├── logs/
├── temporary/
├── fixtures/
├── browser-profile/
├── playwright/
└── state/
```

Use the goal’s dedicated backend/frontend ports and a goal-prefixed LangGraph thread/checkpoint namespace. Never share SQLite, ports, artifacts, temp files, browser profile, Node cache, command ownership, or test output between sessions.

Generated full Angular fixtures must stay outside the Git worktree and enter the product through production intake APIs. The VM is Linux; Windows-specific acceptance must be identified honestly and cannot be inferred from Linux-only evidence.
