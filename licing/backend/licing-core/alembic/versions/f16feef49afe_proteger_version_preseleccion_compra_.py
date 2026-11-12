"""proteger_version_preseleccion_compra_agil

Revision ID: f16feef49afe
Revises: a13c4d7e9f20
Create Date: 2026-11-11 21:29:38.651767

"""
from alembic import op


# revision identifiers, used by Alembic.
revision = 'f16feef49afe'
down_revision = 'a13c4d7e9f20'
branch_labels = None
depends_on = None

SQL_UPGRADE = r"""
CREATE OR REPLACE FUNCTION public.tg_compra_agil_version_preseleccion()
RETURNS trigger LANGUAGE plpgsql SECURITY INVOKER SET search_path = '' AS $func$
DECLARE
 motor_anterior integer;
 motor_nuevo integer;
 propia_anterior integer;
 propia_nueva integer;
 catalogo_anterior integer;
 catalogo_nuevo integer;
BEGIN
 IF NEW.preseleccion IS NULL OR OLD.preseleccion IS NULL OR NEW.raw_id IS DISTINCT FROM OLD.raw_id THEN
  RETURN NEW;
 END IF;
 motor_anterior := ((regexp_match(OLD.preseleccion->>'version','^reglas-hotel-([0-9]+)\|'))[1])::integer;
 motor_nuevo := ((regexp_match(NEW.preseleccion->>'version','^reglas-hotel-([0-9]+)\|'))[1])::integer;
 propia_anterior := coalesce(((regexp_match(OLD.preseleccion->>'version','\|ca-([0-9]+)\|'))[1])::integer,0);
 propia_nueva := coalesce(((regexp_match(NEW.preseleccion->>'version','\|ca-([0-9]+)\|'))[1])::integer,0);
 catalogo_anterior := ((regexp_match(OLD.preseleccion->>'version','-v([0-9]+)$'))[1])::integer;
 catalogo_nuevo := ((regexp_match(NEW.preseleccion->>'version','-v([0-9]+)$'))[1])::integer;
 IF motor_nuevo < motor_anterior OR (motor_nuevo=motor_anterior AND propia_nueva < propia_anterior)
    OR catalogo_nuevo < catalogo_anterior THEN
  NEW.preseleccion := OLD.preseleccion;
 END IF;
 RETURN NEW;
END;
$func$;
REVOKE ALL ON FUNCTION public.tg_compra_agil_version_preseleccion() FROM PUBLIC,anon,authenticated;
DROP TRIGGER IF EXISTS compra_agil_version_preseleccion ON public.compra_agil;
CREATE TRIGGER compra_agil_version_preseleccion
BEFORE UPDATE OF preseleccion ON public.compra_agil
FOR EACH ROW EXECUTE FUNCTION public.tg_compra_agil_version_preseleccion();
"""


def upgrade() -> None:
    op.execute(SQL_UPGRADE)


def downgrade() -> None:
    op.execute('DROP TRIGGER compra_agil_version_preseleccion ON public.compra_agil')
    op.execute('DROP FUNCTION public.tg_compra_agil_version_preseleccion()')
