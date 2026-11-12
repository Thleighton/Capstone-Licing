-- Las instancias antiguas no pueden sustituir un motor o catálogo más reciente.
-- El guardado usa el bloqueo de escritura existente; listar continúa sin tomarlo.
BEGIN;
ALTER FUNCTION public.lf_operar(text,jsonb) RENAME TO lf_operar_pre_guardia_version;

CREATE FUNCTION public.lf_operar(operacion text, datos jsonb DEFAULT '{}'::jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path = '' AS $func$
DECLARE
 entrada jsonb;
 aceptadas jsonb := '[]'::jsonb;
 omitidas jsonb := '[]'::jsonb;
 motor integer;
 subversion integer;
 catalogo integer;
 catalogo_actual integer;
 salida jsonb;
BEGIN
 IF operacion <> 'guardar' THEN
  RETURN public.lf_operar_pre_guardia_version(operacion,datos);
 END IF;
 IF jsonb_typeof(datos->'lote') IS DISTINCT FROM 'array' THEN
  RETURN public.lf_operar_pre_guardia_version(operacion,datos);
 END IF;
 IF jsonb_array_length(datos->'lote') NOT BETWEEN 1 AND 20 THEN
  RETURN public.lf_operar_pre_guardia_version(operacion,datos);
 END IF;
 PERFORM pg_advisory_xact_lock(710263,1);
 catalogo := ((regexp_match(datos->'perfil'->>'version','-v([0-9]+)$'))[1])::integer;
 SELECT ((regexp_match(p.criterios->>'version','-v([0-9]+)$'))[1])::integer
  INTO catalogo_actual FROM public.perfil_filtro_version p WHERE p.activa;
 FOR entrada IN SELECT value FROM jsonb_array_elements(datos->'lote') LOOP
  motor := ((regexp_match(entrada->'resultado'->>'version_motor','^reglas-hotel-([0-9]+)'))[1])::integer;
  subversion := coalesce(((regexp_match(entrada->'resultado'->>'version_motor','\+ca-([0-9]+)$'))[1])::integer,0);
  IF catalogo < catalogo_actual OR (motor IS NOT NULL AND EXISTS (
   SELECT 1 FROM public.oportunidad o JOIN public.evaluacion_filtro e ON e.oportunidad_id=o.id
   CROSS JOIN LATERAL (
    SELECT ((regexp_match(e.version_motor,'^reglas-hotel-([0-9]+)'))[1])::integer AS principal,
     coalesce(((regexp_match(e.version_motor,'\+ca-([0-9]+)$'))[1])::integer,0) AS propia
   ) v
   WHERE o.origen='mercado_publico' AND o.codigo_externo=entrada->'datos'->>'codigo_externo'
    AND v.principal IS NOT NULL
    AND (v.principal > motor OR (v.principal=motor AND v.propia > subversion))
  )) THEN
   omitidas := omitidas || jsonb_build_array(entrada->'datos'->>'codigo_externo');
  ELSE
   aceptadas := aceptadas || jsonb_build_array(entrada);
  END IF;
 END LOOP;
 IF jsonb_array_length(aceptadas)=0 THEN
  RETURN jsonb_build_object('evaluadas','[]'::jsonb,'omitidas_version',omitidas);
 END IF;
 salida := public.lf_operar_pre_guardia_version(operacion,jsonb_set(datos,'{lote}',aceptadas));
 RETURN salida || jsonb_build_object('omitidas_version',omitidas);
END;
$func$;
REVOKE ALL ON FUNCTION public.lf_operar(text,jsonb) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.lf_operar(text,jsonb) TO service_role;
COMMIT;
