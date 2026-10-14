"""Agent objective metadata and optional template origin; preserve legacy behavior."""
from alembic import op
import sqlalchemy as sa

revision = "0043_agent_configuration"
down_revision = "0042_automation_templates"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("agents", sa.Column("objectives", sa.JSON(), nullable=False, server_default="[]"))
    op.add_column("agents", sa.Column("template_id", sa.String(80), nullable=True))


def downgrade():
    op.drop_column("agents", "template_id")
    op.drop_column("agents", "objectives")
