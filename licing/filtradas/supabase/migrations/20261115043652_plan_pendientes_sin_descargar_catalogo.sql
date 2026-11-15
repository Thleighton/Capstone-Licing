-- El cron reconcilia códigos pendientes sin descargar las fichas ya evaluadas.
-- Conserva la lectura normal, el filtro por RAW y los permisos privados existentes.
BEGIN;
SET LOCAL lock_timeout='5s';
SET LOCAL statement_timeout='20s';
DO $migration$
DECLARE
 definicion text;
 ancla text := E'   WITH codigos AS MATERIALIZED (\n';
 plan text := $plan$
   IF datos->'solo_pendientes'='true'::jsonb THEN
    WITH codigos AS MATERIALIZED (
     SELECT codigo_externo,min(orden) AS orden
     FROM jsonb_array_elements_text(datos->'codigos') WITH ORDINALITY AS solicitado(codigo_externo,orden)
     GROUP BY codigo_externo
    ), fuentes AS MATERIALIZED (
     SELECT key AS codigo_externo,value AS raw_id
     FROM jsonb_each_text(CASE WHEN jsonb_typeof(datos->'fuentes')='object'
       THEN datos->'fuentes' ELSE '{}'::jsonb END)
    ), pendientes AS MATERIALIZED (
     SELECT solicitado.codigo_externo,solicitado.orden FROM codigos solicitado
     LEFT JOIN public.vw_oportunidades_estado v ON v.codigo_externo=solicitado.codigo_externo
     LEFT JOIN fuentes f ON f.codigo_externo=solicitado.codigo_externo
     WHERE v.codigo_externo IS NULL OR v.estado_seleccion='pendiente_evaluacion'
      OR (verificar_fuentes AND v.datos_fuente->>'raw_id' IS DISTINCT FROM f.raw_id)
    ), pagina AS (
     SELECT * FROM pendientes ORDER BY orden LIMIT limite_pagina
    )
    SELECT jsonb_build_object(
     'codigos_pendientes',coalesce((SELECT jsonb_agg(codigo_externo ORDER BY orden) FROM pagina),'[]'::jsonb),
     'total',(SELECT count(*) FROM pendientes)
    ) INTO salida;
    RETURN salida;
   END IF;
$plan$;
BEGIN
 definicion:=pg_get_functiondef('public.lf_operar_pre_guardia_version(text,jsonb)'::regprocedure);
 IF (length(definicion)-length(replace(definicion,ancla,'')))/length(ancla)<>1
    OR strpos(definicion,'verificar_fuentes boolean')=0
    OR strpos(definicion,'limite_pagina integer')=0 THEN
  RAISE EXCEPTION 'El listado no coincide con la versión esperada';
 END IF;
 EXECUTE replace(definicion,ancla,plan||ancla);
END;
$migration$;
COMMIT;
