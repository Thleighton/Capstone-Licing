-- LICING | LicitacionesFiltradas | Estructura inicial 1.0.0
-- PostgreSQL 15+ / Supabase. Ejecutar UNA VEZ en el SQL Editor del proyecto nuevo.
-- El proyecto ya existe: este archivo crea sus tablas, indices, vistas y permisos.
-- No conecta la aplicacion, no copia datos y no ejecuta filtros ni llamadas a IA.
-- No ejecutar sobre el proyecto que contiene las licitaciones originales.
-- Todo se crea en una transaccion; un error revierte esta ejecucion completa.
-- Una segunda ejecucion falla si las tablas ya existen: no borra ni reemplaza datos.
--
-- Flujo previsto:
-- originales -> reglas y semantica -> preseleccionada / revision_manual / descartada
-- preseleccionada o recuperada manualmente -> analisis LLM -> decision del hotel.
-- La puntuacion semantica NO representa porcentaje de cumplimiento ni de exito.
--
-- Acceso: backend de Licing. Los usuarios siguen en el proyecto de Auth actual.
-- Los UUID de revisores son referencias externas, sin FK a auth.users de esta BD.
-- El backend debe autenticar al usuario y obtener su UUID de la sesion validada.
-- Nunca enviar la credencial privilegiada de este proyecto al navegador.

BEGIN;
SET LOCAL TIME ZONE 'UTC';
SET LOCAL search_path = pg_catalog, public;

DO $preflight$
BEGIN
    IF current_setting('server_version_num')::integer < 150000 THEN
        RAISE EXCEPTION 'Este script requiere PostgreSQL 15 o superior.';
    END IF;
    IF to_regclass('public.raw_mercado_publico') IS NOT NULL THEN
        RAISE EXCEPTION 'Se detecto la base original. Selecciona el proyecto NUEVO LicitacionesFiltradas.';
    END IF;
    IF (SELECT count(*) FROM pg_roles WHERE rolname IN ('anon', 'authenticated', 'service_role')) <> 3 THEN
        RAISE EXCEPTION 'Faltan los roles de Supabase. Ejecuta el script en el SQL Editor del proyecto nuevo.';
    END IF;
END;
$preflight$;

-- 1. Copia de trabajo de cada oportunidad. El codigo identifica la fuente;
--    el id local no coincide necesariamente con el id de la base original.
CREATE TABLE public.oportunidad (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    origen text NOT NULL DEFAULT 'mercado_publico' CHECK (btrim(origen) <> ''),
    codigo_externo text NOT NULL CHECK (
        btrim(codigo_externo) <> '' AND codigo_externo = upper(btrim(codigo_externo))
    ),
    modalidad text NOT NULL CHECK (modalidad IN ('licitacion', 'compra_agil')),
    origen_proyecto text,
    origen_licitacion_id bigint,
    url_oficial text CHECK (
        url_oficial IS NULL OR
        url_oficial ~* '^https://([a-z0-9-]+\.)*mercadopublico\.cl([/?#]|$)'
    ),
    nombre text NOT NULL CHECK (btrim(nombre) <> ''),
    descripcion text,
    codigo_estado integer,
    estado text,
    tipo text,
    codigo_tipo integer,
    monto_estimado numeric CHECK (monto_estimado >= 0 AND monto_estimado NOT IN ('NaN'::numeric, 'Infinity'::numeric)),
    moneda text,
    estimacion integer,
    visibilidad_monto integer,
    justificacion_monto text,
    fecha_publicacion timestamptz,
    fecha_cierre timestamptz,
    codigo_organismo text,
    nombre_organismo text,
    codigo_unidad text,
    nombre_unidad text,
    region_comprador text,
    comuna_comprador text,
    direccion_comprador text,
    direccion_entrega text,
    direccion_visita text,
    fechas_fuente jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(fechas_fuente) = 'object'),
    condiciones_fuente jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(condiciones_fuente) = 'object'),
    datos_fuente jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(datos_fuente) = 'object'),
    hash_fuente text CHECK (hash_fuente ~ '^[0-9a-f]{64}$'),
    version_datos bigint NOT NULL DEFAULT 1 CHECK (version_datos > 0),
    creado_en timestamptz NOT NULL DEFAULT clock_timestamp(),
    actualizado_en timestamptz NOT NULL DEFAULT clock_timestamp(),
    sincronizado_en timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT uq_oportunidad_fuente UNIQUE (origen, codigo_externo)
);

COMMENT ON COLUMN public.oportunidad.modalidad IS
    'Tipo de proceso; no confundir con tipo/codigo_tipo entregados por la fuente.';
COMMENT ON COLUMN public.oportunidad.region_comprador IS
    'Ubicacion del comprador. No implica lugar de ejecucion del servicio.';
COMMENT ON COLUMN public.oportunidad.fecha_cierre IS
    'Instante con zona. Si el origen no trae zona, convertir explicitamente desde America/Santiago en el backend.';
COMMENT ON COLUMN public.oportunidad.version_datos IS
    'Se incrementa al cambiar el contenido o sus items/documentos; invalida evaluaciones anteriores en las vistas.';

-- 2. Items normalizados. Vigente=false permite retirar un item sin borrarlo.
CREATE TABLE public.oportunidad_item (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    oportunidad_id bigint NOT NULL REFERENCES public.oportunidad(id) ON DELETE RESTRICT,
    correlativo integer NOT NULL CHECK (correlativo > 0),
    codigo_producto text,
    nombre_producto text,
    descripcion text,
    cantidad numeric CHECK (cantidad >= 0 AND cantidad NOT IN ('NaN'::numeric, 'Infinity'::numeric)),
    unidad_medida text,
    codigo_categoria text,
    categoria text,
    estado_fuente integer,
    adjudicacion_fuente jsonb,
    vigente boolean NOT NULL DEFAULT true,
    CONSTRAINT uq_oportunidad_item UNIQUE (oportunidad_id, correlativo)
);

-- 3. Versiones de documentos. Se guardan texto y procedencia, no el binario PDF.
CREATE TABLE public.documento_oportunidad (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    oportunidad_id bigint NOT NULL REFERENCES public.oportunidad(id) ON DELETE RESTRICT,
    nombre text NOT NULL CHECK (btrim(nombre) <> ''),
    tipo text NOT NULL CHECK (tipo IN ('bases_administrativas', 'bases_tecnicas', 'anexo', 'otro')),
    url_origen text NOT NULL CHECK (url_origen ~* '^https://'),
    version integer NOT NULL DEFAULT 1 CHECK (version > 0),
    hash_archivo text CHECK (hash_archivo ~ '^[0-9a-f]{64}$'),
    estado_extraccion text NOT NULL DEFAULT 'pendiente'
        CHECK (estado_extraccion IN ('pendiente', 'extraido', 'parcial', 'sin_texto', 'error')),
    texto_extraido text,
    paginas integer CHECK (paginas > 0),
    cobertura jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(cobertura) = 'object'),
    extraido_en timestamptz,
    vigente boolean NOT NULL DEFAULT true,
    creado_en timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT uq_documento_version UNIQUE (oportunidad_id, url_origen, version),
    CONSTRAINT ck_documento_texto CHECK (
        estado_extraccion NOT IN ('extraido', 'parcial') OR
        (texto_extraido IS NOT NULL AND btrim(texto_extraido) <> '' AND extraido_en IS NOT NULL)
    )
);

-- 4. Perfil y criterios versionados. No se precargan umbrales ni capacidades
--    inventadas. Solo una version validada puede estar activa para este hotel.
CREATE TABLE public.perfil_filtro_version (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    version integer NOT NULL UNIQUE CHECK (version > 0),
    nombre text NOT NULL CHECK (btrim(nombre) <> ''),
    descripcion_oferta text NOT NULL CHECK (btrim(descripcion_oferta) <> ''),
    criterios jsonb NOT NULL CHECK (jsonb_typeof(criterios) = 'object' AND criterios <> '{}'::jsonb),
    fuentes jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(fuentes) = 'array'),
    validada boolean NOT NULL DEFAULT false,
    activa boolean NOT NULL DEFAULT false,
    creado_por uuid NOT NULL,
    creado_en timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT ck_perfil_activo CHECK (NOT activa OR validada)
);

CREATE UNIQUE INDEX uq_perfil_filtro_activo ON public.perfil_filtro_version ((true)) WHERE activa;
COMMENT ON TABLE public.perfil_filtro_version IS
    'Versiones del perfil del hotel y de las reglas. Crear una version nueva para cambiar criterios; activar/desactivar en una transaccion.';

-- 5. Evaluaciones acumulativas de reglas y semantica, antes del LLM.
--    Se conserva la entrada exacta para explicar resultados historicos.
CREATE TABLE public.evaluacion_filtro (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    oportunidad_id bigint NOT NULL REFERENCES public.oportunidad(id) ON DELETE RESTRICT,
    perfil_version_id bigint NOT NULL REFERENCES public.perfil_filtro_version(id) ON DELETE RESTRICT,
    version_datos bigint NOT NULL CHECK (version_datos > 0),
    clave_ejecucion uuid NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    version_motor text NOT NULL CHECK (btrim(version_motor) <> ''),
    modelo_semantico text,
    puntuacion_semantica double precision CHECK (puntuacion_semantica BETWEEN -1 AND 1),
    puntuacion_exclusion double precision CHECK (puntuacion_exclusion BETWEEN -1 AND 1),
    cobertura text NOT NULL CHECK (cobertura IN ('completa', 'parcial', 'sin_bases')),
    clasificacion text NOT NULL CHECK (clasificacion IN ('preseleccionada', 'revision_manual', 'descartada')),
    motivo text NOT NULL CHECK (btrim(motivo) <> ''),
    entrada_evaluada jsonb NOT NULL CHECK (
        jsonb_typeof(entrada_evaluada) = 'object' AND entrada_evaluada <> '{}'::jsonb
    ),
    metadatos jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(metadatos) = 'object'),
    evaluado_en timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT ck_evaluacion_modelo CHECK (
        (puntuacion_semantica IS NULL AND puntuacion_exclusion IS NULL) OR
        (modelo_semantico IS NOT NULL AND btrim(modelo_semantico) <> '')
    )
);

COMMENT ON COLUMN public.evaluacion_filtro.entrada_evaluada IS
    'Snapshot de datos, items y texto/evidencias usados. Incluir identificadores y versiones de documentos y la cobertura disponible.';
COMMENT ON COLUMN public.evaluacion_filtro.puntuacion_semantica IS
    'Similitud coseno opcional, entre -1 y 1. No es probabilidad ni porcentaje de cumplimiento. Sin umbrales fijados en SQL.';

-- 6. Resultado explicable de cada criterio; sin informacion no equivale a incumplir.
CREATE TABLE public.resultado_criterio (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    evaluacion_id bigint NOT NULL REFERENCES public.evaluacion_filtro(id) ON DELETE RESTRICT,
    codigo text NOT NULL CHECK (btrim(codigo) <> ''),
    nombre text NOT NULL CHECK (btrim(nombre) <> ''),
    caracter text NOT NULL CHECK (caracter IN ('obligatorio', 'preferencia')),
    resultado text NOT NULL CHECK (resultado IN ('cumple', 'no_cumple', 'sin_informacion', 'no_aplica')),
    motivo text NOT NULL CHECK (btrim(motivo) <> ''),
    valor_esperado jsonb,
    valor_observado jsonb,
    evidencias jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(evidencias) = 'array'),
    CONSTRAINT uq_resultado_criterio UNIQUE (evaluacion_id, codigo)
);

COMMENT ON COLUMN public.resultado_criterio.evidencias IS
    'Lista de evidencias: documento_id/version/url/pagina/cita, o campo/valor de la API. El backend debe validar las citas contra el texto.';

-- 7. Correcciones humanas, separadas de la puntuacion automatica.
--    Una oportunidad puede ser relevante y descartarse por capacidad o fecha;
--    esta separacion evita usar ese descarte como ejemplo semantico negativo.
CREATE TABLE public.revision_manual (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    evaluacion_id bigint NOT NULL REFERENCES public.evaluacion_filtro(id) ON DELETE RESTRICT,
    accion text NOT NULL CHECK (accion IN ('enviar_a_llm', 'descartar', 'mantener_pendiente')),
    relevancia_confirmada text NOT NULL DEFAULT 'sin_determinar'
        CHECK (relevancia_confirmada IN ('relevante', 'no_relevante', 'sin_determinar')),
    categoria_motivo text NOT NULL CHECK (categoria_motivo IN (
        'servicio', 'capacidad', 'ubicacion', 'plazo', 'documentos', 'presupuesto', 'otro'
    )),
    motivo text NOT NULL CHECK (btrim(motivo) <> ''),
    revisado_por uuid NOT NULL,
    revisado_en timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT uq_revision_evaluacion UNIQUE (id, evaluacion_id)
);

COMMENT ON COLUMN public.revision_manual.revisado_por IS
    'UUID del usuario del proyecto de Auth original. El backend lo toma de una sesion validada, no del cuerpo enviado por el navegador.';

-- 8. Solicitudes/resultados del LLM. La tabla no ejecuta IA automaticamente.
CREATE TABLE public.analisis_llm (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    evaluacion_id bigint NOT NULL REFERENCES public.evaluacion_filtro(id) ON DELETE RESTRICT,
    revision_id bigint,
    solicitud_id uuid NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    estado text NOT NULL DEFAULT 'pendiente'
        CHECK (estado IN ('pendiente', 'procesando', 'completado', 'error')),
    proveedor text,
    modelo text,
    version_prompt text,
    resumen text,
    salida_estructurada jsonb CHECK (jsonb_typeof(salida_estructurada) = 'object'),
    error text,
    intentos integer NOT NULL DEFAULT 0 CHECK (intentos >= 0),
    solicitado_en timestamptz NOT NULL DEFAULT clock_timestamp(),
    iniciado_en timestamptz,
    finalizado_en timestamptz,
    CONSTRAINT fk_analisis_revision FOREIGN KEY (revision_id, evaluacion_id)
        REFERENCES public.revision_manual(id, evaluacion_id) ON DELETE RESTRICT,
    CONSTRAINT ck_analisis_completo CHECK (
        estado <> 'completado' OR (
            proveedor IS NOT NULL AND btrim(proveedor) <> '' AND
            modelo IS NOT NULL AND btrim(modelo) <> '' AND
            version_prompt IS NOT NULL AND btrim(version_prompt) <> '' AND
            resumen IS NOT NULL AND btrim(resumen) <> '' AND
            salida_estructurada IS NOT NULL AND salida_estructurada <> '{}'::jsonb AND
            iniciado_en IS NOT NULL AND finalizado_en IS NOT NULL
        )
    ),
    CONSTRAINT ck_analisis_error CHECK (
        estado <> 'error' OR (error IS NOT NULL AND btrim(error) <> '' AND finalizado_en IS NOT NULL)
    ),
    CONSTRAINT ck_analisis_fechas CHECK (
        finalizado_en IS NULL OR iniciado_en IS NULL OR finalizado_en >= iniciado_en
    )
);

COMMENT ON COLUMN public.analisis_llm.solicitud_id IS
    'Clave de idempotencia. Reutilizar la misma en reintentos de una solicitud para evitar trabajos duplicados.';
COMMENT ON COLUMN public.analisis_llm.salida_estructurada IS
    'Salida versionada: servicios, requisitos, documentos requeridos, fechas, criterios de evaluacion, pendientes y evidencias. No es una decision de participar.';

-- Versionado automatico de la entrada: evita seguir mostrando como actual
-- una evaluacion cuando cambian descripcion, items o documentos.
CREATE FUNCTION public.lf_versionar_oportunidad()
RETURNS trigger LANGUAGE plpgsql SET search_path = pg_catalog AS $function$
BEGIN
    IF NEW.version_datos NOT IN (OLD.version_datos, OLD.version_datos + 1) THEN
        RAISE EXCEPTION 'version_datos solo puede conservarse o incrementarse en una unidad.';
    END IF;
    IF (to_jsonb(NEW) - ARRAY['actualizado_en', 'sincronizado_en', 'version_datos'])
       IS DISTINCT FROM
       (to_jsonb(OLD) - ARRAY['actualizado_en', 'sincronizado_en', 'version_datos']) THEN
        NEW.version_datos := OLD.version_datos + 1;
    END IF;
    NEW.actualizado_en := clock_timestamp();
    RETURN NEW;
END;
$function$;

CREATE TRIGGER trg_oportunidad_version
BEFORE UPDATE ON public.oportunidad FOR EACH ROW
EXECUTE FUNCTION public.lf_versionar_oportunidad();

CREATE FUNCTION public.lf_actualizar_version_padre()
RETURNS trigger LANGUAGE plpgsql SET search_path = pg_catalog AS $function$
DECLARE
    destino bigint;
BEGIN
    IF TG_OP = 'UPDATE' AND NEW IS NOT DISTINCT FROM OLD THEN
        RETURN NEW;
    END IF;
    IF TG_OP = 'DELETE' THEN
        destino := OLD.oportunidad_id;
    ELSE
        destino := NEW.oportunidad_id;
    END IF;
    IF TG_OP = 'UPDATE' AND OLD.oportunidad_id IS DISTINCT FROM NEW.oportunidad_id THEN
        UPDATE public.oportunidad SET version_datos = version_datos + 1 WHERE id = OLD.oportunidad_id;
    END IF;
    UPDATE public.oportunidad SET version_datos = version_datos + 1 WHERE id = destino;
    IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
    RETURN NEW;
END;
$function$;

CREATE TRIGGER trg_item_version
AFTER INSERT OR UPDATE OR DELETE ON public.oportunidad_item FOR EACH ROW
EXECUTE FUNCTION public.lf_actualizar_version_padre();
CREATE TRIGGER trg_documento_version
AFTER INSERT OR UPDATE OR DELETE ON public.documento_oportunidad FOR EACH ROW
EXECUTE FUNCTION public.lf_actualizar_version_padre();

-- Indices de lectura, seguimiento y claves foraneas.
CREATE INDEX idx_oportunidad_modalidad_cierre ON public.oportunidad (modalidad, fecha_cierre);
CREATE INDEX idx_oportunidad_organismo ON public.oportunidad (codigo_organismo);
CREATE INDEX idx_oportunidad_region ON public.oportunidad (region_comprador);
CREATE INDEX idx_oportunidad_sincronizacion ON public.oportunidad (sincronizado_en DESC);
CREATE INDEX idx_item_categoria ON public.oportunidad_item (codigo_categoria) WHERE vigente;
CREATE INDEX idx_evaluacion_actual ON public.evaluacion_filtro
    (oportunidad_id, perfil_version_id, version_datos, evaluado_en DESC, id DESC);
CREATE INDEX idx_evaluacion_perfil ON public.evaluacion_filtro (perfil_version_id);
CREATE INDEX idx_revision_actual ON public.revision_manual (evaluacion_id, revisado_en DESC, id DESC);
CREATE INDEX idx_llm_actual ON public.analisis_llm (evaluacion_id, revision_id, solicitado_en DESC, id DESC);
CREATE INDEX idx_llm_cola ON public.analisis_llm (estado, solicitado_en) WHERE estado IN ('pendiente', 'error');

-- La vista toma solo la ultima evaluacion del contenido y perfil ACTIVOS.
-- Una revision humana posterior prevalece sobre la propuesta del filtro.
-- Un analisis asociado a otra revision no se presenta como vigente.
CREATE VIEW public.vw_oportunidades_estado WITH (security_invoker = true) AS
SELECT
    o.*,
    p.id AS perfil_activo_id,
    e.id AS evaluacion_id,
    e.evaluado_en,
    e.cobertura,
    e.puntuacion_semantica,
    e.puntuacion_exclusion,
    (e.id IS NOT NULL) AS evaluacion_vigente,
    e.clasificacion AS propuesta_automatica,
    CASE
        WHEN e.id IS NULL THEN 'pendiente_evaluacion'
        WHEN r.accion = 'enviar_a_llm' THEN 'preseleccionada'
        WHEN r.accion = 'descartar' THEN 'descartada'
        WHEN r.accion = 'mantener_pendiente' THEN 'revision_manual'
        ELSE e.clasificacion
    END AS estado_seleccion,
    coalesce(r.motivo, e.motivo, 'Sin evaluacion vigente del contenido y perfil actuales.') AS motivo_seleccion,
    r.id AS revision_id,
    r.relevancia_confirmada,
    r.revisado_por,
    r.revisado_en,
    a.id AS analisis_id,
    coalesce(a.estado, 'sin_solicitar') AS estado_analisis_llm,
    a.resumen AS resumen_llm,
    a.finalizado_en AS analizado_en
FROM public.oportunidad o
LEFT JOIN public.perfil_filtro_version p ON p.activa
LEFT JOIN LATERAL (
    SELECT ev.* FROM public.evaluacion_filtro ev
    WHERE ev.oportunidad_id = o.id
      AND ev.perfil_version_id = p.id
      AND ev.version_datos = o.version_datos
    ORDER BY ev.evaluado_en DESC, ev.id DESC LIMIT 1
) e ON true
LEFT JOIN LATERAL (
    SELECT rm.* FROM public.revision_manual rm WHERE rm.evaluacion_id = e.id
    ORDER BY rm.revisado_en DESC, rm.id DESC LIMIT 1
) r ON true
LEFT JOIN LATERAL (
    SELECT al.* FROM public.analisis_llm al
    WHERE al.evaluacion_id = e.id AND al.revision_id IS NOT DISTINCT FROM r.id
    ORDER BY al.solicitado_en DESC, al.id DESC LIMIT 1
) a ON true;

CREATE VIEW public.vw_licitaciones_filtradas WITH (security_invoker = true) AS
SELECT * FROM public.vw_oportunidades_estado WHERE estado_seleccion = 'preseleccionada';

CREATE VIEW public.vw_revision_manual WITH (security_invoker = true) AS
SELECT * FROM public.vw_oportunidades_estado
WHERE estado_seleccion IN ('revision_manual', 'pendiente_evaluacion');

CREATE VIEW public.vw_descartadas WITH (security_invoker = true) AS
SELECT * FROM public.vw_oportunidades_estado WHERE estado_seleccion = 'descartada';

COMMENT ON VIEW public.vw_licitaciones_filtradas IS
    'Licitaciones y Compras Agiles preseleccionadas por el filtro o recuperadas por un usuario. Revisar estado_analisis_llm: no implica aprobacion del hotel.';
COMMENT ON VIEW public.vw_revision_manual IS
    'Oportunidades dudosas y oportunidades cuya evaluacion no existe o quedo obsoleta.';
COMMENT ON VIEW public.vw_descartadas IS
    'Descartes conservados con su motivo; pueden recuperarse mediante una revision nueva.';

-- Acceso exclusivo desde servidor. No se conceden accesos anonimos ni se
-- copian politicas de usuarios de otro proyecto (sus JWT no se comparten solos).
-- Los permisos se limitan a los objetos de este script; no afectan otras tablas.
DO $security$
DECLARE
    tabla text;
    vista text;
    secuencia text;
BEGIN
    FOREACH tabla IN ARRAY ARRAY[
        'oportunidad', 'oportunidad_item', 'documento_oportunidad', 'perfil_filtro_version',
        'evaluacion_filtro', 'resultado_criterio', 'revision_manual', 'analisis_llm'
    ] LOOP
        EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', tabla);
        EXECUTE format('REVOKE ALL ON TABLE public.%I FROM PUBLIC, anon, authenticated, service_role', tabla);
        EXECUTE format('GRANT SELECT, INSERT ON TABLE public.%I TO service_role', tabla);
        secuencia := pg_get_serial_sequence(format('public.%I', tabla), 'id');
        EXECUTE format('REVOKE ALL ON SEQUENCE %s FROM PUBLIC, anon, authenticated, service_role', secuencia);
        EXECUTE format('GRANT USAGE, SELECT ON SEQUENCE %s TO service_role', secuencia);
    END LOOP;
    FOREACH vista IN ARRAY ARRAY[
        'vw_oportunidades_estado', 'vw_licitaciones_filtradas', 'vw_revision_manual', 'vw_descartadas'
    ] LOOP
        EXECUTE format('REVOKE ALL ON TABLE public.%I FROM PUBLIC, anon, authenticated, service_role', vista);
        EXECUTE format('GRANT SELECT ON TABLE public.%I TO service_role', vista);
    END LOOP;
END;
$security$;

GRANT USAGE ON SCHEMA public TO service_role;
GRANT UPDATE ON TABLE public.oportunidad, public.oportunidad_item,
    public.documento_oportunidad, public.analisis_llm TO service_role;
GRANT UPDATE (activa) ON TABLE public.perfil_filtro_version TO service_role;
REVOKE ALL ON FUNCTION public.lf_versionar_oportunidad() FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.lf_actualizar_version_padre() FROM PUBLIC, anon, authenticated;

-- Evaluaciones, resultados por criterio y revisiones son de solo INSERT/SELECT
-- para el servidor. Una correccion se registra con otra fila, no sobrescribiendo.
-- No se otorga DELETE sobre ninguna de estas tablas a los roles de la API.

COMMIT;

-- Comprobacion de instalacion (solo lectura; cada fila debe indicar true).
SELECT c.relname AS tabla, c.relrowsecurity AS rls_habilitado
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'public' AND c.relkind = 'r' AND c.relname IN (
    'oportunidad', 'oportunidad_item', 'documento_oportunidad', 'perfil_filtro_version',
    'evaluacion_filtro', 'resultado_criterio', 'revision_manual', 'analisis_llm'
)
ORDER BY c.relname;

-- Proximos pasos de integracion, posteriores a ejecutar este archivo:
-- 1. Configurar en el backend la conexion privada al proyecto nuevo.
-- 2. Registrar y validar la primera version del perfil y sus criterios.
-- 3. Implementar copia/sincronizacion, evaluacion, revision y analisis LLM.
-- 4. Consultar estas vistas desde la API; mantener la autenticacion actual.
-- El script no cambia la pagina ni el proyecto de datos originales.
-- Referencias: https://supabase.com/docs/guides/database/postgres/row-level-security
--              https://supabase.com/docs/guides/database/views
