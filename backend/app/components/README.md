# Components

Owns deterministic workflow components such as preflight checks, compatibility
resolution, snapshots, command request construction, static checks, checkpoints,
and delivery verification.

Components may request trusted services but must not call LLMs, execute commands
directly, import command-worker internals, or mutate source projects outside the
internal workspace boundary.