"""Persist guided choices on the existing Agent; preserve legacy grants."""
from alembic import op
import sqlalchemy as sa
revision = "0045_agent_builder"
down_revision = "0044_ollama_provider"
branch_labels = None
depends_on = None


def upgrade():
    for name in ("selected_channels", "selected_tools", "shared_tool_ids"):
        op.add_column("agents", sa.Column(name, sa.JSON(), nullable=False, server_default="[]"))
    op.add_column("agents", sa.Column("tone", sa.String(30), nullable=False, server_default=""))
    op.add_column("agents", sa.Column("welcome_message", sa.Text(), nullable=False, server_default=""))
    op.add_column("agents", sa.Column("knowledge_enabled", sa.Boolean(), nullable=False, server_default=sa.true()))


def downgrade():
    for name in ("knowledge_enabled", "welcome_message", "tone", "shared_tool_ids", "selected_tools", "selected_channels"):
        op.drop_column("agents", name)
