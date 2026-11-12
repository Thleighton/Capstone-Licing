-- Política operativa: una evaluación y una decisión actuales por oportunidad.
-- No conserva snapshots ni un historial de evaluaciones anteriores.
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '60s';
SELECT pg_advisory_xact_lock(710263,1);
SELECT public.lf_purgar_vencidas();
LOCK TABLE public.oportunidad,public.evaluacion_filtro,public.resultado_criterio,
 public.revision_manual IN SHARE ROW EXCLUSIVE MODE;

CREATE TEMP TABLE _lf_vista_antes ON COMMIT DROP AS
 SELECT id,evaluacion_id,revision_id,estado_seleccion,hash_fuente
 FROM public.vw_oportunidades_estado;
CREATE TEMP TABLE _lf_conservar ON COMMIT DROP AS
 SELECT o.id AS oportunidad_id,coalesce(v.evaluacion_id,ultima.id) AS evaluacion_id
 FROM public.oportunidad o
 LEFT JOIN public.vw_oportunidades_estado v ON v.id=o.id
 LEFT JOIN LATERAL (SELECT e.id FROM public.evaluacion_filtro e
  WHERE e.oportunidad_id=o.id ORDER BY e.evaluado_en DESC,e.id DESC LIMIT 1) ultima ON true;

DELETE FROM public.revision_manual r
 WHERE NOT EXISTS(SELECT 1 FROM pg_temp._lf_conservar k WHERE k.evaluacion_id=r.evaluacion_id);
DELETE FROM public.revision_manual r USING public.revision_manual posterior
 WHERE r.evaluacion_id=posterior.evaluacion_id
 AND (r.revisado_en,r.id)<(posterior.revisado_en,posterior.id);
DELETE FROM public.resultado_criterio c
 WHERE NOT EXISTS(SELECT 1 FROM pg_temp._lf_conservar k WHERE k.evaluacion_id=c.evaluacion_id);
DELETE FROM public.evaluacion_filtro e
 WHERE NOT EXISTS(SELECT 1 FROM pg_temp._lf_conservar k WHERE k.evaluacion_id=e.id);

UPDATE public.evaluacion_filtro e SET entrada_evaluada=jsonb_build_object(
 'codigo_externo',o.codigo_externo,
 'raw_id',coalesce(e.entrada_evaluada->'raw_id',e.entrada_evaluada#>'{datos,raw_id}',o.datos_fuente->'raw_id'),
 'documentos',coalesce(e.entrada_evaluada->'documentos','[]'::jsonb))
 FROM public.oportunidad o WHERE o.id=e.oportunidad_id;
DELETE FROM public.perfil_filtro_version p WHERE NOT p.activa
 AND NOT EXISTS(SELECT 1 FROM public.evaluacion_filtro e WHERE e.perfil_version_id=p.id);

ALTER TABLE public.evaluacion_filtro ADD CONSTRAINT uq_evaluacion_oportunidad UNIQUE(oportunidad_id);
ALTER TABLE public.evaluacion_filtro ADD CONSTRAINT ck_evaluacion_referencia CHECK (
 NOT (entrada_evaluada ? 'datos') AND entrada_evaluada ? 'codigo_externo'
 AND (jsonb_typeof(entrada_evaluada->'raw_id')='number') IS TRUE);
ALTER TABLE public.revision_manual DROP CONSTRAINT uq_revision_evaluacion;
ALTER TABLE public.revision_manual ADD CONSTRAINT uq_revision_evaluacion UNIQUE(evaluacion_id);
GRANT UPDATE,DELETE ON public.evaluacion_filtro,public.resultado_criterio,public.revision_manual TO service_role;

DO $patch$
DECLARE
 f text;
 inicio integer;
 fin integer;
 guardar text := $guardar$
   SELECT version_datos INTO version_actual FROM public.oportunidad WHERE id=oid;
   SELECT * INTO ev FROM public.evaluacion_filtro WHERE oportunidad_id=oid;
   IF ev.id IS NULL OR (ev.perfil_version_id,ev.version_datos,ev.version_motor,ev.metadatos->>'huella_entrada')
      IS DISTINCT FROM (perfil.id,version_actual,r->>'version_motor',r->>'huella_entrada') THEN
    -- Una decisión anterior deja de ser vigente cuando cambia lo evaluado.
    DELETE FROM public.revision_manual WHERE evaluacion_id=ev.id;
    INSERT INTO public.evaluacion_filtro(oportunidad_id,perfil_version_id,version_datos,version_motor,cobertura,clasificacion,motivo,entrada_evaluada,metadatos)
    VALUES(oid,perfil.id,version_actual,r->>'version_motor',r->>'cobertura',r->>'clasificacion',r->>'motivo',
     jsonb_build_object('codigo_externo',d->>'codigo_externo','raw_id',d->'raw_id','documentos',docs),r-'criterios')
    ON CONFLICT(oportunidad_id) DO UPDATE SET
     perfil_version_id=excluded.perfil_version_id,version_datos=excluded.version_datos,
     version_motor=excluded.version_motor,cobertura=excluded.cobertura,clasificacion=excluded.clasificacion,
     motivo=excluded.motivo,entrada_evaluada=excluded.entrada_evaluada,metadatos=excluded.metadatos,
     clave_ejecucion=gen_random_uuid(),evaluado_en=clock_timestamp()
    RETURNING id INTO eid;
    DELETE FROM public.resultado_criterio WHERE evaluacion_id=eid
     AND codigo NOT IN(SELECT key FROM jsonb_each(r->'criterios'));
    FOR c IN SELECT key,value FROM jsonb_each(r->'criterios') LOOP
     INSERT INTO public.resultado_criterio(evaluacion_id,codigo,nombre,caracter,resultado,motivo,valor_observado,evidencias)
     VALUES(eid,c.key,c.key,'obligatorio',c.value->>'resultado',coalesce(c.value->>'motivo',r->>'motivo'),c.value,
      coalesce(c.value->'evidencias',c.value->'coincidencias','[]'))
     ON CONFLICT(evaluacion_id,codigo) DO UPDATE SET
      nombre=excluded.nombre,caracter=excluded.caracter,resultado=excluded.resultado,
      motivo=excluded.motivo,valor_observado=excluded.valor_observado,evidencias=excluded.evidencias;
    END LOOP;
   ELSE eid:=ev.id;
   END IF;
   salida:=salida||jsonb_build_array(jsonb_build_object('codigo',d->>'codigo_externo','evaluacion_id',eid));
  END LOOP;
  RETURN jsonb_build_object('evaluadas',salida);
 $guardar$;
BEGIN
 f:=pg_get_functiondef('public.lf_operar_pre_guardia_version(text,jsonb)'::regprocedure);
 inicio:=strpos(f,'   SELECT version_datos INTO version_actual');
 fin:=strpos(f,E' ELSIF operacion=''sincronizar_fuente'' THEN');
 IF inicio=0 OR fin<=inicio THEN RAISE EXCEPTION 'Guardado de preselección inesperado'; END IF;
 f:=substr(f,1,inicio-1)||guardar||substr(f,fin);
 -- Evita también nuevas versiones físicas de ítems que no cambiaron.
 IF strpos(f,'adjudicacion_fuente=excluded.adjudicacion_fuente,vigente=true;')=0 THEN
  RAISE EXCEPTION 'Guardado de ítems inesperado';
 END IF;
 f:=replace(f,'adjudicacion_fuente=excluded.adjudicacion_fuente,vigente=true;',
  $items$adjudicacion_fuente=excluded.adjudicacion_fuente,vigente=true
  WHERE (public.oportunidad_item.correlativo,public.oportunidad_item.codigo_producto,
   public.oportunidad_item.nombre_producto,public.oportunidad_item.descripcion,
   public.oportunidad_item.cantidad,public.oportunidad_item.unidad_medida,
   public.oportunidad_item.codigo_categoria,public.oportunidad_item.categoria,
   public.oportunidad_item.estado_fuente,public.oportunidad_item.adjudicacion_fuente,public.oportunidad_item.vigente)
  IS DISTINCT FROM (excluded.correlativo,excluded.codigo_producto,excluded.nombre_producto,excluded.descripcion,
   excluded.cantidad,excluded.unidad_medida,excluded.codigo_categoria,excluded.categoria,
   excluded.estado_fuente,excluded.adjudicacion_fuente,true);$items$);
 IF strpos(f,E'   datos->>''categoria_motivo'',datos->>''motivo'',(datos->>''usuario'')::uuid);')=0 THEN
  RAISE EXCEPTION 'Guardado de decisión inesperado';
 END IF;
 f:=replace(f,E'   datos->>''categoria_motivo'',datos->>''motivo'',(datos->>''usuario'')::uuid);',
  E'   datos->>''categoria_motivo'',datos->>''motivo'',(datos->>''usuario'')::uuid)\n  ON CONFLICT(evaluacion_id) DO UPDATE SET accion=excluded.accion,\n   relevancia_confirmada=excluded.relevancia_confirmada,categoria_motivo=excluded.categoria_motivo,\n   motivo=excluded.motivo,revisado_por=excluded.revisado_por,revisado_en=clock_timestamp();');
 EXECUTE f;
END;
$patch$;

-- Mantiene la misma limpieza de vencidas y retira perfiles sin uso.
CREATE OR REPLACE FUNCTION public.lf_purgar_vencidas()
RETURNS integer LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $func$
DECLARE ids bigint[]; n integer;
BEGIN
 PERFORM pg_advisory_xact_lock(710263,1);
 SELECT array_agg(id) INTO ids FROM public.oportunidad
  WHERE fecha_cierre<=clock_timestamp() OR codigo_estado IN(6,7,8,18,19);
 n:=public.lf_eliminar(ids);
 DELETE FROM public.perfil_filtro_version p WHERE NOT p.activa
  AND NOT EXISTS(SELECT 1 FROM public.evaluacion_filtro e WHERE e.perfil_version_id=p.id);
 RETURN n;
END;
$func$;
REVOKE ALL ON FUNCTION public.lf_purgar_vencidas() FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.lf_purgar_vencidas() TO service_role;
COMMENT ON TABLE public.evaluacion_filtro IS 'Una evaluación vigente por oportunidad; las actualizaciones reemplazan su contenido.';
COMMENT ON COLUMN public.evaluacion_filtro.entrada_evaluada IS 'Referencias al RAW y documentos de origen; no copia la ficha ni sus ítems.';
COMMENT ON TABLE public.revision_manual IS 'Última decisión del usuario sobre la evaluación vigente, sin historial.';

DO $verify$
BEGIN
 IF EXISTS(SELECT id,evaluacion_id,revision_id,estado_seleccion,hash_fuente FROM pg_temp._lf_vista_antes
  EXCEPT SELECT id,evaluacion_id,revision_id,estado_seleccion,hash_fuente FROM public.vw_oportunidades_estado) THEN
  RAISE EXCEPTION 'La limpieza alteró una clasificación o decisión vigente';
 END IF;
END;
$verify$;
COMMIT;
