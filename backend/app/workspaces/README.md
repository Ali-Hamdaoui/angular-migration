# Workspaces

Owns internal run workspace layout and lifecycle under the migration factory
data directory.

Workspace mutation is allowed only for backend-controlled migration work. This
module must not mutate the original source, publish `migrated-app` directly, or
let paths overlap source, snapshots, artifacts, or delivery output.