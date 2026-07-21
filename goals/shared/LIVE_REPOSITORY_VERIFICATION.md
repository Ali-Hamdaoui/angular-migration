# Live Repository Verification

The included inventory is generated directly from the uploaded source ZIP and excludes cache/bytecode. It is not proof of the VM branch.

At goal startup, re-run a live inventory/diff against the locked base SHA. Confirm exact symbols, current migrations/heads, current OpenAPI/event generation, frontend package scripts, test commands, and upstream Sprint 2 state. Record drift in the current-state gap map. Never overwrite newer VM code based on an older archive path or line number.
