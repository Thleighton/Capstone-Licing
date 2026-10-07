"""GET /api/sync?fuente=todas|licitaciones|compra_agil

Lo invoca Vercel Cron (vercel.json) o se llama a mano:
    curl -H "Authorization: Bearer $CRON_SECRET" "https://TU-APP.vercel.app/api/sync?fuente=compra_agil"
"""
import asyncio
from datetime import datetime, timezone
from urllib.parse import quote, urlencode

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ...core.config import env, faltantes
from ...core.supabase import TIMEOUT, sb
from .mercadopublico import get_compra_agil, get_licitaciones
from .normalizacion import norm, norm_compra_agil, norm_licitacion, region_codigo
from .requisitos import extraer_requisitos

router = APIRouter(tags=["sync"])


def _ahora() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


# ---------- Persistencia ----------
async def guardar(client: httpx.AsyncClient, n: dict, ejecucion_id: int) -> None:
    org, lic, items = n["org"], n["lic"], n["items"]
    organismo_id = None
    if org:
        r = await sb(client, "organismo?on_conflict=rut", method="POST", body=org,
                     prefer="resolution=merge-duplicates,return=representation")
        organismo_id = r[0]["id"]
    [row] = await sb(client, "licitacion?on_conflict=codigo_mp", method="POST",
                     prefer="resolution=merge-duplicates,return=representation",
                     body={**lic, "organismo_id": organismo_id, "ejecucion_id": ejecucion_id, "actualizado_en": _ahora()})
    await sb(client, f"licitacion_item?licitacion_id=eq.{row['id']}", method="DELETE")
    if items:
        await sb(client, "licitacion_item", method="POST", body=[{**i, "licitacion_id": row["id"]} for i in items])
    await sb(client, f"requisito_extraido?licitacion_id=eq.{row['id']}&validado_manual=eq.false", method="DELETE")
    await sb(client, "requisito_extraido", method="POST",
             body={"licitacion_id": row["id"], **extraer_requisitos(lic["nombre"], lic["descripcion"], items)})


async def codigos_existentes(client: httpx.AsyncClient, codigos: list[str]) -> set[str]:
    existentes: set[str] = set()
    for i in range(0, len(codigos), 50):
        lote = ",".join(quote(c, safe="") for c in codigos[i:i + 50])
        for x in await sb(client, f"licitacion?select=codigo_mp&codigo_mp=in.({lote})"):
            existentes.add(x["codigo_mp"])
    return existentes


# ---------- Fuentes ----------
async def sync_licitaciones(client, crit: dict, ejec_id: int, maximo: int, stats: dict) -> None:
    kws = [norm(k) for k in crit["keywords"]]
    lista = (await get_licitaciones(client, "estado=activas")).get("Listado") or []
    candidatas = [l for l in lista if any(k in norm(l.get("Nombre")) for k in kws)]
    stats["obtenidas"] += len(candidatas)
    existentes = await codigos_existentes(client, [l["CodigoExterno"] for l in candidatas])
    nuevas = [l for l in candidatas if l["CodigoExterno"] not in existentes][:maximo]
    for c in nuevas:
        try:
            await asyncio.sleep(0.4)  # la API rechaza peticiones simultáneas
            det = ((await get_licitaciones(client, "codigo=" + quote(c["CodigoExterno"], safe=""))).get("Listado") or [None])[0]
            if not det:
                continue
            n = norm_licitacion(det, crit["region"])
            await guardar(client, n, ejec_id)
            stats["nuevas"] += 1
            if not n["lic"]["descartada_filtro"]:
                stats["filtradas"] += 1
        except Exception as e:  # noqa: BLE001 — se registra y se sigue con la siguiente
            stats["errores"].append(f"{c['CodigoExterno']}: {e}")


async def sync_compra_agil(client, crit: dict, ejec_id: int, maximo: int, stats: dict) -> None:
    reg = region_codigo(crit["region"]) if crit["region"] else None
    vistos: dict[str, dict] = {}
    for kw in crit["keywords"]:
        qs = {"estado": "publicada", "q": kw, "tamano_pagina": "50", "ordenar_por": "FechaPublicacion"}
        if reg:
            qs["region"] = str(reg)
        try:
            p = await get_compra_agil(client, "/v2/compra-agil?" + urlencode(qs))
            for i in p.get("items") or []:
                vistos[i["codigo"]] = i
        except Exception as e:  # noqa: BLE001
            stats["errores"].append(f"búsqueda '{kw}': {e}")
            if "429" in str(e):
                break
    stats["obtenidas"] += len(vistos)
    existentes = await codigos_existentes(client, list(vistos))
    nuevos = [c for c in vistos if c not in existentes][:maximo]
    for codigo in nuevos:
        try:
            det = await get_compra_agil(client, "/v2/compra-agil/" + quote(codigo, safe=""))
            n = norm_compra_agil(det, crit["region"])
            await guardar(client, n, ejec_id)
            stats["nuevas"] += 1
            if not n["lic"]["descartada_filtro"]:
                stats["filtradas"] += 1
        except Exception as e:  # noqa: BLE001
            stats["errores"].append(f"{codigo}: {e}")


# ---------- Handler ----------
@router.get("/api/sync")
async def sincronizar(request: Request, fuente: str = "todas"):
    secret = env("CRON_SECRET")
    if not secret or request.headers.get("authorization") != f"Bearer {secret}":
        return JSONResponse({"error": "No autorizado"}, status_code=401)
    faltan = faltantes("MP_TICKET", "SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY")
    if faltan:
        return JSONResponse({"error": "Faltan variables de entorno", "faltan": faltan}, status_code=500)

    maximo = int(env("MAX_DETALLES", "30") or 30)
    stats = {"obtenidas": 0, "nuevas": 0, "filtradas": 0, "errores": []}
    ejec_id = None
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        try:
            criterios = await sb(client, "criterio_busqueda?select=*&activo=eq.true&order=id")
            if not criterios:
                raise RuntimeError("No hay criterio_busqueda activo")
            crit = {
                "keywords": [k for c in criterios for k in (c.get("keywords") or [])],
                "region": next((c["region"] for c in criterios if c.get("region")), None),
            }
            disparo = "cron" if "vercel-cron" in request.headers.get("user-agent", "") else "manual"
            ejec_id = (await sb(client, "ejecucion_busqueda", method="POST", body={"disparo": disparo},
                                prefer="return=representation"))[0]["id"]

            if fuente in ("todas", "licitaciones"):
                try:
                    await sync_licitaciones(client, crit, ejec_id, maximo, stats)
                except Exception as e:  # noqa: BLE001
                    stats["errores"].append("licitaciones: " + str(e))
            if fuente in ("todas", "compra_agil"):
                try:
                    await sync_compra_agil(client, crit, ejec_id, maximo, stats)
                except Exception as e:  # noqa: BLE001
                    stats["errores"].append("compra_agil: " + str(e))

            fallo = bool(stats["errores"]) and stats["nuevas"] == 0
            await sb(client, f"ejecucion_busqueda?id=eq.{ejec_id}", method="PATCH", body={
                "fin": _ahora(), "estado": "error" if fallo else "ok", "n_obtenidas": stats["obtenidas"],
                "n_nuevas": stats["nuevas"], "n_filtradas": stats["filtradas"],
                "error": "\n".join(stats["errores"])[:2000] or None,
            })
            return JSONResponse({"ejecucion": ejec_id, **stats}, status_code=502 if fallo else 200)
        except Exception as e:  # noqa: BLE001
            if ejec_id:
                try:
                    await sb(client, f"ejecucion_busqueda?id=eq.{ejec_id}", method="PATCH",
                             body={"fin": _ahora(), "estado": "error", "error": str(e)})
                except Exception:  # noqa: BLE001
                    pass
            return JSONResponse({"error": str(e), **stats}, status_code=500)
