"""Lectura breve asistida por Gemini para una ficha individual y su preselección."""
import hashlib
import json
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal
from zoneinfo import ZoneInfo

import httpx
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, text, update
from sqlalchemy.exc import InvalidRequestError
from sqlalchemy.orm.exc import ObjectDeletedError

from ..config import settings
from ..models.raw import RawMercadoPublico

logger = logging.getLogger(__name__)
PROMPT_VERSION = "resumen-hotel-san-francisco-salones-v3"
MAX_TEXTO = 14000
CHILE = ZoneInfo('America/Santiago')
_TECNICOS = {'id', 'raw_id', 'resumen_ia', 'preseleccion', 'normalizado_en',
             'normalizacion_version', 'cambio_sincronizado', 'ingesta_documental', 'ubicacion_servicio'}


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
    """Firma anterior, únicamente para reutilizar resúmenes ya guardados."""
    contenido = json.dumps({"v": PROMPT_VERSION, "fuente": fuente}, sort_keys=True,
                           ensure_ascii=False, default=str)
    return hashlib.sha256(contenido.encode("utf-8")).hexdigest()


def _serializar(valor):
    if isinstance(valor, datetime):
        return (valor.replace(tzinfo=CHILE) if valor.tzinfo is None else valor).isoformat()
    if isinstance(valor, Decimal):
        return str(valor)
    raise TypeError(type(valor).__name__)


def firma_ficha(fila, entrada: dict) -> str:
    """Solo cambia con la información de negocio; no con filtros ni verificaciones."""
    datos = {c.name: getattr(fila, c.name) for c in fila.__table__.columns if c.name not in _TECNICOS}
    datos['items'] = [{k: v for k, v in i.items() if k not in {'id', 'licitacion_id', 'compra_agil_id'}}
                      for i in entrada.get('items', [])]
    contenido = json.dumps({'tipo': fila.__tablename__, 'datos': datos}, sort_keys=True,
                           ensure_ascii=False, default=_serializar)
    return hashlib.sha256(contenido.encode()).hexdigest()


def fuente_resumen(fila, entrada: dict, tipo: str, clasificacion: str | None) -> dict:
    # Conserva la forma de la firma anterior para migrar cachés sin llamar a Gemini.
    fuente = {'tipo': tipo, 'codigo': fila.codigo_externo, 'clasificacion_actual': clasificacion,
        'nombre': fila.nombre, 'organismo': fila.nombre_organismo, 'unidad': fila.nombre_unidad,
        'descripcion': fila.descripcion, 'region_comprador': fila.region_comprador,
        'direccion_entrega': fila.direccion_entrega,
        'monto': str(fila.monto_disponible if tipo == 'compra_agil' else fila.monto_estimado)
                 if (fila.monto_disponible if tipo == 'compra_agil' else fila.monto_estimado) is not None else None,
        'fecha_cierre': fila.fecha_cierre.isoformat() if fila.fecha_cierre else None,
        'items': entrada.get('items', [])}
    if tipo == 'licitacion':
        fuente['comuna_comprador'] = fila.comuna_comprador
    return fuente


def _disponible(fila):
    cierre = fila.fecha_cierre
    if cierre is not None:
        cierre = cierre.replace(tzinfo=CHILE) if cierre.tzinfo is None else cierre
        if cierre <= datetime.now(CHILE):
            return False
    return (getattr(fila, 'codigo_estado', None) not in {6, 7, 8, 18, 19}
            and str(fila.estado or '').lower() not in {'cerrada', 'desierta', 'adjudicada', 'revocada', 'suspendida', 'cancelada'})


def cache_actual(db, fila, entrada: dict, fuente: dict) -> dict | None:
    """Nunca entrega una lectura de otra versión de la ficha ni de una vencida."""
    cache = fila.resumen_ia or {}
    if not cache.get('resumen') or not _disponible(fila):
        return None
    if cache.get('version_cache') == 2:
        return cache if cache.get('firma') == firma_ficha(fila, entrada) else None
    firmas_anteriores = {huella({**fuente, 'clasificacion_actual': c})
                        for c in ('preseleccionada', 'revision_manual')}
    if cache.get('firma') not in firmas_anteriores:
        return None
    # El RAW identifica la versión completa de la API, incluso campos que el
    # antiguo resumen no enviaba a Gemini. Una versión posterior invalida la caché.
    creado = db.scalar(select(RawMercadoPublico.consultado_en).where(RawMercadoPublico.id == fila.raw_id))
    try:
        generado = datetime.fromisoformat(cache['resumen']['generado_en'])
        generado = generado.replace(tzinfo=timezone.utc) if generado.tzinfo is None else generado
        creado = creado.replace(tzinfo=timezone.utc) if creado and creado.tzinfo is None else creado
        return cache if creado and creado <= generado else None
    except (KeyError, TypeError, ValueError):
        return None


async def obtener_o_generar(db, fila, fuente: dict, entrada: dict, cargar_actuales) -> dict:
    """Una lectura persistida por ficha; una sola solicitud al proveedor a la vez."""
    modelo, identificador = type(fila), fila.id
    firma_inicial = firma_ficha(fila, entrada)
    namespace = 710265 if fila.__tablename__ == 'licitacion' else 710266
    disponible = db.scalar(text('SELECT pg_try_advisory_xact_lock(:ns,:id)'),
                           {'ns': namespace, 'id': identificador})
    if not disponible:
        raise HTTPException(423, 'El análisis de esta ficha ya se está preparando. Consulta nuevamente en unos segundos.')

    def recargar():
        try:
            db.expire_all()
            db.refresh(fila)
        except (ObjectDeletedError, InvalidRequestError):
            raise HTTPException(404, 'La oportunidad ya no está disponible.') from None
        actuales = cargar_actuales()
        if not actuales:
            raise HTTPException(404, 'La oportunidad ya no está disponible.')
        if not _disponible(fila):
            raise HTTPException(410, 'La oportunidad ya venció o dejó de estar disponible.')
        if firma_ficha(fila, actuales) != firma_inicial:
            raise HTTPException(409, 'La ficha cambió durante el análisis. Actualiza la información antes de solicitarlo nuevamente.')
        return actuales

    actuales = recargar()
    cache = cache_actual(db, fila, actuales, fuente)
    if cache and cache.get('version_cache') == 2:
        db.commit()
        return {'resumen': cache['resumen'], 'cache': True}
    lectura = cache['resumen'] if cache else await generar({
        **{k: v for k, v in fuente.items() if k != 'clasificacion_actual'},
        'moneda': fila.moneda, 'estado': fila.estado,
    })
    actuales = recargar()
    raw_actual, normalizado_en = fila.raw_id, fila.normalizado_en
    guardada = {'version_cache': 2, 'firma': firma_inicial, 'resumen': lectura}
    condicion = [modelo.id == identificador, modelo.raw_id == raw_actual,
                 modelo.normalizado_en == normalizado_en]
    actualizadas = db.execute(update(modelo).where(*condicion).values(resumen_ia=guardada)
                              .execution_options(synchronize_session=False)).rowcount
    if actualizadas != 1:
        db.rollback()
        raise HTTPException(409, 'La ficha cambió antes de guardar el análisis. Actualiza e inténtalo nuevamente.')
    db.commit()
    return {'resumen': lectura, 'cache': bool(cache)}


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
