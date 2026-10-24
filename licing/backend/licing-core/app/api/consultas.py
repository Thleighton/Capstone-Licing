"""Consultas del frontend sobre las tablas existentes de Core."""
from datetime import datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from starlette.concurrency import run_in_threadpool
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
from ..services import filtradas
from ..services.clientes_importantes import identificar_clientes_importantes, listar_clientes_importantes
from .preseleccion import cargar_entradas, firma_fuente

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
    def clientes_importantes(self) -> list[dict]:
        return identificar_clientes_importantes({"nombre_organismo": self.nombre_organismo,
                                                 "nombre_unidad": self.nombre_unidad})

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
    ubicacion_servicio: dict | None = None
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


@router.get("/clientes")
def clientes_importantes(response: Response):
    response.headers["Cache-Control"] = "no-store"
    return {"clientes": listar_clientes_importantes()}


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
    # Un escritor anterior puede cambiar raw_id sin regenerar la evidencia.
    if detalle.ubicacion_servicio and detalle.ubicacion_servicio.get("raw_id") != fila.raw_id:
        detalle = detalle.model_copy(update={"ubicacion_servicio": None})
    return {"licitacion": detalle, "items": [ItemResumen.model_validate(i) for i in items]}


async def _proximas_filtradas(db, candidatas):
    """Interseca cierres abiertos y ordenados con selecciones guardadas vigentes."""
    if not candidatas:
        return [], True
    fuentes = {f.codigo_externo: f.raw_id for f in candidatas}
    seleccionadas = []
    try:
        for offset in range(0, len(candidatas), 100):
            pagina = await filtradas.operar("listar", {"codigos": list(fuentes), "fuentes": fuentes,
                "limite": 100, "offset": offset})
            for guardada in pagina.get("filas", []):
                if guardada.get("estado_seleccion") not in {"preseleccionada", "revision_manual"}:
                    continue
                seleccionadas.append(guardada)
    except filtradas.FiltradasNoDisponible:
        # Nunca sustituir una clasificación no disponible por licitaciones sin filtrar.
        return [], False
    # Leer ítems y versiones documentales solo de resultados que podrían mostrarse.
    # La sesión se usa secuencialmente; el SQL síncrono no bloquea otras peticiones.
    ids_candidatas = {f.id for f in candidatas}
    ids = list({f["id"] for f in seleccionadas if f["id"] in ids_candidatas})
    if not ids:
        return [], True
    entradas = await run_in_threadpool(cargar_entradas, db, ids)
    estados = {}
    for guardada in seleccionadas:
        entrada = entradas.get(str(guardada["id"]))
        if (entrada is not None and guardada.get("codigo_externo") == entrada["codigo_externo"]
                and guardada.get("fuente_raw_id") == entrada["raw_id"]
                and guardada.get("hash_fuente") == firma_fuente(entrada)):
            estados[guardada["id"]] = guardada["estado_seleccion"]
    return [(f, estados[f.id]) for f in candidatas if f.id in estados], True


@router.get("/dashboard")
async def dashboard(response: Response, db: Session = Depends(get_db)):
    ahora = _ahora_chile()
    resumen, candidatas = await run_in_threadpool(_resumen_dashboard, db, ahora)
    proximas, proximas_disponibles = await _proximas_filtradas(db, candidatas)
    response.headers["Cache-Control"] = "no-store"
    return {
        **resumen,
        "proximas": [{**LicitacionResumen.model_validate(f).model_dump(), "estado_seleccion": estado}
                     for f, estado in proximas],
        "proximas_disponibles": proximas_disponibles,
    }


def _resumen_dashboard(db, ahora):
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
    candidatas = db.scalars(select(Licitacion).where(
        *_abiertas(ahora), Licitacion.fecha_cierre.is_not(None),
    ).order_by(Licitacion.fecha_cierre, Licitacion.id)).all()
    return {
        "total": total, "abiertas": abiertas, "cierran_pronto": cierran_pronto, "nuevas": nuevas,
        "publicaciones": publicaciones,
        "estados": [{"estado": estado, "cantidad": n} for estado, n in estados],
    }, candidatas


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

