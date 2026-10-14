"""Client calendar credentials and durable appointment synchronization state."""
from alembic import op
import sqlalchemy as sa

revision = "0041_appointment_calendars"
down_revision = "0040_native_appointments"
branch_labels = None
depends_on = None


def upgrade():
    for name, kind, default in [("appointment_min_notice_minutes", sa.Integer(), "0"),
                                ("appointment_booking_days", sa.Integer(), "365"),
                                ("appointment_reminders", sa.JSON(), "[]")]:
        op.add_column("clients", sa.Column(name, kind, nullable=False, server_default=default))
    op.add_column("appointment_services", sa.Column("price", sa.String(32)))
    op.add_column("appointment_services", sa.Column("color", sa.String(7)))
    for name, kind in [("external_calendar_id", sa.String(1024)), ("calendar_sync_error", sa.String(80)),
                       ("calendar_retry_at", sa.DateTime(timezone=True)), ("calendar_synced_at", sa.DateTime(timezone=True))]:
        op.add_column("appointments", sa.Column(name, kind))
    op.add_column("appointments", sa.Column("calendar_sync_status", sa.String(20), nullable=False, server_default="not_connected"))
    op.add_column("appointments", sa.Column("calendar_sync_attempts", sa.Integer(), nullable=False, server_default="0"))
    op.create_table("appointment_calendars",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("agency_id", sa.Uuid(), sa.ForeignKey("agencies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("client_id", sa.Uuid(), sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("encrypted_tokens", sa.Text()), sa.Column("account_email", sa.String(320)),
        sa.Column("calendar_id", sa.String(1024)), sa.Column("calendar_name", sa.String(255)),
        sa.Column("connected", sa.Boolean(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_appointment_calendars_agency_id", "appointment_calendars", ["agency_id"])
    op.create_table("appointment_calendar_oauth",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("agency_id", sa.Uuid(), sa.ForeignKey("agencies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("client_id", sa.Uuid(), sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("encrypted_verifier", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False))


def downgrade():
    op.drop_table("appointment_calendar_oauth")
    op.drop_table("appointment_calendars")
    for name in ("external_calendar_id", "calendar_sync_error", "calendar_retry_at", "calendar_synced_at", "calendar_sync_status", "calendar_sync_attempts"):
        op.drop_column("appointments", name)
    for name in ("price", "color"):
        op.drop_column("appointment_services", name)
    for name in ("appointment_min_notice_minutes", "appointment_booking_days", "appointment_reminders"):
        op.drop_column("clients", name)
