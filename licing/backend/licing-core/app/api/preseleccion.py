"""Preselección explicable y documentos del hotel; LLM fuera de esta etapa."""
import base64
import binascii
import asyncio
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
from ..models.licitacion_documento import LicitacionDocumento
from ..services import filtradas, documentos_origen
from ..services.enlaces import ficha_oficial
from ..services.pdf_bases import extraer_pdf, MAX_BYTES
from ..services.preseleccion import cargar_catalogo, evaluar_preseleccion, evaluar_vigencia, CHILE, VERSION_MOTOR
from ..services.clientes_importantes import identificar_clientes_importantes

router = APIRouter(prefix="/api/preseleccion", tags=["Preselección"])


def serializable(valor):
    if isinstance(valor, datetime):
        return (valor.replace(tzinfo=CHILE) if valor.tzinfo is None else valor).isoformat()
    if isinstance(valor, Decimal):
        return str(valor)
    raise TypeError(type(valor).__name__)


def cargar_entradas(db, ids):
    if not ids:
        return {}
    filas = db.scalars(select(Licitacion).where(Licitacion.id.in_(ids))).all()
    entradas = {}
    versiones = documentos_origen.versiones(db, ids)
    verificaciones = dict(db.execute(select(RawMercadoPublico.id, RawMercadoPublico.verificado_en)
        .where(RawMercadoPublico.id.in_({f.raw_id for f in filas}))).all())
    for fila in filas:
        datos = {c.name: getattr(fila, c.name) for c in Licitacion.__table__.columns if c.name != "ingesta_documental"}
        datos.update(items=[], documentos_version=versiones[fila.id], url_oficial=ficha_oficial(fila.codigo_externo),
                     fuente_verificada_en=verificaciones.get(fila.raw_id))
        if fila.ingesta_documental.get("incidencia_documental"):
            datos["incidencia_documental"] = fila.ingesta_documental["incidencia_documental"]
        entradas[fila.id] = datos
    for item in db.scalars(select(LicitacionItem).where(LicitacionItem.licitacion_id.in_(ids))
                           .order_by(LicitacionItem.licitacion_id, LicitacionItem.posicion_fuente)):
        entradas[item.licitacion_id]["items"].append({c.name: getattr(item, c.name)
                                                    for c in LicitacionItem.__table__.columns})
    return json.loads(json.dumps(entradas, default=serializable))


def firma_fuente(datos):
    estables = {k: v for k, v in datos.items() if k not in {"fuente_verificada_en", "normalizado_en"}}
    estables.update(version_motor=VERSION_MOTOR, catalogo_version=cargar_catalogo()["version"])
    return hashlib.sha256(json.dumps(estables, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


async def evaluar_lote(db, ids, actor=None):
    ids = list(dict.fromkeys(ids))
    entradas = cargar_entradas(db, ids)
    if len(entradas) != len(set(ids)):
        raise HTTPException(404, "Alguna licitación ya no está disponible. Actualiza la lista.")
    documentos = documentos_origen.cargar(db, ids)
    lote = []
    for datos in entradas.values():
        docs = documentos.get(datos["id"], [])
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
    versiones = documentos_origen.versiones(db, ids)
    if any(versiones[d["id"]] != d["documentos_version"] for d in entradas.values()):
        raise HTTPException(409, "Los documentos cambiaron durante la evaluación. Vuelve a intentarlo.")
    observado_en = datetime.now(timezone.utc).isoformat()
    codigos_vigentes = list(db.scalars(select(Licitacion.codigo_externo)))
    await filtradas.operar("sincronizar_fuente", {"codigos": codigos_vigentes, "observado_en": observado_en})
    # La persistencia admite 20 entradas. Se carga y comprueba la fuente una sola
    # vez y se mantienen como máximo dos peticiones de guardado en curso.
    semaforo = asyncio.Semaphore(2)
    async def guardar(parte):
        async with semaforo:
            return await filtradas.operar("guardar", {"lote": parte, "perfil": cargar_catalogo(), "actor": actor})
    respuestas = await asyncio.gather(*(guardar(lote[i:i+20]) for i in range(0, len(lote), 20)),
                                     return_exceptions=True)
    for respuesta in respuestas:
        if isinstance(respuesta, BaseException):
            raise respuesta
    return {"evaluadas": [e for r in respuestas for e in r.get("evaluadas", [])]}


class Lote(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ids: list[Annotated[int, Field(strict=True, gt=0)]] = Field(min_length=1, max_length=100)


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
    entradas_actuales = cargar_entradas(db, [f["id"] for f in respuesta.get("filas", [])])
    for fila in respuesta.get("filas", []):
        entrada = entradas_actuales.get(str(fila["id"]), {})
        fila["nombre_organismo"] = entrada.get("nombre_organismo")
        fila["nombre_unidad"] = entrada.get("nombre_unidad")
        fila["clientes_importantes"] = identificar_clientes_importantes(entrada)
        if (actuales.get(fila["id"]) != fila.get("fuente_raw_id") or
                fila.get("hash_fuente") != firma_fuente(entradas_actuales.get(str(fila["id"]), {}))):
            fila.update(estado_seleccion="pendiente_evaluacion", motivo_seleccion="La fuente cambió; actualiza la preselección.")
    respuesta["ids_fuente"] = list(db.scalars(select(Licitacion.id).order_by(Licitacion.id)))
    response.headers["Cache-Control"] = "no-store"
    return respuesta


@router.post("/evaluar")
async def evaluar(entrada: Lote, usuario=Depends(usuario_actual), db: Session = Depends(get_db)):
    return await evaluar_lote(db, entrada.ids, str(UUID(usuario["id"])))


@router.get("/plan", dependencies=[Depends(usuario_actual)])
async def plan(response: Response, db: Session = Depends(get_db)):
    """Evalúa al cambiar la fuente o las reglas; conserva resultados y revisiones vigentes."""
    ids = list(db.scalars(select(Licitacion.id).order_by(Licitacion.id)))
    entradas = cargar_entradas(db, ids)
    fuentes = {d["codigo_externo"]: d["raw_id"] for d in entradas.values()}
    guardadas = {}
    for offset in range(0, len(ids), 100):
        pagina = await filtradas.operar("listar", {"codigos": list(fuentes), "fuentes": fuentes,
            "limite": 100, "offset": offset})
        guardadas.update({str(f["id"]): f for f in pagina.get("filas", [])})
    pendientes = [int(i) for i, d in entradas.items()
        if guardadas.get(i, {}).get("hash_fuente") != firma_fuente(d)
        or guardadas.get(i, {}).get("estado_seleccion") == "pendiente_evaluacion"]
    response.headers["Cache-Control"] = "no-store"
    return {"ids": pendientes, "total": len(ids), "version_motor": VERSION_MOTOR}


@router.post("/documentos/obtener")
async def obtener_documentos(usuario=Depends(usuario_actual), db: Session = Depends(get_db)):
    from ..services.ingesta_documental import procesar_documentos
    return await procesar_documentos(db, str(UUID(usuario["id"])))


@router.get("/pendientes-documentales", dependencies=[Depends(usuario_actual)])
def pendientes_documentales(response: Response, limite: int = Query(default=25, ge=1, le=100),
                            offset: int = Query(default=0, ge=0), db: Session = Depends(get_db)):
    # Lee la fuente original: también funciona si filtradas todavía no se ha evaluado o no responde.
    fuentes = list(db.execute(select(Licitacion.id, Licitacion.codigo_externo, Licitacion.nombre,
        Licitacion.fecha_cierre, Licitacion.codigo_estado, Licitacion.estado)
        .order_by(Licitacion.fecha_cierre.asc().nulls_last(), Licitacion.id)).mappings())
    incidencias = documentos_origen.incidencias(db, [f["id"] for f in fuentes])
    ahora = datetime.now(CHILE)
    filas = []
    for f in fuentes:
        fallos = incidencias[f["id"]]
        if not fallos or evaluar_vigencia(dict(f), ahora)["resultado"] == "no_cumple":
            continue
        filas.append({**dict(f), "fecha_cierre": serializable(f["fecha_cierre"]) if f["fecha_cierre"] else None,
            "estado_seleccion": "revision_manual", "url_oficial": ficha_oficial(f["codigo_externo"]),
            "motivo_seleccion": fallos[0]["motivo"], "incidencias_documentales": fallos})
    response.headers["Cache-Control"] = "no-store"
    return {"filas": filas[offset:offset+limite], "total": len(filas), "ids_fuente": [f["id"] for f in fuentes]}


@router.get("/{licitacion_id}", dependencies=[Depends(usuario_actual)])
async def detalle(licitacion_id: int, response: Response, db: Session = Depends(get_db)):
    fila = db.get(Licitacion, licitacion_id)
    if fila is None:
        raise HTTPException(404, "La licitación ya no está disponible.")
    try:
        resultado = await filtradas.operar("detalle", {"codigo": fila.codigo_externo})
    except filtradas.FiltradasNoDisponible:
        resultado = {"evaluacion": None, "criterios": [], "hash_fuente": None}
    resultado["documentos"] = await documentos_origen.detalle(db, licitacion_id)
    resultado["ingesta_documental"] = {k: v for k, v in fila.ingesta_documental.items() if k != "token"}
    resultado["incidencias_documentales"] = documentos_origen.incidencias(db, [licitacion_id])[licitacion_id]
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
    if not contenido:
        incidencia = documentos_origen.registrar_incidencia(db, licitacion_id, "archivo_vacio", nombre)
        try:
            evaluacion = await evaluar_lote(db, [licitacion_id], str(UUID(usuario["id"])))
        except filtradas.FiltradasNoDisponible:
            evaluacion = {"pendiente": True}
        return {"documento": None, "incidencia": incidencia, "evaluacion": evaluacion}
    from starlette.concurrency import run_in_threadpool
    try:
        extraccion = await run_in_threadpool(extraer_pdf, contenido)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    try:
        guardado = await documentos_origen.guardar(db, licitacion_id, nombre, tipo,
            ficha_oficial(fila.codigo_externo), contenido, extraccion, str(UUID(usuario["id"])))
    except documentos_origen.StorageNoDisponible as exc:
        raise HTTPException(503, str(exc)) from None
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
    doc = db.scalar(select(LicitacionDocumento).where(LicitacionDocumento.id == documento_id,
                                                     LicitacionDocumento.licitacion_id == licitacion_id))
    if not doc:
        raise HTTPException(404, "Documento no encontrado en esta licitación.")
    doc.vigente = False
    db.commit()
    try:
        return await evaluar_lote(db, [licitacion_id], str(UUID(usuario["id"])))
    except filtradas.FiltradasNoDisponible:
        return {"pendiente": True, "retirado": True}
