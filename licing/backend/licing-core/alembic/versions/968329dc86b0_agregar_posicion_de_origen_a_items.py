"""Agrega posición y última verificación conservando compatibilidad con el código anterior."""
from alembic import op
revision = "968329dc86b0"
down_revision = "c4f8a19d620e"
branch_labels = None
depends_on = None
SQL_UPGRADE = r"""SET LOCAL lock_timeout = '5s';
SELECT pg_advisory_xact_lock(728401);
ALTER TABLE public.licitacion_item ADD COLUMN posicion_fuente INTEGER;
UPDATE public.licitacion_item i SET posicion_fuente = x.posicion
FROM public.licitacion l
JOIN public.raw_mercado_publico r ON r.id=l.raw_id
CROSS JOIN LATERAL jsonb_array_elements(r.respuesta#>'{Items,Listado}')
  WITH ORDINALITY x(item,posicion)
WHERE i.licitacion_id=l.id AND i.posicion_fuente IS NULL
  AND x.item->>'Correlativo'=i.correlativo::text;
DO $check$ BEGIN
 IF EXISTS(SELECT 1 FROM public.licitacion_item WHERE posicion_fuente IS NULL)
 THEN RAISE EXCEPTION 'No se pudo recuperar la posición de todos los ítems desde su RAW'; END IF;
END $check$;
ALTER TABLE public.licitacion_item ADD CONSTRAINT uq_licitacion_item_posicion UNIQUE(licitacion_id,posicion_fuente);
ALTER TABLE public.licitacion_item ADD CONSTRAINT ck_item_posicion_positiva CHECK(posicion_fuente > 0);
ALTER TABLE public.raw_mercado_publico ADD COLUMN verificado_en TIMESTAMPTZ;
UPDATE public.raw_mercado_publico SET verificado_en=consultado_en;
ALTER TABLE public.raw_mercado_publico ALTER COLUMN verificado_en SET DEFAULT now();
ALTER TABLE public.raw_mercado_publico ALTER COLUMN verificado_en SET NOT NULL;
"""
def upgrade():
    op.execute(SQL_UPGRADE)
def downgrade():
    op.drop_column("raw_mercado_publico", "verificado_en")
    op.drop_constraint("uq_licitacion_item_posicion", "licitacion_item", type_="unique")
    op.drop_constraint("ck_item_posicion_positiva", "licitacion_item", type_="check")
    op.drop_column("licitacion_item", "posicion_fuente")

