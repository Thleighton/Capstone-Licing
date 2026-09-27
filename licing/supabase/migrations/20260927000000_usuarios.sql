-- =====================================================================
-- LICING - Base de datos de USUARIOS
-- Ejecutar en el SQL Editor del proyecto Supabase "Licing/Usuarios"
-- (proyecto separado de "Licing/Datos", que guarda licitaciones y criterios).
--
-- Qué implementa (fuentes en Drive / proyecto):
--   * Modelo relacional Fase 1: Usuario(id, nombre, email, rol), referenciado
--     por CriterioBusqueda, UmbralPresupuestario e Informe (usuario_id).
--   * Mockups v1.0, pantalla 5.1 "Login": acceso con credenciales.
--   * Requerimientos: perfil único "Encargado de Licitaciones"; pendiente
--     "Acceso y seguridad" (autenticación, sesión, auditoría).
--   * index.html > Configuración: correo de notificaciones, resumen diario,
--     avisos de cierre y anticipación (3/5/7 días).
--
-- Decisiones:
--   * Credenciales y sesión las maneja Supabase Auth (auth.users). Aquí NO
--     se guardan contraseñas: public.usuario es el perfil de negocio 1:1.
--   * Rol principal = encargado_licitaciones (único perfil de los RF).
--     Se agrega 'administrador' solo para dar de alta / desactivar cuentas
--     (C.U. de administración pendiente de validar con el cliente).
--   * Usuarios y Datos son proyectos distintos: no hay FK entre ellos.
--     En Datos, las columnas usuario_id (criterio_busqueda, historial, etc.)
--     guardan el uuid de este proyecto como valor simple (sin FK).
--     El backend (api/ en Vercel) valida la sesión contra Usuarios y consulta
--     Datos con service_role. sync.js no se ve afectado.
--
-- El script es re-ejecutable (IF NOT EXISTS / OR REPLACE / DROP POLICY IF EXISTS).
-- =====================================================================


-- ---------------------------------------------------------------------
-- 1. Tipos
-- ---------------------------------------------------------------------
DO $$ BEGIN
  CREATE TYPE public.rol_usuario AS ENUM ('encargado_licitaciones', 'administrador');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- ---------------------------------------------------------------------
-- 2. Tablas
-- ---------------------------------------------------------------------

-- Perfil de negocio del usuario (1:1 con auth.users)
CREATE TABLE IF NOT EXISTS public.usuario (
  id              uuid PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  nombre          text NOT NULL CHECK (char_length(btrim(nombre)) BETWEEN 2 AND 120),
  email           text NOT NULL UNIQUE CHECK (email = lower(email) AND email LIKE '%_@_%'),
  rol             public.rol_usuario NOT NULL DEFAULT 'encargado_licitaciones',
  area            text NOT NULL DEFAULT 'Eventos y ventas',
  cargo           text,
  activo          boolean NOT NULL DEFAULT true,
  ultimo_acceso   timestamptz,
  creado_en       timestamptz NOT NULL DEFAULT now(),
  actualizado_en  timestamptz NOT NULL DEFAULT now()
);
COMMENT ON TABLE  public.usuario IS 'Perfil de negocio de cada usuario de LICING. Credenciales en auth.users.';
COMMENT ON COLUMN public.usuario.rol IS 'encargado_licitaciones = perfil único de los RF; administrador = gestiona cuentas.';
COMMENT ON COLUMN public.usuario.activo IS 'false bloquea el acceso a datos vía RLS sin borrar historial.';

-- Preferencias de trabajo y notificación (pantalla Configuración)
CREATE TABLE IF NOT EXISTS public.usuario_preferencia (
  usuario_id              uuid PRIMARY KEY REFERENCES public.usuario(id) ON DELETE CASCADE,
  correo_notificaciones   text CHECK (correo_notificaciones IS NULL OR correo_notificaciones LIKE '%_@_%'),
  resumen_diario          boolean  NOT NULL DEFAULT true,
  aviso_cierre            boolean  NOT NULL DEFAULT true,
  dias_anticipacion_aviso smallint NOT NULL DEFAULT 3 CHECK (dias_anticipacion_aviso IN (3, 5, 7)),
  tema                    text     NOT NULL DEFAULT 'claro' CHECK (tema IN ('claro', 'oscuro', 'sistema')),
  actualizado_en          timestamptz NOT NULL DEFAULT now()
);
COMMENT ON TABLE public.usuario_preferencia IS 'Preferencias 1:1 por usuario: correo, resumen diario, avisos de cierre, tema.';

-- Bitácora de acciones relevantes (auditoría: pendiente "Acceso y seguridad")
CREATE TABLE IF NOT EXISTS public.usuario_auditoria (
  id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  usuario_id  uuid REFERENCES public.usuario(id) ON DELETE SET NULL,
  accion      text NOT NULL CHECK (accion IN (
                'login', 'logout', 'alta_usuario', 'cambio_rol', 'desactivacion', 'reactivacion',
                'cambio_criterio', 'cambio_umbral', 'cambio_estado_oportunidad', 'generar_informe', 'otro')),
  entidad     text,
  entidad_id  text,
  detalle     jsonb NOT NULL DEFAULT '{}'::jsonb,
  creado_en   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS usuario_auditoria_usuario_idx ON public.usuario_auditoria (usuario_id, creado_en DESC);
COMMENT ON TABLE public.usuario_auditoria IS 'Registro de acciones por usuario (login, cambios de rol, criterios, estados).';

-- ---------------------------------------------------------------------
-- 3. Funciones auxiliares
-- ---------------------------------------------------------------------

-- ¿El usuario autenticado es administrador activo?
CREATE OR REPLACE FUNCTION public.es_admin()
RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path = '' AS $$
  SELECT EXISTS (
    SELECT 1 FROM public.usuario
    WHERE id = auth.uid() AND rol = 'administrador' AND activo
  );
$$;

-- ¿El usuario autenticado tiene cuenta activa en LICING?
CREATE OR REPLACE FUNCTION public.es_usuario_activo()
RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path = '' AS $$
  SELECT EXISTS (SELECT 1 FROM public.usuario WHERE id = auth.uid() AND activo);
$$;

-- Marca de actualización
CREATE OR REPLACE FUNCTION public.tg_set_actualizado_en()
RETURNS trigger LANGUAGE plpgsql SET search_path = '' AS $$
BEGIN
  NEW.actualizado_en := now();
  RETURN NEW;
END $$;

-- Alta automática del perfil al registrarse / ser invitado en Supabase Auth.
-- El nombre se toma de raw_user_meta_data->>'nombre' (o del correo).
CREATE OR REPLACE FUNCTION public.tg_crear_perfil_usuario()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE
  v_nombre text := COALESCE(NULLIF(btrim(NEW.raw_user_meta_data->>'nombre'), ''),
                            split_part(NEW.email, '@', 1));
BEGIN
  INSERT INTO public.usuario (id, nombre, email)
  VALUES (NEW.id, v_nombre, lower(NEW.email))
  ON CONFLICT (id) DO NOTHING;

  INSERT INTO public.usuario_preferencia (usuario_id, correo_notificaciones)
  VALUES (NEW.id, lower(NEW.email))
  ON CONFLICT (usuario_id) DO NOTHING;

  INSERT INTO public.usuario_auditoria (usuario_id, accion, entidad, entidad_id)
  VALUES (NEW.id, 'alta_usuario', 'usuario', NEW.id::text);
  RETURN NEW;
END $$;

-- Mantiene email y último acceso sincronizados con auth.users
CREATE OR REPLACE FUNCTION public.tg_sync_usuario_auth()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
BEGIN
  IF NEW.email IS DISTINCT FROM OLD.email THEN
    UPDATE public.usuario SET email = lower(NEW.email) WHERE id = NEW.id;
  END IF;
  IF NEW.last_sign_in_at IS DISTINCT FROM OLD.last_sign_in_at THEN
    UPDATE public.usuario SET ultimo_acceso = NEW.last_sign_in_at WHERE id = NEW.id;
    INSERT INTO public.usuario_auditoria (usuario_id, accion) VALUES (NEW.id, 'login');
  END IF;
  RETURN NEW;
END $$;

-- Un usuario común solo puede editar sus datos personales (nombre, cargo, área).
-- rol, activo, email e id quedan reservados a administradores o al servidor.
-- Los cambios de rol/activo quedan en la bitácora.
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

-- ---------------------------------------------------------------------
-- 4. Triggers
-- ---------------------------------------------------------------------
DROP TRIGGER IF EXISTS crear_perfil_usuario ON auth.users;
CREATE TRIGGER crear_perfil_usuario
  AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE FUNCTION public.tg_crear_perfil_usuario();

DROP TRIGGER IF EXISTS sync_usuario_auth ON auth.users;
CREATE TRIGGER sync_usuario_auth
  AFTER UPDATE OF email, last_sign_in_at ON auth.users
  FOR EACH ROW EXECUTE FUNCTION public.tg_sync_usuario_auth();

DROP TRIGGER IF EXISTS proteger_campos_usuario ON public.usuario;
CREATE TRIGGER proteger_campos_usuario
  BEFORE UPDATE ON public.usuario
  FOR EACH ROW EXECUTE FUNCTION public.tg_proteger_campos_usuario();

DROP TRIGGER IF EXISTS set_actualizado_en ON public.usuario;
CREATE TRIGGER set_actualizado_en
  BEFORE UPDATE ON public.usuario
  FOR EACH ROW EXECUTE FUNCTION public.tg_set_actualizado_en();

DROP TRIGGER IF EXISTS set_actualizado_en ON public.usuario_preferencia;
CREATE TRIGGER set_actualizado_en
  BEFORE UPDATE ON public.usuario_preferencia
  FOR EACH ROW EXECUTE FUNCTION public.tg_set_actualizado_en();

-- Perfiles para usuarios que ya existían en auth.users antes de este script
INSERT INTO public.usuario (id, nombre, email)
SELECT u.id,
       COALESCE(NULLIF(btrim(u.raw_user_meta_data->>'nombre'), ''), split_part(u.email, '@', 1)),
       lower(u.email)
FROM auth.users u
WHERE u.email IS NOT NULL
ON CONFLICT (id) DO NOTHING;

INSERT INTO public.usuario_preferencia (usuario_id, correo_notificaciones)
SELECT id, email FROM public.usuario
ON CONFLICT (usuario_id) DO NOTHING;

-- ---------------------------------------------------------------------
-- 5. Seguridad (RLS). anon no tiene ninguna política: no ve usuarios.
-- ---------------------------------------------------------------------
ALTER TABLE public.usuario             ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.usuario_preferencia ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.usuario_auditoria   ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON public.usuario, public.usuario_preferencia, public.usuario_auditoria FROM anon;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.usuario, public.usuario_preferencia TO authenticated;
GRANT SELECT, INSERT ON public.usuario_auditoria TO authenticated;

-- usuario: el equipo activo se ve entre sí (para asignar responsables);
-- cada uno edita lo suyo; solo admin crea/borra.
DROP POLICY IF EXISTS usuario_select ON public.usuario;
CREATE POLICY usuario_select ON public.usuario FOR SELECT TO authenticated
  USING (id = auth.uid() OR public.es_usuario_activo());

DROP POLICY IF EXISTS usuario_update ON public.usuario;
CREATE POLICY usuario_update ON public.usuario FOR UPDATE TO authenticated
  USING (id = auth.uid() OR public.es_admin())
  WITH CHECK (id = auth.uid() OR public.es_admin());

DROP POLICY IF EXISTS usuario_insert_admin ON public.usuario;
CREATE POLICY usuario_insert_admin ON public.usuario FOR INSERT TO authenticated
  WITH CHECK (public.es_admin());

DROP POLICY IF EXISTS usuario_delete_admin ON public.usuario;
CREATE POLICY usuario_delete_admin ON public.usuario FOR DELETE TO authenticated
  USING (public.es_admin() AND id <> auth.uid());

-- usuario_preferencia: solo el propio usuario (admin puede leer)
DROP POLICY IF EXISTS preferencia_propia ON public.usuario_preferencia;
CREATE POLICY preferencia_propia ON public.usuario_preferencia FOR ALL TO authenticated
  USING (usuario_id = auth.uid()) WITH CHECK (usuario_id = auth.uid());

DROP POLICY IF EXISTS preferencia_admin_lee ON public.usuario_preferencia;
CREATE POLICY preferencia_admin_lee ON public.usuario_preferencia FOR SELECT TO authenticated
  USING (public.es_admin());

-- usuario_auditoria: cada uno registra acciones propias; lee lo propio; admin lee todo
DROP POLICY IF EXISTS auditoria_insert_propia ON public.usuario_auditoria;
CREATE POLICY auditoria_insert_propia ON public.usuario_auditoria FOR INSERT TO authenticated
  WITH CHECK (usuario_id = auth.uid() AND public.es_usuario_activo());

DROP POLICY IF EXISTS auditoria_select ON public.usuario_auditoria;
CREATE POLICY auditoria_select ON public.usuario_auditoria FOR SELECT TO authenticated
  USING (usuario_id = auth.uid() OR public.es_admin());

-- Las funciones auxiliares solo deben ser invocables por usuarios logueados
REVOKE EXECUTE ON FUNCTION public.es_admin(), public.es_usuario_activo() FROM PUBLIC, anon;
GRANT  EXECUTE ON FUNCTION public.es_admin(), public.es_usuario_activo() TO authenticated;


-- =====================================================================
-- DESPUÉS DE EJECUTAR
-- 1) Crear las cuentas en Authentication > Users > "Invite user" (o "Add user"),
--    con metadata {"nombre": "Francisca Salato"}. El perfil se crea solo.
-- 2) Nombrar al primer administrador (una vez, desde el SQL Editor):
--      UPDATE public.usuario SET rol = 'administrador' WHERE email = 'correo@hotel.cl';
-- 3) Desactivar Authentication > Providers > Email > "Allow new users to sign up"
--    para que solo entren cuentas invitadas (uso interno del hotel).
--
-- PASO SIGUIENTE (en Licing/Datos, cuando index.html tenga login):
--   ALTER TABLE criterio_busqueda ADD COLUMN IF NOT EXISTS usuario_id uuid; -- sin FK
--   y mover las lecturas del dashboard a una ruta api/ que verifique el token
--   de Licing/Usuarios (supabase.auth.getUser) antes de consultar Datos.
-- =====================================================================
