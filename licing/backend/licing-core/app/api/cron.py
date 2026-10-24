import asyncio

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..auth import solo_cron
from ..database import get_db
from ..config import settings
from ..services.ingesta_documental import correr_documentos
from ..services.ingesta_lote import EjecucionEnCursoError
from .ingesta import correr_lote

router = APIRouter(prefix="/api/cron", tags=["Cron"], dependencies=[Depends(solo_cron)])


# GET para Vercel Cron y POST para planificadores externos como cron-job.org.
@router.get("/ingesta")
@router.post("/ingesta")
async def ingesta_programada(
    limite: int = Query(default=1, ge=1, le=5),
    db: Session = Depends(get_db),
):
    documental = asyncio.create_task(correr_documentos()) if settings.documentos_automaticos else None
    try:
        resultado = await correr_lote(db=db, limite=limite)
    except EjecucionEnCursoError as exc:
        # Otra ingesta sigue activa: se omite este turno sin contarlo como fallo.
        resultado = {"omitida": True, "motivo": str(exc)}
    finally:
        # No dejar tareas de fondo que Vercel pueda cortar al devolver la respuesta.
        if documental:
            try:
                documentos = await documental
            except Exception:
                documentos = {"pendiente": True, "motivo": "error_temporal"}
    if documental:
        resultado["documentos"] = documentos
    return resultado


@router.get("/documentos")
@router.post("/documentos")
async def documentos_programados():
    """Permite un planificador documental independiente con el mismo secreto."""
    return await correr_documentos()
