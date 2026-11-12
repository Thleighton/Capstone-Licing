"""Consultas del frontend sobre las Compras Ágiles guardadas por Core."""
from datetime import date, datetime, timedelta
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
from ..models.compra_agil_sincronizacion import CompraAgilSincronizacion
from ..models.raw import RawMercadoPublico
from ..services import filtradas
from ..services.clientes_importantes import identificar_clientes_importantes
from ..services.compra_agil_preseleccion import (
    cargar_catalogo, cargar_entradas as cargar_entradas_compra,
    contar_pendientes, evaluar_compras_agiles, firma as firma_compra,
    plan_pendientes, version_preseleccion,
)
from ..services.enlaces import ficha_compra_agil
from ..services.fechas_consulta import filtrar_cierre
from ..services.resumen_gemini import SolicitudResumenIA, obtener_o_generar, cache_actual, fuente_resumen

CHILE = ZoneInfo("America/Santiago")
router = APIRouter(prefix="/api", tags=["Compras Ágiles"], dependencies=[Depends(usuario_actual)])


def _orden_compra_agil(orden_cierre: str, orden_publicacion: str):
    cierre = {"proximo": CompraAgil.fecha_cierre.asc().nullslast(),
              "lejano": CompraAgil.fecha_cierre.desc().nullslast()}.get(orden_cierre)
    publicacion = {"reciente": CompraAgil.fecha_publicacion.desc().nullslast(),
                   "antigua": CompraAgil.fecha_publicacion.asc().nullslast()}.get(orden_publicacion)
    return tuple(x for x in (cierre, publicacion) if x is not None) or (CompraAgil.fecha_cierre.asc().nullslast(),)


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
    preseleccion: dict | None = Field(default=None, exclude=True)

    @computed_field
    @property
    def clasificacion(self) -> str | None:
        """Propuesta automática con las reglas vigentes; None mientras falte evaluarla."""
        guardada = self.preseleccion or {}
        return guardada.get("clasificacion") if guardada.get("version") == version_preseleccion() else None

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
    resumen_ia: dict | None = None

    @field_validator("fecha_ultimo_cambio", "fecha_cancelacion")
    @classmethod
    def otras_fechas_de_chile(cls, valor):
        return valor.replace(tzinfo=CHILE) if valor is not None and valor.tzinfo is None else valor


@router.get("/compras-agiles")
def listar_compras_agiles(
    response: Response,
    q: str = Query(default="", max_length=200),
    codigo: str = Query(default="", max_length=60),
    region: str = Query(default="", max_length=200),
    solo_abiertas: bool = False,
    limite: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    cierre_desde: date | None = None,
    cierre_hasta: date | None = None,
    orden_cierre: str = Query(default="proximo", pattern="^(proximo|lejano|ninguno)$"),
    orden_publicacion: str = Query(default="ninguna", pattern="^(ninguna|reciente|antigua)$"),
):
    filtros = []
    if q.strip():
        filtros.append(or_(*[
            func.lower(campo).contains(q.strip().lower(), autoescape=True)
            for campo in (CompraAgil.codigo_externo, CompraAgil.nombre, CompraAgil.descripcion,
                          CompraAgil.nombre_organismo, CompraAgil.nombre_unidad)
        ]))
    if codigo.strip():
        filtros.append(func.lower(CompraAgil.codigo_externo).contains(codigo.strip().lower(), autoescape=True))
    if region.strip():
        filtros.append(func.lower(CompraAgil.region_comprador).contains(region.strip().lower(), autoescape=True))
    if solo_abiertas:
        ahora = datetime.now(CHILE).replace(tzinfo=None)
        filtros.extend((
            CompraAgil.estado == "publicada",
            or_(CompraAgil.fecha_cierre.is_(None), CompraAgil.fecha_cierre >= ahora),
        ))
    consulta = filtrar_cierre(select(CompraAgil).where(*filtros), CompraAgil.fecha_cierre, cierre_desde, cierre_hasta)
    total = db.scalar(select(func.count()).select_from(consulta.subquery()))
    filas = db.scalars(consulta.order_by(*_orden_compra_agil(orden_cierre, orden_publicacion), CompraAgil.id.desc()).offset(offset).limit(limite)).all()
    response.headers["Cache-Control"] = "no-store"
    return {"items": [CompraAgilResumen.model_validate(f) for f in filas], "total": total,
            "limite": limite, "offset": offset}


def _evaluacion_vigente(compra: CompraAgil | None, hash_fuente, raw_id=None, firma_actual=None) -> bool:
    guardada = compra.preseleccion if compra is not None else None
    firma_coincide = bool(guardada) and guardada.get("firma") == hash_fuente
    if firma_actual is not None:
        firma_coincide = firma_coincide and guardada.get("firma") == firma_actual
    return bool(guardada) and guardada.get("version") == version_preseleccion() and \
        firma_coincide and (raw_id is None or raw_id == compra.raw_id)


class LoteCompras(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ids: list[Annotated[int, Field(strict=True, gt=0)]] | None = Field(default=None, min_length=1, max_length=100)


# Antes de /compras-agiles/{compra_agil_id}: «resumen» y «preseleccion» no son ids.
@router.get("/compras-agiles/resumen")
def resumen_compras_agiles(response: Response, db: Session = Depends(get_db)):
    """Indicadores del dashboard en una sola consulta; la clasificación es la propuesta automática vigente."""
    ahora = datetime.now(CHILE).replace(tzinfo=None)
    abiertas = (CompraAgil.estado == "publicada", or_(CompraAgil.fecha_cierre.is_(None), CompraAgil.fecha_cierre >= ahora))

    def contar(*filtros):
        return db.scalar(select(func.count()).select_from(CompraAgil).where(*filtros))
    primeras = select(RawMercadoPublico.codigo_externo.label("codigo"),
                      func.min(RawMercadoPublico.consultado_en).label("primera")).where(
        RawMercadoPublico.fuente == "compra_agil").group_by(RawMercadoPublico.codigo_externo).subquery()
    nuevas = db.scalar(select(func.count()).select_from(CompraAgil).join(
        primeras, primeras.c.codigo == CompraAgil.codigo_externo,
    ).where(primeras.c.primera >= datetime.now(CHILE) - timedelta(days=1)))
    clasificacion = CompraAgil.preseleccion["clasificacion"].astext
    propuestas = dict(db.execute(select(clasificacion, func.count()).where(
        *abiertas, CompraAgil.preseleccion["version"].astext == version_preseleccion(),
    ).group_by(clasificacion)).all())
    sincronizacion = db.get(CompraAgilSincronizacion, 1)
    response.headers["Cache-Control"] = "no-store"
    return {
        "total": contar(), "abiertas": contar(*abiertas), "nuevas": nuevas,
        "cierran_pronto": contar(*abiertas, CompraAgil.fecha_cierre <= ahora + timedelta(days=1)),
        "preseleccion": {**{c: propuestas.get(c, 0) for c in ("preseleccionada", "revision_manual", "descartada")},
                         "pendientes": contar_pendientes(db)},
        "carga_inicial_completa": sincronizacion is not None and sincronizacion.cursor is not None,
    }


@router.get("/compras-agiles/exportar.xlsx")
async def exportar_compras_agiles(db: Session = Depends(get_db)):
    """Excel separado por clasificación; datos desactualizados quedan en revisión."""
    from starlette.concurrency import run_in_threadpool
    from ..services.exportacion_oportunidades import crear_excel, HOJAS

    ids = list(db.scalars(select(CompraAgil.id).order_by(CompraAgil.id)))
    entradas = await run_in_threadpool(cargar_entradas_compra, db, ids)
    fuentes = {datos["codigo_externo"]: datos["raw_id"] for datos in entradas.values()}
    guardadas = {}
    for offset in range(0, len(ids), 100):
        pagina = await filtradas.operar("listar", {
            "codigos": list(fuentes), "fuentes": fuentes, "limite": 100, "offset": offset,
        })
        guardadas.update({str(fila["id"]): fila for fila in pagina.get("filas", [])})

    compras = {compra.id: compra for compra in db.scalars(
        select(CompraAgil).where(CompraAgil.id.in_(ids))
    )} if ids else {}
    filas = []
    for identificador, datos in entradas.items():
        guardada = guardadas.get(identificador, {})
        compra = compras.get(int(identificador))
        estado = guardada.get("estado_seleccion")
        if (estado not in HOJAS or not _evaluacion_vigente(
            compra, guardada.get("hash_fuente"), guardada.get("fuente_raw_id"), firma_compra(datos)
        )):
            estado = "revision_manual"
        filas.append({**datos, "estado_seleccion": estado})

    contenido = await run_in_threadpool(crear_excel, filas, "compra_agil")
    fecha = datetime.now(CHILE).strftime("%Y-%m-%d")
    return Response(contenido,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="LICING-compras-agiles-{fecha}.xlsx"',
                 "Cache-Control": "no-store"})


@router.get("/compras-agiles/preseleccion")
async def preseleccion_compras_agiles(
    response: Response,
    clasificacion: str = Query(default="", max_length=30),
    q: str = Query(default="", max_length=150),
    codigo: str = Query(default="", max_length=60),
    orden_cierre: str = Query(default="proximo", pattern="^(proximo|lejano|ninguno)$"),
    orden_publicacion: str = Query(default="ninguna", pattern="^(ninguna|reciente|antigua)$"),
    limite: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    cierre_desde: date | None = None,
    cierre_hasta: date | None = None,
):
    """Evaluaciones de LicitacionesFiltradas, solo para las Compras Ágiles que Core conserva."""
    consulta_fuentes = select(CompraAgil.codigo_externo, CompraAgil.raw_id)
    if codigo.strip():
        consulta_fuentes = consulta_fuentes.where(
            func.lower(CompraAgil.codigo_externo).contains(codigo.strip().lower(), autoescape=True)
        )
    consulta = filtrar_cierre(consulta_fuentes, CompraAgil.fecha_cierre, cierre_desde, cierre_hasta)
    fuentes = dict(db.execute(consulta).all())
    respuesta = await filtradas.operar("listar", {"codigos": list(fuentes), "fuentes": fuentes,
        "orden_cierre": orden_cierre, "orden_publicacion": orden_publicacion,
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


@router.get("/compras-agiles/preseleccion/plan")
async def plan_preseleccion_compras_agiles(response: Response, db: Session = Depends(get_db)):
    """Comprueba las evaluaciones pendientes sin guardar cambios."""
    ids = await plan_pendientes(db)
    catalogo = cargar_catalogo()
    response.headers["Cache-Control"] = "no-store"
    return {
        "ids": ids,
        "pendientes": max(len(ids), contar_pendientes(db)),
        "version_filtro": version_preseleccion(),
        "nombre_perfil": (catalogo.get("perfil_comercial") or {}).get("nombre"),
    }


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
    # cargar_entradas serializa el mapa a JSON, que convierte las claves int a str.
    entrada_actual = cargar_entradas_compra(db, [fila.id]).get(str(fila.id))
    firma_actual = firma_compra(entrada_actual) if entrada_actual else None
    resultado["fuente_actualizada"] = _evaluacion_vigente(
        fila, resultado.get("hash_fuente"), firma_actual=firma_actual,
    )
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
    entrada_actual = cargar_entradas_compra(db, [compra_agil_id]).get(str(compra_agil_id))
    detalle.resumen_ia = cache_actual(db, fila, entrada_actual,
        fuente_resumen(fila, entrada_actual, 'compra_agil', None)) if entrada_actual else None
    return {"compra_agil": detalle, "items": [CompraAgilItemResumen.model_validate(i) for i in items]}


@router.post("/compras-agiles/{compra_agil_id}/resumen-ia")
async def resumen_ia_compra_agil(compra_agil_id: int, solicitud: SolicitudResumenIA,
                                 db: Session = Depends(get_db)):
    fila = db.get(CompraAgil, compra_agil_id)
    if fila is None:
        raise HTTPException(404, "No se encontró la Compra Ágil.")
    guardada = fila.preseleccion or {}
    clasificacion = guardada.get("clasificacion")
    if (solicitud.clasificacion not in {"preseleccionada", "revision_manual"}
            or solicitud.clasificacion != clasificacion
            or guardada.get("version") != version_preseleccion()):
        raise HTTPException(409, "La lectura asistida está disponible para posibles oportunidades y revisiones vigentes.")
    # Mantener el mismo tipo de clave que devuelve cargar_entradas tras serializar a JSON.
    entrada = cargar_entradas_compra(db, [compra_agil_id]).get(str(compra_agil_id))
    firma_actual = firma_compra(entrada) if entrada else None
    # Igual que en licitaciones, la protección contra datos obsoletos compara
    # la huella que vio la pantalla con la ficha actual. La firma local de la
    # preselección es una copia de control y puede quedar desfasada respecto de
    # Filtradas; no debe bloquear un resumen cuando la fuente actual sí coincide.
    if not firma_actual or solicitud.hash_fuente != firma_actual:
        raise HTTPException(409, "La ficha de la Compra Ágil cambió desde que la abriste. Actualiza la ficha antes de generar el resumen.")
    fuente = fuente_resumen(fila, entrada, 'compra_agil', clasificacion)
    return await obtener_o_generar(db, fila, fuente, entrada,
        lambda: cargar_entradas_compra(db, [compra_agil_id]).get(str(compra_agil_id)))
