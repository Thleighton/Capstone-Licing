-- Una sola evaluación vigente, con identificador nuevo cuando cambia su contenido.
-- Las pantallas abiertas conservan el id anterior y no pueden decidir sobre otra versión.
BEGIN;
SET LOCAL lock_timeout='5s';
SET LOCAL statement_timeout='20s';
SELECT pg_advisory_xact_lock(710263,1);
DO $patch$
DECLARE f text;
BEGIN
 f:=pg_get_functiondef('public.lf_operar_pre_guardia_version(text,jsonb)'::regprocedure);
 IF strpos(f,'ON CONFLICT(oportunidad_id) DO UPDATE SET')=0
 OR strpos(f,'DELETE FROM public.revision_manual WHERE evaluacion_id=ev.id;')=0 THEN
  RAISE EXCEPTION 'Se requiere la política de una evaluación vigente';
 END IF;
 f:=replace(f,'DELETE FROM public.revision_manual WHERE evaluacion_id=ev.id;',
  E'DELETE FROM public.revision_manual WHERE evaluacion_id=ev.id;\n    DELETE FROM public.resultado_criterio WHERE evaluacion_id=ev.id;\n    DELETE FROM public.evaluacion_filtro WHERE id=ev.id;');
 EXECUTE f;
END;
$patch$;
COMMENT ON TABLE public.evaluacion_filtro IS 'Una evaluación vigente por oportunidad. Una entrada idéntica conserva su id; un cambio reemplaza la evaluación y su id, sin historial.';
COMMIT;
