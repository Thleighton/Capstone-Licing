-- Ejecutar únicamente en Usuarios/Licitaciones, después de documentos_storage_origen.sql.
-- Admite anexos Word y Excel en el bucket privado; mantiene el límite de 3 MB por archivo.
BEGIN;
DO $$ BEGIN
 IF to_regclass('public.licitacion_documento') IS NULL THEN
  RAISE EXCEPTION 'Se requiere Usuarios/Licitaciones con documentos de origen'; END IF;
 UPDATE storage.buckets SET public=false,file_size_limit=3145728,allowed_mime_types=ARRAY[
  'application/pdf',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  'application/msword',
  'application/vnd.ms-excel']
 WHERE id='licitacion-bases';
 IF NOT FOUND THEN
  RAISE EXCEPTION 'Falta el bucket licitacion-bases: aplicar antes documentos_storage_origen.sql'; END IF;
END $$;
COMMIT;
