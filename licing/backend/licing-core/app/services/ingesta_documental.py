"""Descarga a la capa original; la preselección posterior es independiente."""
import asyncio
import hashlib

from starlette.concurrency import run_in_threadpool

from ..database import SessionLocal
from ..config import settings
from . import documentos_origen as origen
from .bases_mercado_publico import BasesNoDisponibles, descargar_bases
from .pdf_bases import extraer_pdf


async def procesar_documentos(db, actor=None):
    if not settings.mp_descarga_portal_habilitada:
        return {"pendiente": True, "motivo": "canal_descarga_no_confirmado"}
    tarea = None
    try:
        async with asyncio.timeout(45):
            tarea = origen.reservar(db)
            if not tarea:
                return {"procesados": 0}
            descarga = await descargar_bases(tarea["codigo"])
            contenido = descarga.pop("contenido")
            reutilizado = hashlib.sha256(contenido).hexdigest() in tarea["hashes"]
            if not reutilizado:
                extraccion = await run_in_threadpool(extraer_pdf, contenido)
                extraccion["cobertura"].update(origen_captura="portal_bases",
                    anexos_completos=False, bases_completas_confirmadas=False,
                    advertencia="PDF principal del portal; anexos adicionales no comprobados.")
                await origen.guardar(db, tarea["id"], contenido=contenido, extraccion=extraccion,
                    actor=actor, token=tarea["token"], **descarga)
            origen.finalizar(db, tarea, "descargada")
    except asyncio.CancelledError:
        db.rollback()
        if tarea:
            origen.finalizar(db, tarea, "error_temporal")
        raise
    except Exception as exc:
        db.rollback()
        motivo = exc.motivo if isinstance(exc, BasesNoDisponibles) else "error_temporal"
        if tarea:
            origen.finalizar(db, tarea, motivo)
            try:
                from ..api.preseleccion import evaluar_lote
                async with asyncio.timeout(5):
                    await evaluar_lote(db, [tarea["id"]], actor)
            except Exception:
                db.rollback()
        return {"pendiente": True, "motivo": motivo}
    # El documento fuente ya quedó confirmado, incluso si filtradas no responde.
    evaluacion = {"pendiente": True}
    try:
        from ..api.preseleccion import evaluar_lote
        async with asyncio.timeout(5):
            evaluacion = await evaluar_lote(db, [tarea["id"]], actor)
    except Exception:
        db.rollback()
    return {"procesados": 1, "codigo": tarea["codigo"], "reutilizado": reutilizado,
            "anexos_completos": False, "evaluacion": evaluacion}


async def correr_documentos():
    if not settings.mp_descarga_portal_habilitada:
        return {"pendiente": True, "motivo": "canal_descarga_no_confirmado"}
    with SessionLocal() as db:
        try:
            async with asyncio.timeout(settings.documentos_timeout_segundos):
                try:
                    async with asyncio.timeout(1):
                        await origen.storage("limpiar", {})
                except Exception:
                    pass
                return await procesar_documentos(db)
        except TimeoutError:
            db.rollback()
            return {"pendiente": True, "motivo": "tiempo_turno_agotado"}
