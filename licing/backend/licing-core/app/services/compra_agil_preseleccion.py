"""Preselección de Compras Ágiles con el mismo motor y la misma persistencia que las licitaciones.

Las evaluaciones viven en LicitacionesFiltradas con modalidad 'compra_agil'. compra_agil.preseleccion
recuerda qué firma y versión del motor se guardaron, para reintentar lo pendiente en cada lote.
"""
import asyncio
import json
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session

from ..models.compra_agil import CompraAgil
from ..models.compra_agil_item import CompraAgilItem
from ..models.raw import RawMercadoPublico
from . import filtradas
from .enlaces import ficha_compra_agil
from .preseleccion import CHILE, VERSION_MOTOR, cargar_catalogo, evaluar_preseleccion

MODALIDAD = "compra_agil"
# guardar admite 20 entradas por llamada.
TAMANO_GUARDADO = 20
LIMITE_POR_LOTE = 40
COLUMNAS = (
    "id", "codigo_externo", "raw_id", "nombre", "descripcion", "estado", "fecha_publicacion", "fecha_cierre",
    "moneda", "nombre_organismo", "nombre_unidad", "region_comprador", "direccion_entrega",
    "fechas_fuente", "condiciones_fuente", "normalizacion_version",
)


def version_preseleccion() -> str:
    return f"{VERSION_MOTOR}|{cargar_catalogo()['version']}"


def _serializable(valor):
    # Mismo formato que las licitaciones: hora de Chile con zona y montos como texto.
    from ..api.preseleccion import serializable
    return serializable(valor)


def firma(datos: dict) -> str:
    from ..api.preseleccion import firma_fuente
    return firma_fuente(datos)


def cargar_entradas(db: Session, ids) -> dict[str, dict]:
    """Datos con los nombres de columna de filtradas.oportunidad y oportunidad_item."""
    if not ids:
        return {}
    filas = db.scalars(select(CompraAgil).where(CompraAgil.id.in_(ids))).all()
    verificaciones = dict(db.execute(select(RawMercadoPublico.id, RawMercadoPublico.verificado_en)
        .where(RawMercadoPublico.id.in_({f.raw_id for f in filas}))).all())
    entradas = {}
    for fila in filas:
        datos = {campo: getattr(fila, campo) for campo in COLUMNAS}
        datos.update(
            modalidad=MODALIDAD, codigo_estado=None, monto_estimado=fila.monto_disponible,
            url_oficial=ficha_compra_agil(fila.codigo_externo), items=[], documentos_version=[],
            fuente_verificada_en=verificaciones.get(fila.raw_id),
        )
        entradas[fila.id] = datos
    for item in db.scalars(select(CompraAgilItem).where(CompraAgilItem.compra_agil_id.in_(ids))
                           .order_by(CompraAgilItem.compra_agil_id, CompraAgilItem.posicion_fuente)):
        # oportunidad_item exige correlativo; Compra Ágil no lo tiene y se usa la posición.
        entradas[item.compra_agil_id]["items"].append({
            "posicion_fuente": item.posicion_fuente, "correlativo": item.posicion_fuente,
            "codigo_producto": item.codigo_producto, "nombre_producto": item.nombre_producto,
            "descripcion": item.descripcion, "cantidad": item.cantidad, "unidad_medida": item.unidad_medida,
        })
    return json.loads(json.dumps(entradas, default=_serializable))


def _sin_evaluacion_vigente(version):
    return or_(CompraAgil.preseleccion.is_(None), CompraAgil.preseleccion["version"].astext != version)


def contar_pendientes(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(CompraAgil).where(_sin_evaluacion_vigente(version_preseleccion())))


def pendientes(db: Session, limite: int = LIMITE_POR_LOTE) -> list[int]:
    """Abiertas sin evaluación guardada, o evaluadas con otra versión del motor o del catálogo."""
    ahora = datetime.now(CHILE).replace(tzinfo=None)
    return list(db.scalars(select(CompraAgil.id).where(
        _sin_evaluacion_vigente(version_preseleccion()),
        or_(CompraAgil.fecha_cierre.is_(None), CompraAgil.fecha_cierre > ahora),
    ).order_by(CompraAgil.fecha_publicacion.desc().nullslast(), CompraAgil.id).limit(limite)))


async def evaluar_compras_agiles(db: Session, ids=None, actor=None, limite: int = LIMITE_POR_LOTE) -> dict:
    """Evalúa y guarda en filtradas. FiltradasNoDisponible deja las compras pendientes."""
    ids = list(dict.fromkeys(ids)) if ids is not None else pendientes(db, limite)
    entradas = cargar_entradas(db, ids)
    if not entradas:
        return {"evaluadas": [], "pendientes": 0}
    version = version_preseleccion()
    lote = []
    for datos in entradas.values():
        lote.append({"datos": datos, "resultado": evaluar_preseleccion({**datos, "documentos": []}),
                     "hash_fuente": firma(datos), "documentos_version": []})
    semaforo = asyncio.Semaphore(2)

    async def guardar(parte):
        async with semaforo:
            return await filtradas.operar("guardar", {"lote": parte, "perfil": cargar_catalogo(), "actor": actor})
    partes = [lote[i:i + TAMANO_GUARDADO] for i in range(0, len(lote), TAMANO_GUARDADO)]
    respuestas = await asyncio.gather(*(guardar(parte) for parte in partes), return_exceptions=True)
    evaluadas, errores = [], []
    for parte, respuesta in zip(partes, respuestas):
        if isinstance(respuesta, BaseException):
            errores.append(respuesta)
            continue
        guardadas = {e["codigo"]: e["evaluacion_id"] for e in respuesta.get("evaluadas", [])}
        for entrada in parte:
            datos, resultado = entrada["datos"], entrada["resultado"]
            if datos["codigo_externo"] not in guardadas:
                continue  # Filtradas omite las que ya cerraron.
            # Si el RAW cambió mientras tanto, la compra sigue pendiente con sus datos nuevos.
            db.execute(update(CompraAgil).where(
                CompraAgil.id == datos["id"], CompraAgil.raw_id == datos["raw_id"],
            ).values(preseleccion={
                "firma": entrada["hash_fuente"], "version": version, "clasificacion": resultado["clasificacion"],
                "evaluacion_id": guardadas[datos["codigo_externo"]], "evaluado_en": resultado["evaluado_en"],
            }))
            evaluadas.append({"compra_agil_id": datos["id"], "codigo_externo": datos["codigo_externo"],
                              "clasificacion": resultado["clasificacion"]})
    db.commit()
    if errores and not evaluadas:
        raise errores[0]
    return {"evaluadas": evaluadas, "pendientes": contar_pendientes(db), "sin_guardar": len(lote) - len(evaluadas),
            "sincronizada": bool(evaluadas) and await _sincronizar(db)}


async def _sincronizar(db: Session) -> bool:
    """Retira de filtradas las Compras Ágiles que Core ya no conserva.

    Solo se llama después de que filtradas aceptó una Compra Ágil. Una filtradas sin la migración
    de Compra Ágil rechaza los códigos COT al guardar e ignoraría la modalidad al sincronizar,
    retirando también todas las licitaciones y sus revisiones manuales.
    """
    codigos = list(db.scalars(select(CompraAgil.codigo_externo)))
    try:
        await filtradas.operar("sincronizar_fuente", {"codigos": codigos, "modalidad": MODALIDAD,
                                                      "observado_en": datetime.now(timezone.utc).isoformat()})
    except (filtradas.FiltradasNoDisponible, HTTPException):
        return False  # Las evaluaciones ya quedaron guardadas; el próximo lote vuelve a sincronizar.
    return True
