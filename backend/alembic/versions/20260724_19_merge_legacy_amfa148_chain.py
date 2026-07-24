"""Merge the restored, previously shipped AMFA-148 branch with the current chain."""
from alembic import op

revision = "20260724_19"
down_revision = ("20260724_18", "20260724_20")
branch_labels = None
depends_on = None

def upgrade():
    pass

def downgrade():
    pass
