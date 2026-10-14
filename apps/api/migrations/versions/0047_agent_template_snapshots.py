"""Pin template origin metadata without changing existing agent configuration."""
from alembic import op
import sqlalchemy as sa

revision = "0047_agent_template_snapshots"
down_revision = "0046_tool_executions"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("agents", sa.Column("template_version", sa.Integer(), nullable=True))
    op.add_column("agents", sa.Column("template_snapshot", sa.JSON(), nullable=True))


def downgrade():
    op.drop_column("agents", "template_snapshot")
    op.drop_column("agents", "template_version")
