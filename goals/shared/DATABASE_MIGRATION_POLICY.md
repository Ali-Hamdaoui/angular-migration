# Database Migration Policy

Inspect the live Alembic head before creating a revision. A goal owns only schema needed by its Jira features. Migrations document existing-data behavior, unique/index/foreign-key constraints, SQLite behavior, downgrade support/limitations, and idempotency lineage.

Parallel branches may create independent heads. Record revision/down_revision and touched tables in `evidence/database-migration.json`. The integration coordinator explicitly merges heads and runs clean upgrade, existing-DB upgrade, downgrade where supported, and data-preservation tests. Never rewrite an integrated migration.
