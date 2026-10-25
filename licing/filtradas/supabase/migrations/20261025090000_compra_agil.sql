-- Proyecto LicitacionesFiltradas exclusivamente. No añade tablas.
-- Admite Compras Ágiles con los mismos pilares y tablas (oportunidad.modalidad='compra_agil').
-- Cada modalidad sincroniza solo sus propias oportunidades: la lista de licitaciones de Core
-- no retira Compras Ágiles, ni al revés. Sin modalidad se asume 'licitacion', como antes.
BEGIN;
SET LOCAL search_path = pg_catalog, public;
DO $$ BEGIN
 IF to_regclass('public.raw_mercado_publico') IS NOT NULL THEN
  RAISE EXCEPTION 'Proyecto incorrecto: esta migración es para LicitacionesFiltradas';
 END IF;
END $$;
DO $patch$
DECLARE f text; antes text; despues text;
BEGIN
 f:=pg_get_functiondef('public.lf_operar(text,jsonb)'::regprocedure);
 antes:='IF d->>''codigo_externo'' ~* ''-COT[0-9]*$'' THEN RAISE EXCEPTION ''Compra Ágil fuera de alcance''; END IF;';
 despues:='IF coalesce(d->>''modalidad'',''licitacion'') NOT IN (''licitacion'',''compra_agil'')'
  ||' OR (d->>''codigo_externo'' ~* ''-COT[0-9]*$'') IS DISTINCT FROM (coalesce(d->>''modalidad'',''licitacion'')=''compra_agil'')'
  ||' THEN RAISE EXCEPTION ''La modalidad no coincide con el código''; END IF;';
 IF strpos(f,antes)=0 THEN RAISE EXCEPTION 'Validación de Compra Ágil inesperada'; END IF;
 f:=replace(f,antes,despues);
 antes:='SELECT ''mercado_publico'',x.codigo_externo,''licitacion'',';
 IF strpos(f,antes)=0 THEN RAISE EXCEPTION 'Modalidad del guardado inesperada'; END IF;
 f:=replace(f,antes,'SELECT ''mercado_publico'',x.codigo_externo,coalesce(d->>''modalidad'',''licitacion''),');
 antes:='AND sincronizado_en < (datos->>''observado_en'')::timestamptz';
 IF strpos(f,antes)=0 THEN RAISE EXCEPTION 'Sincronización inesperada'; END IF;
 f:=replace(f,antes,'AND modalidad=coalesce(datos->>''modalidad'',''licitacion'') '||antes);
 EXECUTE f;
END $patch$;
COMMIT;
