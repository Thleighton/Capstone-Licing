"""Sesiones y perfiles del proyecto Supabase Usuarios/Licitaciones."""
import hmac
import time

import httpx
from fastapi import Depends, HTTPException, Request

from .config import settings

CACHE_SEG = 60
_cache: dict[str, tuple[float, dict]] = {}


async def perfil_desde_token(token: str) -> dict:
    if not settings.usuarios_url or not settings.usuarios_anon_key:
        raise HTTPException(503, "Falta configurar el acceso de usuarios")
    hit = _cache.get(token)
    if hit and hit[0] > time.time():
        return hit[1]

    headers = {"apikey": settings.usuarios_anon_key, "Authorization": "Bearer " + token}
    base = settings.usuarios_url.rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(base + "/auth/v1/user", headers=headers)
            if r.status_code in (401, 403):
                raise HTTPException(401, "Sesión inválida o expirada")
            r.raise_for_status()
            user = r.json()
            p = await client.get(base + "/rest/v1/usuario", headers=headers, params={
                "select": "id,nombre,email,rol,activo", "id": "eq." + user["id"],
            })
            p.raise_for_status()
            filas = p.json()
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
        raise HTTPException(503, "No se pudo validar la sesión. Inténtalo nuevamente.") from exc

    perfil = filas[0] if isinstance(filas, list) and filas else None
    if not isinstance(perfil, dict):
        raise HTTPException(403, "Tu usuario no tiene perfil en LICING")
    if perfil.get("activo") is not True:
        raise HTTPException(403, "Tu cuenta está desactivada. Contacta al administrador.")
    if len(_cache) > 500:
        _cache.clear()
    _cache[token] = (time.time() + CACHE_SEG, perfil)
    return perfil


async def usuario_actual(request: Request) -> dict:
    h = request.headers.get("authorization", "")
    token = h[7:].strip() if h.startswith("Bearer ") else ""
    if not token:
        raise HTTPException(401, "Debes iniciar sesión")
    return await perfil_desde_token(token)


def solo_rol(*roles: str):
    async def verificar(perfil: dict = Depends(usuario_actual)) -> dict:
        if perfil.get("rol") not in roles:
            raise HTTPException(403, "No tienes permiso para esta acción")
        return perfil
    return verificar


def solo_cron(request: Request) -> None:
    """Planificador externo: Authorization: Bearer <CRON_SECRET>, como Vercel Cron."""
    if not settings.cron_secret:
        raise HTTPException(503, "La ingesta programada no está configurada")
    h = request.headers.get("authorization", "")
    token = h[7:].strip() if h.startswith("Bearer ") else ""
    if not hmac.compare_digest(token.encode(), settings.cron_secret.encode()):
        raise HTTPException(401, "Credencial del planificador inválida")
