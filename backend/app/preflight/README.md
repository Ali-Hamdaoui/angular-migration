# Preflight

Owns setup validation for source paths, output paths, runtime capabilities,
fixture topology, checksum-bound preflight results, and support classification.

Preflight checks must not mutate source projects, run `ng update`, install
packages, create migration workspaces, or mark a migration as started.