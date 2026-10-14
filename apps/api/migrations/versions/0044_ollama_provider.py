"""Extend existing agency provider connections for Ollama."""
from alembic import op
import sqlalchemy as sa

revision = "0044_ollama_provider"
down_revision = "0043_agent_configuration"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("provider_credentials", sa.Column("name", sa.String(180), nullable=True))
    op.add_column("provider_credentials", sa.Column("base_url", sa.String(2048), nullable=True))
    op.add_column("provider_credentials", sa.Column("default_model", sa.String(180), nullable=True))


def downgrade():
    for column in ("default_model", "base_url", "name"):
        op.drop_column("provider_credentials", column)
