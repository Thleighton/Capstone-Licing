from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..auth import solo_cron
from ..database import get_db
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
    try:
        return await correr_lote(db=db, limite=limite)
    except EjecucionEnCursoError as exc:
        # Otra ingesta sigue activa: se omite este turno sin contarlo como fallo.
        return {"omitida": True, "motivo": str(exc)}
