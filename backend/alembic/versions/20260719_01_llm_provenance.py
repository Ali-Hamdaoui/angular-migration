"""Complete governed LLM invocation provenance."""
from alembic import op
import sqlalchemy as sa
revision = "20260719_01"
down_revision = "20260718_03"
branch_labels = None
depends_on = None
def upgrade():
    op.add_column("llm_invocations", sa.Column("input_hashes", sa.JSON(), nullable=False, server_default="[]"))
    op.add_column("llm_invocations", sa.Column("pricing_version", sa.String(128), nullable=False, server_default="unknown"))
    op.add_column("llm_invocations", sa.Column("stage", sa.String(128)))
    op.add_column("llm_invocations", sa.Column("redacted_summary", sa.Text()))
def downgrade():
    op.drop_column("llm_invocations", "redacted_summary")
    op.drop_column("llm_invocations", "stage")
    op.drop_column("llm_invocations", "pricing_version")
    op.drop_column("llm_invocations", "input_hashes")
