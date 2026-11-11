"""Cachea solo el resumen compacto de Gemini, nunca el texto completo enviado."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "a13c4d7e9f20"
down_revision = "e3a17c52d9b4"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("licitacion", sa.Column("resumen_ia", postgresql.JSONB(), nullable=True))
    op.add_column("compra_agil", sa.Column("resumen_ia", postgresql.JSONB(), nullable=True))


def downgrade():
    op.drop_column("compra_agil", "resumen_ia")
    op.drop_column("licitacion", "resumen_ia")
