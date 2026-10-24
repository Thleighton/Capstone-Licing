-- Filtradas conserva referencias en la evaluación; los documentos pertenecen a Core.
BEGIN;
DO $$ BEGIN
 LOCK TABLE public.documento_oportunidad IN ACCESS EXCLUSIVE MODE;
 IF EXISTS(SELECT 1 FROM public.documento_oportunidad) THEN
  RAISE EXCEPTION 'Hay documentos: migrarlos a origen antes de retirar el almacenamiento'; END IF;
END $$;
DO $patch$
DECLARE f text; inicio integer; fin integer;
BEGIN
 f:=pg_get_functiondef('public.lf_operar(text,jsonb)'::regprocedure);
 inicio:=strpos(f,'   SELECT coalesce(jsonb_agg(jsonb_build_array(id,version,hash_archivo) ORDER BY id)');
 fin:=strpos(f,'   FOR it IN SELECT');
 IF inicio=0 OR fin<=inicio THEN RAISE EXCEPTION 'Bloque documental inesperado'; END IF;
 f:=overlay(f placing E'   docs:=coalesce(lote->''documentos_version'',''[]'');\n' from inicio for fin-inicio);
 inicio:=strpos(f,E' ELSIF operacion=''documentos'' THEN');
 fin:=strpos(f,E' ELSIF operacion=''listar'' THEN');
 IF inicio=0 OR fin<=inicio THEN RAISE EXCEPTION 'Lectura documental inesperada'; END IF;
 f:=overlay(f placing '' from inicio for fin-inicio);
 inicio:=strpos(f,'  SELECT coalesce(jsonb_agg(to_jsonb(dr)');
 fin:=strpos(f,'  RETURN jsonb_build_object(''raw_id''');
 IF inicio=0 OR fin<=inicio THEN RAISE EXCEPTION 'Detalle documental inesperado'; END IF;
 f:=overlay(f placing E'  docs:=''[]'';\n' from inicio for fin-inicio);
 f:=replace(f,'''ingesta_documental'',o.ingesta_documental-''token'', ', '');
 f:=replace(f,'datos_fuente->''raw_id'' AS fuente_raw_id', 'datos_fuente->''raw_id'' AS fuente_raw_id,hash_fuente');
 inicio:=strpos(f,E' ELSIF operacion=''retirar_documento'' THEN');
 fin:=strpos(f,E' ELSE RAISE EXCEPTION ''Operación no admitida'';');
 IF inicio=0 OR fin<=inicio THEN RAISE EXCEPTION 'Escritura documental inesperada'; END IF;
 f:=overlay(f placing '' from inicio for fin-inicio);
 f:=replace(f,'doc public.documento_oportunidad; ', '');
 IF strpos(f,'public.documento_oportunidad')<>0 OR strpos(f,'o.ingesta_documental')<>0 THEN
  RAISE EXCEPTION 'Persisten dependencias documentales'; END IF;
 EXECUTE f;
 f:=pg_get_functiondef('public.lf_eliminar(bigint[])'::regprocedure);
 f:=replace(f,E' DELETE FROM public.documento_oportunidad WHERE oportunidad_id=ANY(ids);\n','');
 IF strpos(f,'public.documento_oportunidad')<>0 THEN RAISE EXCEPTION 'Limpieza inesperada'; END IF;
 EXECUTE f;
END $patch$;
DROP FUNCTION public.lf_documental(text,jsonb);
DROP TABLE public.documento_oportunidad;
ALTER TABLE public.oportunidad DROP COLUMN ingesta_documental;
-- Compatibilidad con el adaptador anterior: ya no hay binarios de filtradas que gestionar.
DO $$ BEGIN
 IF to_regprocedure('public.lf_archivos_huerfanos()') IS NOT NULL THEN
  EXECUTE 'CREATE OR REPLACE FUNCTION public.lf_archivos_huerfanos() RETURNS jsonb LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog AS $f$ SELECT ''[]''::jsonb $f$';
 END IF;
 IF to_regclass('storage.buckets') IS NOT NULL THEN
  UPDATE storage.buckets SET public=false,file_size_limit=1 WHERE id='licitacion-bases';
 END IF;
END $$;
COMMIT;
