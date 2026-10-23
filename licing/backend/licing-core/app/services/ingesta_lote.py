import asyncio
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from ..config import settings
from ..database import engine
from ..models.ejecucion_ingesta import EjecucionIngesta
from ..models.licitacion import Licitacion
from ..models.raw import RawMercadoPublico
from .mercado_publico import MercadoPublicoClient
from .normalizacion import VERSION_NORMALIZACION
from .procesamiento import procesar_detalle_guardado
from .limpieza import LicitacionNoDisponible, ausencia_confirmada, eliminar_no_disponibles, motivo_no_disponible

ID_BLOQUEO_INGESTA = 728401
CHILE = ZoneInfo("America/Santiago")


class EjecucionEnCursoError(RuntimeError):
    pass


def seleccionar_codigos_nuevos(listado, codigos_existentes, limite=5):
    if not isinstance(limite, int) or isinstance(limite, bool) or not 1 <= limite <= 20:
        raise ValueError("El límite debe ser un entero entre 1 y 20.")
    seleccionados, vistos = [], set(codigos_existentes)
    for resumen in listado:
        codigo = resumen.get("CodigoExterno")
        if not isinstance(codigo, str) or not codigo.strip() or codigo.strip() in vistos:
            continue
        codigo = codigo.strip()
        seleccionados.append(codigo)
        vistos.add(codigo)
        if len(seleccionados) >= limite:
            break
    return seleccionados


def alternar_codigos(nuevos, actualizar, limite, priorizar_actualizacion=False):
    """Alternar las dos colas evita que nuevas y actualizaciones se bloqueen entre sí."""
    colas = [iter(actualizar), iter(nuevos)] if priorizar_actualizacion else [iter(nuevos), iter(actualizar)]
    salida = []
    while len(salida) < limite and colas:
        siguientes = []
        for cola in colas:
            codigo = next(cola, None)
            if codigo is None:
                continue
            siguientes.append(cola)
            if codigo not in salida:
                salida.append(codigo)
            if len(salida) == limite:
                break
        colas = siguientes
    return salida


async def planificar_ingesta(db: Session, client: MercadoPublicoClient, limite=5):
    seleccionar_codigos_nuevos([], set(), limite)
    respuesta = await client.licitaciones_activas()
    if not isinstance(respuesta, dict) or not isinstance(respuesta.get("Listado"), list):
        raise ValueError("La respuesta no contiene un Listado válido.")
    listado = respuesta["Listado"]
    if any(not isinstance(item, dict) for item in listado):
        raise ValueError("El listado contiene elementos inválidos.")
    listado_vigente = [item for item in listado if not motivo_no_disponible(item)]

    ahora = datetime.now(timezone.utc)
    filas = db.execute(select(
        Licitacion.codigo_externo, Licitacion.codigo_estado, Licitacion.estado,
        Licitacion.fecha_cierre, RawMercadoPublico.verificado_en,
    ).join(RawMercadoPublico, RawMercadoPublico.id == Licitacion.raw_id)).all()
    existentes = {f.codigo_externo for f in filas}
    pospuestos, redescargar = set(), set()
    recientes = db.execute(select(EjecucionIngesta.inicio, EjecucionIngesta.errores).where(
        EjecucionIngesta.inicio >= ahora - timedelta(days=1),
    )).all()
    for inicio, errores in recientes:
        for error in errores or []:
            # Una nueva versión puede recuperar un RAW rechazado por la anterior.
            if error.get("normalizacion_version") != VERSION_NORMALIZACION:
                continue
            codigo = error.get("codigo_externo")
            if not isinstance(codigo, str) or error.get("tipo") not in {
                "ValueError", "HTTPStatusError", "RequestError", "TimeoutError",
            }:
                continue
            redescargar.add(codigo)
            if inicio + timedelta(minutes=settings.mp_reintento_error_minutos) > ahora:
                pospuestos.add(codigo)

    actualizar = []
    for fila in filas:
        if fila.codigo_externo in pospuestos:
            continue
        if fila.codigo_estado != 5 and (fila.estado or "").strip().lower() != "publicada":
            continue
        consultado = fila.verificado_en
        cierre = fila.fecha_cierre
        cierre_utc = cierre.replace(tzinfo=CHILE).astimezone(timezone.utc) if cierre else None
        antiguo = consultado <= ahora - timedelta(hours=settings.mp_actualizacion_horas)
        cierre_pendiente = cierre_utc is not None and consultado < cierre_utc <= ahora
        if antiguo or cierre_pendiente:
            actualizar.append((not cierre_pendiente, consultado, fila.codigo_externo))
    actualizar.sort()
    codigos_actualizar = [f[2] for f in actualizar]
    excluidos = existentes | pospuestos
    nuevos = [
        codigo for codigo in dict.fromkeys(
            r["CodigoExterno"].strip() for r in listado_vigente
            if isinstance(r.get("CodigoExterno"), str) and r["CodigoExterno"].strip()
        ) if codigo not in excluidos
    ]
    turno = db.scalar(select(func.max(EjecucionIngesta.id))) or 0
    seleccionados = alternar_codigos(nuevos, codigos_actualizar, limite, turno % 2 == 0)
    return {
        "total_informado_api": respuesta.get("Cantidad"),
        "resumenes_recibidos": len(listado),
        "limite_detalles": limite,
        "cantidad_seleccionada": len(seleccionados),
        "codigos_a_descargar": seleccionados,
        "codigos_a_actualizar": [c for c in seleccionados if c in codigos_actualizar],
        "codigos_redescargar": [c for c in seleccionados if c in redescargar or c in codigos_actualizar],
        "nuevos_pendientes": len(nuevos),
        "actualizaciones_pendientes": len(codigos_actualizar),
        "pospuestos_por_error": len(pospuestos),
    }


async def obtener_o_descargar_detalle(db, client, codigo, forzar_descarga=False):
    existente = db.scalars(select(RawMercadoPublico).where(
        RawMercadoPublico.codigo_externo == codigo,
        RawMercadoPublico.tipo_consulta == "detalle_codigo",
    ).order_by(RawMercadoPublico.id.desc()).limit(1)).first()
    if existente is not None and not forzar_descarga:
        motivo = motivo_no_disponible(existente.respuesta)
        if motivo:
            raise LicitacionNoDisponible(motivo)
        return existente, False
    await asyncio.sleep(settings.mp_pausa_detalles_segundos)
    respuesta = await client.licitacion_por_codigo(codigo)
    if not isinstance(respuesta, dict):
        raise ValueError("La consulta por código no devolvió un objeto JSON.")
    listado = respuesta.get("Listado")
    if ausencia_confirmada(respuesta):
        raise LicitacionNoDisponible("no_encontrada_por_codigo")
    if not isinstance(listado, list) or len(listado) != 1:
        raise ValueError("Se esperaba exactamente un detalle por código.")
    detalle = listado[0]
    if not isinstance(detalle, dict):
        raise ValueError("El detalle tiene una estructura inválida.")
    if detalle.get("CodigoExterno") != codigo:
        raise ValueError("La API devolvió un código diferente del solicitado.")
    motivo = motivo_no_disponible(detalle)
    if motivo:
        raise LicitacionNoDisponible(motivo)
    # Una actualización idéntica confirma frescura sin duplicar todo el JSON.
    if existente is not None and existente.respuesta == detalle:
        existente.verificado_en = datetime.now(timezone.utc)
        db.commit()
        return existente, True
    registro = RawMercadoPublico(
        fuente="licitaciones", tipo_consulta="detalle_codigo", parametro_consulta=codigo,
        codigo_externo=codigo, respuesta=detalle, http_status=200,
        cantidad_resultados=respuesta.get("Cantidad"),
    )
    try:
        db.add(registro)
        db.commit()
        db.refresh(registro)
    except Exception:
        db.rollback()
        raise
    return registro, True


def error_de_codigo(codigo, exc, raw_id=None):
    error = {
        "codigo_externo": codigo,
        "raw_id": raw_id,
        "normalizacion_version": VERSION_NORMALIZACION,
    }
    if isinstance(exc, httpx.HTTPStatusError):
        error.update(tipo="HTTPStatusError", status_code=exc.response.status_code,
                     mensaje=f"Mercado Público respondió HTTP {exc.response.status_code}.")
    elif isinstance(exc, httpx.RequestError):
        error.update(tipo="RequestError", mensaje="No se pudo conectar con Mercado Público.")
    elif isinstance(exc, ValueError):
        error.update(tipo="ValueError", mensaje=str(exc)[:400])
    else:
        error.update(tipo=type(exc).__name__, mensaje="No se pudo persistir el detalle.")
    return error


async def _ejecutar_lote_interno(db, client, limite_detalles=1, progreso=None):
    resultado = progreso if progreso is not None else {}
    # Se confirma antes de la llamada externa: una caída de la API no revierte la limpieza.
    resultado["limpieza"] = eliminar_no_disponibles(db)
    db.commit()
    plan = await planificar_ingesta(db, client, limite_detalles)
    resultado.update(plan=plan)
    actualizar = set(plan["codigos_a_actualizar"])
    for codigo in plan["codigos_a_descargar"]:
        resultado["codigo_en_curso"] = codigo
        raw_id = None
        try:
            registro, descargado = await obtener_o_descargar_detalle(
                db, client, codigo, forzar_descarga=codigo in plan["codigos_redescargar"],
            )
            raw_id = registro.id
            resultado["descargados" if descargado else "reutilizados"] += 1
            with db.begin_nested():
                procesado = procesar_detalle_guardado(db, registro)
            db.commit()
            if procesado["procesado"]:
                resultado["procesados"] += 1
                resultado["actualizados"] += int(codigo in actualizar)
                resultado["resultados"].append(procesado)
            else:
                resultado["descartadas"].append(procesado)
        except LicitacionNoDisponible as exc:
            db.rollback()
            eliminados = eliminar_no_disponibles(db, codigo, confirmada=True)
            db.commit()
            resultado["descartadas"].append({"codigo_externo": codigo, "motivo": str(exc), **eliminados})
        except Exception as exc:
            db.rollback()
            resultado["errores"].append(error_de_codigo(codigo, exc, raw_id))
            if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code in {401, 403, 429}:
                resultado["detenido_por_error_api"] = True
                break
        finally:
            resultado["codigo_en_curso"] = None
    return resultado


async def ejecutar_ingesta_lote(db, client, limite_detalles=1):
    seleccionar_codigos_nuevos([], set(), limite_detalles)
    conexion = engine.connect()
    adquirido = False
    try:
        adquirido = conexion.execute(text("SELECT pg_try_advisory_lock(:id)"), {"id": ID_BLOQUEO_INGESTA}).scalar_one()
        if not adquirido:
            raise EjecucionEnCursoError("Ya existe una ejecución de ingesta en curso.")
        return await _ejecutar_ingesta_lote_con_bloqueo(db, client, limite_detalles)
    finally:
        try:
            if adquirido:
                conexion.execute(text("SELECT pg_advisory_unlock(:id)"), {"id": ID_BLOQUEO_INGESTA})
                conexion.commit()
        finally:
            conexion.close()


def _cerrar_ejecucion(db, ejecucion_id, resultado, estado):
    fila = db.get(EjecucionIngesta, ejecucion_id)
    fila.fin = datetime.now(timezone.utc)
    fila.estado = estado
    fila.resumenes_recibidos = resultado["plan"].get("resumenes_recibidos", 0)
    fila.seleccionados = resultado["plan"].get("cantidad_seleccionada", 0)
    for nombre in ("descargados", "reutilizados", "procesados", "detenido_por_error_api", "errores"):
        setattr(fila, nombre, resultado[nombre])
    db.commit()


async def _ejecutar_ingesta_lote_con_bloqueo(db, client, limite_detalles=1):
    ejecucion = EjecucionIngesta(limite_detalles=limite_detalles, estado="en_curso")
    db.add(ejecucion)
    db.commit()
    db.refresh(ejecucion)
    ejecucion_id = ejecucion.id
    progreso = {
        "plan": {}, "descargados": 0, "reutilizados": 0, "procesados": 0,
        "actualizados": 0, "resultados": [], "errores": [], "descartadas": [],
        "detenido_por_error_api": False, "codigo_en_curso": None,
    }
    try:
        async with asyncio.timeout(settings.mp_lote_timeout_segundos):
            await _ejecutar_lote_interno(db, client, limite_detalles, progreso)
        estado = "completada" if not progreso["errores"] else "parcial" if progreso["procesados"] else "error"
    except TimeoutError:
        db.rollback()
        progreso["interrumpido"] = True
        progreso["errores"].append({
            "tipo": "TimeoutError", "mensaje": "Se agotó el tiempo del lote; los avances confirmados se conservan.",
            "normalizacion_version": VERSION_NORMALIZACION,
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
    return progreso
