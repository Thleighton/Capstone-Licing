from fastapi import APIRouter, Response

from ..config import settings

router = APIRouter(prefix="/api", tags=["Configuración"])


@router.get("/config")
def config_publica(response: Response):
    response.headers["Cache-Control"] = "no-store"
    return {
        "USUARIOS_URL": settings.usuarios_url,
        "USUARIOS_KEY": settings.usuarios_anon_key,
    }
