"""Preselección explicable y documentos del hotel; LLM fuera de esta etapa."""
import base64
import binascii
import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import solo_cron, usuario_actual
from ..database import get_db
from ..models.licitacion import Licitacion
from ..models.licitacion_item import LicitacionItem
from ..models.raw import RawMercadoPublico
from ..services import filtradas
from ..services.enlaces import ficha_oficial
from ..services.pdf_bases import extraer_pdf, MAX_BYTES
from ..services.preseleccion import cargar_catalogo, evaluar_preseleccion, CHILE

router = APIRouter(prefix="/api/preseleccion", tags=["Preselección"])


def serializable(valor):
    if isinstance(valor, datetime):
        return (valor.replace(tzinfo=CHILE) if valor.tzinfo is None else valor).isoformat()
    if isinstance(valor, Decimal):
        return str(valor)
    raise TypeError(type(valor).__name__)


def cargar_entradas(db, ids):
    filas = db.scalars(select(Licitacion).where(Licitacion.id.in_(ids))).all()
    entradas = {}
    for fila in filas:
        datos = {c.name: getattr(fila, c.name) for c in Licitacion.__table__.columns}
        raw = db.get(RawMercadoPublico, fila.raw_id)
        datos.update(items=[], url_oficial=ficha_oficial(fila.codigo_externo),
                     fuente_verificada_en=raw.verificado_en if raw else None)
        entradas[fila.id] = datos
    for item in db.scalars(select(LicitacionItem).where(LicitacionItem.licitacion_id.in_(ids))
                           .order_by(LicitacionItem.licitacion_id, LicitacionItem.posicion_fuente)):
        entradas[item.licitacion_id]["items"].append({c.name: getattr(item, c.name)
                                                    for c in LicitacionItem.__table__.columns})
    return json.loads(json.dumps(entradas, default=serializable))


def firma_fuente(datos):
    estables = {k: v for k, v in datos.items() if k not in {"fuente_verificada_en", "normalizado_en"}}
    return hashlib.sha256(json.dumps(estables, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


async def evaluar_lote(db, ids, actor=None):
    observado_en = datetime.now(timezone.utc).isoformat()
    codigos_vigentes = list(db.scalars(select(Licitacion.codigo_externo)))
    await filtradas.operar("sincronizar_fuente", {"codigos": codigos_vigentes, "observado_en": observado_en})
    entradas = cargar_entradas(db, ids)
    if len(entradas) != len(set(ids)):
        raise HTTPException(404, "Alguna licitación ya no está disponible. Actualiza la lista.")
    codigos = [d["codigo_externo"] for d in entradas.values()]
    documentos = await filtradas.operar("documentos", {"codigos": codigos})
    lote = []
    for datos in entradas.values():
        docs = documentos.get(datos["codigo_externo"], [])
        entrada = {**datos, "documentos": docs}
        resultado = evaluar_preseleccion(entrada)
        # No duplicar RAW ni PDF completos en las evaluaciones: conservar referencias y evidencias.
        firma = firma_fuente(datos)
        lote.append({"datos": datos, "resultado": resultado, "hash_fuente": firma,
                     "documentos_version": [[d["id"], d["version"], d["hash_archivo"]]
                                             for d in sorted(docs, key=lambda x: x["id"])]})
    actuales = dict(db.execute(select(Licitacion.id, Licitacion.raw_id).where(Licitacion.id.in_(ids))).all())
    if any(actuales.get(d["id"]) != d["raw_id"] for d in entradas.values()):
        raise HTTPException(409, "La fuente cambió durante la evaluación. Actualiza y vuelve a intentarlo.")
    return await filtradas.operar("guardar", {"lote": lote, "perfil": cargar_catalogo(), "actor": actor})


class Lote(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ids: list[Annotated[int, Field(strict=True, gt=0)]] = Field(min_length=1, max_length=20)


class Revision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    evaluacion_id: Annotated[int, Field(strict=True, gt=0)]
    accion: Literal["confirmar_relevante", "descartar", "mantener_pendiente"]
    categoria_motivo: Literal["servicio", "capacidad", "ubicacion", "plazo", "documentos", "presupuesto", "otro"]
    motivo: str = Field(min_length=5, max_length=1500)


@router.get("/integracion/verificar", dependencies=[Depends(solo_cron)], include_in_schema=False)
def verificar_integracion():
    # La función del segundo proyecto valida aquí la credencial privada existente.
    return {"autorizada": True}


@router.get("", dependencies=[Depends(usuario_actual)])
async def listar(response: Response, clasificacion: str = Query(default="", max_length=30),
                 q: str = Query(default="", max_length=150), limite: int = Query(default=25, ge=1, le=100),
                 offset: int = Query(default=0, ge=0), db: Session = Depends(get_db)):
    fuentes = dict(db.execute(select(Licitacion.codigo_externo, Licitacion.raw_id)).all())
    codigos = list(fuentes)
    respuesta = await filtradas.operar("listar", {"codigos": codigos, "fuentes": fuentes, "clasificacion": clasificacion,
                                                   "q": q, "limite": limite, "offset": offset})
    actuales = dict(db.execute(select(Licitacion.id, Licitacion.raw_id)).all())
    for fila in respuesta.get("filas", []):
        if actuales.get(fila["id"]) != fila.get("fuente_raw_id"):
            fila.update(estado_seleccion="pendiente_evaluacion", motivo_seleccion="La fuente cambió; actualiza la preselección.")
    respuesta["ids_fuente"] = list(db.scalars(select(Licitacion.id).order_by(Licitacion.id)))
    response.headers["Cache-Control"] = "no-store"
    return respuesta


@router.post("/evaluar")
async def evaluar(entrada: Lote, usuario=Depends(usuario_actual), db: Session = Depends(get_db)):
    return await evaluar_lote(db, entrada.ids, str(UUID(usuario["id"])))


@router.get("/{licitacion_id}", dependencies=[Depends(usuario_actual)])
async def detalle(licitacion_id: int, response: Response, db: Session = Depends(get_db)):
    fila = db.get(Licitacion, licitacion_id)
    if fila is None:
        raise HTTPException(404, "La licitación ya no está disponible.")
    resultado = await filtradas.operar("detalle", {"codigo": fila.codigo_externo})
    resultado["fuente_actualizada"] = resultado.get("hash_fuente") == firma_fuente(cargar_entradas(db, [licitacion_id])[str(licitacion_id)])
    response.headers["Cache-Control"] = "no-store"
    return resultado


@router.post("/{licitacion_id}/revision")
async def revisar(licitacion_id: int, entrada: Revision, usuario=Depends(usuario_actual), db: Session = Depends(get_db)):
    fila = db.get(Licitacion, licitacion_id)
    if fila is None:
        raise HTTPException(404, "La licitación ya no está disponible.")
    return await filtradas.operar("revision", {**entrada.model_dump(), "codigo": fila.codigo_externo,
                                              "raw_id": fila.raw_id, "hash_fuente": firma_fuente(cargar_entradas(db, [licitacion_id])[str(licitacion_id)]), "usuario": str(UUID(usuario["id"]))})


@router.post("/{licitacion_id}/documentos")
async def documento(licitacion_id: int, request: Request, usuario=Depends(usuario_actual), db: Session = Depends(get_db)):
    fila = db.get(Licitacion, licitacion_id)
    if fila is None:
        raise HTTPException(404, "La licitación ya no está disponible.")
    cuerpo = bytearray()
    async for bloque in request.stream():
        cuerpo.extend(bloque)
        if len(cuerpo) > MAX_BYTES * 4 // 3 + 4096:
            raise HTTPException(413, "El PDF supera el límite de 3 MB.")
    try:
        entrada = json.loads(cuerpo)
        nombre = str(entrada["nombre"])
        if not nombre.lower().endswith(".pdf") or len(nombre) > 180:
            raise ValueError()
        contenido = base64.b64decode(entrada["contenido_base64"], validate=True)
        tipo = entrada.get("tipo", "bases_tecnicas")
        if tipo not in {"bases_tecnicas", "bases_administrativas", "anexo", "otro"}:
            raise ValueError()
    except (ValueError, KeyError, TypeError, binascii.Error):
        raise HTTPException(422, "Adjunta un PDF válido e indica su tipo.") from None
    from starlette.concurrency import run_in_threadpool
    try:
        extraccion = await run_in_threadpool(extraer_pdf, contenido)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    await evaluar_lote(db, [licitacion_id], str(UUID(usuario["id"])))
    guardado = await filtradas.operar("guardar_documento", {"codigo": fila.codigo_externo,
        "nombre": nombre, "tipo": tipo, "extraccion": extraccion,
        "contenido_base64": entrada["contenido_base64"], "usuario": str(UUID(usuario["id"]))})
    try:
        evaluacion = await evaluar_lote(db, [licitacion_id], str(UUID(usuario["id"])))
    except filtradas.FiltradasNoDisponible:
        evaluacion = {"pendiente": True}
    return {"documento": guardado, "evaluacion": evaluacion}


@router.delete("/{licitacion_id}/documentos/{documento_id}")
async def retirar_documento(licitacion_id: int, documento_id: int, usuario=Depends(usuario_actual), db: Session = Depends(get_db)):
    fila = db.get(Licitacion, licitacion_id)
    if fila is None:
        raise HTTPException(404, "La licitación ya no está disponible.")
    await filtradas.operar("retirar_documento", {"codigo": fila.codigo_externo, "documento_id": documento_id})
    return await evaluar_lote(db, [licitacion_id], str(UUID(usuario["id"])))
