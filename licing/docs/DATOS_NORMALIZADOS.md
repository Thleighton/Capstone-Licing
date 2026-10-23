# Información conservada para futuras búsquedas

La revisión `c4f8a19d620e` amplía el almacenamiento. No implementa filtros
semánticos, embeddings, descarga de adjuntos ni análisis automático con IA.

## JSON y datos generales

`raw_mercado_publico.respuesta` conserva el detalle original. `licitacion` incorpora
tipo, estimación, visibilidad y justificación del monto, direcciones de comprador,
entrega y visita, el calendario original y las condiciones contractuales de la API.
`licitacion_item` incorpora código y nombre de categoría, estado y adjudicación de
origen. La migración completa estos campos desde los JSON ya guardados, sin
consultar Mercado Público, cambiar los identificadores o borrar información.

Las fechas del foro y la dirección del comprador no se interpretan como fechas o
ubicación de un evento. `NULL`, cero y un campo ausente conservan su significado;
los objetos de contexto mantienen las claves y unidades originales. La API pública
de la aplicación entrega `url_oficial`, calculada desde el código externo y sin ticket.

## Texto documental sin almacenar PDF

- `licitacion_documento`: URL pública, nombre, tipo, versión, fecha y huella opcional
  del archivo. No contiene PDF, binarios ni una referencia a una copia en Storage.
- `licitacion_extraccion`: método y versión de extracción, estado, cobertura por
  página y huella de la importación. Conserva versiones y evita repetir el mismo
  contenido. Una nueva versión documental no borra la anterior.
- `documento_fragmento`: texto, sección, tipo, orden, páginas y necesidad de OCR.
- `licitacion_prestacion`: objeto del servicio, modalidad, grupo de servicios,
  relación opcional con el correlativo de un ítem, adjudicación y ofertas parciales.
- `licitacion_requisito`: condición original, obligatoriedad o carácter evaluable,
  rangos, unidades, alcance, alternativas, condiciones, excepciones, ponderación y
  parámetros específicos (por ejemplo comunas, importe, moneda e impuestos).
- `licitacion_periodo_servicio`: períodos repetibles de evento, montaje o estadía;
  ventanas de inicio/fin, precisión, hora local y zona, cantidades y tipo de habitación.
  Una fecha sin hora se marca como tal; no representa disponibilidad confirmada.

Prestaciones, requisitos y períodos conservan el fragmento que los respalda y un
estado: confirmado en el documento, no informado, ambiguo o contradictorio.
`no_exigido` es un carácter explícito del requisito; no equivale a no informado.
La confianza es opcional y no representa compatibilidad con el hotel.

## Registro desde un extractor futuro o una revisión manual

`POST /api/licitaciones/{id}/extracciones` (administrador) acepta un objeto con
`documento`, `metodo`, `version_metodo`, `estado`, `cobertura`, `fragmentos`,
`prestaciones`, `requisitos` y `periodos`. El contrato completo y los tipos están en
`/api/docs`; no se reciben archivos ni se descarga la URL. Un extractor externo
puede usar el PDF temporalmente y enviar solamente el texto y los datos obtenidos.

Los hechos apuntan a `fragmento_orden`; requisitos y períodos pueden referir la
`prestacion_clave`. La cita de cada requisito debe aparecer en su fragmento. Se
rechazan rangos invertidos, referencias ajenas, cobertura incoherente y URLs con
credenciales. El registro es atómico; repetir la misma entrada devuelve el mismo
`extraccion_id` con `creada=false`. Para corregir datos, se registra otra extracción;
no se reescribe silenciosamente una versión del documento.

`GET /api/licitaciones/{id}/documentos?limite=50&offset=0` lista sus versiones.
`GET /api/licitaciones/{id}/extracciones/{extraccion_id}` consulta metadatos y hechos.
El texto completo se incluye solo con `?incluir_texto=true`. Ambas consultas exigen
usuario activo. RLS protege todas las tablas nuevas frente a las claves públicas.

Los datos específicos de las bases solo aparecerán después de registrar una
extracción. La migración no inventa requisitos ni carga documentos de ejemplo.

## Preparación y validación

Ejecutar `alembic upgrade head` antes de desplegar la nueva API. La ampliación y el
relleno desde raw se ejecutan en la transacción de Alembic. El código anterior
tolera las columnas y tablas adicionales durante el despliegue.

Para el SQL Editor de Supabase está el equivalente transaccional
[`sql/20261021_normalizacion_v2.sql`](sql/20261021_normalizacion_v2.sql). Usar una
sola de las dos vías. El script exige la revisión de origen, coordina el bloqueo
con la ingesta, verifica conservación de datos/categorías/RLS y registra la nueva
revisión. No hace falta ejecutar luego la misma ampliación otra vez.

Verificar conteos de raw, licitaciones e ítems antes y después, categorías contra el
JSON, ausencia de registros huérfanos, revisión Alembic y RLS. El almacenamiento de
texto y futuras representaciones semánticas debe medirse con una muestra real;
la estimación de espacio del JSON no incluye estas tablas ni vectores.

## Corrección de ingesta y normalización 3

Los correlativos de Mercado Público pueden repetirse en productos diferentes.
`licitacion_item.correlativo` conserva el valor original. `posicion_fuente` identifica
la posición, desde 1, dentro de `Items.Listado`; la unicidad pasa a
`(licitacion_id, posicion_fuente)`. No se eliminan ni renumeran los ítems de origen.
Las filas existentes conservan sus identificadores. Las posiciones corresponden a
la versión RAW referenciada por la licitación, no son identificadores comerciales
permanentes entre versiones de las bases.

`raw_mercado_publico.consultado_en` conserva la primera descarga de esa respuesta;
`verificado_en` registra la última comprobación en la API. Si la respuesta cambia,
se conserva una nueva versión RAW. Si es idéntica, solo se actualiza la verificación.
Reprocesar el RAW por sí solo no actualiza esa fecha.

El lote alterna altas y actualizaciones de las publicadas. Prioriza dentro de las
actualizaciones los cierres aún no comprobados y después la verificación más antigua.
Los errores de un código tienen una espera antes del reintento; después se vuelve a
consultar la API. No se considera vigente una fuente solo porque se haya renormalizado.

Parámetros operativos, sin relación con los criterios comerciales del hotel:

- `MP_ACTUALIZACION_HORAS=24`: antigüedad que habilita una actualización; la capacidad
  de cada lote determina cuándo se ejecuta, no garantiza una revisión diaria de toda la base.
- `MP_REINTENTO_ERROR_MINUTOS=60`: espera de un código fallido.
- `MP_LOTE_TIMEOUT_SEGUNDOS=45`: límite de aplicación inferior a los 60 segundos del hosting.

Cada detalle correcto se confirma por separado. Un error o un tiempo agotado conserva
los avances y cierra el historial como parcial, error o interrumpida. Los mensajes HTTP
omiten URLs y credenciales. Las fechas con offset se convierten a `America/Santiago`.

Despliegue de una instalación existente: aplicar `968329dc86b0`, desplegar el nuevo
escritor y después aplicar `b9a70e6d4a93`. La primera etapa conserva la restricción
anterior y admite inserciones del escritor antiguo; la segunda completa posiciones
pendientes y elimina únicamente la suposición de unicidad del correlativo de origen.
En instalaciones nuevas, `alembic upgrade head` aplica ambas.

Estas correcciones no determinan la ubicación del servicio ni activan filtros hoteleros.
