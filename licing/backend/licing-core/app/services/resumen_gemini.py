"""Lectura breve asistida por Gemini para una ficha individual y su preselección."""
import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Literal

import httpx
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field

from ..config import settings

logger = logging.getLogger(__name__)
PROMPT_VERSION = "resumen-hotel-san-francisco-salones-v3"
MAX_TEXTO = 14000


class SolicitudResumenIA(BaseModel):
    model_config = ConfigDict(extra="forbid")
    clasificacion: Literal["preseleccionada", "revision_manual"]
    hash_fuente: str = Field(min_length=64, max_length=64, pattern=r"^[a-f0-9]{64}$")

ESQUEMA = {
    "type": "OBJECT",
    "properties": {
        "sintesis": {"type": "STRING"},
        "ubicacion_requerida": {"type": "STRING"},
        "personas": {"type": "STRING"},
        "fechas_horarios": {"type": "STRING"},
        "alertas": {"type": "ARRAY", "items": {"type": "STRING"}},
        "siguiente_paso": {"type": "STRING"},
    },
    "required": ["sintesis", "ubicacion_requerida", "personas",
                 "fechas_horarios", "alertas", "siguiente_paso"],
}


def huella(fuente: dict) -> str:
    contenido = json.dumps({"v": PROMPT_VERSION, "fuente": fuente}, sort_keys=True,
                           ensure_ascii=False, default=str)
    return hashlib.sha256(contenido.encode("utf-8")).hexdigest()


async def obtener_o_generar(db, fila, fuente: dict) -> dict:
    """Usa el mismo hash, caché y guardado para licitaciones y Compras Ágiles."""
    firma = huella(fuente)
    cache = fila.resumen_ia or {}
    if cache.get("firma") == firma and cache.get("resumen"):
        return {"resumen": cache["resumen"], "cache": True}
    lectura = await generar(fuente)
    fila.resumen_ia = {"firma": firma, "resumen": lectura}
    db.commit()
    return {"resumen": lectura, "cache": False}


def compactar_texto(fuente: dict) -> str:
    return json.dumps(fuente, ensure_ascii=False, default=str)[:MAX_TEXTO]


async def generar(fuente: dict) -> dict:
    if not settings.gemini_api_key:
        raise HTTPException(503, "La lectura asistida no está configurada todavía.")
    prompt = (
        "Ayudas al Hotel San Francisco, ubicado en Av. Libertador Bernardo O’Higgins 816 (La Alameda), "
        "Santiago Centro, Región Metropolitana. En esta versión el hotel ofrece arriendo de sus salones "
        "para eventos, reuniones, jornadas y capacitaciones, con coffee break, catering o banquetería "
        "asociada cuando se solicite. No ofrece habitaciones ni alojamiento para este análisis.\n"
        "Analiza solo la descripción de la ficha y sus ítems. No busques ni supongas contenido de bases o "
        "anexos. Resume qué se compra y extrae, si aparecen explícitamente, el lugar donde debe hacerse "
        "el evento, cantidad de asistentes/personas, fechas y horarios. Distingue la ubicación del evento "
        "de la dirección del comprador o la dirección del hotel; si el lugar no está expresado, indícalo.\n"
        "En la síntesis explica en una sola frase qué solicitan y qué relación concreta tiene con los "
        "salones o servicios asociados del hotel. No repitas la clasificación del filtro. No repitas en "
        "la síntesis el lugar, número de personas, fechas, horarios o monto: esos datos se mostrarán aparte. "
        "Es compatible si pide arrendar un salón del hotel o contratar "
        "el salón para una actividad; catering o alimentos solos no confirman arriendo de salón. Marca "
        "como alerta si la actividad se pide en un espacio público, en un recinto externo o fuera de la "
        "Región Metropolitana. No confundas servicios de personal, compras de insumos/equipos, aseo, "
        "mantención o talleres que no requieren arrendar un salón con la oferta hotelera.\n"
        "Usa solo los datos entregados. No cambies la clasificación del filtro, no declares que el hotel "
        "puede cumplir sin confirmación, y no inventes montos, cifras, fechas, aforos ni horarios. Cuando "
        "falte evidencia escribe 'No informado en la ficha o sus ítems'. Responde en español, claro y breve.\n\n"
        "DATOS DE FICHA E ÍTEMS:\n" + compactar_texto(fuente)
    )
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{settings.gemini_modelo}:generateContent"
    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.2, "maxOutputTokens": 700,
                             "responseMimeType": "application/json", "responseSchema": ESQUEMA},
    }
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(20, connect=5)) as client:
            respuesta = await client.post(url, headers={"x-goog-api-key": settings.gemini_api_key}, json=payload)
        if respuesta.status_code == 429:
            raise HTTPException(429, "Gemini alcanzó su cuota temporal. Inténtalo más tarde.")
        respuesta.raise_for_status()
        cuerpo = respuesta.json()
        texto = cuerpo["candidates"][0]["content"]["parts"][0]["text"]
        lectura = json.loads(texto)
        no_informado = "No informado en la ficha o sus ítems"
        salida = {
            "sintesis": str(lectura.get("sintesis", ""))[:600],
            "ubicacion_requerida": str(lectura.get("ubicacion_requerida", "")).strip()[:300] or no_informado,
            "personas": str(lectura.get("personas", "")).strip()[:180] or no_informado,
            "fechas_horarios": str(lectura.get("fechas_horarios", "")).strip()[:220] or no_informado,
            "alertas": [str(x)[:240] for x in lectura.get("alertas", [])[:5]],
            "siguiente_paso": str(lectura.get("siguiente_paso", ""))[:300],
            "modelo": settings.gemini_modelo,
            "generado_en": datetime.now(timezone.utc).isoformat(),
            "aviso": "Lectura asistida por IA basada en la ficha e información disponible; verifica las bases oficiales.",
        }
        if not salida["sintesis"]:
            raise ValueError("respuesta vacía")
        return salida
    except HTTPException:
        raise
    except httpx.HTTPStatusError as exc:
        logger.warning("Gemini respondió HTTP %s", exc.response.status_code)
        raise HTTPException(503, "Gemini no pudo generar la lectura. Inténtalo más tarde.") from None
    except (httpx.RequestError, KeyError, IndexError, ValueError, TypeError):
        logger.warning("No se pudo interpretar la respuesta de Gemini")
        raise HTTPException(503, "No se pudo generar la lectura asistida. La ficha sigue disponible.") from None
