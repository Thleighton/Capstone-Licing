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

## Ingesta de Compra Ágil

La revisión `e3a17c52d9b4` incorpora las Compras Ágiles desde la API oficial v2
(`https://api2.mercadopublico.cl/v2/compra-agil`, guía de ChileCompra, mayo de 2026).
Usa el mismo `MP_TICKET`, enviado en la cabecera `ticket` y nunca en la URL.

| Tabla | Uso |
|---|---|
| `compra_agil` | Compra normalizada desde el detalle, con su RAW (`fuente='compra_agil'`, `tipo_consulta='detalle_compra_agil'`) y su última preselección (`preseleccion`) |
| `compra_agil_item` | `productos_solicitados`, identificados por su posición en el RAW |
| `compra_agil_pendiente` | Cola de detalles por descargar, alimentada por el listado |
| `compra_agil_sincronizacion` | Fila única con el cursor y la ventana del listado en curso |

`ejecucion_ingesta.fuente` distingue los lotes (`licitaciones` o `compra_agil`). El
planificador de licitaciones solo considera sus propios lotes para alternar turnos y
posponer errores. Las cuatro tablas tienen RLS y sin permisos para `anon` ni
`authenticated`, igual que el resto de Core.

**Fechas.** La API publica hora de Chile en todos sus campos, aunque algunos terminen
en `Z`: el listado entrega `2026-10-26T08:00:00Z` como cierre del primer llamado y el
detalle `2026-10-26 08:00` para el mismo instante, y los cierres se concentran en horas
hábiles locales. Por eso la `Z` se descarta y las fechas se guardan como hora de Chile
sin zona, como en `licitacion`. Por la misma razón `ttl_cambio_ms` no es fiable (compara
contra UTC) y el lote usa `cambio_desde` y `cambio_hasta` en hora local.

**Sincronización.** Cada lote:

1. Elimina las compras vencidas o no publicadas (`purgar_compras_agiles_no_disponibles`).
2. Lee el listado por ventanas de `fecha_ultimo_cambio` con fin fijo, desde la última
   página hacia la primera. Si un registro vuelve a cambiar y sale de la ventana, los
   demás solo pueden repetirse, nunca saltarse. La ventana siguiente se solapa 5 minutos.
   La carga inicial busca las publicadas de los últimos 60 días; después se siguen
   `publicada`, `cancelada` y `desierta`. Una ventana de más de 10.000 resultados (tope
   de paginación de la API) se acorta por la mitad.
3. Encola las publicadas con un cambio que aún no se incorporó y elimina las que el
   listado informa como no disponibles.
4. Descarga hasta `limite` detalles, primero los que aún no están guardados y desde la
   publicación más reciente. Hasta 3 descargas avanzan a la vez, separadas por
   `MP_COMPRA_AGIL_PAUSA_SEGUNDOS`; el guardado sigue el orden de prioridad. Un detalle
   idéntico solo actualiza `verificado_en`.

Un 404 `NO_ENCONTRADO`, un estado distinto de `publicada` o un cierre cumplido eliminan
la compra, sus productos, su RAW y su pendiente. Otros errores posponen ese código
`MP_REINTENTO_ERROR_MINUTOS`. Un 401, 403 o 429 detiene el lote sin posponer el código.
Un listado fallido no impide descargar los detalles ya encolados. El lote se detiene
antes de `MP_COMPRA_AGIL_LOTE_TIMEOUT_SEGUNDOS` (20 s) y deja el resto para el siguiente.
El estado se consulta en `GET /api/ingesta/compras-agiles/estado`.

**Capacidad.** Un día hábil se publican unas 4.000 Compras Ágiles y suele haber más
de 7.000 abiertas en el país. `/api/cron/ingesta` corre en paralelo un lote de 20
detalles (`COMPRAS_AGILES_AUTOMATICAS=true`) con su propio bloqueo y su propia sesión.
Cada 5 minutos son hasta 5.760 detalles y unas 600 páginas de listado diarias. La
carga inicial lee unas 145 páginas y tarda unas 2 a 3 horas; mientras dura, avanza desde
los cambios más antiguos. Para más cobertura se puede programar también
`/api/cron/compras-agiles` en cron-job.org. Para reducir el volumen,
`MP_COMPRA_AGIL_REGIONES=13` limita el listado a compradores de la Región Metropolitana;
la región del comprador no prueba el lugar del servicio. La guía indica una cuota diaria
por ticket (10.000 solicitudes en la práctica). Considera también las solicitudes de la
ingesta de licitaciones si ambas APIs comparten la cuota.

**Preselección.** Las Compras Ágiles pasan por el mismo motor (`reglas-hotel-8`) y los
mismos tres pilares que las licitaciones: vigencia, lugar de prestación en la RM y
alojamiento, salones o alimentación. No tienen bases, así que la cobertura es
`sin_bases`. Como su ficha es toda la información y se entrega, por lo general, donde está
el comprador, las reglas `ca-1` agregan la región del comprador al pilar de ubicación
cuando el texto no ubica el servicio:

- Comprador fuera de la RM y sin mención de la RM en el texto: no cumple, y la compra se
  descarta con ese motivo.
- Comprador en la RM y sin otro lugar en el texto: cumple, y decide el servicio solicitado.
- Si el texto ubica el servicio o lo menciona de forma ambigua, decide el motor común.

En el servicio solicitado también pesan los códigos de producto. Si todas las líneas tienen
códigos ajenos al hotel (por ejemplo, 52 artículos domésticos o 56 mobiliario), la compra se
descarta cuando el texto no menciona servicios del hotel y queda en revisión cuando sí los
menciona: una palabra suelta no la convierte en posible oportunidad. «Residencia» cuenta
como alojamiento solo como «servicio de residencia» o «residencia temporal»; la
«residencia de internos» de un hospital no lo es.

En las licitaciones la región del comprador sigue sin probar el lugar del servicio. Las
evaluaciones se guardan en LicitacionesFiltradas con `oportunidad.modalidad='compra_agil'`,
`version_motor` `reglas-hotel-8+ca-1` y los productos como ítems (`correlativo` = posición).

A la vez que cada lote de ingesta, con su propia sesión, Core evalúa hasta 100 compras
abiertas sin evaluación vigente, en llamadas de 20, durante 15 s como máximo, y confirma el
avance de cada grupo: si el plazo del cron corta el turno, lo ya guardado no se repite. Lo
que guarde el lote del mismo turno se evalúa en el siguiente. `compra_agil.preseleccion` guarda la firma, la
versión del motor, de las reglas de Compra Ágil y del catálogo, y la propuesta automática.
Cambiar `VERSION_REGLAS` reevalúa solo las Compras Ágiles; las licitaciones y sus
revisiones manuales no cambian. Un RAW nuevo la borra; una
versión nueva del motor o del catálogo la deja pendiente. Si filtradas no responde, o si
el perfil del hotel aún no se inicializó desde una sesión, las compras siguen pendientes
y el lote siguiente reintenta. La sincronización con filtradas retira solo Compras Ágiles
que Core ya no conserva, y se ejecuta únicamente después de que filtradas aceptó una: una
filtradas sin la migración `20261025090000_compra_agil.sql` rechaza los códigos COT al
guardar e ignoraría la modalidad, retirando también las licitaciones y sus revisiones.
Las licitaciones sincronizan solo las suyas.

| Ruta | Uso |
|---|---|
| `GET /api/compras-agiles/resumen` | Totales, abiertas, incorporadas en 24 h, cierres en 24 h y propuestas automáticas vigentes de las abiertas |
| `GET /api/compras-agiles/preseleccion` | Clasificación vigente (`clasificacion`, `q`, `limite`, `offset`); marca `pendiente_evaluacion` si la fuente o las reglas cambiaron |
| `POST /api/compras-agiles/preseleccion/evaluar` | Evalúa las pendientes (o los `ids` indicados) con la sesión como autor |
| `GET /api/compras-agiles/{id}/preseleccion` | Criterios y evidencias guardados en filtradas |

**Despliegue**, en este orden; cada paso es compatible con el código anterior:

1. En LicitacionesFiltradas, aplicar `filtradas/supabase/migrations/20261025090000_compra_agil.sql`.
2. En Usuarios/Licitaciones, `alembic upgrade head`. Sin conexión directa, `alembic upgrade
   b5df9fcc5f0d:head --sql` genera el SQL equivalente para el SQL Editor, incluida la
   actualización de `alembic_version`. Debe aplicarse antes de desplegar: el planificador
   de licitaciones consulta `ejecucion_ingesta.fuente`.
3. En Usuarios/Licitaciones, ejecutar desde `SELECT cron.schedule` en adelante de
   `sql/limpieza_programada_supabase.sql`, para incluir la limpieza de Compra Ágil en el
   trabajo de cada minuto. Si pg_cron ya estaba configurado, repetir sus permisos falla con
   `dependent privileges exist`.
4. Publicar Core. El cron existente empieza a ingerir y preseleccionar Compras Ágiles.

El downgrade solo procede sin datos ni ejecuciones de Compra Ágil.

No se descargan adjuntos ni se guardan `proveedores_cotizando` fuera del RAW. Las
pantallas Compras Ágiles y dashboard las muestran; la revisión manual de Compras Ágiles
desde la aplicación queda pendiente.
