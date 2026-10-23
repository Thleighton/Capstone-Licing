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

## Esquema operativo actual

La base Usuarios/Licitaciones conserva ocho tablas:

| Tabla | Uso |
|---|---|
| `raw_mercado_publico` | Respuesta original de Mercado Público |
| `licitacion` | Datos consultables y evidencia geográfica |
| `licitacion_item` | Productos y servicios solicitados |
| `ejecucion_ingesta` | Avances y errores de ingesta |
| `usuario` | Perfil y permisos |
| `usuario_preferencia` | Preferencias de la cuenta |
| `usuario_auditoria` | Acciones de usuarios |
| `alembic_version` | Revisión del esquema |

La revisión `b8654f3a89fc` retira las seis tablas documentales vacías y sus rutas,
modelos y servicios. Ajusta la limpieza automática para funcionar únicamente con
licitaciones, ítems y RAW. Las tablas de usuarios y todos los datos operativos se
conservan. La migración comprueba que las tablas retiradas estén vacías y usa
`DROP TABLE` sin `CASCADE`; cualquier dato o dependencia externa impide el retiro.

Despliegue: publicar primero el backend sin las rutas documentales y después
aplicar `alembic upgrade head`. El downgrade permite restablecer el esquema previo
como reversión técnica. Las instalaciones nuevas terminan también con este núcleo
mínimo; las migraciones históricas no se reescriben. El SQL manual de normalización
v2 es histórico; para instalaciones actuales se usa la cadena completa de Alembic.

La extracción de bases, sus tablas y sus API se diseñarán cuando entren al alcance.
No se añaden tablas a `LicitacionesFiltradas` durante este retiro.

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
cerradas, desiertas, adjudicadas, revocadas o suspendidas. Se borran sus ítems y
versiones RAW. También se limpian los RAW pendientes de normalización cuando su versión más
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
