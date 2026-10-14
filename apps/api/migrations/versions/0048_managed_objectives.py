"""Objective configuration and stable managed rules; legacy rows remain custom."""
from alembic import op
import sqlalchemy as sa
revision = "0048_managed_objectives"
down_revision = "0047_agent_template_snapshots"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("agents", sa.Column("objectives_managed", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("agents", sa.Column("objective_config", sa.JSON(), nullable=False, server_default="{}"))
    op.add_column("conversations", sa.Column("lead_profile", sa.JSON(), nullable=False, server_default="{}"))
    op.add_column("conversations", sa.Column("lead_temperature", sa.String(20), nullable=True))
    for name, kind in (("managed_by", sa.String(30)), ("objective_id", sa.String(80)), ("rule_key", sa.String(80))):
        op.add_column("automations", sa.Column(name, kind, nullable=True))
    op.add_column("automations", sa.Column("agent_id", sa.Uuid(), sa.ForeignKey("agents.id", ondelete="CASCADE"), nullable=True))
    op.create_index("ix_automations_agent_id", "automations", ["agent_id"])
    op.create_unique_constraint("uq_managed_objective_rule", "automations", ["agent_id", "objective_id", "rule_key"])


def downgrade():
    op.drop_constraint("uq_managed_objective_rule", "automations", type_="unique")
    op.drop_index("ix_automations_agent_id", table_name="automations")
    for name in ("agent_id", "rule_key", "objective_id", "managed_by"):
        op.drop_column("automations", name)
    op.drop_column("conversations", "lead_temperature")
    op.drop_column("conversations", "lead_profile")
    op.drop_column("agents", "objective_config")
    op.drop_column("agents", "objectives_managed")
