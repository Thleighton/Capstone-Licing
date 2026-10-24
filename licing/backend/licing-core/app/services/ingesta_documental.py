"""Descarga a la capa original; la preselección posterior es independiente."""
import asyncio
import hashlib

from starlette.concurrency import run_in_threadpool

from ..database import SessionLocal
from ..config import settings
from . import bases_mercado_publico as portal
from . import documentos_origen as origen
from .bases_mercado_publico import BasesNoDisponibles
from .lectura_office import extraer_office
from .pdf_bases import extraer_pdf

# No empezar otro archivo con menos tiempo que esto: descarga, lectura y guardado.
MARGEN_DOCUMENTO = 7
# Fallos que afectan a la ficha completa: el turno termina y no se insiste ante límites del portal.
DETIENEN_TURNO = {"acceso_restringido", "error_temporal", "redireccion_no_admitida",
                  "demasiadas_redirecciones", "respuesta_invalida"}
ADVERTENCIAS = {
    "portal_bases": "PDF principal del portal; anexos adicionales no comprobados.",
    "portal_anexos": "Anexo de «Antecedentes para incluir en la oferta»; los archivos adjuntos protegidos no se consultan.",
}


async def guardar_descarga(db, tarea, descarga, fuente, actor, resumen):
    contenido = descarga.pop("contenido")
    extension = descarga.pop("extension")
    huella = hashlib.sha256(contenido).hexdigest()
    if huella in tarea["hashes"]:
        resumen["reutilizados"] += 1
        return
    if extension == "pdf":
        extraccion = await run_in_threadpool(extraer_pdf, contenido)
    else:
        extraccion = await run_in_threadpool(extraer_office, contenido, extension)
    captura = "portal_anexos" if fuente else "portal_bases"
    extraccion["cobertura"].update(origen_captura=captura, anexos_completos=False,
        bases_completas_confirmadas=False, advertencia=ADVERTENCIAS[captura])
    if fuente:
        extraccion["cobertura"].update(categoria=fuente["categoria"], fecha_portal=fuente.get("fecha"),
                                       descripcion=fuente.get("descripcion"))
    try:
        await origen.guardar(db, tarea["id"], contenido=contenido, extraccion=extraccion, actor=actor,
                             token=tarea["token"], extension=extension, **descarga)
    except origen.LimiteDocumentos:
        raise BasesNoDisponibles("limite_documentos") from None
    tarea["hashes"].append(huella)
    resumen["guardados"] += 1


async def capturar(db, tarea, actor, plazo):
    """Bases y anexos de una ficha, uno a uno, mientras quede tiempo en el turno."""
    loop = asyncio.get_running_loop()
    resumen = {"guardados": 0, "reutilizados": 0, "omitidos": [], "pendientes": 0}
    async with portal.sesion() as cliente:
        ficha = await portal.abrir_ficha(cliente, tarea["codigo"])
        fuentes = [None] if ficha.boton else []
        if settings.mp_descarga_anexos_habilitada:
            fuentes += await portal.listar_anexos(cliente, ficha)
        if not fuentes:
            raise BasesNoDisponibles("sin_descarga_publica")
        for fuente in fuentes:
            # Un anexo sin cambios no se vuelve a bajar; las bases se omiten solo al continuar una captura.
            clave = (fuente["url_origen"], fuente.get("fecha")) if fuente else (ficha.origen, None)
            if clave in tarea["fuentes"] and (fuente or tarea["continuacion"]):
                resumen["reutilizados"] += 1
                continue
            if plazo - loop.time() < MARGEN_DOCUMENTO:
                resumen["pendientes"] += 1
                continue
            try:
                descarga = await (portal.descargar_anexo(cliente, fuente) if fuente
                                  else portal.descargar_bases_ficha(cliente, ficha))
                await guardar_descarga(db, tarea, descarga, fuente, actor, resumen)
            except BasesNoDisponibles as exc:
                if exc.motivo in DETIENEN_TURNO:
                    raise
                resumen["omitidos"].append({"nombre": fuente["nombre"] if fuente else "Descarga bases",
                                            "codigo": exc.motivo})
    return resumen


async def procesar_documentos(db, actor=None, plazo=None):
    if not settings.mp_descarga_portal_habilitada:
        return {"pendiente": True, "motivo": "canal_descarga_no_confirmado"}
    plazo = plazo or asyncio.get_running_loop().time() + 40
    tarea = None
    try:
        async with asyncio.timeout(45):
            tarea = origen.reservar(db)
            if not tarea:
                return {"procesados": 0}
            resumen = await capturar(db, tarea, actor, plazo)
            if not (resumen["guardados"] or resumen["reutilizados"] or resumen["pendientes"]):
                raise BasesNoDisponibles(resumen["omitidos"][0]["codigo"])
            # Lo guardado ya está confirmado; si faltan archivos, el siguiente turno continúa la ficha.
            origen.finalizar(db, tarea, "pendiente_continuar" if resumen["pendientes"] else "descargada",
                             resumen["omitidos"])
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
    # Los documentos fuente ya quedaron confirmados, incluso si filtradas no responde.
    evaluacion = {"pendiente": True}
    try:
        from ..api.preseleccion import evaluar_lote
        async with asyncio.timeout(5):
            evaluacion = await evaluar_lote(db, [tarea["id"]], actor)
    except Exception:
        db.rollback()
    return {"procesados": 1, "codigo": tarea["codigo"], **resumen, "anexos_completos": False,
            "evaluacion": evaluacion}


async def correr_documentos():
    if not settings.mp_descarga_portal_habilitada:
        return {"pendiente": True, "motivo": "canal_descarga_no_confirmado"}
    with SessionLocal() as db:
        try:
            plazo = asyncio.get_running_loop().time() + settings.documentos_timeout_segundos
            async with asyncio.timeout(settings.documentos_timeout_segundos):
                try:
                    async with asyncio.timeout(1):
                        await origen.storage("limpiar", {})
                except Exception:
                    pass
                return await procesar_documentos(db, plazo=plazo)
        except TimeoutError:
            db.rollback()
            return {"pendiente": True, "motivo": "tiempo_turno_agotado"}
