"""Acceso desde Core al proyecto de filtradas, sin credenciales en el navegador."""
import httpx
from fastapi import HTTPException

from ..config import settings


class FiltradasNoDisponible(RuntimeError):
    pass


async def operar(operacion, datos=None):
    if not settings.filtradas_url or not settings.cron_secret:
        raise FiltradasNoDisponible("Falta configurar la conexión privada con LicitacionesFiltradas.")
    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=False) as cliente:
            r = await cliente.post(settings.filtradas_url,
                headers={"Authorization": "Bearer " + settings.cron_secret},
                json={"operacion": operacion, "datos": datos or {}})
            if r.status_code == 409:
                raise HTTPException(409, "Los datos cambiaron o la operación requiere revisión. Actualiza y vuelve a intentarlo.")
            r.raise_for_status()
            return r.json()
    except (httpx.HTTPError, ValueError):
        raise FiltradasNoDisponible("No se pudo acceder a LicitacionesFiltradas. Los datos originales se conservan.") from None
