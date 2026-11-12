-- Permite ordenar las páginas de preselección por vencimiento o publicación.
-- Se modifica la función compartida que conserva la guardia de versiones.
BEGIN;
DO $migration$
DECLARE
 definicion text;
 original text;
 orden text := $orden$
  ORDER BY
   CASE WHEN coalesce(datos->>'orden_cierre','proximo')='proximo' THEN fecha_cierre END ASC NULLS LAST,
   CASE WHEN datos->>'orden_cierre'='lejano' THEN fecha_cierre END DESC NULLS LAST,
   CASE WHEN datos->>'orden_publicacion'='reciente' THEN fecha_publicacion END DESC NULLS LAST,
   CASE WHEN datos->>'orden_publicacion'='antigua' THEN fecha_publicacion END ASC NULLS LAST,
   id
 $orden$;
BEGIN
 definicion := pg_get_functiondef('public.lf_operar_pre_guardia_version(text,jsonb)'::regprocedure);
 original := definicion;
 definicion := replace(definicion,'v.nombre,v.fecha_cierre,v.url_oficial,','v.nombre,v.fecha_cierre,v.fecha_publicacion,v.url_oficial,');
 definicion := replace(definicion,'SELECT id,codigo_externo,nombre,fecha_cierre,url_oficial,','SELECT id,codigo_externo,nombre,fecha_cierre,fecha_publicacion,url_oficial,');
 definicion := replace(definicion,'SELECT * FROM filtradas ORDER BY fecha_cierre NULLS LAST,id',
  'SELECT * FROM filtradas'||orden);
 definicion := replace(definicion,'END ORDER BY fecha_cierre NULLS LAST,id) FROM pagina',
  'END'||orden||') FROM pagina');
 IF definicion=original OR position('fecha_publicacion' in definicion)=0
    OR position('datos->>''orden_cierre''' in definicion)=0
    OR position('datos->>''orden_publicacion''' in definicion)=0 THEN
  RAISE EXCEPTION 'No se pudo adaptar el listado de preselección al orden solicitado';
 END IF;
 EXECUTE definicion;
END;
$migration$;
COMMIT;
