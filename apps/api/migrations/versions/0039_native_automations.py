"""Native automation definitions, execution history and durable actions."""
from alembic import op
import sqlalchemy as sa

revision = "0039_native_automations"
down_revision = "0038_whatsapp_coexistence"
branch_labels = None
depends_on = None


def agency():
    return sa.Column("agency_id", sa.Uuid(), sa.ForeignKey("agencies.id", ondelete="CASCADE"), nullable=False)


def automation():
    return sa.Column("automation_id", sa.Uuid(), sa.ForeignKey("automations.id", ondelete="CASCADE"), nullable=False)


def stamp(name, nullable=False):
    return sa.Column(name, sa.DateTime(timezone=True), nullable=nullable)


def upgrade():
    op.create_table("automations",
        sa.Column("id", sa.Uuid(), primary_key=True), agency(),
        sa.Column("client_id", sa.Uuid(), sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=True),
        sa.Column("name", sa.String(180), nullable=False), sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False), sa.Column("trigger_type", sa.String(40), nullable=False),
        sa.Column("trigger_config", sa.JSON(), nullable=False), sa.Column("conditions", sa.JSON(), nullable=False),
        sa.Column("actions", sa.JSON(), nullable=False), stamp("created_at"), stamp("updated_at"))
    op.create_table("automation_runs",
        sa.Column("id", sa.Uuid(), primary_key=True), agency(), automation(),
        sa.Column("revision", sa.Integer(), nullable=False), sa.Column("event_key", sa.String(180), nullable=False),
        sa.Column("event_type", sa.String(40), nullable=False), sa.Column("event_payload", sa.JSON(), nullable=False),
        sa.Column("actions", sa.JSON(), nullable=False), sa.Column("status", sa.String(20), nullable=False),
        sa.Column("actions_executed", sa.Integer(), nullable=False), stamp("started_at"), stamp("completed_at", True),
        sa.Column("error", sa.Text(), nullable=True), sa.UniqueConstraint("automation_id", "event_key", name="uq_automation_event"))
    op.create_table("scheduled_automation_actions",
        sa.Column("id", sa.Uuid(), primary_key=True), agency(), automation(),
        sa.Column("automation_run_id", sa.Uuid(), sa.ForeignKey("automation_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("action_index", sa.Integer(), nullable=False), sa.Column("action", sa.JSON(), nullable=False),
        stamp("execute_at"), sa.Column("status", sa.String(20), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False), stamp("locked_until", True),
        sa.Column("last_error", sa.Text(), nullable=True), stamp("created_at"), stamp("completed_at", True),
        sa.UniqueConstraint("automation_run_id", "action_index", name="uq_automation_run_action"))
    for table, columns in {"automations": ("agency_id", "client_id"),
        "automation_runs": ("agency_id", "automation_id"),
        "scheduled_automation_actions": ("agency_id", "automation_id", "automation_run_id")}.items():
        for column in columns:
            op.create_index(f"ix_{table}_{column}", table, [column])
    op.create_index("ix_automation_actions_due", "scheduled_automation_actions", ["status", "execute_at"])


def downgrade():
    op.drop_table("scheduled_automation_actions")
    op.drop_table("automation_runs")
    op.drop_table("automations")
