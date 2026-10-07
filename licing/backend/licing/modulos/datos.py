"""GET /api/datos?t=<tabla>&q=<query string de PostgREST codificado>

Lectura de "Licing/Datos" para el frontend, solo con sesión válida de "Licing/Usuarios".
Solo lectura, solo tablas de la lista blanca (también en recursos embebidos).
Usa la service_role en el servidor."""
import re
from urllib.parse import parse_qs

import httpx
from fastapi import APIRouter, Depends, Request, Response

from ..core.auth import usuario_actual
from ..core.config import env
from ..core.errores import ErrorApi
from ..core.supabase import headers_service

router = APIRouter(tags=["datos"])

# Para exponer una tabla nueva al frontend, agrégala aquí.
TABLAS = {"licitacion", "licitacion_item", "requisito_extraido", "ejecucion_busqueda", "organismo"}

_EMBEBIDA = re.compile(r"([a-z_][a-z0-9_]*)\s*(?:![a-z0-9_]+)?\s*\(", re.I)


def embebidas(select: str | None) -> list[str]:
    """'organismo(nombre)', 'alias:organismo(...)', 'organismo!fk(...)' -> ['organismo']"""
    return [m.group(1).lower() for m in _EMBEBIDA.finditer(select or "")]


@router.get("/api/datos")
async def leer_datos(request: Request, t: str = "", q: str = "", _usuario: dict = Depends(usuario_actual)):
    if t not in TABLAS:
        raise ErrorApi(400, "Tabla no permitida: " + t)
    select = (parse_qs(q).get("select") or [""])[0]
    no_permitidas = [x for x in embebidas(select) if x not in TABLAS]
    if no_permitidas:
        raise ErrorApi(400, "Relación no permitida: " + ", ".join(no_permitidas))
    if not env("SUPABASE_URL") or not env("SUPABASE_SERVICE_ROLE_KEY"):
        raise ErrorApi(500, "Faltan SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY")

    headers = headers_service()
    if "count=exact" in request.headers.get("prefer", ""):
        headers["Prefer"] = "count=exact"
    rango = request.headers.get("range", "")
    if re.fullmatch(r"\d+-\d+", rango):
        headers["Range"] = rango

    url = env("SUPABASE_URL") + "/rest/v1/" + t + ("?" + q if q else "")
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(url, headers=headers)
    except httpx.HTTPError as e:
        raise ErrorApi(502, "No se pudo consultar Licing/Datos: " + str(e))

    out = Response(content=r.content, status_code=r.status_code, media_type="application/json; charset=utf-8")
    out.headers["Cache-Control"] = "no-store"
    if cr := r.headers.get("content-range"):
        out.headers["Content-Range"] = cr
        out.headers["Access-Control-Expose-Headers"] = "Content-Range"
    return out
