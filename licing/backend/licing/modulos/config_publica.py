"""GET /api/config — configuración pública para iniciar sesión en "Licing/Usuarios".
Solo expone la anon/publishable key de Usuarios. Los datos de "Licing/Datos" se leen
por /api/datos, que verifica la sesión; el navegador no recibe keys de Datos."""
from urllib.parse import urlparse

from fastapi import APIRouter, Response

from ..core.config import env

router = APIRouter(tags=["core"])


@router.get("/api/config")
def config_publica(response: Response):
    response.headers["Cache-Control"] = "no-store"
    return {
        "USUARIOS_URL": env("USUARIOS_URL"),
        "USUARIOS_KEY": env("USUARIOS_ANON_KEY"),
        "DATOS_HOST": urlparse(env("SUPABASE_URL")).netloc,
    }
