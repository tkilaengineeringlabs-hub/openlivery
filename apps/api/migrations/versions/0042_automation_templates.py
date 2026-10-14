"""Optional template origin; execution continues to use the existing rule DSL."""
from alembic import op
import sqlalchemy as sa

revision = "0042_automation_templates"
down_revision = "0041_appointment_calendars"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("automations", sa.Column("template_id", sa.String(80), nullable=True))


def downgrade():
    op.drop_column("automations", "template_id")
