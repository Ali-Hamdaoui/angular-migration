# Tests

This workspace contains cross-workspace and end-to-end validation suites.

Tests may exercise the backend, frontend, shared contracts, fixture applications,
and developer scripts. They must not execute real migrations, mutate arbitrary
user source projects, or bypass backend command authority. Fixture-bound tests
belong here when they validate behavior across workspace boundaries.