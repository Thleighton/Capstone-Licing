"""Admite correlativos repetidos de la fuente; ejecutar después de desplegar el nuevo escritor."""
from alembic import op
revision = "b9a70e6d4a93"
down_revision = "968329dc86b0"
branch_labels = None
depends_on = None
SQL_UPGRADE = r"""SET LOCAL lock_timeout = '5s';
SELECT pg_advisory_xact_lock(728401);
UPDATE public.licitacion_item i SET posicion_fuente = x.posicion
FROM public.licitacion l
JOIN public.raw_mercado_publico r ON r.id=l.raw_id
CROSS JOIN LATERAL jsonb_array_elements(r.respuesta#>'{Items,Listado}')
  WITH ORDINALITY x(item,posicion)
WHERE i.licitacion_id=l.id AND i.posicion_fuente IS NULL
  AND x.item->>'Correlativo'=i.correlativo::text;
ALTER TABLE public.licitacion_item ALTER COLUMN posicion_fuente SET NOT NULL;
ALTER TABLE public.licitacion_item DROP CONSTRAINT uq_licitacion_item_correlativo;
"""
def upgrade():
    op.execute(SQL_UPGRADE)
def downgrade():
    # PostgreSQL rechazará recrear la unicidad si ya hay duplicados. No se borra
    # ni renumera información para forzar un retroceso incompatible.
    op.create_unique_constraint("uq_licitacion_item_correlativo", "licitacion_item", ["licitacion_id","correlativo"])
    op.alter_column("licitacion_item", "posicion_fuente", nullable=True)

