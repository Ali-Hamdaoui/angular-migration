"""AMFA-185 database migration tests for transformation evidence schema.

Verifies:
- Clean database upgrades to the latest head revision
- Incremental migration from a specific base revision
- Column parity between the ORM model and the migrated database schema
"""

from pathlib import Path

import pytest
from sqlalchemy import inspect, create_engine
from alembic.config import Config
from alembic import command

BACKEND_DIR = Path(__file__).parent.parent


@pytest.fixture
def alembic_cfg(tmp_path):
    """Configure alembic to use a temporary SQLite database."""
    db_path = tmp_path / "test_migrations.db"
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    yield cfg


class TestEvidenceMigrations:
    def test_clean_database_upgrade_to_head(self, alembic_cfg, tmp_path):
        """A clean database should upgrade through all migrations without error."""
        command.upgrade(alembic_cfg, "head")

        db_path = tmp_path / "test_migrations.db"
        engine = create_engine(f"sqlite:///{db_path}")
        insp = inspect(engine)
        tables = set(insp.get_table_names())

        assert "transformation_evidence" in tables
        assert "angular_update_records" in tables
        assert "g08_approvals" in tables
        assert "migration_runs" in tables
        assert "migration_stages" in tables
        assert "command_executions" in tables
        assert "workflow_events" in tables
        assert "preflights" in tables
        assert "execution_profiles" in tables

        te_cols = {c["name"] for c in insp.get_columns("transformation_evidence")}
        for col in (
            "id", "run_id", "stage_id", "idempotency_key", "actor",
            "status", "overall_risk_level", "total_files_changed",
            "diff_checksum", "diff_summary", "evidence_complete",
            "artifact_ids", "state_version", "event_sequence",
            "correlation_id", "input_fingerprint", "target_fingerprint",
            "request_checksum", "gate_version",
            "source_sandbox_path", "target_sandbox_path",
            "evidence_schema_version", "angular_update_record_id",
            "angular_update_binding_checksum", "inventory_checksum",
            "builder_comparison", "risk_report", "artifact_manifest",
            "artifact_set_checksum", "integrity_status",
            "stale_reason", "failure_code",
            "computation_started_at", "computation_completed_at",
            "created_at", "updated_at",
        ):
            assert col in te_cols, f"Column {col!r} missing from transformation_evidence"

        engine.dispose()

    def test_migration_20260720_01_upgrade_to_head(self, alembic_cfg, tmp_path):
        """Upgrade from 20260719_07 base to head verifies AMFA-185 column additions."""
        command.upgrade(alembic_cfg, "20260719_07")

        db_path = tmp_path / "test_migrations.db"
        engine = create_engine(f"sqlite:///{db_path}")
        insp = inspect(engine)

        tables = set(insp.get_table_names())
        assert "transformation_evidence" in tables
        assert "angular_update_records" in tables

        te_cols = {c["name"] for c in insp.get_columns("transformation_evidence")}
        pre_upgrade_cols = {
            "correlation_id", "input_fingerprint", "target_fingerprint",
            "request_checksum", "gate_version",
            "source_sandbox_path", "target_sandbox_path",
            "evidence_schema_version", "angular_update_record_id",
            "angular_update_binding_checksum", "inventory_checksum",
            "builder_comparison", "risk_report", "artifact_manifest",
            "artifact_set_checksum", "integrity_status",
            "stale_reason", "failure_code",
            "computation_started_at", "computation_completed_at",
        }
        absent = pre_upgrade_cols & te_cols
        if absent:
            pytest.fail(f"Columns already exist before upgrade: {sorted(absent)}")
        engine.dispose()

        command.upgrade(alembic_cfg, "head")

        engine2 = create_engine(f"sqlite:///{db_path}")
        insp2 = inspect(engine2)
        te_cols_after = {c["name"] for c in insp2.get_columns("transformation_evidence")}
        missing = pre_upgrade_cols - te_cols_after
        if missing:
            pytest.fail(f"AMFA-185 columns missing after upgrade: {sorted(missing)}")

        engine2.dispose()

    def test_model_migration_column_parity(self, alembic_cfg, tmp_path):
        """Every ORM model column has a matching column in the migrated database."""
        command.upgrade(alembic_cfg, "head")

        from app.repositories.transformation_models import TransformationEvidenceModel

        db_path = tmp_path / "test_migrations.db"
        engine = create_engine(f"sqlite:///{db_path}")
        insp = inspect(engine)
        db_cols = {c["name"]: c for c in insp.get_columns("transformation_evidence")}

        model_cols = TransformationEvidenceModel.__table__.columns
        model_lookup = {c.name: c for c in model_cols}

        model_only = set(model_lookup) - set(db_cols)
        if model_only:
            pytest.fail(f"Model columns missing from database: {sorted(model_only)}")

        db_only = set(db_cols) - set(model_lookup)
        if db_only:
            pytest.fail(f"Database columns missing from model: {sorted(db_only)}")

        for name, model_col in model_lookup.items():
            db_col = db_cols[name]
            if model_col.nullable is not None:
                if db_col["nullable"] != model_col.nullable:
                    pytest.fail(
                        f"Column {name!r} nullable mismatch: "
                        f"DB={db_col['nullable']} Model={model_col.nullable}"
                    )

        engine.dispose()
