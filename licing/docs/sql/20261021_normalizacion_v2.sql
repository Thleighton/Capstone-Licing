-- Ampliación compatible con el backend anterior. No descarga datos ni almacena PDF.
-- Equivalente a Alembic b7e29c41a806 -> c4f8a19d620e, en una transacción.
BEGIN;
SET LOCAL search_path = public;
SET LOCAL lock_timeout = '5s';
DO $licing_normalizacion$
DECLARE
    antes_raw bigint;
    antes_licitaciones bigint;
    antes_items bigint;
    antes_raw_hash text;
BEGIN
    IF (SELECT count(*) FROM public.alembic_version) <> 1 OR
       (SELECT version_num FROM public.alembic_version LIMIT 1) <> 'b7e29c41a806' THEN
        RAISE EXCEPTION 'La revisión de origen debe ser b7e29c41a806; no se aplicó la ampliación.';
    END IF;
    PERFORM pg_advisory_xact_lock(728401);
    SELECT count(*),md5(string_agg(to_jsonb(r)::text, ',' ORDER BY id)) INTO antes_raw,antes_raw_hash FROM public.raw_mercado_publico r;
    SELECT count(*) INTO antes_licitaciones FROM public.licitacion;
    SELECT count(*) INTO antes_items FROM public.licitacion_item;

ALTER TABLE public.licitacion ADD COLUMN tipo VARCHAR(30);

ALTER TABLE public.licitacion ADD COLUMN codigo_tipo INTEGER;

ALTER TABLE public.licitacion ADD COLUMN estimacion INTEGER;

ALTER TABLE public.licitacion ADD COLUMN visibilidad_monto INTEGER;

ALTER TABLE public.licitacion ADD COLUMN justificacion_monto TEXT;

ALTER TABLE public.licitacion ADD COLUMN direccion_comprador TEXT;

ALTER TABLE public.licitacion ADD COLUMN direccion_entrega TEXT;

ALTER TABLE public.licitacion ADD COLUMN direccion_visita TEXT;

ALTER TABLE public.licitacion ADD COLUMN fechas_fuente JSONB;

ALTER TABLE public.licitacion ADD COLUMN condiciones_fuente JSONB;

ALTER TABLE public.licitacion ADD COLUMN normalizacion_version VARCHAR(30);

ALTER TABLE public.licitacion ADD COLUMN normalizado_en TIMESTAMP WITH TIME ZONE;

ALTER TABLE public.licitacion_item ADD COLUMN codigo_categoria VARCHAR(100);

ALTER TABLE public.licitacion_item ADD COLUMN categoria TEXT;

ALTER TABLE public.licitacion_item ADD COLUMN estado_fuente INTEGER;

ALTER TABLE public.licitacion_item ADD COLUMN adjudicacion_fuente JSONB;

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

CREATE INDEX ix_licitacion_item_codigo_categoria ON public.licitacion_item (codigo_categoria);

UPDATE public.licitacion l SET
tipo = NULLIF(btrim(r.respuesta->>'Tipo'), ''),
codigo_tipo = NULLIF(btrim(r.respuesta->>'CodigoTipo'), '')::integer,
estimacion = NULLIF(btrim(r.respuesta->>'Estimacion'), '')::integer,
visibilidad_monto = NULLIF(btrim(r.respuesta->>'VisibilidadMonto'), '')::integer,
justificacion_monto = NULLIF(btrim(r.respuesta->>'JustificacionMontoEstimado'), ''),
direccion_entrega = NULLIF(btrim(r.respuesta->>'DireccionEntrega'), ''),
direccion_visita = NULLIF(btrim(r.respuesta->>'DireccionVisita'), ''),
direccion_comprador = NULLIF(btrim(r.respuesta#>>'{Comprador,DireccionUnidad}'), ''),
fechas_fuente = coalesce(nullif(r.respuesta->'Fechas', 'null'::jsonb), '{}'::jsonb),
condiciones_fuente = coalesce((SELECT jsonb_object_agg(key,value) FROM jsonb_each(r.respuesta) WHERE key IN ('Contrato', 'TipoConvocatoria', 'Etapas', 'EstadoEtapas', 'Informada', 'Obras', 'SubContratacion', 'ProhibicionContratacion', 'Modalidad', 'TipoPago', 'FuenteFinanciamiento', 'UnidadTiempo', 'Tiempo', 'TiempoDuracionContrato', 'UnidadTiempoDuracionContrato', 'TipoDuracionContrato', 'UnidadTiempoContratoLicitacion', 'ValorTiempoRenovacion', 'PeriodoTiempoRenovacion', 'EsRenovable', 'ExtensionPlazo', 'EsBaseTipo', 'Adjudicacion', 'ObservacionContract')), '{}'::jsonb),
normalizacion_version = '2',
normalizado_en = now()
FROM public.raw_mercado_publico r WHERE r.id = l.raw_id;

UPDATE public.licitacion_item i SET
codigo_categoria = NULLIF(btrim(x.item->>'CodigoCategoria'), ''),
categoria = NULLIF(btrim(x.item->>'Categoria'), ''),
estado_fuente = NULLIF(btrim(x.item->>'CodigoEstadoLicitacion'), '')::integer,
adjudicacion_fuente = x.item->'Adjudicacion'
FROM public.licitacion l JOIN public.raw_mercado_publico r ON r.id=l.raw_id
CROSS JOIN LATERAL jsonb_array_elements(r.respuesta#>'{Items,Listado}') x(item)
WHERE i.licitacion_id=l.id AND x.item->>'Correlativo'=i.correlativo::text;

    IF antes_raw <> (SELECT count(*) FROM public.raw_mercado_publico) OR
       antes_licitaciones <> (SELECT count(*) FROM public.licitacion) OR
       antes_items <> (SELECT count(*) FROM public.licitacion_item) OR
       antes_raw_hash IS DISTINCT FROM (SELECT md5(string_agg(to_jsonb(r)::text, ',' ORDER BY id)) FROM public.raw_mercado_publico r) THEN
        RAISE EXCEPTION 'La verificación de conservación de datos no coincide; se revierte la transacción.';
    END IF;
    IF EXISTS (
        SELECT 1 FROM public.licitacion_item i
        JOIN public.licitacion l ON l.id=i.licitacion_id
        JOIN public.raw_mercado_publico r ON r.id=l.raw_id
        CROSS JOIN LATERAL jsonb_array_elements(r.respuesta#>'{Items,Listado}') x(item)
        WHERE x.item->>'Correlativo'=i.correlativo::text
        AND (i.codigo_categoria IS DISTINCT FROM NULLIF(btrim(x.item->>'CodigoCategoria'),'')
          OR i.categoria IS DISTINCT FROM NULLIF(btrim(x.item->>'Categoria'),''))
    ) THEN
        RAISE EXCEPTION 'Las categorías no coinciden con el JSON; se revierte la transacción.';
    END IF;
    IF (SELECT count(*) FROM pg_class WHERE relnamespace='public'::regnamespace AND relrowsecurity
        AND relname IN ('licitacion_documento','licitacion_extraccion','documento_fragmento',
                        'licitacion_prestacion','licitacion_requisito','licitacion_periodo_servicio')) <> 6 THEN
        RAISE EXCEPTION 'Falta RLS en documentación; se revierte la transacción.';
    END IF;
    UPDATE public.alembic_version SET version_num='c4f8a19d620e' WHERE version_num='b7e29c41a806';
END $licing_normalizacion$;
COMMIT;
SELECT 'Normalización ampliada y datos conservados' AS resultado,
       (SELECT version_num FROM public.alembic_version) AS revision,
       (SELECT count(*) FROM public.raw_mercado_publico) AS raw,
       (SELECT count(*) FROM public.licitacion) AS licitaciones,
       (SELECT count(*) FROM public.licitacion_item) AS items;
