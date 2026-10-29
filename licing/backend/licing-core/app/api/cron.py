import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..auth import solo_cron
from ..database import SessionLocal, get_db
from ..config import settings
from ..services.ingesta_documental import correr_documentos, procesar_cola_analisis_documental
from ..services.ingesta_lote import EjecucionEnCursoError
from .ingesta import correr_compras_agiles, correr_lote

router = APIRouter(prefix="/api/cron", tags=["Cron"], dependencies=[Depends(solo_cron)])

# Detalles de Compra Ágil por turno cuando corre junto a la ingesta de licitaciones.
LIMITE_COMPRAS_AGILES_AUTOMATICAS = 20


async def compras_agiles_en_paralelo():
    """Sesión propia: corre a la vez que el lote de licitaciones sin compartir transacción."""
    with SessionLocal() as db:
        try:
            return await correr_compras_agiles(db=db, limite=LIMITE_COMPRAS_AGILES_AUTOMATICAS)
        except EjecucionEnCursoError as exc:
            return {"omitida": True, "motivo": str(exc)}
        except HTTPException as exc:
            return {"pendiente": True, "motivo": exc.detail}
        except Exception:
            db.rollback()
            return {"pendiente": True, "motivo": "error_temporal"}


async def esperar_hasta(tarea, plazo):
    """Si la tarea no termina antes del plazo se cancela: su lote queda 'interrumpida'."""
    try:
        async with asyncio.timeout_at(plazo):
            return await tarea
    except TimeoutError:
        return {"pendiente": True, "motivo": "tiempo_turno_agotado"}
    except Exception:
        return {"pendiente": True, "motivo": "error_temporal"}


# GET para Vercel Cron y POST para planificadores externos como cron-job.org.
@router.get("/ingesta")
@router.post("/ingesta")
async def ingesta_programada(
    limite: int = Query(default=1, ge=1, le=5),
    db: Session = Depends(get_db),
):
    # Un solo plazo para las tres tareas: cron-job.org no espera más de 30 s.
    plazo = asyncio.get_running_loop().time() + settings.cron_plazo_respuesta_segundos
    documental = asyncio.create_task(procesar_cola_analisis_documental(1)) if settings.documentos_automaticos else None
    compras = asyncio.create_task(compras_agiles_en_paralelo()) if settings.compras_agiles_automaticas else None
    try:
        async with asyncio.timeout_at(plazo):
            resultado = await correr_lote(db=db, limite=limite)
    except EjecucionEnCursoError as exc:
        # Otra ingesta sigue activa: se omite este turno sin contarlo como fallo.
        resultado = {"omitida": True, "motivo": str(exc)}
    except TimeoutError:
        # Lo confirmado se conserva y el lote queda 'interrumpida'; el siguiente turno continúa.
        db.rollback()
        resultado = {"pendiente": True, "motivo": "tiempo_turno_agotado"}
    finally:
        # No dejar tareas de fondo que Vercel pueda cortar al devolver la respuesta.
        if documental:
            documentos = await esperar_hasta(documental, plazo)
        if compras:
            compras_agiles = await esperar_hasta(compras, plazo)
    if documental:
        resultado["analisis_documental"] = documentos
    if compras:
        resultado["compras_agiles"] = compras_agiles
    return resultado


@router.get("/documentos")
@router.post("/documentos")
async def documentos_programados():
    """Permite un planificador documental independiente con el mismo secreto."""
    return await correr_documentos()


@router.get("/compras-agiles")
@router.post("/compras-agiles")
async def compras_agiles_programadas(
    limite: int = Query(default=20, ge=1, le=20),
    db: Session = Depends(get_db),
):
    """Planificador independiente de Compra Ágil, con el mismo secreto y bloqueo propio."""
    try:
        return await correr_compras_agiles(db=db, limite=limite)
    except EjecucionEnCursoError as exc:
        return {"omitida": True, "motivo": str(exc)}
