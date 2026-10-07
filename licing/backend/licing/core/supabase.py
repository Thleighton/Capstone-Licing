"""Cliente REST (PostgREST) del proyecto Supabase "Licing/Datos", con service_role.
Solo se usa en el servidor: la service_role nunca llega al navegador."""
from typing import Any

import httpx

from .config import env

TIMEOUT = httpx.Timeout(30.0)


def headers_service() -> dict[str, str]:
    key = env("SUPABASE_SERVICE_ROLE_KEY")
    return {"apikey": key, "Authorization": "Bearer " + key}


async def sb(
    client: httpx.AsyncClient, path: str, *, method: str = "GET", body: Any = None, prefer: str | None = None
) -> Any:
    """Llama a /rest/v1/<path> y devuelve el JSON (o None si la respuesta viene vacía)."""
    headers = {**headers_service(), "Content-Type": "application/json"}
    if prefer:
        headers["Prefer"] = prefer
    res = await client.request(method, env("SUPABASE_URL") + "/rest/v1/" + path, headers=headers,
                               json=body if body is not None else None)
    if res.status_code >= 400:
        raise RuntimeError(f"Supabase {method} {path.split('?')[0]} -> {res.status_code} {res.text[:300]}")
    return res.json() if res.text else None
