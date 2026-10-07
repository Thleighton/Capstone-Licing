"""Verifica la sesión emitida por el proyecto Supabase "Licing/Usuarios" y que el
perfil (public.usuario) exista y esté activo.

Uso en cualquier módulo:
    @router.get("/algo")
    async def algo(usuario: dict = Depends(usuario_actual)): ...
"""
import time

import httpx
from fastapi import Request

from .config import env
from .errores import ErrorApi

CACHE_SEG = 60  # evita validar el mismo token en cada petición paralela
_cache: dict[str, tuple[float, dict]] = {}


async def perfil_desde_token(token: str) -> dict:
    base, key = env("USUARIOS_URL"), env("USUARIOS_ANON_KEY")
    if not base or not key:
        raise ErrorApi(500, "Faltan USUARIOS_URL / USUARIOS_ANON_KEY en las variables de entorno")

    hit = _cache.get(token)
    if hit and hit[0] > time.time():
        return hit[1]

    headers = {"apikey": key, "Authorization": "Bearer " + token}
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(base + "/auth/v1/user", headers=headers)
        if r.status_code != 200:
            raise ErrorApi(401, "Sesión inválida o expirada")
        user = r.json()
        # RLS de Licing/Usuarios permite a cada usuario leer su propia fila
        p = await client.get(base + "/rest/v1/usuario", headers=headers,
                             params={"select": "id,nombre,email,rol,activo", "id": "eq." + user["id"]})
    filas = p.json() if p.status_code == 200 else []
    perfil = filas[0] if filas else None
    if not perfil:
        raise ErrorApi(403, "Tu usuario no tiene perfil en LICING")
    if not perfil.get("activo"):
        raise ErrorApi(403, "Tu cuenta está desactivada. Contacta al administrador.")

    if len(_cache) > 500:
        _cache.clear()
    _cache[token] = (time.time() + CACHE_SEG, perfil)
    return perfil


async def usuario_actual(request: Request) -> dict:
    """Dependencia FastAPI: exige 'Authorization: Bearer <token de Licing/Usuarios>'."""
    h = request.headers.get("authorization", "")
    token = h[7:].strip() if h.startswith("Bearer ") else ""
    if not token:
        raise ErrorApi(401, "Debes iniciar sesión")
    return await perfil_desde_token(token)


def solo_rol(*roles: str):
    """Dependencia para restringir por rol: Depends(solo_rol("administrador"))."""
    async def _dep(request: Request) -> dict:
        perfil = await usuario_actual(request)
        if perfil.get("rol") not in roles:
            raise ErrorApi(403, "No tienes permiso para esta acción")
        return perfil
    return _dep
