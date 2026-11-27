"""Acceso desde Core al proyecto de filtradas, sin credenciales en el navegador."""
import asyncio
import logging
from typing import Annotated, Literal
from uuid import UUID

import httpx
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field

from ..config import settings

logger = logging.getLogger(__name__)


class FiltradasNoDisponible(RuntimeError):
    pass


class Revision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    evaluacion_id: Annotated[int, Field(strict=True, gt=0)]
    accion: Literal["confirmar_relevante", "descartar", "mantener_pendiente"]
    categoria_motivo: Literal["servicio", "capacidad", "ubicacion", "plazo", "documentos", "presupuesto", "otro"]
    motivo: str = Field(min_length=5, max_length=1500)


async def registrar_revision(entrada: Revision, usuario: dict, *, codigo: str, raw_id: int, hash_fuente: str):
    nombre = " ".join(str(usuario.get("nombre") or "").split())
    motivo = entrada.motivo
    if nombre and f"Registrado por {nombre}" not in motivo:
        motivo = f"{motivo} · Registrado por {nombre}"[:1500]
    return await operar("revision", {
        **entrada.model_dump(), "motivo": motivo, "codigo": codigo, "raw_id": raw_id,
        "hash_fuente": hash_fuente, "usuario": str(UUID(usuario["id"])),
    })


async def cargar_clasificaciones(fuentes: dict[str, int], limite=100, concurrencia=3):
    """Lee las clasificaciones en una respuesta ligera y pagina solo por compatibilidad."""
    codigos = list(fuentes)
    if not codigos:
        return {}

    async def cargar_pagina(offset):
        return await operar("listar", {
            "codigos": codigos, "fuentes": fuentes, "solo_firmas": True,
            "limite": limite, "offset": offset,
        })

    primera = await cargar_pagina(0)
    try:
        total = max(0, int(primera.get("total", len(codigos))))
    except (TypeError, ValueError):
        total = len(codigos)

    filas = list(primera.get("filas", []))
    # La lectura solo_firmas omite paginación. Si el servicio remoto todavía es
    # antiguo y devuelve una página normal, completar las páginas restantes.
    offsets = range(limite, total, limite) if total > len(filas) else ()
    semaforo = asyncio.Semaphore(concurrencia)

    async def cargar_acotada(offset):
        async with semaforo:
            return await cargar_pagina(offset)

    paginas = await asyncio.gather(*(cargar_acotada(offset) for offset in offsets))
    for pagina in paginas:
        filas.extend(pagina.get("filas", []))
    return {str(fila["id"]): fila for fila in filas}


async def operar(operacion, datos=None):
    if not settings.filtradas_url or not settings.cron_secret:
        raise FiltradasNoDisponible("Falta configurar la conexión privada con LicitacionesFiltradas.")
    try:
        async with httpx.AsyncClient(timeout=settings.filtradas_timeout_segundos,
                                     follow_redirects=False) as cliente:
            r = await cliente.post(settings.filtradas_url,
                headers={"Authorization": "Bearer " + settings.cron_secret},
                json={"operacion": operacion, "datos": datos or {}})
            if r.status_code == 409:
                raise HTTPException(409, "Los datos cambiaron o la operación requiere revisión. Actualiza y vuelve a intentarlo.")
            r.raise_for_status()
            respuesta = r.json()
            if operacion == 'guardar' and respuesta.get('omitidas_version'):
                raise HTTPException(409,
                    'La evaluación no se guardó porque el filtro de esta aplicación está desactualizado. '
                    'Los resultados ya guardados se conservan; se requiere actualizar el filtro antes de reintentar.')
            return respuesta
    except httpx.HTTPStatusError as exc:
        # La función privada devuelve mensajes genéricos y seguros para distinguir
        # autorización, RPC y disponibilidad sin registrar credenciales ni cuerpos completos.
        detalle = ""
        codigo = ""
        try:
            cuerpo = exc.response.json()
            if not isinstance(cuerpo, dict):
                cuerpo = {}
            error = cuerpo.get("error")
            if isinstance(error, str):
                detalle = " ".join(error.split())[:180]
            codigo_respuesta = cuerpo.get("codigo")
            if isinstance(codigo_respuesta, str) and codigo_respuesta.isascii():
                codigo = codigo_respuesta[:40]
        except (ValueError, AttributeError):
            pass
        logger.warning("LicitacionesFiltradas falló en %s con HTTP %s%s%s",
                       operacion, exc.response.status_code,
                       f" ({detalle})" if detalle else "",
                       f" [{codigo}]" if codigo else "")
        raise FiltradasNoDisponible("No se pudo acceder a LicitacionesFiltradas. Los datos originales se conservan.") from None
    except httpx.RequestError as exc:
        logger.warning("LicitacionesFiltradas no respondió en %s (%s)",
                       operacion, type(exc).__name__)
        raise FiltradasNoDisponible("No se pudo acceder a LicitacionesFiltradas. Los datos originales se conservan.") from None
    except ValueError:
        logger.warning("LicitacionesFiltradas devolvió una respuesta no válida en %s", operacion)
        raise FiltradasNoDisponible("No se pudo acceder a LicitacionesFiltradas. Los datos originales se conservan.") from None
