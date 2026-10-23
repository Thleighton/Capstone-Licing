-- Proyecto LicitacionesFiltradas exclusivamente. No añade tablas.
BEGIN;
SET LOCAL search_path = pg_catalog, public;
DO $$ BEGIN
 IF to_regclass('public.raw_mercado_publico') IS NOT NULL THEN
  RAISE EXCEPTION 'Proyecto incorrecto: esta migración es para LicitacionesFiltradas';
 END IF;
END $$;
ALTER TABLE public.oportunidad_item ADD COLUMN posicion_fuente integer;
WITH posiciones AS (
 SELECT id, row_number() OVER (PARTITION BY oportunidad_id ORDER BY id)::integer AS posicion
 FROM public.oportunidad_item
) UPDATE public.oportunidad_item i SET posicion_fuente=p.posicion FROM posiciones p WHERE p.id=i.id;
ALTER TABLE public.oportunidad_item ALTER COLUMN posicion_fuente SET NOT NULL;
ALTER TABLE public.oportunidad_item ADD CHECK (posicion_fuente > 0);
ALTER TABLE public.oportunidad_item DROP CONSTRAINT uq_oportunidad_item;
ALTER TABLE public.oportunidad_item ADD CONSTRAINT uq_oportunidad_item UNIQUE(oportunidad_id,posicion_fuente);
ALTER TABLE public.revision_manual DROP CONSTRAINT revision_manual_accion_check;
ALTER TABLE public.revision_manual ADD CHECK (accion IN ('enviar_a_llm','confirmar_relevante','descartar','mantener_pendiente'));
CREATE OR REPLACE VIEW public.vw_oportunidades_estado WITH (security_invoker = true) AS
SELECT
    o.*,
    p.id AS perfil_activo_id,
    e.id AS evaluacion_id,
    e.evaluado_en,
    e.cobertura,
    e.puntuacion_semantica,
    e.puntuacion_exclusion,
    (e.id IS NOT NULL) AS evaluacion_vigente,
    e.clasificacion AS propuesta_automatica,
    CASE
        WHEN e.id IS NULL THEN 'pendiente_evaluacion'
        WHEN r.accion IN ('enviar_a_llm','confirmar_relevante') THEN 'preseleccionada'
        WHEN r.accion = 'descartar' THEN 'descartada'
        WHEN r.accion = 'mantener_pendiente' THEN 'revision_manual'
        ELSE e.clasificacion
    END AS estado_seleccion,
    coalesce(r.motivo, e.motivo, 'Sin evaluacion vigente del contenido y perfil actuales.') AS motivo_seleccion,
    r.id AS revision_id,
    r.relevancia_confirmada,
    r.revisado_por,
    r.revisado_en,
    a.id AS analisis_id,
    coalesce(a.estado, 'sin_solicitar') AS estado_analisis_llm,
    a.resumen AS resumen_llm,
    a.finalizado_en AS analizado_en
FROM public.oportunidad o
LEFT JOIN public.perfil_filtro_version p ON p.activa
LEFT JOIN LATERAL (
    SELECT ev.* FROM public.evaluacion_filtro ev
    WHERE ev.oportunidad_id = o.id
      AND ev.perfil_version_id = p.id
      AND ev.version_datos = o.version_datos
    ORDER BY ev.evaluado_en DESC, ev.id DESC LIMIT 1
) e ON true
LEFT JOIN LATERAL (
    SELECT rm.* FROM public.revision_manual rm WHERE rm.evaluacion_id = e.id
    ORDER BY rm.revisado_en DESC, rm.id DESC LIMIT 1
) r ON true
LEFT JOIN LATERAL (
    SELECT al.* FROM public.analisis_llm al
    WHERE al.evaluacion_id = e.id AND al.revision_id IS NOT DISTINCT FROM r.id
    ORDER BY al.solicitado_en DESC, al.id DESC LIMIT 1
) a ON true;


-- Solo el servidor autenticado puede invocar estas operaciones atómicas.
CREATE FUNCTION public.lf_eliminar(ids bigint[]) RETURNS integer
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE n integer;
BEGIN
 PERFORM pg_advisory_xact_lock(710263,1);
 IF ids IS NULL THEN RETURN 0; END IF;
 DELETE FROM public.analisis_llm WHERE evaluacion_id IN (SELECT id FROM public.evaluacion_filtro WHERE oportunidad_id=ANY(ids));
 DELETE FROM public.revision_manual WHERE evaluacion_id IN (SELECT id FROM public.evaluacion_filtro WHERE oportunidad_id=ANY(ids));
 DELETE FROM public.resultado_criterio WHERE evaluacion_id IN (SELECT id FROM public.evaluacion_filtro WHERE oportunidad_id=ANY(ids));
 DELETE FROM public.evaluacion_filtro WHERE oportunidad_id=ANY(ids);
 DELETE FROM public.documento_oportunidad WHERE oportunidad_id=ANY(ids);
 DELETE FROM public.oportunidad_item WHERE oportunidad_id=ANY(ids);
 DELETE FROM public.oportunidad WHERE id=ANY(ids);
 GET DIAGNOSTICS n=ROW_COUNT;
 RETURN n;
END $$;
REVOKE ALL ON FUNCTION public.lf_eliminar(bigint[]) FROM PUBLIC,anon,authenticated,service_role;

CREATE FUNCTION public.lf_purgar_vencidas() RETURNS integer
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE ids bigint[];
BEGIN
 PERFORM pg_advisory_xact_lock(710263,1);
 SELECT array_agg(id) INTO ids FROM public.oportunidad
 WHERE fecha_cierre <= clock_timestamp() OR codigo_estado IN (6,7,8,18,19);
 RETURN public.lf_eliminar(ids);
END $$;

CREATE FUNCTION public.lf_operar(operacion text, datos jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE
 lote jsonb; d jsonb; r jsonb; it jsonb; c record; o public.oportunidad;
 perfil public.perfil_filtro_version; ev public.evaluacion_filtro;
 doc public.documento_oportunidad; oid bigint; eid bigint; docs jsonb; salida jsonb:='[]';
 actor uuid; filas jsonb; total integer; version_actual bigint; hash_actual text;
BEGIN
 IF jsonb_typeof(datos) <> 'object' OR octet_length(datos::text)>16000000 THEN
  RAISE EXCEPTION 'Entrada inválida';
 END IF;
 PERFORM pg_advisory_xact_lock(710263,1);
 PERFORM public.lf_purgar_vencidas();
 IF operacion='guardar' THEN
  IF jsonb_typeof(datos->'lote') <> 'array' OR jsonb_array_length(datos->'lote') NOT BETWEEN 1 AND 20 THEN
   RAISE EXCEPTION 'Lote inválido';
  END IF;
  SELECT * INTO perfil FROM public.perfil_filtro_version WHERE activa;
  IF perfil.id IS NULL OR perfil.criterios IS DISTINCT FROM datos->'perfil' THEN
   actor := (datos->>'actor')::uuid;
   IF actor IS NULL THEN RAISE EXCEPTION 'Inicializa el perfil desde el dashboard'; END IF;
   UPDATE public.perfil_filtro_version SET activa=false WHERE activa;
   INSERT INTO public.perfil_filtro_version(version,nombre,descripcion_oferta,criterios,fuentes,validada,activa,creado_por)
   SELECT coalesce(max(version),0)+1,'Hotel Plaza San Francisco: preselección',
    'Habitaciones y salones en la RM. Las capacidades y disponibilidades se revisan; no decide postular.',
    datos->'perfil', '["Correo del hotel 19-10-2026","SALONES HPSF.pdf"]',true,true,actor
   FROM public.perfil_filtro_version RETURNING * INTO perfil;
  END IF;
  FOR lote IN SELECT value FROM jsonb_array_elements(datos->'lote') LOOP
   d:=lote->'datos'; r:=lote->'resultado';
   IF d->>'codigo_externo' ~* '-COT[0-9]*$' THEN RAISE EXCEPTION 'Compra Ágil fuera de alcance'; END IF;
   IF (d->>'fecha_cierre')::timestamptz <= clock_timestamp() OR (d->>'codigo_estado')::int IN (6,7,8,18,19) THEN
    CONTINUE;
   END IF;
   SELECT * INTO o FROM public.oportunidad WHERE origen='mercado_publico' AND codigo_externo=d->>'codigo_externo' FOR UPDATE;
   IF o.id IS NOT NULL AND (o.datos_fuente->>'raw_id')::bigint > (d->>'raw_id')::bigint THEN
    RAISE EXCEPTION 'La fuente cambió; vuelve a evaluar' USING ERRCODE='40001';
   END IF;
   INSERT INTO public.oportunidad(origen,codigo_externo,modalidad,origen_proyecto,origen_licitacion_id,nombre,descripcion,codigo_estado,estado,tipo,codigo_tipo,monto_estimado,moneda,estimacion,visibilidad_monto,justificacion_monto,fecha_publicacion,fecha_cierre,codigo_organismo,nombre_organismo,codigo_unidad,nombre_unidad,region_comprador,comuna_comprador,direccion_comprador,direccion_entrega,direccion_visita,fechas_fuente,condiciones_fuente,url_oficial,datos_fuente,hash_fuente)
   SELECT 'mercado_publico',x.codigo_externo,'licitacion','nylzzocvemddikexqzav',(d->>'id')::bigint,coalesce(nullif(x.nombre,''),x.codigo_externo),x.descripcion,x.codigo_estado,x.estado,x.tipo,x.codigo_tipo,x.monto_estimado,x.moneda,x.estimacion,x.visibilidad_monto,x.justificacion_monto,x.fecha_publicacion,x.fecha_cierre,x.codigo_organismo,x.nombre_organismo,x.codigo_unidad,x.nombre_unidad,x.region_comprador,x.comuna_comprador,x.direccion_comprador,x.direccion_entrega,x.direccion_visita,coalesce(x.fechas_fuente,'{}'::jsonb),coalesce(x.condiciones_fuente,'{}'::jsonb),x.url_oficial,jsonb_build_object('raw_id',d->'raw_id','normalizacion_version',d->'normalizacion_version','ubicacion_servicio',d->'ubicacion_servicio'),lote->>'hash_fuente'
   FROM jsonb_populate_record(NULL::public.oportunidad,d) x
   ON CONFLICT (origen,codigo_externo) DO UPDATE SET nombre=excluded.nombre,descripcion=excluded.descripcion,codigo_estado=excluded.codigo_estado,estado=excluded.estado,tipo=excluded.tipo,codigo_tipo=excluded.codigo_tipo,monto_estimado=excluded.monto_estimado,moneda=excluded.moneda,estimacion=excluded.estimacion,visibilidad_monto=excluded.visibilidad_monto,justificacion_monto=excluded.justificacion_monto,fecha_publicacion=excluded.fecha_publicacion,fecha_cierre=excluded.fecha_cierre,codigo_organismo=excluded.codigo_organismo,nombre_organismo=excluded.nombre_organismo,codigo_unidad=excluded.codigo_unidad,nombre_unidad=excluded.nombre_unidad,region_comprador=excluded.region_comprador,comuna_comprador=excluded.comuna_comprador,direccion_comprador=excluded.direccion_comprador,direccion_entrega=excluded.direccion_entrega,direccion_visita=excluded.direccion_visita,fechas_fuente=excluded.fechas_fuente,condiciones_fuente=excluded.condiciones_fuente,url_oficial=excluded.url_oficial,origen_licitacion_id=excluded.origen_licitacion_id,datos_fuente=excluded.datos_fuente,hash_fuente=excluded.hash_fuente WHERE public.oportunidad.hash_fuente IS DISTINCT FROM excluded.hash_fuente;
   SELECT id INTO oid FROM public.oportunidad WHERE origen='mercado_publico' AND codigo_externo=d->>'codigo_externo';
   SELECT coalesce(jsonb_agg(jsonb_build_array(id,version,hash_archivo) ORDER BY id),'[]') INTO docs
   FROM public.documento_oportunidad WHERE oportunidad_id=oid AND vigente;
   IF docs IS DISTINCT FROM lote->'documentos_version' THEN
    RAISE EXCEPTION 'Los documentos cambiaron; vuelve a evaluar' USING ERRCODE='40001';
   END IF;
   FOR it IN SELECT value FROM jsonb_array_elements(coalesce(d->'items','[]')) LOOP
    INSERT INTO public.oportunidad_item(oportunidad_id,posicion_fuente,correlativo,codigo_producto,nombre_producto,descripcion,cantidad,unidad_medida,codigo_categoria,categoria,estado_fuente,adjudicacion_fuente,vigente)
    SELECT oid,x.posicion_fuente,x.correlativo,x.codigo_producto,x.nombre_producto,x.descripcion,x.cantidad,x.unidad_medida,x.codigo_categoria,x.categoria,x.estado_fuente,x.adjudicacion_fuente,true
    FROM jsonb_populate_record(NULL::public.oportunidad_item,it) x
    ON CONFLICT (oportunidad_id,posicion_fuente) DO UPDATE SET
     correlativo=excluded.correlativo,codigo_producto=excluded.codigo_producto,nombre_producto=excluded.nombre_producto,
     descripcion=excluded.descripcion,cantidad=excluded.cantidad,unidad_medida=excluded.unidad_medida,
     codigo_categoria=excluded.codigo_categoria,categoria=excluded.categoria,estado_fuente=excluded.estado_fuente,
     adjudicacion_fuente=excluded.adjudicacion_fuente,vigente=true;
   END LOOP;
   UPDATE public.oportunidad_item SET vigente=false WHERE oportunidad_id=oid AND vigente
    AND posicion_fuente NOT IN (SELECT (value->>'posicion_fuente')::int FROM jsonb_array_elements(coalesce(d->'items','[]')));
   SELECT version_datos INTO version_actual FROM public.oportunidad WHERE id=oid;
   SELECT * INTO ev FROM public.evaluacion_filtro WHERE oportunidad_id=oid AND perfil_version_id=perfil.id
    AND version_datos=version_actual AND version_motor=r->>'version_motor'
    AND metadatos->>'huella_entrada'=r->>'huella_entrada' ORDER BY id DESC LIMIT 1;
   IF ev.id IS NULL THEN
    INSERT INTO public.evaluacion_filtro(oportunidad_id,perfil_version_id,version_datos,version_motor,cobertura,clasificacion,motivo,entrada_evaluada,metadatos)
    VALUES(oid,perfil.id,version_actual,r->>'version_motor',r->>'cobertura',r->>'clasificacion',r->>'motivo',
     jsonb_build_object('datos',d,'documentos',docs),r-'criterios') RETURNING id INTO eid;
    FOR c IN SELECT key,value FROM jsonb_each(r->'criterios') LOOP
     INSERT INTO public.resultado_criterio(evaluacion_id,codigo,nombre,caracter,resultado,motivo,valor_observado,evidencias)
     VALUES(eid,c.key,c.key,'obligatorio',c.value->>'resultado',coalesce(c.value->>'motivo',r->>'motivo'),c.value,
      coalesce(c.value->'evidencias',c.value->'coincidencias','[]'));
    END LOOP;
   ELSE eid:=ev.id;
   END IF;
   salida:=salida||jsonb_build_array(jsonb_build_object('codigo',d->>'codigo_externo','evaluacion_id',eid));
  END LOOP;
  RETURN jsonb_build_object('evaluadas',salida);
 ELSIF operacion='sincronizar_fuente' THEN
  IF jsonb_typeof(datos->'codigos') IS DISTINCT FROM 'array' OR datos->>'observado_en' IS NULL THEN
   RAISE EXCEPTION 'Falta snapshot completo de la fuente';
  END IF;
  RETURN jsonb_build_object('eliminadas', public.lf_eliminar(ARRAY(
   SELECT id FROM public.oportunidad WHERE origen='mercado_publico'
    AND sincronizado_en < (datos->>'observado_en')::timestamptz
    AND codigo_externo NOT IN (SELECT jsonb_array_elements_text(datos->'codigos'))
  )));
 ELSIF operacion='documentos' THEN
  SELECT coalesce(jsonb_object_agg(codigo_externo,documentos),'{}') INTO salida FROM (
   SELECT src.codigo_externo,jsonb_agg(jsonb_build_object('id',dr.id,'version',dr.version,'hash_archivo',dr.hash_archivo,
    'estado_extraccion',dr.estado_extraccion,'vigente',dr.vigente,'paginas_texto',dr.cobertura->'paginas_texto') ORDER BY dr.id) AS documentos
   FROM public.oportunidad src JOIN public.documento_oportunidad dr ON dr.oportunidad_id=src.id AND dr.vigente
   WHERE src.codigo_externo IN (SELECT jsonb_array_elements_text(datos->'codigos')) GROUP BY src.codigo_externo
  ) x;
  RETURN salida;
 ELSIF operacion='listar' THEN
  SELECT coalesce(jsonb_agg(to_jsonb(x)),'[]') INTO filas FROM (
   SELECT origen_licitacion_id AS id,codigo_externo,nombre,fecha_cierre,url_oficial,estado_actual AS estado_seleccion,CASE WHEN estado_actual='pendiente_evaluacion' THEN 'Actualiza la preselección: no hay evaluación vigente.' ELSE motivo_seleccion END AS motivo_seleccion,cobertura,evaluacion_id,datos_fuente->'raw_id' AS fuente_raw_id
   FROM (SELECT v.*, CASE WHEN datos ? 'fuentes' AND v.datos_fuente->>'raw_id' IS DISTINCT FROM datos->'fuentes'->>v.codigo_externo
     THEN 'pendiente_evaluacion' ELSE v.estado_seleccion END AS estado_actual FROM public.vw_oportunidades_estado v) vigentes
   WHERE codigo_externo IN (SELECT jsonb_array_elements_text(datos->'codigos'))
    AND (coalesce(datos->>'clasificacion','')='' OR estado_actual=datos->>'clasificacion')
    AND (coalesce(datos->>'q','')='' OR strpos(lower(nombre||' '||codigo_externo),lower(datos->>'q'))>0)
   ORDER BY fecha_cierre NULLS LAST,id LIMIT least(greatest(coalesce((datos->>'limite')::int,25),1),100)
   OFFSET greatest(coalesce((datos->>'offset')::int,0),0)
  ) x;
  SELECT count(*) INTO total FROM (SELECT v.*, CASE WHEN datos ? 'fuentes' AND v.datos_fuente->>'raw_id' IS DISTINCT FROM datos->'fuentes'->>v.codigo_externo
     THEN 'pendiente_evaluacion' ELSE v.estado_seleccion END AS estado_actual FROM public.vw_oportunidades_estado v) vigentes
   WHERE codigo_externo IN (SELECT jsonb_array_elements_text(datos->'codigos'))
    AND (coalesce(datos->>'clasificacion','')='' OR estado_actual=datos->>'clasificacion')
    AND (coalesce(datos->>'q','')='' OR strpos(lower(nombre||' '||codigo_externo),lower(datos->>'q'))>0);
  RETURN jsonb_build_object('filas',filas,'total',total);
 ELSIF operacion='detalle' THEN
  SELECT * INTO o FROM public.oportunidad WHERE codigo_externo=datos->>'codigo';
  SELECT evaluacion_id INTO eid FROM public.vw_oportunidades_estado WHERE id=o.id;
  SELECT to_jsonb(e) INTO r FROM public.evaluacion_filtro e WHERE id=eid;
  SELECT coalesce(jsonb_agg(to_jsonb(rc)),'[]') INTO filas FROM public.resultado_criterio rc WHERE evaluacion_id=eid;
  SELECT coalesce(jsonb_agg(to_jsonb(dr)-'texto_extraido'-'cobertura'||jsonb_build_object('cobertura',dr.cobertura-'paginas_texto')),'[]') INTO docs
   FROM public.documento_oportunidad dr WHERE oportunidad_id=o.id AND vigente;
  RETURN jsonb_build_object('raw_id',o.datos_fuente->'raw_id','hash_fuente',o.hash_fuente,'evaluacion',r-'entrada_evaluada','criterios',filas,'documentos',docs);
 ELSIF operacion='revision' THEN
  SELECT * INTO o FROM public.oportunidad WHERE codigo_externo=datos->>'codigo' FOR UPDATE;
  SELECT evaluacion_id INTO eid FROM public.vw_oportunidades_estado WHERE id=o.id;
  IF eid IS NULL OR eid<>(datos->>'evaluacion_id')::bigint OR o.datos_fuente->>'raw_id' IS DISTINCT FROM datos->>'raw_id' OR o.hash_fuente IS DISTINCT FROM datos->>'hash_fuente' THEN
   RAISE EXCEPTION 'La evaluación cambió; actualiza antes de revisar' USING ERRCODE='40001';
  END IF;
  IF datos->>'accion' NOT IN ('confirmar_relevante','descartar','mantener_pendiente') THEN RAISE EXCEPTION 'Acción inválida'; END IF;
  INSERT INTO public.revision_manual(evaluacion_id,accion,relevancia_confirmada,categoria_motivo,motivo,revisado_por)
  VALUES(eid,datos->>'accion',CASE WHEN datos->>'accion'='confirmar_relevante' THEN 'relevante' ELSE 'sin_determinar' END,
   datos->>'categoria_motivo',datos->>'motivo',(datos->>'usuario')::uuid);
  RETURN jsonb_build_object('guardada',true);
 ELSIF operacion='retirar_documento' THEN
  UPDATE public.documento_oportunidad SET vigente=false WHERE id=(datos->>'documento_id')::bigint
   AND oportunidad_id IN (SELECT id FROM public.oportunidad WHERE codigo_externo=datos->>'codigo');
  RETURN jsonb_build_object('retirado',true);
 ELSIF operacion='guardar_documento' THEN
  SELECT * INTO o FROM public.oportunidad WHERE codigo_externo=datos->>'codigo' FOR UPDATE;
  IF o.id IS NULL THEN RAISE EXCEPTION 'Licitación no disponible'; END IF;
  SELECT * INTO doc FROM public.documento_oportunidad WHERE oportunidad_id=o.id AND hash_archivo=datos->'extraccion'->>'hash_archivo' ORDER BY id DESC LIMIT 1;
  IF doc.id IS NOT NULL THEN
   UPDATE public.documento_oportunidad SET vigente=true WHERE id=doc.id;
   RETURN jsonb_build_object('id',doc.id,'reutilizado',true); END IF;
  IF (SELECT count(*) FROM public.documento_oportunidad WHERE oportunidad_id=o.id AND vigente)>=10 THEN
   RAISE EXCEPTION 'Máximo 10 documentos por licitación';
  END IF;
  d:=datos->'extraccion';
  INSERT INTO public.documento_oportunidad(oportunidad_id,nombre,tipo,url_origen,hash_archivo,estado_extraccion,texto_extraido,paginas,cobertura,extraido_en)
  VALUES(o.id,datos->>'nombre',datos->>'tipo',datos->>'url_origen',d->>'hash_archivo',d->>'estado_extraccion',
   (SELECT string_agg(value->>'texto',E'\n' ORDER BY (value->>'pagina')::int) FROM jsonb_array_elements(d->'paginas_texto')),
   (d->>'paginas')::int,(d->'cobertura')||jsonb_build_object('paginas_texto',d->'paginas_texto','storage_path',datos->>'storage_path',
     'version_extractor',d->>'version_extractor','subido_por',datos->>'usuario'),clock_timestamp()) RETURNING * INTO doc;
  RETURN jsonb_build_object('id',doc.id,'estado_extraccion',doc.estado_extraccion);
 ELSE RAISE EXCEPTION 'Operación no admitida';
 END IF;
END $$;
REVOKE ALL ON FUNCTION public.lf_operar(text,jsonb),public.lf_purgar_vencidas() FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.lf_operar(text,jsonb),public.lf_purgar_vencidas() TO service_role;
COMMIT;
