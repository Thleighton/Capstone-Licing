"""Protege las tablas de Core cuando comparte proyecto con Supabase Auth."""
from alembic import op

revision = "b7e29c41a806"
down_revision = "83c9bcf6857f"
branch_labels = None
depends_on = None

TABLAS = ("raw_mercado_publico", "licitacion", "licitacion_item", "ejecucion_ingesta", "alembic_version")


def upgrade():
    # Sin políticas: las claves públicas no pueden leer/escribir filas de Core.
    # El propietario PostgreSQL que usa el backend conserva su acceso.
    for tabla in TABLAS:
        op.execute(f'ALTER TABLE public."{tabla}" ENABLE ROW LEVEL SECURITY')


def downgrade():
    for tabla in TABLAS:
        op.execute(f'ALTER TABLE public."{tabla}" DISABLE ROW LEVEL SECURITY')
