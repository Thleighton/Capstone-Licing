-- Ejecutar DESPUES de licing_datos_3.sql, en el SQL Editor del proyecto Supabase de Licing.
-- Deja las tablas en solo lectura para la anon key que usa index.html (visible en el navegador).
-- Con RLS activo y sin politicas de escritura, la anon key no puede insertar, editar ni borrar.

ALTER TABLE organismo          ENABLE ROW LEVEL SECURITY;
ALTER TABLE licitacion         ENABLE ROW LEVEL SECURITY;
ALTER TABLE licitacion_item    ENABLE ROW LEVEL SECURITY;
ALTER TABLE requisito_extraido ENABLE ROW LEVEL SECURITY;

CREATE POLICY lectura_publica ON organismo          FOR SELECT TO anon USING (true);
CREATE POLICY lectura_publica ON licitacion         FOR SELECT TO anon USING (true);
CREATE POLICY lectura_publica ON licitacion_item    FOR SELECT TO anon USING (true);
CREATE POLICY lectura_publica ON requisito_extraido FOR SELECT TO anon USING (true);

-- Historial de sincronizaciones (el dashboard muestra la ultima)
ALTER TABLE ejecucion_busqueda ENABLE ROW LEVEL SECURITY;
CREATE POLICY lectura_publica ON ejecucion_busqueda FOR SELECT TO anon USING (true);

-- Las demas tablas (cliente_conocido con datos de contacto, salon, disponibilidad, etc.)
-- quedan sin acceso para anon: activa RLS en ellas tambien.
ALTER TABLE cliente_conocido     ENABLE ROW LEVEL SECURITY;
ALTER TABLE criterio_busqueda    ENABLE ROW LEVEL SECURITY;
ALTER TABLE salon                ENABLE ROW LEVEL SECURITY;
ALTER TABLE salon_montaje        ENABLE ROW LEVEL SECURITY;
ALTER TABLE equipamiento         ENABLE ROW LEVEL SECURITY;
ALTER TABLE salon_equipamiento   ENABLE ROW LEVEL SECURITY;
ALTER TABLE servicio_hotel       ENABLE ROW LEVEL SECURITY;
ALTER TABLE modulo_horario       ENABLE ROW LEVEL SECURITY;
ALTER TABLE disponibilidad_salon ENABLE ROW LEVEL SECURITY;
ALTER TABLE match_resultado      ENABLE ROW LEVEL SECURITY;
ALTER TABLE stg_mp_csv           ENABLE ROW LEVEL SECURITY;
