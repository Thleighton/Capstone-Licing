-- Ejecutar en el SQL Editor de "Licing/Datos" SOLO DESPUÉS de desplegar el login
-- (index.html + api/datos.js) y comprobar que el dashboard carga con sesión.
-- Desde ese momento el navegador ya no lee Datos con la anon key: todo pasa por
-- /api/datos, que valida la sesión de Licing/Usuarios y usa la service_role.
-- Con esto la anon key de Datos deja de ver licitaciones (RLS sin políticas = sin acceso).

DROP POLICY IF EXISTS lectura_publica ON organismo;
DROP POLICY IF EXISTS lectura_publica ON licitacion;
DROP POLICY IF EXISTS lectura_publica ON licitacion_item;
DROP POLICY IF EXISTS lectura_publica ON requisito_extraido;
DROP POLICY IF EXISTS lectura_publica ON ejecucion_busqueda;

-- Para revertir: volver a ejecutar las políticas de supabase_rls_lectura.sql
