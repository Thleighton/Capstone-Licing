# Contexto para continuar el cron con ChatGPT

Copiar el siguiente contexto en el chat del integrante que configurará cron-job.org.

---

Estoy continuando el proyecto LICING, del Hotel Plaza San Francisco. Necesito ayuda para configurar y verificar un cron documental en https://console.cron-job.org. El código está en el PR #10 de https://github.com/Thleighton/Capstone-Licing, rama `feat/filtros-hotel-operativos`. Primero comprueba que el PR corregido esté fusionado y que la versión de producción esté publicada. La tarea no requiere reescribir el backend.

Tenemos unas 150 licitaciones ingresadas sin PDF. Queremos completar únicamente los documentos de las que sigan vigentes, usando su `codigo_externo`, sin repetir sus RAW ni reactivar el cron principal de nuevas licitaciones.

Los PDF y el texto pertenecen al proyecto Supabase **Usuarios/Licitaciones**, referencia `nylzzocvemddikexqzav`: bucket privado `licitacion-bases`, tabla `licitacion_documento`, relación `licitacion_id`. Las migraciones ya están aplicadas; no recrear tablas ni ejecutar SQL históricos. **LicitacionesFiltradas**, referencia `gzhofrcnefoxqvywzgei`, conserva resultados y referencias, sin duplicar los PDF.

Antes del cron debe estar desplegada la función `documentos-origen` en Usuarios/Licitaciones y la versión corregida de `licing-filtradas` en LicitacionesFiltradas. Ambas autentican la integración contra el callback de Core; no quitar esa validación. El dominio de producción es `https://capstone-licing.vercel.app`.

Configuración del nuevo trabajo, inicialmente desactivado:

- URL: `https://capstone-licing.vercel.app/api/cron/documentos`
- Método: `POST`; cuerpo vacío.
- Header `Authorization`: `Bearer VALOR_REAL_DE_CRON_SECRET`.
- Usar el mismo `CRON_SECRET` privado que ya usa el backend/cron principal. Lo introduciré en la configuración privada; no lo pidas en el chat, no lo publiques ni lo confundas con el ticket de Mercado Público o una clave de Supabase.
- Frecuencia inicial: cada 5 minutos, ajustada a las condiciones del canal autorizado. Zona: `America/Santiago`.
- Guardar respuesta en el historial durante la prueba y activar avisos de error.
- El endpoint procesa como máximo una licitación por turno. Tiene un presupuesto de 24 segundos para el límite habitual de 30 segundos de cron-job.org; conserva los avances y reintentos.

Variables de producción que debes comprobar:

- `DOCUMENTOS_TIMEOUT_SEGUNDOS=24`.
- `DOCUMENTOS_AUTOMATICOS=false`, para usar solo el cron documental independiente.
- `MP_DESCARGA_PORTAL_HABILITADA=false` mientras falte confirmar el canal autorizado de ChileCompra.
- `DOCUMENTOS_STORAGE_URL=https://nylzzocvemddikexqzav.supabase.co/functions/v1/documentos-origen`.
- `FILTRADAS_URL=https://gzhofrcnefoxqvywzgei.supabase.co/functions/v1/licing-filtradas`.

Importante: la descarga del botón público se comprobó técnicamente, pero no se confirmó que automatizar el formulario del portal esté autorizado. No habilites la descarga ni el calendario únicamente para saltar ese pendiente. Se necesita un canal documentado aplicable o autorización de ChileCompra; no evadir CAPTCHA, restricciones, autenticación ni límites. Si el canal aprobado es otro, el adaptador deberá ajustarse a ese canal antes de activarlo. La carga manual sigue disponible.

La prueba sin credencial debe responder 401. Con credencial correcta y el canal desactivado debe devolver `{"pendiente":true,"motivo":"canal_descarga_no_confirmado"}`: eso valida la ruta, pero **no significa que descargó PDF**, aunque el historial marque HTTP 200. Mantener el trabajo desactivado en ese estado.

Una vez resuelto el canal y publicado el backend con su configuración, ejecutar primero una prueba manual. Un turno correcto devuelve `procesados:1` y el código real de la licitación. Verificar el PDF en el Storage original y su registro asociado en `licitacion_documento`; hay consultas de solo lectura en `licing/docs/sql/verificar_documentos_origen.sql`. `procesados:0` solo significa que no hay una tarea elegible en ese momento; puede haber reintentos futuros. `tiempo_turno_agotado` significa que debe continuar otro turno; no subir la frecuencia a ciegas.

Los PDF corruptos, vacíos, protegidos, ilegibles o parciales conservan la licitación en **Pendientes por revisar**, con una razón orientativa. Las vencidas o cerradas siguen sujetas a la limpieza física. No se garantiza descargar todos los anexos, no hay OCR ni filtro semántico/LLM todavía. La vista de pendientes consulta la base original y funciona aunque filtradas no responda.

Si la evaluación aparece pendiente, un usuario activo debe inicializar/actualizar la preselección desde el dashboard. La descarga se guarda aunque falle la evaluación. Ayúdame a configurar el trabajo en cron-job.org y validar sus respuestas y el guardado real, manteniendo detenido el cron principal y sin modificar código salvo que una comprobación detecte un bloqueo real.

Referencias oficiales: https://cron-job.org/en/faq/ y https://www.chilecompra.cl/api/.
