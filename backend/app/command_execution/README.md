# Command Execution

Owns structured command validation, allowlisted execution, supervision,
timeouts, output limits, cancellation policy, and idempotent command records.

This is the only backend boundary that may start local processes. It must reject
raw shell strings, unapproved executables, unknown working-directory aliases,
agent-direct requests, and network behavior outside the selected policy.