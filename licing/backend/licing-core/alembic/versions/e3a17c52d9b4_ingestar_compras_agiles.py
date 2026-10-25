"""Ingesta de Compra Ágil (API v2), limpieza de las no disponibles y registro de preselección."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "e3a17c52d9b4"
down_revision = "b5df9fcc5f0d"
branch_labels = None
depends_on = None

TABLAS = ("compra_agil", "compra_agil_item", "compra_agil_pendiente", "compra_agil_sincronizacion")

SQL_FUNCION = r"""
CREATE OR REPLACE FUNCTION public.purgar_compras_agiles_no_disponibles(
    p_codigos text[] DEFAULT NULL, p_confirmada boolean DEFAULT false
) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path = ''
AS $func$
DECLARE
    ahora timestamp := clock_timestamp() AT TIME ZONE 'America/Santiago';
    codigos text[];
    crudo record;
    cierre text;
    vencida boolean;
    numero_compras integer;
    numero_items integer;
    numero_pendientes integer;
    numero_raw integer;
BEGIN
    IF p_confirmada AND coalesce(cardinality(p_codigos), 0) = 0 THEN
        RAISE EXCEPTION 'La eliminación confirmada requiere códigos.';
    END IF;
    SELECT coalesce(array_agg(c.codigo_externo), ARRAY[]::text[]) INTO codigos
      FROM (
        SELECT codigo_externo FROM public.compra_agil
        WHERE (p_codigos IS NULL OR codigo_externo = ANY(p_codigos))
          AND (p_confirmada OR fecha_cierre <= ahora OR lower(btrim(estado)) <> 'publicada')
        ORDER BY id FOR UPDATE
      ) c;

    -- RAW sin compra normalizada: decide su versión más reciente. Un estado o una
    -- fecha desconocidos no prueban que la compra haya dejado de estar disponible.
    FOR crudo IN
        SELECT DISTINCT ON (r.codigo_externo) r.codigo_externo, r.respuesta
        FROM public.raw_mercado_publico r
        WHERE r.fuente = 'compra_agil' AND r.codigo_externo IS NOT NULL
          AND (p_codigos IS NULL OR r.codigo_externo = ANY(p_codigos))
          AND NOT EXISTS (SELECT 1 FROM public.compra_agil c WHERE c.codigo_externo = r.codigo_externo)
        ORDER BY r.codigo_externo, r.id DESC
    LOOP
        vencida := p_confirmada OR lower(btrim(crudo.respuesta#>>'{estado,codigo}')) <> 'publicada';
        -- La API entrega hora de Chile, aunque algunos campos terminen en Z.
        cierre := substring(crudo.respuesta#>>'{fechas,fecha_cierre}'
                            FROM '^[0-9]{4}-[0-9]{2}-[0-9]{2}[T ][0-9]{2}:[0-9]{2}');
        BEGIN
            vencida := coalesce(vencida, false)
                OR coalesce(replace(cierre, 'T', ' ')::timestamp <= ahora, false);
        EXCEPTION WHEN invalid_datetime_format OR datetime_field_overflow THEN
            vencida := coalesce(vencida, false);
        END;
        IF vencida THEN
            codigos := array_append(codigos, crudo.codigo_externo);
        END IF;
    END LOOP;

    DELETE FROM public.compra_agil_pendiente
    WHERE (p_codigos IS NULL OR codigo_externo = ANY(p_codigos))
      AND (p_confirmada OR fecha_cierre <= ahora);
    GET DIAGNOSTICS numero_pendientes = ROW_COUNT;
    DELETE FROM public.compra_agil_item WHERE compra_agil_id IN
        (SELECT id FROM public.compra_agil WHERE codigo_externo = ANY(codigos));
    GET DIAGNOSTICS numero_items = ROW_COUNT;
    DELETE FROM public.compra_agil WHERE codigo_externo = ANY(codigos);
    GET DIAGNOSTICS numero_compras = ROW_COUNT;
    DELETE FROM public.raw_mercado_publico r
        WHERE r.fuente = 'compra_agil' AND r.codigo_externo = ANY(codigos)
          AND NOT EXISTS (SELECT 1 FROM public.compra_agil c WHERE c.raw_id = r.id);
    GET DIAGNOSTICS numero_raw = ROW_COUNT;
    RETURN jsonb_build_object('compras', numero_compras, 'items', numero_items,
                              'pendientes', numero_pendientes, 'raw', numero_raw);
END;
$func$;
REVOKE ALL ON FUNCTION public.purgar_compras_agiles_no_disponibles(text[], boolean)
    FROM PUBLIC, anon, authenticated;
"""


def upgrade():
    op.execute("""DO $$ BEGIN
      IF to_regclass('public.raw_mercado_publico') IS NULL THEN
        RAISE EXCEPTION 'Esta migración corresponde a Usuarios/Licitaciones';
      END IF;
    END $$;""")
    op.add_column("ejecucion_ingesta", sa.Column(
        "fuente", sa.String(length=30), server_default=sa.text("'licitaciones'"), nullable=False,
    ))
    op.create_check_constraint(
        "ck_ejecucion_ingesta_fuente", "ejecucion_ingesta", "fuente IN ('licitaciones', 'compra_agil')",
    )

    op.create_table(
        "compra_agil",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("codigo_externo", sa.String(length=50), nullable=False),
        sa.Column("raw_id", sa.Integer(), nullable=False),
        sa.Column("nombre", sa.Text(), nullable=True),
        sa.Column("descripcion", sa.Text(), nullable=True),
        sa.Column("id_estado", sa.Integer(), nullable=True),
        sa.Column("estado", sa.String(length=50), nullable=True),
        sa.Column("estado_glosa", sa.Text(), nullable=True),
        sa.Column("estado_convocatoria", sa.Integer(), nullable=True),
        sa.Column("fecha_publicacion", sa.DateTime(), nullable=True),
        sa.Column("fecha_cierre", sa.DateTime(), nullable=True),
        sa.Column("fecha_ultimo_cambio", sa.DateTime(), nullable=True),
        sa.Column("fecha_cancelacion", sa.DateTime(), nullable=True),
        sa.Column("moneda", sa.String(length=20), nullable=True),
        sa.Column("tipo_presupuesto", sa.String(length=30), nullable=True),
        sa.Column("presupuesto_estimado", sa.Numeric(), nullable=True),
        sa.Column("monto_disponible", sa.Numeric(), nullable=True),
        sa.Column("monto_disponible_clp", sa.Numeric(), nullable=True),
        sa.Column("rut_organismo", sa.String(length=20), nullable=True),
        sa.Column("nombre_organismo", sa.Text(), nullable=True),
        sa.Column("nombre_unidad", sa.Text(), nullable=True),
        sa.Column("codigo_region", sa.Integer(), nullable=True),
        sa.Column("region_comprador", sa.Text(), nullable=True),
        sa.Column("direccion_entrega", sa.Text(), nullable=True),
        sa.Column("plazo_entrega_dias", sa.Integer(), nullable=True),
        sa.Column("total_ofertas_recibidas", sa.Integer(), nullable=True),
        sa.Column("id_orden_compra", sa.BigInteger(), nullable=True),
        sa.Column("documentos", postgresql.JSONB(astext_type=sa.Text()),
                  server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("fechas_fuente", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("condiciones_fuente", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("normalizacion_version", sa.String(length=30), nullable=True),
        sa.Column("normalizado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cambio_sincronizado", sa.DateTime(), nullable=True),
        sa.Column("preseleccion", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(["raw_id"], ["raw_mercado_publico.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("codigo_externo"),
    )
    op.create_index(op.f("ix_compra_agil_raw_id"), "compra_agil", ["raw_id"], unique=False)

    op.create_table(
        "compra_agil_item",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("compra_agil_id", sa.Integer(), nullable=False),
        sa.Column("posicion_fuente", sa.Integer(), nullable=False),
        sa.Column("codigo_producto", sa.String(length=50), nullable=True),
        sa.Column("nombre_producto", sa.Text(), nullable=True),
        sa.Column("descripcion", sa.Text(), nullable=True),
        sa.Column("cantidad", sa.Numeric(), nullable=True),
        sa.Column("unidad_medida", sa.Text(), nullable=True),
        sa.CheckConstraint("posicion_fuente > 0", name="ck_compra_agil_item_posicion_positiva"),
        sa.ForeignKeyConstraint(["compra_agil_id"], ["compra_agil.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("compra_agil_id", "posicion_fuente", name="uq_compra_agil_item_posicion"),
    )
    op.create_index(op.f("ix_compra_agil_item_compra_agil_id"), "compra_agil_item", ["compra_agil_id"], unique=False)
    op.create_index(op.f("ix_compra_agil_item_codigo_producto"), "compra_agil_item", ["codigo_producto"], unique=False)

    op.create_table(
        "compra_agil_pendiente",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("codigo_externo", sa.String(length=50), nullable=False),
        sa.Column("cambio", sa.DateTime(), nullable=False),
        sa.Column("fecha_publicacion", sa.DateTime(), nullable=True),
        sa.Column("fecha_cierre", sa.DateTime(), nullable=True),
        sa.Column("detectado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("intentos", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("reintentar_desde", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ultimo_error", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("codigo_externo"),
    )
    op.create_index(op.f("ix_compra_agil_pendiente_fecha_cierre"), "compra_agil_pendiente", ["fecha_cierre"], unique=False)

    op.create_table(
        "compra_agil_sincronizacion",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("cursor", sa.DateTime(), nullable=True),
        sa.Column("ventana_desde", sa.DateTime(), nullable=True),
        sa.Column("ventana_hasta", sa.DateTime(), nullable=True),
        sa.Column("ventana_estados", sa.String(length=100), nullable=True),
        sa.Column("pagina", sa.Integer(), nullable=True),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("id = 1", name="ck_compra_agil_sincronizacion_unica"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.execute("INSERT INTO public.compra_agil_sincronizacion (id) VALUES (1)")

    # Igual que el resto de Core: sin políticas, la Data API no lee ni escribe filas.
    for tabla in TABLAS:
        op.execute(f"ALTER TABLE public.{tabla} ENABLE ROW LEVEL SECURITY")
        op.execute(f"REVOKE ALL ON public.{tabla} FROM PUBLIC, anon, authenticated")
        op.execute(f"REVOKE ALL ON SEQUENCE public.{tabla}_id_seq FROM PUBLIC, anon, authenticated")
    op.execute(SQL_FUNCION)


def downgrade():
    # Solo en una instalación sin datos de Compra Ágil; nunca borra compras ni su historial.
    op.execute("""DO $$ BEGIN
      IF EXISTS (SELECT 1 FROM public.compra_agil)
         OR EXISTS (SELECT 1 FROM public.compra_agil_pendiente)
         OR EXISTS (SELECT 1 FROM public.raw_mercado_publico WHERE fuente = 'compra_agil')
         OR EXISTS (SELECT 1 FROM public.ejecucion_ingesta WHERE fuente = 'compra_agil') THEN
        RAISE EXCEPTION 'No se puede revertir mientras haya datos o ejecuciones de Compra Ágil';
      END IF;
    END $$;""")
    op.execute("DROP FUNCTION public.purgar_compras_agiles_no_disponibles(text[], boolean)")
    op.drop_table("compra_agil_sincronizacion")
    op.drop_index(op.f("ix_compra_agil_pendiente_fecha_cierre"), table_name="compra_agil_pendiente")
    op.drop_table("compra_agil_pendiente")
    op.drop_index(op.f("ix_compra_agil_item_codigo_producto"), table_name="compra_agil_item")
    op.drop_index(op.f("ix_compra_agil_item_compra_agil_id"), table_name="compra_agil_item")
    op.drop_table("compra_agil_item")
    op.drop_index(op.f("ix_compra_agil_raw_id"), table_name="compra_agil")
    op.drop_table("compra_agil")
    op.drop_constraint("ck_ejecucion_ingesta_fuente", "ejecucion_ingesta", type_="check")
    op.drop_column("ejecucion_ingesta", "fuente")
