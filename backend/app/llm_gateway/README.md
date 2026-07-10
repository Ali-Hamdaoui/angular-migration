# LLM Gateway

Owns the Azure OpenAI gateway abstraction, mock request/response contracts,
secret redaction, untrusted-content boundaries, usage aggregation, budgets, and
pricing snapshots.

The gateway must not expose API keys, execute tools or commands, mutate
workspaces, trust repository content as policy, or let agents bypass backend
execution authority.