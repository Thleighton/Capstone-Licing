"""Consultas del frontend sobre las tablas existentes de Core."""
from datetime import datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, computed_field, field_validator
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..auth import usuario_actual
from ..database import get_db
from ..models.ejecucion_ingesta import EjecucionIngesta
from ..models.licitacion import Licitacion
from ..models.licitacion_item import LicitacionItem
from ..models.raw import RawMercadoPublico
from ..services.enlaces import ficha_oficial

CHILE = ZoneInfo("America/Santiago")
router = APIRouter(prefix="/api", tags=["Consultas"], dependencies=[Depends(usuario_actual)])


class LicitacionResumen(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    codigo_externo: str
    nombre: str | None
    descripcion: str | None
    estado: str | None
    monto_estimado: Decimal | None
    moneda: str | None
    fecha_publicacion: datetime | None
    fecha_cierre: datetime | None
    nombre_organismo: str | None
    nombre_unidad: str | None
    region_comprador: str | None
    comuna_comprador: str | None
    tipo: str | None
    estimacion: int | None
    visibilidad_monto: int | None

    @computed_field
    @property
    def url_oficial(self) -> str | None:
        return ficha_oficial(self.codigo_externo)

    @field_validator("fecha_publicacion", "fecha_cierre")
    @classmethod
    def fechas_de_chile(cls, valor):
        # Core conserva las fechas originales sin zona; la API indica su zona.
        return valor.replace(tzinfo=CHILE) if valor is not None and valor.tzinfo is None else valor


class ItemResumen(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    correlativo: int
    posicion_fuente: int
    codigo_producto: str | None
    nombre_producto: str | None
    descripcion: str | None
    cantidad: Decimal | None
    unidad_medida: str | None
    codigo_categoria: str | None
    categoria: str | None
    estado_fuente: int | None
    adjudicacion_fuente: dict | None


class LicitacionDetalle(LicitacionResumen):
    fuente_consultada_en: datetime | None = None
    codigo_tipo: int | None
    justificacion_monto: str | None
    direccion_comprador: str | None
    direccion_entrega: str | None
    direccion_visita: str | None
    fechas_fuente: dict | None
    condiciones_fuente: dict | None
    normalizacion_version: str | None
    normalizado_en: datetime | None


def _ahora_chile():
    return datetime.now(CHILE).replace(tzinfo=None)


def _abiertas(ahora):
    return (
        func.lower(func.coalesce(Licitacion.estado, "")) == "publicada",
        or_(Licitacion.fecha_cierre.is_(None), Licitacion.fecha_cierre >= ahora),
    )


@router.get("/licitaciones")
def listar_licitaciones(
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
            for campo in (Licitacion.codigo_externo, Licitacion.nombre, Licitacion.nombre_organismo, Licitacion.nombre_unidad)
        ]))
    if region.strip():
        filtros.append(func.lower(Licitacion.region_comprador).contains(region.strip().lower(), autoescape=True))
    if solo_abiertas:
        filtros.extend(_abiertas(_ahora_chile()))
    total = db.scalar(select(func.count()).select_from(Licitacion).where(*filtros))
    filas = db.scalars(select(Licitacion).where(*filtros).order_by(
        Licitacion.fecha_publicacion.desc().nullslast(), Licitacion.id.desc(),
    ).offset(offset).limit(limite)).all()
    response.headers["Cache-Control"] = "no-store"
    return {"items": [LicitacionResumen.model_validate(f) for f in filas], "total": total, "limite": limite, "offset": offset}


@router.get("/licitaciones/{licitacion_id}")
def detalle_licitacion(licitacion_id: int, response: Response, db: Session = Depends(get_db)):
    fila = db.get(Licitacion, licitacion_id)
    if fila is None:
        raise HTTPException(404, "No se encontró la licitación")
    items = db.scalars(select(LicitacionItem).where(
        LicitacionItem.licitacion_id == fila.id,
    ).order_by(LicitacionItem.posicion_fuente)).all()
    response.headers["Cache-Control"] = "no-store"
    raw = db.get(RawMercadoPublico, fila.raw_id)
    detalle = LicitacionDetalle.model_validate(fila).model_copy(update={"fuente_consultada_en": raw.verificado_en if raw else None})
    return {"licitacion": detalle, "items": [ItemResumen.model_validate(i) for i in items]}


@router.get("/dashboard")
def dashboard(response: Response, db: Session = Depends(get_db)):
    ahora = _ahora_chile()
    total = db.scalar(select(func.count()).select_from(Licitacion))
    abiertas = db.scalar(select(func.count()).select_from(Licitacion).where(*_abiertas(ahora)))
    cierran_pronto = db.scalar(select(func.count()).select_from(Licitacion).where(
        *_abiertas(ahora), Licitacion.fecha_cierre <= ahora + timedelta(days=3),
    ))
    primeras_descargas = select(
        RawMercadoPublico.codigo_externo.label("codigo"),
        func.min(RawMercadoPublico.consultado_en).label("primera"),
    ).where(RawMercadoPublico.tipo_consulta == "detalle_codigo").group_by(RawMercadoPublico.codigo_externo).subquery()
    nuevas = db.scalar(select(func.count()).select_from(Licitacion).join(
        primeras_descargas, primeras_descargas.c.codigo == Licitacion.codigo_externo,
    ).where(primeras_descargas.c.primera >= datetime.now(CHILE) - timedelta(days=1)))
    inicio = datetime.combine(ahora.date() - timedelta(days=6), time.min)
    fin = datetime.combine(ahora.date() + timedelta(days=1), time.min)
    conteos = dict(db.execute(select(func.date(Licitacion.fecha_publicacion), func.count()).where(
        Licitacion.fecha_publicacion >= inicio, Licitacion.fecha_publicacion < fin,
    ).group_by(func.date(Licitacion.fecha_publicacion))).all())
    conteos = {str(fecha): n for fecha, n in conteos.items()}
    publicaciones = [
        {"fecha": (inicio.date() + timedelta(days=i)).isoformat(), "cantidad": conteos.get((inicio.date() + timedelta(days=i)).isoformat(), 0)}
        for i in range(7)
    ]
    estados = db.execute(select(func.coalesce(Licitacion.estado, "Sin estado"), func.count()).group_by(Licitacion.estado)).all()
    proximas = db.scalars(select(Licitacion).where(
        *_abiertas(ahora), Licitacion.fecha_cierre.is_not(None),
    ).order_by(Licitacion.fecha_cierre, Licitacion.id).limit(4)).all()
    response.headers["Cache-Control"] = "no-store"
    return {
        "total": total, "abiertas": abiertas, "cierran_pronto": cierran_pronto, "nuevas": nuevas,
        "publicaciones": publicaciones,
        "estados": [{"estado": estado, "cantidad": n} for estado, n in estados],
        "proximas": [LicitacionResumen.model_validate(f) for f in proximas],
    }


@router.get("/ingestas")
def listar_ingestas(response: Response, limite: int = Query(default=5, ge=1, le=100), db: Session = Depends(get_db)):
    filas = db.scalars(select(EjecucionIngesta).order_by(EjecucionIngesta.id.desc()).limit(limite)).all()
    response.headers["Cache-Control"] = "no-store"
    return [{
        "id": f.id, "inicio": f.inicio, "fin": f.fin, "estado": f.estado,
        "seleccionados": f.seleccionados, "descargados": f.descargados, "reutilizados": f.reutilizados,
        "procesados": f.procesados, "n_errores": len(f.errores or []),
        "detenido_por_error_api": f.detenido_por_error_api,
    } for f in filas]

