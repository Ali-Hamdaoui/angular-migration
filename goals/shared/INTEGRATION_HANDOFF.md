# Integration Handoff

Every branch supplies:

- `completion.json` and task results;
- `shared-file-changes.json`;
- database migration metadata;
- API/event/artifact additions;
- consumed/provided cross-goal contract versions;
- tests/manual evidence and limitations;
- branch/base/head SHAs.

The integration coordinator merges in dependency order, resolves central router/model/client/event/Alembic collisions, replaces boundary fakes with real adapters, regenerates aggregate contracts once, and runs cross-goal/runtime proof. Goal agents do not merge.
