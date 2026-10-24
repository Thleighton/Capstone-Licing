-- SOLO LECTURA. Ejecutar en Usuarios/Licitaciones (nylzzocvemddikexqzav).
SELECT to_regclass('public.licitacion_documento') AS tabla_documental,
       (SELECT version_num FROM public.alembic_version) AS version_alembic;

SELECT id,public,file_size_limit,allowed_mime_types FROM storage.buckets WHERE id='licitacion-bases';

SELECT (SELECT count(*) FROM public.licitacion) AS licitaciones,
       (SELECT count(*) FROM public.licitacion_documento) AS documentos,
       (SELECT count(*) FROM storage.objects WHERE bucket_id='licitacion-bases') AS archivos;

SELECT estado_extraccion,count(*) AS documentos
FROM public.licitacion_documento WHERE vigente GROUP BY estado_extraccion ORDER BY estado_extraccion;

SELECT l.codigo_externo,l.nombre,d.id AS documento_id,d.nombre AS documento,
       d.estado_extraccion,d.paginas,d.cobertura->>'motivo' AS motivo_lectura,d.storage_path
FROM public.licitacion_documento d JOIN public.licitacion l ON l.id=d.licitacion_id
ORDER BY d.creado_en DESC LIMIT 25;

SELECT codigo_externo,ingesta_documental->>'estado' AS estado,
       ingesta_documental->>'ultimo_intento' AS ultimo_intento,
       ingesta_documental->>'proximo_intento' AS proximo_intento,
       ingesta_documental#>>'{incidencia_documental,motivo}' AS motivo
FROM public.licitacion ORDER BY id LIMIT 150;

SELECT count(*) AS registros_sin_archivo
FROM public.licitacion_documento d
WHERE NOT EXISTS(SELECT 1 FROM storage.objects s WHERE s.bucket_id='licitacion-bases' AND s.name=d.storage_path);
-- Tras una carga finalizada, registros_sin_archivo debe ser 0.
