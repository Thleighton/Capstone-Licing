-- Proyecto LicitacionesFiltradas exclusivamente.
-- Retira lo reservado para fases futuras que la aplicación no usa: la cola de
-- análisis LLM, las puntuaciones semánticas, la acción enviar_a_llm y las vistas
-- por estado. Se detiene si encuentra datos en esos objetos.
BEGIN;
SET LOCAL search_path = pg_catalog, public;
DO $$ BEGIN
 IF to_regclass('public.raw_mercado_publico') IS NOT NULL THEN
  RAISE EXCEPTION 'Proyecto incorrecto: esta migración es para LicitacionesFiltradas';
 END IF;
 IF EXISTS (SELECT 1 FROM public.analisis_llm) THEN
  RAISE EXCEPTION 'analisis_llm tiene filas; revisarlas antes de retirar la tabla';
 END IF;
 IF EXISTS (SELECT 1 FROM public.revision_manual WHERE accion = 'enviar_a_llm') THEN
  RAISE EXCEPTION 'Hay revisiones con la acción enviar_a_llm; revisarlas antes de retirarla';
 END IF;
 IF EXISTS (SELECT 1 FROM public.evaluacion_filtro WHERE modelo_semantico IS NOT NULL
            OR puntuacion_semantica IS NOT NULL OR puntuacion_exclusion IS NOT NULL) THEN
  RAISE EXCEPTION 'Hay evaluaciones con puntuación semántica; revisarlas antes de retirar las columnas';
 END IF;
END $$;

DROP VIEW public.vw_licitaciones_filtradas, public.vw_revision_manual, public.vw_descartadas;
DROP VIEW public.vw_oportunidades_estado;
DO $patch$
DECLARE f text;
BEGIN
 f:=pg_get_functiondef('public.lf_eliminar(bigint[])'::regprocedure);
 f:=replace(f,E' DELETE FROM public.analisis_llm WHERE evaluacion_id IN (SELECT id FROM public.evaluacion_filtro WHERE oportunidad_id=ANY(ids));\n','');
 IF strpos(f,'analisis_llm')<>0 THEN RAISE EXCEPTION 'Limpieza inesperada de lf_eliminar'; END IF;
 EXECUTE f;
 IF strpos(pg_get_functiondef('public.lf_operar(text,jsonb)'::regprocedure),'analisis_llm')<>0 THEN
  RAISE EXCEPTION 'lf_operar todavía usa analisis_llm';
 END IF;
END $patch$;

DROP TABLE public.analisis_llm;

ALTER TABLE public.revision_manual DROP CONSTRAINT revision_manual_accion_check;
ALTER TABLE public.revision_manual ADD CONSTRAINT revision_manual_accion_check
    CHECK (accion IN ('confirmar_relevante','descartar','mantener_pendiente'));

ALTER TABLE public.evaluacion_filtro DROP CONSTRAINT IF EXISTS ck_evaluacion_modelo;
ALTER TABLE public.evaluacion_filtro
    DROP COLUMN modelo_semantico,
    DROP COLUMN puntuacion_semantica,
    DROP COLUMN puntuacion_exclusion;

CREATE VIEW public.vw_oportunidades_estado WITH (security_invoker = true) AS
SELECT
    o.*,
    p.id AS perfil_activo_id,
    e.id AS evaluacion_id,
    e.evaluado_en,
    e.cobertura,
    (e.id IS NOT NULL) AS evaluacion_vigente,
    e.clasificacion AS propuesta_automatica,
    CASE
        WHEN e.id IS NULL THEN 'pendiente_evaluacion'
        WHEN r.accion = 'confirmar_relevante' THEN 'preseleccionada'
        WHEN r.accion = 'descartar' THEN 'descartada'
        WHEN r.accion = 'mantener_pendiente' THEN 'revision_manual'
        ELSE e.clasificacion
    END AS estado_seleccion,
    coalesce(r.motivo, e.motivo, 'Sin evaluacion vigente del contenido y perfil actuales.') AS motivo_seleccion,
    r.id AS revision_id,
    r.relevancia_confirmada,
    r.revisado_por,
    r.revisado_en
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
) r ON true;
REVOKE ALL ON TABLE public.vw_oportunidades_estado FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT ON TABLE public.vw_oportunidades_estado TO service_role;
COMMIT;
