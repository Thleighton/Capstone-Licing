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

El lote alterna altas y actualizaciones de las publicadas, priorizando la verificación más antigua.
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

## Conservación exclusiva de oportunidades disponibles

La revisión `5c7bbdaa3adf` instala una función de eliminación física transaccional.
Se eliminan licitaciones cuya fecha de cierre ya se cumplió (hora de Chile), y las
cerradas, desiertas, adjudicadas, revocadas o suspendidas. Se borran sus ítems,
documentos, extracciones, fragmentos, prestaciones, requisitos, períodos y versiones
RAW. También se limpian los RAW pendientes de normalización cuando su versión más
reciente demuestra que ya no están disponibles. Una versión RAW antigua no invalida
una licitación vigente con plazo ampliado. Las fechas o estados desconocidos no
constituyen prueba de vencimiento.

La ingesta limpia antes de consultar la API y rechaza nuevos detalles no disponibles.
Una consulta correcta por código que confirma `Cantidad=0` y `Listado=[]` permite
eliminar ese código. Una caída de red, un HTTP de error o la ausencia en el listado
general no autorizan su eliminación. Los fallos de formato se conservan para revisión.

En Supabase, después de migrar, ejecutar `sql/limpieza_programada_supabase.sql` como
`postgres`: programa la misma función cada minuto, independientemente de la ingesta
y sin solicitudes HTTP. Conserva siete días de registros de ese trabajo. Verificar
`cron.job_run_details` para confirmar ejecuciones `succeeded`. El desfase normal de
limpieza es de hasta un minuto; una base detenida no ejecuta trabajos. La función
es `SECURITY INVOKER`, con ejecución revocada a los roles de la Data API.

La eliminación es permanente. No se crea un archivo histórico de oportunidades;
`ejecucion_ingesta` conserva únicamente su seguimiento técnico. El downgrade
desinstala la función, sin reconstruir las licitaciones eliminadas.

## Evidencia de ubicación del servicio

La revisión `c08ccd7a1466` añade solo `licitacion.ubicacion_servicio` (JSONB), sin
crear tablas. La región y comuna del comprador siguen siendo datos independientes.
La nueva columna guarda la versión del extractor, el RAW utilizado, regiones y
comunas candidatas, y evidencias con campo, texto, contexto y posiciones originales.
Los ítems se identifican por su posición en el RAW, incluso con correlativos repetidos.

El catálogo usa las 52 comunas de la RM y nombres de las 16 regiones de Chile.
Fuente territorial: https://www.bcn.cl/siit/mapoteca/comunas. No es un geocodificador
de todas las comunas del país. Se inspeccionan título, descripción, direcciones de
entrega/visita y texto de ítems; se excluye el bloque del comprador. Se distinguen
las menciones, las entregas y las visitas; ninguna demuestra automáticamente el
lugar contractual del servicio. Una región que incluye «de Santiago» no demuestra
que la comuna requerida sea Santiago.

Estados: `NULL` significa pendiente de procesar; `no_informada`, sin menciones del
catálogo; `por_revisar`, con menciones que necesitan interpretación. No se asignan
porcentajes de confianza ni se aprueban o descartan licitaciones por estas señales.
Negaciones, ubicaciones múltiples, sedes institucionales y homónimos requieren
revisión. Se limita a 64 evidencias y se marca `truncada` si quedan más; las listas
de candidatos siguen considerando todo el texto. La evidencia no sustituye las bases.

La normalización y la ingesta guardan esta información automáticamente. Para datos
existentes, desde Core y con la conexión habitual ejecutar:

```bash
python -m alembic upgrade head
python -m app.reprocesar_ubicaciones
```

El reprocesamiento es idempotente, trabaja en lotes de 100 y comprueba que el RAW
siga siendo el mismo antes de actualizar. No descarga archivos, no cambia el RAW,
ni sus fechas de consulta/verificación, ni la fecha anterior de normalización.
El detalle autenticado de la API devuelve la columna; si corresponde a otro RAW,
la devuelve como pendiente. El filtro `region` existente sigue refiriéndose al
comprador. Los filtros de lugar del servicio deben usar evidencia validada y
conservar los casos desconocidos para revisión. No se conecta aún la segunda base
al dashboard ni se activa un modelo semántico o LLM.
