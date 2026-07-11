# Command Execution

Owns structured command validation, allowlisted execution, supervision,
timeouts, output limits, cancellation policy, and idempotent command records.

This is the only backend boundary that may start local processes. Callers submit
`CommandRequestDto` records with command ID, executable, argument array,
`shell=false`, working-directory alias, runtime profile, timeout, network
profile, cancellation policy, idempotency key, and requester metadata. The
worker rejects raw shell behavior, unapproved executables, unknown command IDs,
argument arrays that do not exactly match the registry, unknown aliases,
unknown runtime or network profiles, and unsupported cancellation policies.

Sprint 0's default command registry allows only safe version checks:

- `python-version`: `python --version`
- `node-version`: `node --version`
- `npm-version`: `npm --version`
- `npx-version`: `npx --version`
- `git-version`: `git --version`

The supervisor starts commands with `shell=False`, enforces the request timeout,
and terminates the process tree on timeout. Complete command records are written
as command-log artifacts. Bounded stdout and stderr streams are persisted as text
artifacts and referenced from the `CommandResultDto`. Duplicate `(run_id,
idempotency_key)` requests return the original recorded result without starting
a second process.
