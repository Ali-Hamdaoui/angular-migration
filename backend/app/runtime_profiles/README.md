# Runtime Profiles

Owns runtime-profile metadata, source-compatible toolchain placeholders, and
profile lookup contracts for structured command requests.

Runtime profiles must not install packages, execute commands, select arbitrary
shells, or silently change a run's approved toolchain after planning.

## V2.2 qualification inventory (P2-0)

QUALIFICATION mode exercises officially allowed, explicitly authorized runtime
tuples that are not yet certified. It never installs a runtime and never
promotes a profile by command success alone.

Required local/CI inventory per adjacent bridge (11-12 through 20-21):

- paired Node/npm/npx installations with exact versions recorded
- absolute executable paths and SHA-256 checksums for each descriptor
- the governed PATH value (checksum-bound) used for child-process resolution

Evidence retention: every qualification row persists its immutable
authorization, evidence bundle, reviewed promotion decision, and authoritative
certification artifact under
`04_workflow_state/stages/{stage_id}/runtime-qualification/` and
`04_workflow_state/stages/{stage_id}/runtime-certifications/`. Missing
inventory is explicit BLOCKED_RUNTIME evidence, never a PATH fallback.
