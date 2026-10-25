"""Lote de Compra Ágil: listado incremental -> cola de pendientes -> detalles normalizados.

El listado se recorre por ventanas de fecha_ultimo_cambio. Cada ventana tiene un fin
fijo y se lee desde su última página hacia la primera: si un registro vuelve a cambiar
y sale de la ventana, los demás solo pueden repetirse, nunca saltarse. Lo que cambia
después del fin aparece en la ventana siguiente, que se solapa unos minutos.
"""
import asyncio
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import delete, func, or_, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from ..config import settings
from ..database import engine
from ..models.compra_agil import CompraAgil
from ..models.compra_agil_sincronizacion import CompraAgilPendiente, CompraAgilSincronizacion
from ..models.ejecucion_ingesta import EjecucionIngesta
from .compra_agil_normalizacion import (
    CHILE, VERSION_NORMALIZACION_COMPRA_AGIL, leer_resumen, motivo_no_disponible, normalizar_compra_agil,
)
from .compra_agil_persistencia import (
    CompraAgilNoDisponible, eliminar_compras_no_disponibles, guardar_raw, procesar_compra_guardada,
)
from .ingesta_lote import EjecucionEnCursoError, error_de_codigo

ID_BLOQUEO_COMPRA_AGIL = 728402
TAMANO_PAGINA = 50
# La API rechaza páginas más allá de los primeros 10.000 resultados de una búsqueda.
LIMITE_BUSQUEDA = 10_000
# La carga inicial busca publicadas cuyo último cambio ocurrió en este plazo.
DIAS_ARRANQUE = 60
# Cubre cambios que la API indexa con retraso respecto de su fecha_ultimo_cambio.
SOLAPE = timedelta(minutes=5)
ESTADOS_ARRANQUE = "publicada"
# Cancelada y desierta permiten retirar compras guardadas antes de su cierre.
ESTADOS_SEGUIMIENTO = "publicada,cancelada,desierta"
ERRORES_QUE_DETIENEN = {401, 403, 429}
# El listado usa como máximo esta fracción del lote; los detalles se detienen antes del final.
FRACCION_LISTADO = 0.4
MARGEN_FINAL_SEGUNDOS = 4
# Cada detalle tarda cerca de 1 s; con el ritmo global se descargan varios a la vez.
CONCURRENCIA_DETALLES = 3


class Ritmo:
    """Separa el inicio de cada solicitud del lote; la API admite hasta 4 por segundo."""

    def __init__(self, pausa: float):
        self.pausa = pausa
        self.proximo = 0.0
        self.candado = asyncio.Lock()

    async def esperar(self):
        async with self.candado:
            loop = asyncio.get_running_loop()
            if (espera := self.proximo - loop.time()) > 0:
                await asyncio.sleep(espera)
            self.proximo = loop.time() + self.pausa


class SinTiempo(Exception):
    pass


def ahora_chile() -> datetime:
    return datetime.now(CHILE).replace(tzinfo=None, microsecond=0)


def regiones_configuradas() -> list[int]:
    regiones = [int(r) for r in settings.mp_compra_agil_regiones.replace(" ", "").split(",") if r]
    if any(not 1 <= r <= 16 for r in regiones):
        raise ValueError("MP_COMPRA_AGIL_REGIONES admite códigos de región entre 1 y 16.")
    return regiones


def validar_limite(limite):
    if not isinstance(limite, int) or isinstance(limite, bool) or not 1 <= limite <= 20:
        raise ValueError("El límite debe ser un entero entre 1 y 20.")


def parametros_listado(desde, hasta, estados, pagina) -> dict:
    # Sin zona: la API compara contra hora de Chile e ignora el sufijo de zona.
    params = {
        "cambio_desde": desde.isoformat(timespec="seconds"),
        "cambio_hasta": hasta.isoformat(timespec="seconds"),
        "estado": estados,
        "ordenar_por": "FechaUltimaModificacion",
        "tamano_pagina": TAMANO_PAGINA,
        "numero_pagina": pagina,
    }
    if regiones := regiones_configuradas():
        params["region"] = ",".join(map(str, regiones))
    return params


def leer_pagina(payload: dict):
    items, paginacion = payload.get("items"), payload.get("paginacion")
    if not isinstance(items, list) or not isinstance(paginacion, dict):
        raise ValueError("El listado de Compra Ágil no contiene items y paginacion válidos.")
    total, paginas = paginacion.get("total_resultados"), paginacion.get("total_paginas")
    if not all(isinstance(v, int) and not isinstance(v, bool) and v >= 0 for v in (total, paginas)):
        raise ValueError("La paginación del listado de Compra Ágil es inválida.")
    return items, total, paginas


def registrar_resumenes(db: Session, items: list, progreso: dict):
    """Encola las disponibles con cambios nuevos y retira las que ya no lo están. Sin commit."""
    listado = progreso["listado"]
    vigentes, no_disponibles = {}, set()
    for item in items:
        try:
            resumen = leer_resumen(item)
        except ValueError:
            listado["invalidos"] += 1
            continue
        codigo = resumen["codigo_externo"]
        if motivo_no_disponible(resumen["estado"], resumen["id_estado"], resumen["fecha_cierre"]):
            no_disponibles.add(codigo)
        elif codigo not in vigentes or resumen["cambio"] > vigentes[codigo]["cambio"]:
            vigentes[codigo] = resumen
    if no_disponibles:
        # El listado confirma el estado actual: no es una simple ausencia.
        eliminados = eliminar_compras_no_disponibles(db, sorted(no_disponibles), confirmada=True)
        listado["descartados"] += len(no_disponibles)
        listado["eliminadas"] += eliminados["compras"]
    if not vigentes:
        return
    sincronizadas = dict(db.execute(select(CompraAgil.codigo_externo, CompraAgil.cambio_sincronizado).where(
        CompraAgil.codigo_externo.in_(list(vigentes)),
    )).all())
    filas = [{campo: r[campo] for campo in ("codigo_externo", "cambio", "fecha_publicacion", "fecha_cierre")}
             for codigo, r in sorted(vigentes.items())
             if sincronizadas.get(codigo) is None or r["cambio"] > sincronizadas[codigo]]
    if not filas:
        return
    sentencia = insert(CompraAgilPendiente).values(filas)
    db.execute(sentencia.on_conflict_do_update(index_elements=["codigo_externo"], set_={
        "cambio": func.greatest(CompraAgilPendiente.cambio, sentencia.excluded.cambio),
        "fecha_publicacion": sentencia.excluded.fecha_publicacion,
        "fecha_cierre": sentencia.excluded.fecha_cierre,
    }))
    listado["encolados"] += len(filas)


async def _consultar(client, desde, hasta, estados, pagina, progreso, ritmo):
    await ritmo.esperar()
    payload = await client.listar(parametros_listado(desde, hasta, estados, pagina))
    progreso["listado"]["paginas"] += 1
    items, total, paginas = leer_pagina(payload)
    progreso["listado"]["resumenes"] += len(items)
    return items, total, paginas


def _cerrar_ventana(estado: CompraAgilSincronizacion, hasta):
    estado.cursor = hasta
    estado.ventana_desde = estado.ventana_hasta = estado.ventana_estados = estado.pagina = None


async def sincronizar_listado(db: Session, client, progreso: dict, plazo: float | None = None, ritmo=None):
    ritmo = ritmo or Ritmo(settings.mp_compra_agil_pausa_segundos)
    estado = db.get(CompraAgilSincronizacion, 1)
    if estado is None:
        raise ValueError("Falta la fila de sincronización de Compra Ágil; aplica las migraciones.")
    maximo = settings.mp_compra_agil_paginas_por_lote
    listado = progreso["listado"]
    loop = asyncio.get_running_loop()
    while listado["paginas"] < maximo and (plazo is None or loop.time() < plazo):
        if estado.pagina is None:
            hasta = ahora_chile()
            if estado.cursor is None:
                desde, estados = hasta - timedelta(days=DIAS_ARRANQUE), ESTADOS_ARRANQUE
            else:
                desde, estados = min(estado.cursor - SOLAPE, hasta), ESTADOS_SEGUIMIENTO
            items, total, paginas = await _consultar(client, desde, hasta, estados, 1, progreso, ritmo)
            while total > LIMITE_BUSQUEDA and hasta - desde > timedelta(minutes=1) and listado["paginas"] < maximo:
                hasta = (desde + (hasta - desde) / 2).replace(microsecond=0)
                items, total, paginas = await _consultar(client, desde, hasta, estados, 1, progreso, ritmo)
            if total > LIMITE_BUSQUEDA:
                break  # El siguiente lote vuelve a acotar la ventana.
            if paginas <= 1:
                registrar_resumenes(db, items, progreso)
                _cerrar_ventana(estado, hasta)
            else:
                # La primera página se vuelve a leer al final, cuando la ventana ya no cambia de orden.
                estado.ventana_desde, estado.ventana_hasta = desde, hasta
                estado.ventana_estados, estado.pagina = estados, paginas
        else:
            items, total, paginas = await _consultar(
                client, estado.ventana_desde, estado.ventana_hasta, estado.ventana_estados, estado.pagina,
                progreso, ritmo,
            )
            if estado.pagina > paginas:
                # Salieron registros de la ventana: su última página es ahora una anterior.
                estado.pagina = paginas or None
                if paginas == 0:
                    _cerrar_ventana(estado, estado.ventana_hasta)
            else:
                registrar_resumenes(db, items, progreso)
                if estado.pagina == 1:
                    _cerrar_ventana(estado, estado.ventana_hasta)
                else:
                    estado.pagina -= 1
        estado.actualizado_en = datetime.now(timezone.utc)
        db.commit()
        if estado.pagina is None and estado.cursor >= ahora_chile() - timedelta(minutes=1):
            break  # Al día: no repetir la misma ventana dentro del lote.


async def obtener_detalle(client, codigo: str, contexto: dict) -> dict:
    """Descarga y valida un detalle sin tocar la base. CompraAgilNoDisponible si ya no recibe cotizaciones."""
    detalle = await client.detalle(codigo)
    contexto["descargado"] = True
    if detalle is None:
        raise CompraAgilNoDisponible("no_encontrada_por_codigo")
    datos = normalizar_compra_agil(detalle)
    if datos["codigo_externo"] != codigo:
        raise ValueError("La API devolvió un código diferente del solicitado.")
    motivo = motivo_no_disponible(datos["estado"], datos["id_estado"], datos["fecha_cierre"])
    if motivo:
        raise CompraAgilNoDisponible(motivo)
    return detalle


async def descargar_y_procesar(db: Session, client, codigo: str, cambio=None, contexto: dict | None = None) -> dict:
    contexto = {} if contexto is None else contexto
    return guardar_detalle(db, codigo, await obtener_detalle(client, codigo, contexto), cambio, contexto)


def guardar_detalle(db: Session, codigo: str, detalle: dict, cambio=None, contexto: dict | None = None) -> dict:
    contexto = {} if contexto is None else contexto
    registro = guardar_raw(db, codigo, detalle)
    # El RAW se conserva aunque la normalización posterior falle.
    db.commit()
    contexto["raw_id"] = registro.id
    with db.begin_nested():
        resultado = procesar_compra_guardada(db, registro, cambio_sincronizado=cambio)
    if cambio is not None:
        db.execute(delete(CompraAgilPendiente).where(
            CompraAgilPendiente.codigo_externo == codigo, CompraAgilPendiente.cambio <= cambio,
        ))
    db.commit()
    return resultado


async def descargar_pendientes(db: Session, client, limite: int, progreso: dict, plazo: float | None = None,
                               ritmo=None):
    ritmo = ritmo or Ritmo(settings.mp_compra_agil_pausa_segundos)
    ahora, ahora_utc = ahora_chile(), datetime.now(timezone.utc)
    filas = db.execute(select(CompraAgilPendiente.codigo_externo, CompraAgilPendiente.cambio).outerjoin(
        CompraAgil, CompraAgil.codigo_externo == CompraAgilPendiente.codigo_externo,
    ).where(
        or_(CompraAgilPendiente.fecha_cierre.is_(None), CompraAgilPendiente.fecha_cierre > ahora),
        or_(CompraAgilPendiente.reintentar_desde.is_(None), CompraAgilPendiente.reintentar_desde <= ahora_utc),
    ).order_by(
        # Primero las que aún no están guardadas, desde la publicación más reciente.
        CompraAgil.id.is_not(None), CompraAgilPendiente.fecha_publicacion.desc().nullslast(),
        CompraAgilPendiente.codigo_externo,
    ).limit(limite)).all()
    progreso["seleccionados"] = len(filas)
    loop = asyncio.get_running_loop()
    semaforo = asyncio.Semaphore(CONCURRENCIA_DETALLES)
    contextos = [{} for _ in filas]

    async def bajar(codigo, contexto):
        async with semaforo:
            if plazo is not None and loop.time() >= plazo:
                raise SinTiempo
            await ritmo.esperar()
            return await obtener_detalle(client, codigo, contexto)

    # Las descargas avanzan en paralelo; el guardado sigue el orden de prioridad.
    tareas = [asyncio.create_task(bajar(codigo, contexto)) for (codigo, _), contexto in zip(filas, contextos)]
    try:
        await _guardar_en_orden(db, filas, tareas, contextos, progreso, plazo)
    finally:
        for tarea in tareas:
            tarea.cancel()
        await asyncio.gather(*tareas, return_exceptions=True)


async def _guardar_en_orden(db: Session, filas, tareas, contextos, progreso: dict, plazo: float | None):
    loop = asyncio.get_running_loop()
    for indice, ((codigo, cambio), tarea, contexto) in enumerate(zip(filas, tareas, contextos)):
        if plazo is not None and loop.time() >= plazo:
            progreso["pospuestos_por_tiempo"] = len(filas) - indice
            break
        progreso["codigo_en_curso"] = codigo
        try:
            resultado = guardar_detalle(db, codigo, await tarea, cambio, contexto)
            progreso["procesados"] += 1
            progreso["resultados"].append(resultado)
        except SinTiempo:
            progreso["pospuestos_por_tiempo"] = len(filas) - indice
            break
        except CompraAgilNoDisponible as exc:
            db.rollback()
            eliminados = eliminar_compras_no_disponibles(db, [codigo], confirmada=True)
            db.commit()
            progreso["descartadas"].append({"codigo_externo": codigo, "motivo": str(exc), **eliminados})
        except Exception as exc:
            db.rollback()
            error = {**error_de_codigo(codigo, exc, contexto.get("raw_id")),
                     "normalizacion_version": VERSION_NORMALIZACION_COMPRA_AGIL}
            progreso["errores"].append(error)
            if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code in ERRORES_QUE_DETIENEN:
                # Ticket o cuota: la compra no tiene la culpa y se reintenta en el próximo lote.
                progreso["detenido_por_error_api"] = True
                break
            db.execute(update(CompraAgilPendiente).where(CompraAgilPendiente.codigo_externo == codigo).values(
                intentos=CompraAgilPendiente.intentos + 1,
                reintentar_desde=datetime.now(timezone.utc) + timedelta(minutes=settings.mp_reintento_error_minutos),
                ultimo_error=error,
            ))
            db.commit()
        finally:
            progreso["descargados"] += int(contexto.get("descargado", False))
            progreso["codigo_en_curso"] = None


def estado_sincronizacion(db: Session) -> dict:
    estado = db.get(CompraAgilSincronizacion, 1)
    ahora = ahora_chile()
    vigentes = or_(CompraAgilPendiente.fecha_cierre.is_(None), CompraAgilPendiente.fecha_cierre > ahora)
    return {
        "carga_inicial_completa": estado is not None and estado.cursor is not None,
        "cursor": estado.cursor if estado else None,
        "ventana": None if estado is None or estado.pagina is None else {
            "desde": estado.ventana_desde, "hasta": estado.ventana_hasta,
            "estados": estado.ventana_estados, "pagina_pendiente": estado.pagina,
        },
        "pendientes": db.scalar(select(func.count()).select_from(CompraAgilPendiente).where(vigentes)),
        "pendientes_con_error": db.scalar(select(func.count()).select_from(CompraAgilPendiente).where(
            vigentes, CompraAgilPendiente.reintentar_desde.is_not(None),
        )),
        "compras_guardadas": db.scalar(select(func.count()).select_from(CompraAgil)),
    }


async def _lote_interno(db: Session, client, limite: int, progreso: dict):
    loop = asyncio.get_running_loop()
    ritmo = Ritmo(settings.mp_compra_agil_pausa_segundos)
    duracion = settings.mp_compra_agil_lote_timeout_segundos
    plazo_listado = loop.time() + duracion * FRACCION_LISTADO
    plazo_detalles = loop.time() + max(duracion - MARGEN_FINAL_SEGUNDOS, duracion / 2)
    # Se confirma antes de consultar la API: una caída posterior no revierte la limpieza.
    progreso["limpieza"] = eliminar_compras_no_disponibles(db)
    db.commit()
    try:
        await sincronizar_listado(db, client, progreso, plazo_listado, ritmo)
    except (httpx.HTTPError, ValueError) as exc:
        # Un listado fallido no impide avanzar con los detalles ya encolados.
        db.rollback()
        progreso["errores"].append({**error_de_codigo(None, exc), "etapa": "listado",
                                    "normalizacion_version": VERSION_NORMALIZACION_COMPRA_AGIL})
        if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code in ERRORES_QUE_DETIENEN:
            progreso["detenido_por_error_api"] = True
            return
    await descargar_pendientes(db, client, limite, progreso, plazo_detalles, ritmo)


def _cerrar_ejecucion(db: Session, ejecucion_id: int, progreso: dict, estado: str):
    fila = db.get(EjecucionIngesta, ejecucion_id)
    fila.fin = datetime.now(timezone.utc)
    fila.estado = estado
    fila.resumenes_recibidos = progreso["listado"]["resumenes"]
    for nombre in ("seleccionados", "descargados", "procesados", "detenido_por_error_api", "errores"):
        setattr(fila, nombre, progreso[nombre])
    db.commit()


async def _ejecutar_con_bloqueo(db: Session, client, limite: int) -> dict:
    ejecucion = EjecucionIngesta(fuente="compra_agil", limite_detalles=limite, estado="en_curso")
    db.add(ejecucion)
    db.commit()
    db.refresh(ejecucion)
    ejecucion_id = ejecucion.id
    progreso = {
        "listado": {"paginas": 0, "resumenes": 0, "encolados": 0, "descartados": 0, "eliminadas": 0, "invalidos": 0},
        "seleccionados": 0, "descargados": 0, "procesados": 0, "resultados": [], "descartadas": [],
        "errores": [], "detenido_por_error_api": False, "codigo_en_curso": None,
    }
    try:
        async with asyncio.timeout(settings.mp_compra_agil_lote_timeout_segundos):
            await _lote_interno(db, client, limite, progreso)
        estado = "completada" if not progreso["errores"] else "parcial" if progreso["procesados"] else "error"
    except TimeoutError:
        db.rollback()
        progreso["interrumpido"] = True
        progreso["errores"].append({
            "tipo": "TimeoutError", "mensaje": "Se agotó el tiempo del lote; los avances confirmados se conservan.",
            "normalizacion_version": VERSION_NORMALIZACION_COMPRA_AGIL,
        })
        estado = "interrumpida"
    except asyncio.CancelledError:
        db.rollback()
        progreso["errores"].append({"tipo": "CancelledError", "mensaje": "La ejecución fue cancelada."})
        _cerrar_ejecucion(db, ejecucion_id, progreso, "interrumpida")
        raise
    except Exception as exc:
        db.rollback()
        progreso["errores"].append({"tipo": type(exc).__name__, "mensaje": "No se pudo completar el lote."})
        _cerrar_ejecucion(db, ejecucion_id, progreso, "error")
        raise
    _cerrar_ejecucion(db, ejecucion_id, progreso, estado)
    progreso.pop("codigo_en_curso", None)
    progreso["ejecucion_id"] = ejecucion_id
    progreso["sincronizacion"] = estado_sincronizacion(db)
    return progreso


async def ejecutar_lote_compras_agiles(db: Session, client, limite: int = 10) -> dict:
    """Bloqueo propio: puede correr en paralelo con el lote de licitaciones."""
    validar_limite(limite)
    regiones_configuradas()
    conexion = engine.connect()
    adquirido = False
    try:
        adquirido = conexion.execute(
            text("SELECT pg_try_advisory_lock(:id)"), {"id": ID_BLOQUEO_COMPRA_AGIL},
        ).scalar_one()
        if not adquirido:
            raise EjecucionEnCursoError("Ya existe una ejecución de Compra Ágil en curso.")
        return await _ejecutar_con_bloqueo(db, client, limite)
    finally:
        try:
            if adquirido:
                conexion.execute(text("SELECT pg_advisory_unlock(:id)"), {"id": ID_BLOQUEO_COMPRA_AGIL})
                conexion.commit()
        finally:
            conexion.close()

