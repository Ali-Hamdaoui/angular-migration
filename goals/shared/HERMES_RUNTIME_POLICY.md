# Hermes Runtime Policy

Use Hermes local terminal backend for the ten-session VM workflow. A shared persistent container backend is not accepted because parallel sessions/subagents could share mutable container cwd/environment/filesystem state. Never use unrestricted `--yolo` mode.

Each parent session records a unique session identity under its external runtime root. Delegation is bounded to two concurrent children, depth one, no delegated orchestrator, and 1800-second child timeout. `goals.max_turns` controls persistent `/goal` budget; `agent.max_turns` controls normal agent execution.

If stronger OS isolation is required later, provision one independent container/VM per parent session outside Hermes and retain one worktree/runtime root per session.
