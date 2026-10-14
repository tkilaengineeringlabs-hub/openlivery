"""Durable scoped tool execution audit."""
from alembic import op
import sqlalchemy as sa
revision = "0046_tool_executions"
down_revision = "0045_agent_builder"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("tool_executions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        *[sa.Column(name, sa.Uuid(), sa.ForeignKey(target + ".id", ondelete="CASCADE"), nullable=nullable)
          for name, target, nullable in [("agency_id", "agencies", False), ("client_id", "clients", False), ("agent_id", "agents", False), ("conversation_id", "conversations", True)]],
        sa.Column("provider", sa.String(30), nullable=False), sa.Column("model", sa.String(180), nullable=False),
        sa.Column("channel", sa.String(30)), sa.Column("tool_name", sa.String(64), nullable=False),
        sa.Column("status", sa.String(20), nullable=False), sa.Column("arguments", sa.JSON(), nullable=False),
        sa.Column("result_summary", sa.Text(), nullable=False), sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("finished_at", sa.DateTime(timezone=True)))
    for name in ("agency_id", "client_id", "agent_id", "conversation_id"):
        op.create_index("ix_tool_executions_" + name, "tool_executions", [name])


def downgrade():
    op.drop_table("tool_executions")
