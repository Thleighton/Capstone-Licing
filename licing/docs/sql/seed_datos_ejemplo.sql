-- =====================================================================
-- LICING - Script para poblar tablas con datos de EJEMPLO (demo / pruebas)
--
-- Puebla: raw_mercado_publico, licitacion, licitacion_item, compra_agil,
--         compra_agil_item.
-- Los datos son FICTICIOS. Todos los códigos empiezan con 'SEED-' y la
-- fuente RAW es 'seed', así se identifican y se pueden borrar sin tocar
-- datos reales (ver bloque de limpieza al final).
--
-- Requisitos: migraciones de Alembic aplicadas (alembic upgrade head).
-- Es re-ejecutable: borra los SEED- anteriores y los vuelve a insertar.
-- NO usar en producción con datos reales de clientes.
-- NO crea usuarios: public.usuario depende de Supabase Auth (auth.users);
-- créalos desde Authentication en Supabase o con supabase_usuarios.sql.
-- =====================================================================

BEGIN;

-- 0. Limpieza de una ejecución anterior (solo filas SEED)
DELETE FROM compra_agil_item WHERE compra_agil_id IN
  (SELECT id FROM compra_agil WHERE codigo_externo LIKE 'SEED-%');
DELETE FROM compra_agil WHERE codigo_externo LIKE 'SEED-%';
DELETE FROM licitacion_item WHERE licitacion_id IN
  (SELECT id FROM licitacion WHERE codigo_externo LIKE 'SEED-%');
DELETE FROM licitacion WHERE codigo_externo LIKE 'SEED-%';
DELETE FROM raw_mercado_publico WHERE fuente = 'seed';

-- 1. RAW: una respuesta simulada por cada licitación / compra ágil
INSERT INTO raw_mercado_publico
  (fuente, tipo_consulta, parametro_consulta, codigo_externo, respuesta, http_status, cantidad_resultados)
SELECT 'seed', t, c, c, jsonb_build_object('ejemplo', true, 'codigo', c), 200, 1
FROM (VALUES
  ('licitacion',   'SEED-1001-1-LE26'),
  ('licitacion',   'SEED-1002-2-LE26'),
  ('licitacion',   'SEED-1003-3-LP26'),
  ('licitacion',   'SEED-1004-4-L126'),
  ('compra_agil',  'SEED-2001-1-COT26'),
  ('compra_agil',  'SEED-2002-2-COT26'),
  ('compra_agil',  'SEED-2003-3-COT26')
) AS v(t, c);

-- 2. Licitaciones
INSERT INTO licitacion
  (codigo_externo, raw_id, nombre, descripcion, codigo_estado, estado,
   monto_estimado, moneda, fecha_publicacion, fecha_cierre,
   codigo_organismo, nombre_organismo, region_comprador, comuna_comprador,
   tipo, codigo_tipo)
SELECT v.codigo, r.id, v.nombre, v.descr, 5, 'Publicada',
       v.monto, 'CLP', v.f_pub, v.f_cierre,
       v.cod_org, v.org, 'Metropolitana de Santiago', v.comuna, v.tipo, v.cod_tipo
FROM (VALUES
  ('SEED-1001-1-LE26', 'Servicio de arriendo de salones y coffee break para jornada de capacitación',
   'Arriendo de salón con capacidad para 80 personas, equipamiento audiovisual y coffee break (2 pausas).',
   4500000, TIMESTAMP '2026-11-03 10:00', TIMESTAMP '2026-11-25 15:00',
   '100001', 'Ministerio de Ejemplo - Subsecretaría A', 'Santiago', 'LE', 2),
  ('SEED-1002-2-LE26', 'Servicio de alojamiento y alimentación para seminario regional',
   'Alojamiento en habitaciones dobles (20) y almuerzos para 3 días de seminario.',
   12800000, TIMESTAMP '2026-11-05 09:30', TIMESTAMP '2026-11-27 12:00',
   '100002', 'Servicio de Ejemplo B', 'Providencia', 'LE', 2),
  ('SEED-1003-3-LP26', 'Servicio de banquetería para ceremonia institucional',
   'Banquetería para 150 personas, montaje de salón y servicio de garzones.',
   9200000, TIMESTAMP '2026-11-09 11:00', TIMESTAMP '2026-12-02 16:00',
   '100003', 'Municipalidad de Ejemplo', 'Santiago', 'LP', 3),
  ('SEED-1004-4-L126', 'Adquisición de mobiliario de oficina',
   'Compra de escritorios y sillas ergonómicas. Sin relación con servicios hoteleros.',
   6000000, TIMESTAMP '2026-11-02 08:00', TIMESTAMP '2026-11-20 14:00',
   '100004', 'Hospital de Ejemplo', 'Ñuñoa', 'L1', 1)
) AS v(codigo, nombre, descr, monto, f_pub, f_cierre, cod_org, org, comuna, tipo, cod_tipo)
JOIN raw_mercado_publico r ON r.fuente = 'seed' AND r.codigo_externo = v.codigo;

-- 3. Ítems de licitación
INSERT INTO licitacion_item
  (licitacion_id, correlativo, posicion_fuente, codigo_producto, nombre_producto,
   descripcion, cantidad, unidad_medida, codigo_categoria, categoria)
SELECT l.id, v.pos, v.pos, v.cod_prod, v.prod, v.descr, v.cant, v.um, v.cod_cat, v.cat
FROM (VALUES
  ('SEED-1001-1-LE26', 1, '90111501', 'Arriendo de salón',     'Salón 80 personas, 8 horas',        1,   'Servicio',  '90110000', 'Servicios de hotelería y eventos'),
  ('SEED-1001-1-LE26', 2, '90101603', 'Coffee break',          '2 pausas por asistente',            80,  'Persona',   '90100000', 'Servicios de alimentación'),
  ('SEED-1002-2-LE26', 1, '90111500', 'Alojamiento',           'Habitación doble, 3 noches',        20,  'Habitación','90110000', 'Servicios de hotelería y eventos'),
  ('SEED-1002-2-LE26', 2, '90101501', 'Almuerzo',              'Menú de 3 tiempos, 3 días',         60,  'Persona',   '90100000', 'Servicios de alimentación'),
  ('SEED-1003-3-LP26', 1, '90101700', 'Banquetería',           'Cóctel y cena, 150 personas',       150, 'Persona',   '90100000', 'Servicios de alimentación'),
  ('SEED-1003-3-LP26', 2, '90111501', 'Montaje de salón',      'Mesas, mantelería y ambientación',  1,   'Servicio',  '90110000', 'Servicios de hotelería y eventos'),
  ('SEED-1004-4-L126', 1, '56101500', 'Escritorios',           'Escritorio 140x70 cm',              30,  'Unidad',    '56100000', 'Mobiliario'),
  ('SEED-1004-4-L126', 2, '56112100', 'Sillas ergonómicas',    'Silla con apoyabrazos regulable',   30,  'Unidad',    '56110000', 'Mobiliario')
) AS v(codigo, pos, cod_prod, prod, descr, cant, um, cod_cat, cat)
JOIN licitacion l ON l.codigo_externo = v.codigo;

-- 4. Compras ágiles
INSERT INTO compra_agil
  (codigo_externo, raw_id, nombre, descripcion, id_estado, estado,
   fecha_publicacion, fecha_cierre, moneda, tipo_presupuesto,
   presupuesto_estimado, monto_disponible, monto_disponible_clp,
   nombre_organismo, region_comprador, direccion_entrega, plazo_entrega_dias)
SELECT v.codigo, r.id, v.nombre, v.descr, 2, 'publicada',
       v.f_pub, v.f_cierre, 'CLP', 'estimado',
       v.monto, v.monto, v.monto,
       v.org, 'Metropolitana de Santiago', v.dir, v.plazo
FROM (VALUES
  ('SEED-2001-1-COT26', 'Servicio de coffee break para reunión de directorio',
   'Coffee break para 25 personas, reunión de una jornada.',
   TIMESTAMP '2026-11-12 09:00', TIMESTAMP '2026-11-19 17:00', 350000,
   'Servicio de Ejemplo C', 'Santiago Centro, Santiago', 7),
  ('SEED-2002-2-COT26', 'Arriendo de sala para taller de 40 personas',
   'Sala con proyector, pizarra y conexión a internet por un día.',
   TIMESTAMP '2026-11-13 10:00', TIMESTAMP '2026-11-20 12:00', 600000,
   'Universidad de Ejemplo', 'Santiago Centro, Santiago', 10),
  ('SEED-2003-3-COT26', 'Compra de resmas de papel y tóner',
   'Insumos de oficina. Sin relación con servicios hoteleros.',
   TIMESTAMP '2026-11-12 14:00', TIMESTAMP '2026-11-18 16:00', 280000,
   'Servicio de Ejemplo D', 'Maipú, Santiago', 5)
) AS v(codigo, nombre, descr, f_pub, f_cierre, monto, org, dir, plazo)
JOIN raw_mercado_publico r ON r.fuente = 'seed' AND r.codigo_externo = v.codigo;

-- 5. Ítems de compra ágil
INSERT INTO compra_agil_item
  (compra_agil_id, posicion_fuente, codigo_producto, nombre_producto, descripcion, cantidad, unidad_medida)
SELECT c.id, v.pos, v.cod_prod, v.prod, v.descr, v.cant, v.um
FROM (VALUES
  ('SEED-2001-1-COT26', 1, '90101603', 'Coffee break',     'Café, té, jugos y snacks',        25,  'Persona'),
  ('SEED-2002-2-COT26', 1, '90111501', 'Arriendo de sala', 'Sala 40 personas, 8 horas',        1,   'Servicio'),
  ('SEED-2002-2-COT26', 2, '90101603', 'Coffee break',     'Una pausa por asistente',          40,  'Persona'),
  ('SEED-2003-3-COT26', 1, '14111500', 'Resma de papel',   'Carta, 75 g, caja de 10 resmas',   20,  'Caja'),
  ('SEED-2003-3-COT26', 2, '44103100', 'Tóner',            'Tóner negro compatible',           6,   'Unidad')
) AS v(codigo, pos, cod_prod, prod, descr, cant, um)
JOIN compra_agil c ON c.codigo_externo = v.codigo;

COMMIT;

-- Verificación rápida (debería dar 4 / 8 / 3 / 5):
--   SELECT (SELECT count(*) FROM licitacion WHERE codigo_externo LIKE 'SEED-%') AS licitaciones,
--          (SELECT count(*) FROM licitacion_item i JOIN licitacion l ON l.id=i.licitacion_id WHERE l.codigo_externo LIKE 'SEED-%') AS items_lic,
--          (SELECT count(*) FROM compra_agil WHERE codigo_externo LIKE 'SEED-%') AS compras,
--          (SELECT count(*) FROM compra_agil_item i JOIN compra_agil c ON c.id=i.compra_agil_id WHERE c.codigo_externo LIKE 'SEED-%') AS items_ca;
-- Para quitar los datos de ejemplo, ejecuta solo el bloque "0. Limpieza".
