-- Solo LicitacionesFiltradas. Reutiliza documentos; no crea tablas.
BEGIN;
ALTER TABLE public.oportunidad ADD COLUMN ingesta_documental jsonb NOT NULL DEFAULT '{}'
 CHECK (jsonb_typeof(ingesta_documental)='object');
COMMENT ON COLUMN public.oportunidad.ingesta_documental IS
 'Estado de descarga, reserva temporal y reintentos. No implica que estén todos los anexos.';

-- Cambiar un intento de descarga no cambia el contenido evaluado ni una revisión.
DO $$
DECLARE f text;
BEGIN
 f:=pg_get_functiondef('public.lf_versionar_oportunidad()'::regprocedure);
 IF strpos(f, '''sincronizado_en'', ''version_datos''')=0 THEN RAISE EXCEPTION 'Trigger inesperado'; END IF;
 EXECUTE replace(f, '''sincronizado_en'', ''version_datos''', '''sincronizado_en'', ''version_datos'', ''ingesta_documental''');
END $$;

CREATE FUNCTION public.lf_documental(operacion text, datos jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE o public.oportunidad; token uuid; intento integer; estado_descarga text; faltantes jsonb;
BEGIN
 IF jsonb_typeof(datos) IS DISTINCT FROM 'object' OR octet_length(datos::text)>1000000 THEN
  RAISE EXCEPTION 'Entrada inválida';
 END IF;
 IF operacion IN ('documental_preparar','documental_reservar') THEN
  IF jsonb_typeof(datos->'codigos') IS DISTINCT FROM 'array' THEN RAISE EXCEPTION 'Falta lista de fuentes'; END IF;
 END IF;
 IF operacion='documental_preparar' THEN
  SELECT coalesce(jsonb_agg(codigo),'[]') INTO faltantes FROM (
   SELECT codigo FROM jsonb_array_elements_text(datos->'codigos') AS fuente(codigo)
   WHERE NOT EXISTS (SELECT 1 FROM public.oportunidad p WHERE p.codigo_externo=codigo)
   ORDER BY codigo LIMIT 20
  ) x;
  RETURN jsonb_build_object('perfil_activo',EXISTS(SELECT 1 FROM public.perfil_filtro_version WHERE activa),'pendientes',faltantes);
 END IF;
 -- El mismo lock que la persistencia: reserva y eliminación son atómicas.
 PERFORM pg_advisory_xact_lock(710263,1);
 IF operacion='documental_reservar' THEN
  SELECT * INTO o FROM public.oportunidad p
  WHERE p.codigo_externo IN (SELECT jsonb_array_elements_text(datos->'codigos'))
   AND p.modalidad='licitacion' AND coalesce(p.codigo_estado,5)=5
   AND (p.fecha_cierre IS NULL OR p.fecha_cierre>clock_timestamp())
   AND coalesce((p.ingesta_documental->>'reservada_hasta')::timestamptz,'-infinity')<=clock_timestamp()
   AND (coalesce((p.ingesta_documental->>'proximo_intento')::timestamptz,'-infinity')<=clock_timestamp()
        OR p.ingesta_documental->>'hash_fuente' IS DISTINCT FROM p.hash_fuente)
  ORDER BY (p.ingesta_documental='{}') DESC,
   coalesce((p.ingesta_documental->>'ultimo_intento')::timestamptz,'-infinity'),p.id
  LIMIT 1 FOR UPDATE;
  IF o.id IS NULL THEN RETURN '{}'::jsonb; END IF;
  token:=gen_random_uuid();
  intento:=coalesce((o.ingesta_documental->>'intentos')::int,0)+1;
  UPDATE public.oportunidad SET ingesta_documental=ingesta_documental||jsonb_build_object(
   'estado','procesando','token',token,'reservada_hasta',clock_timestamp()+interval '2 minutes',
   'ultimo_intento',clock_timestamp(),'intentos',intento,'hash_fuente',o.hash_fuente) WHERE id=o.id;
  RETURN jsonb_build_object('codigo',o.codigo_externo,'token',token,
   'hashes',(SELECT coalesce(jsonb_agg(hash_archivo),'[]') FROM public.documento_oportunidad WHERE oportunidad_id=o.id AND vigente));
 ELSIF operacion='documental_finalizar' THEN
  SELECT * INTO o FROM public.oportunidad WHERE codigo_externo=datos->>'codigo' FOR UPDATE;
  IF o.id IS NULL OR datos->>'token' IS NULL OR o.ingesta_documental->>'token' IS DISTINCT FROM datos->>'token'
   OR (o.ingesta_documental->>'reservada_hasta')::timestamptz<=clock_timestamp() THEN
   RAISE EXCEPTION 'Reserva documental vencida' USING ERRCODE='40001';
  END IF;
  estado_descarga:=datos->>'estado';
  IF estado_descarga IS NULL OR estado_descarga NOT IN ('descargada','error_temporal','acceso_restringido','sin_ficha',
    'ficha_no_verificada','sin_descarga_publica','formulario_no_admitido','respuesta_no_pdf',
    'limite_tamano','codigo_invalido','redireccion_no_admitida','demasiadas_redirecciones','respuesta_invalida') THEN
   RAISE EXCEPTION 'Estado inválido';
  END IF;
  UPDATE public.oportunidad SET ingesta_documental=(ingesta_documental-'token'-'reservada_hasta')||
   jsonb_build_object('estado',estado_descarga,'finalizado_en',clock_timestamp(),'anexos_completos',false,
    'hash_archivo',datos->>'hash_archivo','proximo_intento',clock_timestamp()+CASE
      WHEN estado_descarga='descargada' THEN interval '7 days'
      WHEN coalesce((ingesta_documental->>'intentos')::int,0)>=3 OR estado_descarga<>'error_temporal' THEN interval '24 hours'
      ELSE interval '1 hour' END) WHERE id=o.id;
  RETURN jsonb_build_object('registrado',true);
 END IF;
 RAISE EXCEPTION 'Operación documental inválida';
END $$;
REVOKE ALL ON FUNCTION public.lf_documental(text,jsonb) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.lf_documental(text,jsonb) TO service_role;

-- Conserva procedencia real y versiones del PDF principal al cambiar su contenido.
DO $migration$
DECLARE f text; antes text; despues text;
BEGIN
 f:=pg_get_functiondef('public.lf_operar(text,jsonb)'::regprocedure);
 antes:=E'  IF o.id IS NULL THEN RAISE EXCEPTION ''Licitación no disponible''; END IF;';
 despues:=antes||E'\n  IF datos ? ''tarea_token'' AND (datos->>''tarea_token'' IS NULL OR o.ingesta_documental->>''token'' IS DISTINCT FROM datos->>''tarea_token''\n   OR (o.ingesta_documental->>''reservada_hasta'')::timestamptz<=clock_timestamp()) THEN\n   RAISE EXCEPTION ''Reserva documental vencida'' USING ERRCODE=''40001''; END IF;';
 IF strpos(f,antes)=0 THEN RAISE EXCEPTION 'Persistencia inesperada'; END IF;
 f:=replace(f,antes,despues);
 antes:=E'  SELECT * INTO doc FROM public.documento_oportunidad WHERE oportunidad_id=o.id AND hash_archivo=';
 despues:=E'  IF datos ? ''tarea_token'' THEN\n   UPDATE public.documento_oportunidad SET vigente=false WHERE oportunidad_id=o.id AND vigente\n    AND cobertura->>''origen_captura''=''portal_bases'' AND hash_archivo<>datos->''extraccion''->>''hash_archivo'';\n  END IF;\n'||antes;
 IF strpos(f,antes)=0 THEN RAISE EXCEPTION 'Búsqueda documental inesperada'; END IF;
 f:=replace(f,antes,despues);
 f:=replace(f,'INSERT INTO public.documento_oportunidad(oportunidad_id,nombre,tipo,url_origen,hash_archivo,',
  'INSERT INTO public.documento_oportunidad(oportunidad_id,nombre,tipo,url_origen,version,hash_archivo,');
 f:=replace(f,'datos->>''url_origen'',d->>''hash_archivo''',
  'datos->>''url_origen'',(SELECT coalesce(max(version),0)+1 FROM public.documento_oportunidad WHERE oportunidad_id=o.id AND url_origen=datos->>''url_origen''),d->>''hash_archivo''');
 f:=replace(f,'''hash_fuente'',o.hash_fuente,''evaluacion'',r-',
  '''hash_fuente'',o.hash_fuente,''ingesta_documental'',o.ingesta_documental-''token'', ''evaluacion'',r-');
 EXECUTE f;
END $migration$;
COMMIT;
