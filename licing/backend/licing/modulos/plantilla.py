"""PLANTILLA de módulo backend. Copia este archivo, cambia el prefijo y
regístralo en licing/main.py (lista ROUTERS)."""
from fastapi import APIRouter, Depends

from ..core.auth import usuario_actual

router = APIRouter(prefix="/api/plantilla", tags=["plantilla"])


@router.get("/hola")
def hola(usuario: dict = Depends(usuario_actual)):
    return {"mensaje": "Hola " + usuario["nombre"], "rol": usuario["rol"]}
