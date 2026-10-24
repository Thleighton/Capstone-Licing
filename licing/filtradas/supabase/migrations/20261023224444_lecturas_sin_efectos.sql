-- Las lecturas no ejecutan limpieza. Las bajas se procesan al sincronizar y por cron.
BEGIN;
DO $migration$
DECLARE definicion text; anterior text; nuevo text;
BEGIN
 definicion := pg_get_functiondef('public.lf_operar(text,jsonb)'::regprocedure);
 anterior := E' PERFORM public.lf_purgar_vencidas();';
 nuevo := E' IF operacion IN (\'guardar\',\'revision\',\'guardar_documento\',\'retirar_documento\',\'sincronizar_fuente\') THEN\n  PERFORM public.lf_purgar_vencidas();\n END IF;';
 IF strpos(definicion, anterior)=0 THEN RAISE EXCEPTION 'No se encontró el bloque de limpieza esperado'; END IF;
 EXECUTE replace(definicion, anterior, nuevo);
END;
$migration$;
COMMIT;
