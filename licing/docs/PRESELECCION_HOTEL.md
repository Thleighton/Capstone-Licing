# Piloto de preselección de licitaciones

Este cambio permite evaluar licitaciones que ya están en Core y revisar los motivos
antes de conectar los resultados con el dashboard o la ingesta. Usa las tablas
existentes. No modifica RAW, no elimina oportunidades y no ejecuta migraciones.
El cron y las consultas actuales conservan su comportamiento.

## Orden de implementación

1. Catálogo versionado, vigencia, ubicación del servicio y pertinencia por reglas.
2. Comparación semántica de los textos disponibles con servicios del hotel.
3. Validación con casos revisados por el hotel y persistencia de evaluaciones.
4. Procesamiento de nuevas oportunidades y actualización de las existentes.
5. Análisis generativo con LLM, al final.

## Reglas y alcance

`backend/licing-core/app/data/preseleccion_hotel_v1.json` contiene el catálogo inicial:
alojamiento, salones, actividades, alimentación asociada y complementos. Cada grupo
distingue señales directas de términos contextuales. Los códigos y nombres genéricos
de productos se conservan como señales, pero no bastan solos para seleccionar.

Vigencia usa el estado y el cierre guardados, interpretando las horas sin zona como
America/Santiago, igual que la API de consultas existente. Se devuelve la fecha de
consulta de RAW. No se afirma haber comprobado el estado en Mercado Público en vivo;
la sincronización actual de códigos existentes sigue siendo un trabajo posterior.
No se establece una anticipación mínima de oferta sin validarla con el hotel.

La ubicación se identifica por expresiones que relacionan el servicio o la actividad
con un lugar. El catálogo incluye las 52 comunas de la RM, regiones y un conjunto
inicial de ciudades fuera de ella. La lista de otras ciudades no pretende ser un
catálogo nacional completo: una ubicación no reconocida permanece sin determinar.
Referencia territorial: https://www.gobiernosantiago.cl/nuestra-region/

La región, comuna, nombre y domicilio del comprador no determinan la ubicación del
servicio. Dirección de entrega y visita se devuelven solamente como pistas. Se
conservan la fuente y un fragmento de respaldo por coincidencia. Negaciones,
domicilios administrativos, topónimos ambiguos y ubicaciones múltiples requieren
revisión. Una licitación puede incluir líneas en distintas ciudades.

Resultados de la evaluación:

- `preseleccionada`: vigente según la fuente guardada, ubicación del servicio en
  RM y señal directa de pertinencia sin ambigüedad detectada. Significa posible
  oportunidad; no acredita disponibilidad, capacidad o cumplimiento de requisitos.
- `revision_manual`: ubicación, vigencia o pertinencia insuficiente/ambigua. La
  ausencia de palabras clave conserva el caso para semántica o revisión. OTEC,
  OTIC y capacitación no son términos de exclusión.
- `descartada`: cierre/estado impiden ofertar según los datos guardados, o el
  servicio identificado está fuera de RM sin otras líneas hoteleras sin localizar.
  Es una propuesta de clasificación devuelta por el piloto; no borra ni oculta filas.

Alimentación y equipamiento por separado requieren revisar el alcance comercial
del hotel. No se agregan filtros de monto o capacidad con umbrales inventados.
El texto excesivamente largo se marca parcial y no justifica un descarte territorial.

## API privada de evaluación

`GET /api/preseleccion/catalogo` devuelve el catálogo para usuarios activos.

`POST /api/preseleccion/evaluar` acepta hasta 50 identificadores de Core distintos:

```json
{
  "licitacion_ids": [1, 2],
  "incluir_semantica": false
}
```

El ejemplo requiere reemplazar los identificadores por filas existentes. Las rutas
requieren el token habitual de LICING. La respuesta incluye `modo: simulacion`,
`persistido: false`, conteos, versión del catálogo, huella de entrada, referencia
RAW, evidencia y resultados por criterio. No genera probabilidades de adjudicación.
Un identificador inexistente produce 404; no se inventan evaluaciones.

## Comparación semántica opcional

Para una prueba con el proveedor se admite `incluir_semantica: true`, hasta tres
licitaciones por solicitud y usuario administrador. El servidor requiere:

```dotenv
PRESELECCION_GEMINI_API_KEY=CONFIGURAR_SOLO_EN_EL_SERVIDOR
PRESELECCION_EMBEDDING_DIMENSIONES=768
```

El adaptador usa `gemini-embedding-001` exclusivamente para embeddings; no llama
a modelos de generación. Su configuración no afecta el cron. Solo se envían los
textos de servicios almacenados, excluyendo identidad, domicilios y contactos del
comprador. La evaluación por reglas funciona sin esta clave y sin llamadas externas.
No guardar claves en Git ni compartirlas en el navegador.

Los textos se fragmentan en segmentos de hasta 1.500 caracteres con solapamiento,
con un máximo de ocho por licitación y cobertura parcial explícita cuando se supera.
Los perfiles se codifican como consultas y los fragmentos como documentos. Los
vectores se normalizan y comparan por coseno. Una caché temporal y acotada por
modelo/dimensión/tipo/huella evita repetir entradas durante la vida del proceso.
No se guardan vectores en los 500 MB de PostgreSQL en esta fase.

El resultado ordena afinidades con alojamiento, salones, alimentación asociada y
contextos alternativos de docencia/producción y bienes/obras. Es una ayuda para
revisión: **todavía no cambia la clasificación automáticamente**. Los puntajes no
son probabilidades y no se fijan cortes antes de medirlos con casos del hotel.
Un error del proveedor devuelve 503 sin exponer credenciales; no equivale a no
pertinencia. Las oportunidades ya descartadas por vigencia/ubicación no se envían.

Referencia del adaptador: https://ai.google.dev/api/embeddings

## Validación antes de activar el filtrado operativo

Preparar ejemplos revisados por el hotel, incluyendo servicios redactados de otras
formas, compradores fuera de RM que solicitan Santiago, múltiples ubicaciones,
servicios integrales y casos no pertinentes. Comparar oportunidades útiles
recuperadas y omitidas, revisar las causas y evaluar por separado una muestra que
no se haya usado para ajustar el catálogo y los futuros umbrales.

Las pruebas automatizadas de reglas, autenticación y contrato del proveedor usan
casos controlados y respuestas simuladas. No acreditan precisión sobre los registros
reales de Supabase ni sustituyen una prueba con embeddings reales.
