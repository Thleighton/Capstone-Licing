"""Cliente de la API de Mercado Público (licitaciones y Compra Ágil)."""
import asyncio
from urllib.parse import quote

import httpx

from ...core.config import env

LIC_BASE = "https://api.mercadopublico.cl/servicios/v1/publico"
CA_BASE = "https://api2.mercadopublico.cl"


async def get_licitaciones(client: httpx.AsyncClient, qs: str, intento: int = 0) -> dict:
    url = f"{LIC_BASE}/licitaciones.json?{qs}&ticket={quote(env('MP_TICKET'), safe='')}"
    res = await client.get(url)
    try:
        data = res.json()
    except ValueError:
        data = None
    falla = res.status_code >= 400 or (isinstance(data, dict) and data.get("Codigo"))
    # 10500 = peticiones simultáneas; reintenta
    if falla and intento < 2:
        await asyncio.sleep(1.5)
        return await get_licitaciones(client, qs, intento + 1)
    if falla:
        raise RuntimeError(f"Licitaciones API {res.status_code}: {(data or {}).get('Mensaje') or 'sin detalle'}")
    return data


async def get_compra_agil(client: httpx.AsyncClient, path: str) -> dict:
    res = await client.get(CA_BASE + path, headers={"ticket": env("MP_TICKET")})
    try:
        data = res.json()
    except ValueError:
        data = None
    if res.status_code == 429:
        raise RuntimeError("Compra Ágil: cuota diaria agotada (429)")
    if res.status_code >= 400 or (isinstance(data, dict) and data.get("success") == "NOK"):
        mensaje = (((data or {}).get("errors") or [{}])[0]).get("mensaje") or "sin detalle"
        raise RuntimeError(f"Compra Ágil {res.status_code}: {mensaje}")
    return data["payload"]
