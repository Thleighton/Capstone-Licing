"""Guarda evidencia geográfica sin reemplazar la región del comprador."""
from alembic import op

revision = "c08ccd7a1466"
down_revision = "5c7bbdaa3adf"
branch_labels = None
depends_on = None

SQL_UPGRADE = r"""
ALTER TABLE public.licitacion ADD COLUMN IF NOT EXISTS ubicacion_servicio JSONB;
DO $ddl$
BEGIN
 IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid='public.licitacion'::regclass
     AND conname='ck_licitacion_ubicacion_evidencia') THEN
 ALTER TABLE public.licitacion ADD CONSTRAINT ck_licitacion_ubicacion_evidencia CHECK (ubicacion_servicio IS NULL OR ((jsonb_typeof(ubicacion_servicio) = 'object'
     AND ubicacion_servicio->>'estado' IN ('por_revisar','no_informada')
     AND jsonb_typeof(ubicacion_servicio->'regiones_candidatas') = 'array'
     AND jsonb_typeof(ubicacion_servicio->'comunas_candidatas') = 'array'
     AND jsonb_typeof(ubicacion_servicio->'evidencias') = 'array'
     AND jsonb_typeof(ubicacion_servicio->'truncada') = 'boolean'
     AND jsonb_typeof(ubicacion_servicio->'raw_id') = 'number'
     AND jsonb_typeof(ubicacion_servicio->'version') = 'string') IS TRUE));
 END IF;
END;
$ddl$;
"""


def upgrade():
    op.execute(SQL_UPGRADE)


def downgrade():
    op.execute("ALTER TABLE public.licitacion DROP CONSTRAINT IF EXISTS ck_licitacion_ubicacion_evidencia")
    op.execute("ALTER TABLE public.licitacion DROP COLUMN ubicacion_servicio")
