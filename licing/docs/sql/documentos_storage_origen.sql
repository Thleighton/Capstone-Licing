-- Ejecutar únicamente en Usuarios/Licitaciones, después de la migración de Core.
BEGIN;
DO $$ BEGIN
 IF to_regclass('public.licitacion_documento') IS NULL OR to_regclass('public.raw_mercado_publico') IS NULL THEN
  RAISE EXCEPTION 'Se requiere Usuarios/Licitaciones con documentos de origen'; END IF;
END $$;
INSERT INTO storage.buckets(id,name,public,file_size_limit,allowed_mime_types)
VALUES('licitacion-bases','licitacion-bases',false,3145728,ARRAY['application/pdf'])
ON CONFLICT(id) DO UPDATE SET public=false,file_size_limit=3145728,allowed_mime_types=ARRAY['application/pdf'];
CREATE FUNCTION public.documentos_archivos_huerfanos() RETURNS jsonb
LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog AS $$
 SELECT coalesce(jsonb_agg(name),'[]') FROM (
  SELECT s.name FROM storage.objects s WHERE s.bucket_id='licitacion-bases'
   AND s.created_at<clock_timestamp()-interval '1 hour'
   AND NOT EXISTS(SELECT 1 FROM public.licitacion_documento d WHERE d.storage_path=s.name)
  ORDER BY s.created_at LIMIT 100
 ) x
$$;
REVOKE ALL ON FUNCTION public.documentos_archivos_huerfanos() FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.documentos_archivos_huerfanos() TO service_role;
COMMIT;
