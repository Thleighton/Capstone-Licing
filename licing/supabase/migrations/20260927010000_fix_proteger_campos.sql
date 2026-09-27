-- Corrige tg_proteger_campos_usuario: el SQL Editor quedaba bloqueado al nombrar administradores.
CREATE OR REPLACE FUNCTION public.tg_proteger_campos_usuario()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
BEGIN
  -- Solo se restringe lo que llega por la API (PostgREST se conecta como
  -- 'authenticator'). El SQL Editor y la service_role quedan libres.
  IF session_user = 'authenticator'
     AND coalesce(auth.role(), '') <> 'service_role'
     AND NOT public.es_admin() THEN
    IF NEW.rol IS DISTINCT FROM OLD.rol OR NEW.activo IS DISTINCT FROM OLD.activo
       OR NEW.email IS DISTINCT FROM OLD.email OR NEW.id IS DISTINCT FROM OLD.id
       OR NEW.ultimo_acceso IS DISTINCT FROM OLD.ultimo_acceso THEN
      RAISE EXCEPTION 'Solo un administrador puede cambiar rol, estado o correo del usuario'
        USING ERRCODE = '42501';
    END IF;
  END IF;

  -- Evita dejar el sistema sin administradores activos
  IF (OLD.rol = 'administrador' AND OLD.activo)
     AND (NEW.rol <> 'administrador' OR NOT NEW.activo)
     AND NOT EXISTS (SELECT 1 FROM public.usuario
                     WHERE rol = 'administrador' AND activo AND id <> OLD.id) THEN
    RAISE EXCEPTION 'Debe quedar al menos un administrador activo' USING ERRCODE = '23514';
  END IF;

  IF NEW.rol IS DISTINCT FROM OLD.rol THEN
    INSERT INTO public.usuario_auditoria (usuario_id, accion, entidad, entidad_id, detalle)
    VALUES (auth.uid(), 'cambio_rol', 'usuario', OLD.id::text,
            jsonb_build_object('de', OLD.rol, 'a', NEW.rol));
  END IF;
  IF NEW.activo IS DISTINCT FROM OLD.activo THEN
    INSERT INTO public.usuario_auditoria (usuario_id, accion, entidad, entidad_id)
    VALUES (auth.uid(), CASE WHEN NEW.activo THEN 'reactivacion' ELSE 'desactivacion' END,
            'usuario', OLD.id::text);
  END IF;
  RETURN NEW;
END $$;
