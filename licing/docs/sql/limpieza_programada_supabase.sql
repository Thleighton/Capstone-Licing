-- Después de alembic upgrade head. Instalación exclusiva en Supabase.
-- El mismo nombre actualiza el trabajo existente; no crea duplicados.
-- Las tres líneas siguientes son solo para la primera instalación. Si pg_cron ya está
-- configurado, Supabase rechaza repetirlas («dependent privileges exist»): para
-- actualizar el trabajo, ejecuta desde SELECT cron.schedule.
CREATE EXTENSION IF NOT EXISTS pg_cron WITH SCHEMA pg_catalog;
GRANT USAGE ON SCHEMA cron TO postgres;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA cron TO postgres;

SELECT cron.schedule('licing-limpieza-no-disponibles', '* * * * *', $job$
    SET LOCAL lock_timeout = '5s';
    SET LOCAL statement_timeout = '40s';
    SELECT public.purgar_licitaciones_no_disponibles();
    SELECT public.purgar_compras_agiles_no_disponibles();
    DELETE FROM cron.job_run_details
    WHERE jobid = (SELECT jobid FROM cron.job WHERE jobname = 'licing-limpieza-no-disponibles')
      AND end_time < now() - interval '7 days';
$job$);

-- Comprobación: debe aparecer active=true y ejecuciones succeeded.
SELECT jobname, schedule, active FROM cron.job
WHERE jobname = 'licing-limpieza-no-disponibles';
