"""Consultas del frontend sobre las Compras Ágiles guardadas por Core."""
from datetime import datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..auth import usuario_actual
from ..database import get_db
from ..models.compra_agil import CompraAgil
from ..models.compra_agil_item import CompraAgilItem
from ..models.raw import RawMercadoPublico
from ..services import filtradas
from ..services.clientes_importantes import identificar_clientes_importantes
from ..services.compra_agil_preseleccion import contar_pendientes, evaluar_compras_agiles, version_preseleccion
from ..services.enlaces import ficha_compra_agil

CHILE = ZoneInfo("America/Santiago")
router = APIRouter(prefix="/api", tags=["Compras Ágiles"], dependencies=[Depends(usuario_actual)])


class CompraAgilResumen(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    codigo_externo: str
    nombre: str | None
    descripcion: str | None
    estado: str | None
    estado_glosa: str | None
    estado_convocatoria: int | None
    moneda: str | None
    tipo_presupuesto: str | None
    monto_disponible: Decimal | None
    monto_disponible_clp: Decimal | None
    fecha_publicacion: datetime | None
    fecha_cierre: datetime | None
    nombre_organismo: str | None
    nombre_unidad: str | None
    codigo_region: int | None
    region_comprador: str | None
    total_ofertas_recibidas: int | None

    @computed_field
    @property
    def clientes_importantes(self) -> list[dict]:
        return identificar_clientes_importantes({"nombre_organismo": self.nombre_organismo,
                                                 "nombre_unidad": self.nombre_unidad})

    @computed_field
    @property
    def url_oficial(self) -> str | None:
        return ficha_compra_agil(self.codigo_externo)

    @field_validator("fecha_publicacion", "fecha_cierre")
    @classmethod
    def fechas_de_chile(cls, valor):
        # Core guarda hora de Chile sin zona; la API indica su zona.
        return valor.replace(tzinfo=CHILE) if valor is not None and valor.tzinfo is None else valor


class CompraAgilItemResumen(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    posicion_fuente: int
    codigo_producto: str | None
    nombre_producto: str | None
    descripcion: str | None
    cantidad: Decimal | None
    unidad_medida: str | None


class CompraAgilDetalle(CompraAgilResumen):
    id_estado: int | None
    fecha_ultimo_cambio: datetime | None
    fecha_cancelacion: datetime | None
    presupuesto_estimado: Decimal | None
    rut_organismo: str | None
    direccion_entrega: str | None
    plazo_entrega_dias: int | None
    id_orden_compra: int | None
    documentos: list[dict]
    fechas_fuente: dict | None
    condiciones_fuente: dict | None
    normalizacion_version: str | None
    normalizado_en: datetime | None
    fuente_consultada_en: datetime | None = None

    @field_validator("fecha_ultimo_cambio", "fecha_cancelacion")
    @classmethod
    def otras_fechas_de_chile(cls, valor):
        return valor.replace(tzinfo=CHILE) if valor is not None and valor.tzinfo is None else valor


@router.get("/compras-agiles")
def listar_compras_agiles(
    response: Response,
    q: str = Query(default="", max_length=200),
    region: str = Query(default="", max_length=200),
    solo_abiertas: bool = False,
    limite: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    filtros = []
    if q.strip():
        filtros.append(or_(*[
            func.lower(campo).contains(q.strip().lower(), autoescape=True)
            for campo in (CompraAgil.codigo_externo, CompraAgil.nombre, CompraAgil.descripcion,
                          CompraAgil.nombre_organismo, CompraAgil.nombre_unidad)
        ]))
    if region.strip():
        filtros.append(func.lower(CompraAgil.region_comprador).contains(region.strip().lower(), autoescape=True))
    if solo_abiertas:
        ahora = datetime.now(CHILE).replace(tzinfo=None)
        filtros.extend((
            CompraAgil.estado == "publicada",
            or_(CompraAgil.fecha_cierre.is_(None), CompraAgil.fecha_cierre >= ahora),
        ))
    total = db.scalar(select(func.count()).select_from(CompraAgil).where(*filtros))
    filas = db.scalars(select(CompraAgil).where(*filtros).order_by(
        CompraAgil.fecha_publicacion.desc().nullslast(), CompraAgil.id.desc(),
    ).offset(offset).limit(limite)).all()
    response.headers["Cache-Control"] = "no-store"
    return {"items": [CompraAgilResumen.model_validate(f) for f in filas], "total": total,
            "limite": limite, "offset": offset}


def _evaluacion_vigente(compra: CompraAgil | None, hash_fuente, raw_id=None) -> bool:
    guardada = compra.preseleccion if compra is not None else None
    return bool(guardada) and guardada.get("version") == version_preseleccion() and         guardada.get("firma") == hash_fuente and (raw_id is None or raw_id == compra.raw_id)


class LoteCompras(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ids: list[Annotated[int, Field(strict=True, gt=0)]] | None = Field(default=None, min_length=1, max_length=100)


# Antes de /compras-agiles/{compra_agil_id}: el segmento «preseleccion» no es un id.
@router.get("/compras-agiles/preseleccion")
async def preseleccion_compras_agiles(
    response: Response,
    clasificacion: str = Query(default="", max_length=30),
    q: str = Query(default="", max_length=150),
    limite: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    """Evaluaciones de LicitacionesFiltradas, solo para las Compras Ágiles que Core conserva."""
    fuentes = dict(db.execute(select(CompraAgil.codigo_externo, CompraAgil.raw_id)).all())
    respuesta = await filtradas.operar("listar", {"codigos": list(fuentes), "fuentes": fuentes,
        "clasificacion": clasificacion, "q": q, "limite": limite, "offset": offset})
    filas = respuesta.get("filas", [])
    compras = {c.id: c for c in db.scalars(select(CompraAgil).where(CompraAgil.id.in_([f["id"] for f in filas])))}
    for fila in filas:
        compra = compras.get(fila["id"])
        if compra is not None and compra.codigo_externo == fila["codigo_externo"]:
            fila.update(CompraAgilResumen.model_validate(compra).model_dump(include={
                "nombre_organismo", "nombre_unidad", "region_comprador", "moneda", "monto_disponible_clp",
                "clientes_importantes"}))
        if not _evaluacion_vigente(compra, fila.get("hash_fuente"), fila.get("fuente_raw_id")):
            fila.update(estado_seleccion="pendiente_evaluacion",
                        motivo_seleccion="La fuente o las reglas cambiaron; la preselección se actualizará.")
    respuesta["pendientes"] = contar_pendientes(db)
    response.headers["Cache-Control"] = "no-store"
    return respuesta


@router.post("/compras-agiles/preseleccion/evaluar")
async def evaluar_preseleccion_compras_agiles(
    entrada: LoteCompras | None = None,
    usuario=Depends(usuario_actual),
    db: Session = Depends(get_db),
):
    """Sin ids evalúa las pendientes; registra al usuario como autor si cambia el perfil."""
    ids = entrada.ids if entrada is not None else None
    if ids and db.scalar(select(func.count()).select_from(CompraAgil).where(CompraAgil.id.in_(ids))) != len(set(ids)):
        raise HTTPException(404, "Alguna Compra Ágil ya no está disponible. Actualiza la lista.")
    return await evaluar_compras_agiles(db, ids, actor=str(UUID(usuario["id"])))


@router.get("/compras-agiles/{compra_agil_id}/preseleccion")
async def detalle_preseleccion_compra_agil(compra_agil_id: int, response: Response, db: Session = Depends(get_db)):
    fila = db.get(CompraAgil, compra_agil_id)
    if fila is None:
        raise HTTPException(404, "No se encontró la Compra Ágil")
    try:
        resultado = await filtradas.operar("detalle", {"codigo": fila.codigo_externo})
    except filtradas.FiltradasNoDisponible:
        resultado = {"evaluacion": None, "criterios": [], "hash_fuente": None}
    resultado["fuente_actualizada"] = _evaluacion_vigente(fila, resultado.get("hash_fuente"))
    response.headers["Cache-Control"] = "no-store"
    return resultado


@router.get("/compras-agiles/{compra_agil_id}")
def detalle_compra_agil(compra_agil_id: int, response: Response, db: Session = Depends(get_db)):
    fila = db.get(CompraAgil, compra_agil_id)
    if fila is None:
        raise HTTPException(404, "No se encontró la Compra Ágil")
    items = db.scalars(select(CompraAgilItem).where(
        CompraAgilItem.compra_agil_id == fila.id,
    ).order_by(CompraAgilItem.posicion_fuente)).all()
    raw = db.get(RawMercadoPublico, fila.raw_id)
    response.headers["Cache-Control"] = "no-store"
    detalle = CompraAgilDetalle.model_validate(fila).model_copy(
        update={"fuente_consultada_en": raw.verificado_en if raw else None},
    )
    return {"compra_agil": detalle, "items": [CompraAgilItemResumen.model_validate(i) for i in items]}
