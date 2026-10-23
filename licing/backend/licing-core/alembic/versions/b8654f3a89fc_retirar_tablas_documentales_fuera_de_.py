"""Retira las seis tablas documentales vacías y adapta la limpieza automática."""
from alembic import op

revision = "b8654f3a89fc"
down_revision = "c08ccd7a1466"
branch_labels = None
depends_on = None

SQL_UPGRADE = r"""
DO $guard$
DECLARE tabla text; ocupada boolean;
BEGIN
    FOREACH tabla IN ARRAY ARRAY['licitacion_periodo_servicio','licitacion_requisito',
        'licitacion_prestacion','documento_fragmento','licitacion_extraccion','licitacion_documento']
    LOOP
        IF to_regclass('public.' || tabla) IS NOT NULL THEN
            EXECUTE format('LOCK TABLE public.%I IN ACCESS EXCLUSIVE MODE', tabla);
            EXECUTE format('SELECT EXISTS(SELECT 1 FROM public.%I)', tabla) INTO ocupada;
            IF ocupada THEN
                RAISE EXCEPTION 'No se elimina la tabla %: contiene datos.', tabla;
            END IF;
        END IF;
    END LOOP;
END;
$guard$;

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
DROP TABLE IF EXISTS public.licitacion_periodo_servicio;
DROP TABLE IF EXISTS public.licitacion_requisito;
DROP TABLE IF EXISTS public.licitacion_prestacion;
DROP TABLE IF EXISTS public.documento_fragmento;
DROP TABLE IF EXISTS public.licitacion_extraccion;
DROP TABLE IF EXISTS public.licitacion_documento;
"""

# Copia congelada del esquema anterior para una reversión coherente de Alembic.
SQL_DOWNGRADE = r"""
CREATE TABLE licitacion_documento (
	id SERIAL NOT NULL,
	licitacion_id INTEGER NOT NULL,
	nombre TEXT NOT NULL,
	tipo VARCHAR(40) NOT NULL,
	url_origen VARCHAR(1500) NOT NULL,
	version VARCHAR(100) NOT NULL,
	huella_archivo VARCHAR(64),
	fecha_fuente TIMESTAMP WITH TIME ZONE,
	registrado_en TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT uq_documento_origen_version UNIQUE (licitacion_id, url_origen, version),
	CONSTRAINT uq_documento_licitacion UNIQUE (id, licitacion_id),
	FOREIGN KEY(licitacion_id) REFERENCES licitacion (id)
);

CREATE INDEX ix_licitacion_documento_licitacion_id ON licitacion_documento (licitacion_id);

ALTER TABLE public.licitacion_documento ENABLE ROW LEVEL SECURITY;

CREATE TABLE licitacion_extraccion (
	id SERIAL NOT NULL,
	licitacion_id INTEGER NOT NULL,
	documento_id INTEGER NOT NULL,
	metodo VARCHAR(100) NOT NULL,
	version_metodo VARCHAR(100) NOT NULL,
	estado VARCHAR(20) NOT NULL,
	huella_contenido VARCHAR(64) NOT NULL,
	cobertura JSONB NOT NULL,
	creado_en TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT fk_extraccion_documento FOREIGN KEY(documento_id, licitacion_id) REFERENCES licitacion_documento (id, licitacion_id),
	CONSTRAINT uq_extraccion_licitacion UNIQUE (id, licitacion_id),
	CONSTRAINT uq_extraccion_contenido UNIQUE (documento_id, huella_contenido),
	CONSTRAINT ck_extraccion_estado CHECK (estado IN ('pendiente','completa','parcial','error'))
);

CREATE INDEX ix_licitacion_extraccion_documento_id ON licitacion_extraccion (documento_id);

CREATE INDEX ix_licitacion_extraccion_licitacion_id ON licitacion_extraccion (licitacion_id);

ALTER TABLE public.licitacion_extraccion ENABLE ROW LEVEL SECURITY;

CREATE TABLE documento_fragmento (
	id SERIAL NOT NULL,
	extraccion_id INTEGER NOT NULL,
	orden INTEGER NOT NULL,
	pagina_inicio INTEGER NOT NULL,
	pagina_fin INTEGER NOT NULL,
	seccion TEXT,
	tipo_seccion VARCHAR(40) NOT NULL,
	texto TEXT NOT NULL,
	requiere_ocr BOOLEAN,
	PRIMARY KEY (id),
	CONSTRAINT uq_fragmento_orden UNIQUE (extraccion_id, orden),
	CONSTRAINT uq_fragmento_extraccion UNIQUE (id, extraccion_id),
	CONSTRAINT ck_fragmento_paginas CHECK (pagina_inicio > 0 AND pagina_fin >= pagina_inicio AND orden > 0),
	FOREIGN KEY(extraccion_id) REFERENCES licitacion_extraccion (id)
);

CREATE INDEX ix_documento_fragmento_extraccion_id ON documento_fragmento (extraccion_id);

ALTER TABLE public.documento_fragmento ENABLE ROW LEVEL SECURITY;

CREATE TABLE licitacion_prestacion (
	clave VARCHAR(100) NOT NULL,
	tipo VARCHAR(60) NOT NULL,
	nombre TEXT NOT NULL,
	descripcion TEXT,
	item_correlativo INTEGER,
	modalidad TEXT,
	oferta_parcial BOOLEAN,
	grupo_servicios TEXT,
	adjudicacion TEXT,
	id SERIAL NOT NULL,
	licitacion_id INTEGER NOT NULL,
	extraccion_id INTEGER NOT NULL,
	fragmento_id INTEGER NOT NULL,
	estado_dato VARCHAR(25) NOT NULL,
	confianza NUMERIC,
	PRIMARY KEY (id),
	CONSTRAINT fk_prestacion_extraccion FOREIGN KEY(extraccion_id, licitacion_id) REFERENCES licitacion_extraccion (id, licitacion_id),
	CONSTRAINT fk_prestacion_fragmento FOREIGN KEY(fragmento_id, extraccion_id) REFERENCES documento_fragmento (id, extraccion_id),
	CONSTRAINT ck_prestacion_estado CHECK (estado_dato IN ('confirmado','no_informado','ambiguo','contradictorio')),
	CONSTRAINT ck_prestacion_confianza CHECK (confianza BETWEEN 0 AND 1),
	CONSTRAINT uq_prestacion_contexto UNIQUE (id, extraccion_id, licitacion_id),
	CONSTRAINT uq_prestacion_clave UNIQUE (extraccion_id, clave)
);

CREATE INDEX ix_licitacion_prestacion_extraccion_id ON licitacion_prestacion (extraccion_id);

CREATE INDEX ix_licitacion_prestacion_licitacion_id ON licitacion_prestacion (licitacion_id);

ALTER TABLE public.licitacion_prestacion ENABLE ROW LEVEL SECURITY;

CREATE TABLE licitacion_periodo_servicio (
	prestacion_id INTEGER NOT NULL,
	tipo VARCHAR(40) NOT NULL,
	precision VARCHAR(20) NOT NULL,
	inicio_min TIMESTAMP WITHOUT TIME ZONE,
	inicio_max TIMESTAMP WITHOUT TIME ZONE,
	fin_min TIMESTAMP WITHOUT TIME ZONE,
	fin_max TIMESTAMP WITHOUT TIME ZONE,
	zona_horaria VARCHAR(60),
	incluye_hora BOOLEAN NOT NULL,
	cantidad_min NUMERIC,
	cantidad_max NUMERIC,
	unidad TEXT,
	tipo_habitacion TEXT,
	ocupantes_por_unidad INTEGER,
	id SERIAL NOT NULL,
	licitacion_id INTEGER NOT NULL,
	extraccion_id INTEGER NOT NULL,
	fragmento_id INTEGER NOT NULL,
	estado_dato VARCHAR(25) NOT NULL,
	confianza NUMERIC,
	PRIMARY KEY (id),
	CONSTRAINT fk_periodo_extraccion FOREIGN KEY(extraccion_id, licitacion_id) REFERENCES licitacion_extraccion (id, licitacion_id),
	CONSTRAINT fk_periodo_fragmento FOREIGN KEY(fragmento_id, extraccion_id) REFERENCES documento_fragmento (id, extraccion_id),
	CONSTRAINT ck_periodo_estado CHECK (estado_dato IN ('confirmado','no_informado','ambiguo','contradictorio')),
	CONSTRAINT ck_periodo_confianza CHECK (confianza BETWEEN 0 AND 1),
	CONSTRAINT fk_periodo_prestacion FOREIGN KEY(prestacion_id, extraccion_id, licitacion_id) REFERENCES licitacion_prestacion (id, extraccion_id, licitacion_id),
	CONSTRAINT ck_periodo_precision CHECK (precision IN ('exacta','intervalo','por_coordinar','no_informada')),
	CONSTRAINT ck_periodo_inicio CHECK (inicio_min IS NULL OR inicio_max IS NULL OR inicio_min <= inicio_max),
	CONSTRAINT ck_periodo_fin CHECK (fin_min IS NULL OR fin_max IS NULL OR fin_min <= fin_max),
	CONSTRAINT ck_periodo_orden CHECK (inicio_min IS NULL OR fin_min IS NULL OR inicio_min <= fin_min),
	CONSTRAINT ck_periodo_cantidad CHECK (cantidad_min IS NULL OR cantidad_max IS NULL OR cantidad_min <= cantidad_max),
	CONSTRAINT ck_periodo_cantidad_positiva CHECK (cantidad_min >= 0 AND cantidad_max >= 0),
	CONSTRAINT ck_periodo_ocupantes CHECK (ocupantes_por_unidad > 0)
);

CREATE INDEX ix_licitacion_periodo_servicio_extraccion_id ON licitacion_periodo_servicio (extraccion_id);

CREATE INDEX ix_licitacion_periodo_servicio_licitacion_id ON licitacion_periodo_servicio (licitacion_id);

CREATE INDEX ix_licitacion_periodo_servicio_prestacion_id ON licitacion_periodo_servicio (prestacion_id);

ALTER TABLE public.licitacion_periodo_servicio ENABLE ROW LEVEL SECURITY;

CREATE TABLE licitacion_requisito (
	prestacion_id INTEGER,
	tipo VARCHAR(60) NOT NULL,
	clave VARCHAR(100) NOT NULL,
	texto_original TEXT NOT NULL,
	caracter VARCHAR(20) NOT NULL,
	operador VARCHAR(40),
	valor_texto TEXT,
	valor_min NUMERIC,
	valor_max NUMERIC,
	unidad TEXT,
	alcance TEXT,
	grupo_alternativa TEXT,
	condicion TEXT,
	excepciones TEXT,
	ponderacion NUMERIC,
	parametros JSONB,
	id SERIAL NOT NULL,
	licitacion_id INTEGER NOT NULL,
	extraccion_id INTEGER NOT NULL,
	fragmento_id INTEGER NOT NULL,
	estado_dato VARCHAR(25) NOT NULL,
	confianza NUMERIC,
	PRIMARY KEY (id),
	CONSTRAINT fk_requisito_extraccion FOREIGN KEY(extraccion_id, licitacion_id) REFERENCES licitacion_extraccion (id, licitacion_id),
	CONSTRAINT fk_requisito_fragmento FOREIGN KEY(fragmento_id, extraccion_id) REFERENCES documento_fragmento (id, extraccion_id),
	CONSTRAINT ck_requisito_estado CHECK (estado_dato IN ('confirmado','no_informado','ambiguo','contradictorio')),
	CONSTRAINT ck_requisito_confianza CHECK (confianza BETWEEN 0 AND 1),
	CONSTRAINT fk_requisito_prestacion FOREIGN KEY(prestacion_id, extraccion_id, licitacion_id) REFERENCES licitacion_prestacion (id, extraccion_id, licitacion_id),
	CONSTRAINT ck_requisito_caracter CHECK (caracter IN ('obligatorio','evaluable','condicional','no_exigido','no_indicado')),
	CONSTRAINT ck_requisito_rango CHECK (valor_min IS NULL OR valor_max IS NULL OR valor_min <= valor_max),
	CONSTRAINT ck_requisito_ponderacion CHECK (ponderacion BETWEEN 0 AND 100)
);

CREATE INDEX ix_licitacion_requisito_extraccion_id ON licitacion_requisito (extraccion_id);

CREATE INDEX ix_licitacion_requisito_licitacion_id ON licitacion_requisito (licitacion_id);

CREATE INDEX ix_licitacion_requisito_prestacion_id ON licitacion_requisito (prestacion_id);

ALTER TABLE public.licitacion_requisito ENABLE ROW LEVEL SECURITY;


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
    op.execute(SQL_DOWNGRADE)
