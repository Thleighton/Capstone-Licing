"""Eliminación física y transaccional de oportunidades no disponibles."""
from alembic import op

revision = "5c7bbdaa3adf"
down_revision = "b9a70e6d4a93"
branch_labels = None
depends_on = None

SQL_UPGRADE = r"""
CREATE OR REPLACE FUNCTION public.purgar_licitaciones_no_disponibles(
    p_codigo text DEFAULT NULL, p_confirmada boolean DEFAULT false
) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path = ''
AS $func$
DECLARE
    codigos text[] := ARRAY[]::text[];
    ids integer[] := ARRAY[]::integer[];
    crudo record;
    cierre text;
    vencido boolean;
    numero_licitaciones integer;
    numero_items integer;
    numero_raw integer;
BEGIN
    IF p_confirmada AND nullif(btrim(p_codigo), '') IS NULL THEN
        RAISE EXCEPTION 'La eliminación confirmada requiere un código.';
    END IF;
    SELECT coalesce(array_agg(l.id), ARRAY[]::integer[]),
           coalesce(array_agg(l.codigo_externo), ARRAY[]::text[])
      INTO ids, codigos
      FROM (
        SELECT id, codigo_externo FROM public.licitacion
        WHERE (p_codigo IS NULL OR codigo_externo = p_codigo)
          AND (p_confirmada
            OR fecha_cierre <= clock_timestamp() AT TIME ZONE 'America/Santiago'
            OR codigo_estado IN (6,7,8,18,19)
            OR (codigo_estado IS NULL AND lower(btrim(estado)) IN
                ('cerrada','desierta','adjudicada','revocada','suspendida')))
        ORDER BY id FOR UPDATE
      ) l;

    -- Usa el RAW más reciente únicamente cuando no hay una licitación vigente.
    FOR crudo IN
        SELECT DISTINCT ON (r.codigo_externo) r.codigo_externo, r.respuesta
        FROM public.raw_mercado_publico r
        WHERE r.fuente = 'licitaciones' AND r.codigo_externo IS NOT NULL
          AND (p_codigo IS NULL OR r.codigo_externo = p_codigo)
          AND NOT EXISTS (SELECT 1 FROM public.licitacion l
                          WHERE l.codigo_externo = r.codigo_externo)
        ORDER BY r.codigo_externo, r.id DESC
    LOOP
        vencido := p_confirmada
            OR coalesce(crudo.respuesta->>'CodigoEstado', '') IN ('6','7','8','18','19')
            OR (nullif(crudo.respuesta->>'CodigoEstado', '') IS NULL
                AND lower(btrim(crudo.respuesta->>'Estado')) IN
                    ('cerrada','desierta','adjudicada','revocada','suspendida'));
        cierre := coalesce(nullif(crudo.respuesta#>>'{Fechas,FechaCierre}', ''),
                           nullif(crudo.respuesta->>'FechaCierre', ''));
        BEGIN
            IF cierre ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}([T ][0-9]{2}:[0-9]{2}(:[0-9]{2}([.][0-9]+)?)?(Z|[+-][0-9]{2}:[0-9]{2})?)?$' THEN
                IF cierre ~ '(Z|[+-][0-9]{2}:[0-9]{2})$' THEN
                    vencido := coalesce(vencido, false) OR cierre::timestamptz <= clock_timestamp();
                ELSE
                    vencido := coalesce(vencido, false) OR
                        cierre::timestamp <= clock_timestamp() AT TIME ZONE 'America/Santiago';
                END IF;
            END IF;
        EXCEPTION WHEN invalid_datetime_format OR datetime_field_overflow THEN
            NULL;
        END;
        IF vencido THEN
            codigos := array_append(codigos, crudo.codigo_externo);
        END IF;
    END LOOP;

    DELETE FROM public.licitacion_periodo_servicio WHERE licitacion_id = ANY(ids);
    DELETE FROM public.licitacion_requisito WHERE licitacion_id = ANY(ids);
    DELETE FROM public.licitacion_prestacion WHERE licitacion_id = ANY(ids);
    DELETE FROM public.documento_fragmento WHERE extraccion_id IN
        (SELECT id FROM public.licitacion_extraccion WHERE licitacion_id = ANY(ids));
    DELETE FROM public.licitacion_extraccion WHERE licitacion_id = ANY(ids);
    DELETE FROM public.licitacion_documento WHERE licitacion_id = ANY(ids);
    DELETE FROM public.licitacion_item WHERE licitacion_id = ANY(ids);
    GET DIAGNOSTICS numero_items = ROW_COUNT;
    DELETE FROM public.licitacion WHERE id = ANY(ids);
    GET DIAGNOSTICS numero_licitaciones = ROW_COUNT;
    DELETE FROM public.raw_mercado_publico r
        WHERE r.fuente = 'licitaciones' AND r.codigo_externo = ANY(codigos)
          AND NOT EXISTS (SELECT 1 FROM public.licitacion l WHERE l.raw_id = r.id);
    GET DIAGNOSTICS numero_raw = ROW_COUNT;
    RETURN jsonb_build_object('licitaciones', numero_licitaciones,
                             'items', numero_items, 'raw', numero_raw);
END;
$func$;
REVOKE ALL ON FUNCTION public.purgar_licitaciones_no_disponibles(text, boolean)
    FROM PUBLIC, anon, authenticated;
"""


def upgrade():
    op.execute(SQL_UPGRADE)


def downgrade():
    # Los datos eliminados no se reconstruyen al desinstalar la función.
    op.execute("DROP FUNCTION public.purgar_licitaciones_no_disponibles(text, boolean)")
