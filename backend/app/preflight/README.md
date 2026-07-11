# Preflight

Owns setup validation for source paths, output paths, runtime capabilities,
fixture topology, checksum-bound preflight results, and support classification.

Preflight checks must not mutate source projects, run `ng update`, install
packages, create migration workspaces, or mark a migration as started.

## Sprint 0 Runtime Requirements

A runnable Sprint 0 preflight result requires:

- source and target paths that canonicalize inside configured allowed roots;
- source and target paths that are not equal and do not nest the delivery target inside the source tree;
- a writable existing parent for the target output path;
- available disk-space metadata from the target parent filesystem;
- structured worker success for `python --version`, `node --version`, `npm --version`, `npx --version`, and `git --version`;
- a non-expired checksum bound to source path, target path, target Angular family, migration mode, auto-approval policy, and the Sprint 0 preflight policy version.

Sprint 0 records registry, proxy, certificate, topology, and Angular eligibility as placeholders. Placeholder findings are warnings, not automatic blockers. Missing runtime tools and unsafe path relationships are blockers.
