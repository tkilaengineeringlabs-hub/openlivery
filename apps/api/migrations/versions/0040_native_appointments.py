"""Native bookings, business timezone, availability and agent capability."""
from alembic import op
import sqlalchemy as sa

revision = "0040_native_appointments"
down_revision = "0039_native_automations"
branch_labels = None
depends_on = None


def scoped():
    return [sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("agency_id", sa.Uuid(), sa.ForeignKey("agencies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("client_id", sa.Uuid(), sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False)]


def col(name, kind, nullable=False):
    return sa.Column(name, kind, nullable=nullable)


def stamp(name, nullable=False):
    return col(name, sa.DateTime(timezone=True), nullable)


def upgrade():
    op.add_column("clients", sa.Column("timezone", sa.String(64), nullable=False, server_default="UTC"))
    op.add_column("clients", sa.Column("appointment_slot_minutes", sa.Integer(), nullable=False, server_default="15"))
    op.add_column("agents", sa.Column("appointments_enabled", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_table("appointment_services", *scoped(), col("name", sa.String(180)), col("description", sa.Text()),
        col("duration_minutes", sa.Integer()), col("buffer_before_minutes", sa.Integer()), col("buffer_after_minutes", sa.Integer()),
        col("active", sa.Boolean()), stamp("created_at"), stamp("updated_at"),
        sa.CheckConstraint("duration_minutes > 0 AND buffer_before_minutes >= 0 AND buffer_after_minutes >= 0", name="ck_appointment_service_duration"))
    op.create_table("availability_rules", *scoped(), col("weekday", sa.Integer()), col("start_time", sa.Time()),
        col("end_time", sa.Time()), col("active", sa.Boolean()),
        sa.CheckConstraint("weekday BETWEEN 0 AND 6 AND end_time > start_time", name="ck_availability_interval"))
    op.create_table("appointment_blocks", *scoped(), stamp("starts_at"), stamp("ends_at"),
        col("reason", sa.String(500)), stamp("created_at"), sa.CheckConstraint("ends_at > starts_at", name="ck_appointment_block_interval"))
    op.create_table("appointments", *scoped(),
        sa.Column("agent_id", sa.Uuid(), sa.ForeignKey("agents.id", ondelete="SET NULL")),
        sa.Column("conversation_id", sa.Uuid(), sa.ForeignKey("conversations.id", ondelete="SET NULL")),
        sa.Column("service_id", sa.Uuid(), sa.ForeignKey("appointment_services.id", ondelete="SET NULL")),
        col("service_name", sa.String(180)), col("customer_name", sa.String(180)), col("customer_phone", sa.String(40), True),
        col("customer_email", sa.String(255), True), stamp("starts_at"), stamp("ends_at"),
        stamp("reserved_starts_at"), stamp("reserved_ends_at"), col("timezone", sa.String(64)),
        col("status", sa.String(20)), col("source", sa.String(20)), col("notes", sa.Text()), col("revision", sa.Integer()),
        col("external_provider", sa.String(40), True), col("external_event_id", sa.String(255), True),
        stamp("created_at"), stamp("updated_at"), stamp("cancelled_at", True),
        sa.CheckConstraint("ends_at > starts_at AND reserved_starts_at <= starts_at AND reserved_ends_at >= ends_at", name="ck_appointment_interval"),
        sa.CheckConstraint("status IN ('scheduled','confirmed','completed','cancelled','no_show')", name="ck_appointment_status"))
    for table in ("appointment_services", "availability_rules", "appointment_blocks", "appointments"):
        for column in ("agency_id", "client_id"):
            op.create_index(f"ix_{table}_{column}", table, [column])
    op.create_index("ix_appointments_conversation_id", "appointments", ["conversation_id"])
    op.create_index("ix_appointments_calendar", "appointments", ["agency_id", "client_id", "starts_at"])


def downgrade():
    for table in ("appointments", "appointment_blocks", "availability_rules", "appointment_services"):
        op.drop_table(table)
    op.drop_column("agents", "appointments_enabled")
    op.drop_column("clients", "appointment_slot_minutes")
    op.drop_column("clients", "timezone")
