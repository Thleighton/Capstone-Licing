-- El listado no toma el bloqueo de las escrituras del cron.
-- El listado expande el snapshot una vez y comparte el cruce entre página y total.
BEGIN;
DO $migration$
DECLARE
 definicion text;
 inicio integer;
 fin integer;
 bloqueo text := ' PERFORM pg_advisory_xact_lock(710263,1);';
 listado text := $listado$
 ELSIF operacion='listar' THEN
  DECLARE
   verificar_fuentes boolean := datos ? 'fuentes';
   solo_firmas boolean := coalesce(datos->'solo_firmas'='true'::jsonb,false);
   clasificacion_buscada text := coalesce(datos->>'clasificacion','');
   texto_buscado text := lower(coalesce(datos->>'q',''));
   limite_pagina integer := least(greatest(coalesce((datos->>'limite')::int,25),1),100);
   offset_pagina integer := greatest(coalesce((datos->>'offset')::int,0),0);
  BEGIN
   WITH codigos AS MATERIALIZED (
    SELECT DISTINCT value AS codigo_externo FROM jsonb_array_elements_text(datos->'codigos')
   ), fuentes AS MATERIALIZED (
    SELECT key AS codigo_externo,value AS raw_id
    FROM jsonb_each_text(CASE WHEN jsonb_typeof(datos->'fuentes')='object'
      THEN datos->'fuentes' ELSE '{}'::jsonb END)
   ), vigentes AS MATERIALIZED (
    SELECT v.origen_licitacion_id AS id,v.codigo_externo,v.nombre,v.fecha_cierre,v.url_oficial,
     CASE WHEN verificar_fuentes AND v.datos_fuente->>'raw_id' IS DISTINCT FROM f.raw_id
      THEN 'pendiente_evaluacion' ELSE v.estado_seleccion END AS estado_actual,
     v.motivo_seleccion,v.cobertura,v.evaluacion_id,
     v.datos_fuente->'raw_id' AS fuente_raw_id,v.hash_fuente
    FROM public.vw_oportunidades_estado v
    JOIN codigos solicitados ON solicitados.codigo_externo=v.codigo_externo
    LEFT JOIN fuentes f ON f.codigo_externo=v.codigo_externo
   ), filtradas AS MATERIALIZED (
    SELECT id,codigo_externo,nombre,fecha_cierre,url_oficial,
     estado_actual AS estado_seleccion,
     CASE WHEN estado_actual='pendiente_evaluacion'
      THEN 'Actualiza la preselección: no hay evaluación vigente.' ELSE motivo_seleccion END AS motivo_seleccion,
     cobertura,evaluacion_id,fuente_raw_id,hash_fuente
    FROM vigentes
    WHERE (clasificacion_buscada='' OR estado_actual=clasificacion_buscada)
     AND (texto_buscado='' OR strpos(lower(nombre||' '||codigo_externo),texto_buscado)>0)
   ), pagina AS (
    SELECT * FROM filtradas ORDER BY fecha_cierre NULLS LAST,id
    LIMIT CASE WHEN solo_firmas THEN NULL ELSE limite_pagina END
    OFFSET CASE WHEN solo_firmas THEN 0 ELSE offset_pagina END
   )
   SELECT jsonb_build_object(
    'filas',coalesce((SELECT jsonb_agg(CASE WHEN solo_firmas
     THEN jsonb_build_object('id',id,'codigo_externo',codigo_externo,
      'hash_fuente',hash_fuente,'estado_seleccion',estado_seleccion)
     ELSE to_jsonb(pagina) END ORDER BY fecha_cierre NULLS LAST,id) FROM pagina),'[]'::jsonb),
    'total',(SELECT count(*) FROM filtradas)
   ) INTO salida;
   RETURN salida;
  END;
$listado$;
BEGIN
 definicion := pg_get_functiondef('public.lf_operar(text,jsonb)'::regprocedure);
 inicio := strpos(definicion, E' ELSIF operacion=\'listar\' THEN');
 fin := strpos(definicion, E' ELSIF operacion=\'detalle\' THEN');
 IF inicio=0 OR fin<=inicio OR strpos(definicion,bloqueo)=0 THEN
  RAISE EXCEPTION 'No se encontró la versión esperada de lf_operar';
 END IF;
 definicion := substr(definicion,1,inicio-1)||listado||substr(definicion,fin);
 definicion := replace(definicion,bloqueo,
  E' IF operacion<>\'listar\' THEN\n  PERFORM pg_advisory_xact_lock(710263,1);\n END IF;');
 EXECUTE definicion;
END;
$migration$;
COMMIT;

