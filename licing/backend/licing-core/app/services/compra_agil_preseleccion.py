"""Preselección de Compras Ágiles con el mismo motor y la misma persistencia que las licitaciones.

Las evaluaciones viven en LicitacionesFiltradas con modalidad 'compra_agil'. compra_agil.preseleccion
recuerda qué firma y versión del motor se guardaron, para reintentar lo pendiente en cada lote.
"""
import asyncio
import hashlib
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
from .preseleccion import (
    CHILE, VERSION_MOTOR, cargar_catalogo, clasificar_pilares,
    descripcion_producto_ajeno, evaluar_preseleccion,
)

MODALIDAD = "compra_agil"
# Reglas propias sobre el motor común: cambiarlas reevalúa solo las Compras Ágiles,
# sin tocar las evaluaciones ni las revisiones manuales de las licitaciones.
VERSION_REGLAS = "ca-2"
PRODUCTOS_AJENOS_COMPRA_AGIL = {
    "80141605": "regalos publicitarios",
    "80141611": "personalización de productos promocionales",
    "82121505": "impresión promocional o publicitaria",
    "82121511": "impresión de manuales y catálogos",
    "82121903": "encuadernación",
}
# guardar admite 20 entradas por llamada.
TAMANO_GUARDADO = 20
LIMITE_POR_LOTE = 100
COLUMNAS = (
    "id", "codigo_externo", "raw_id", "nombre", "descripcion", "estado", "fecha_publicacion", "fecha_cierre",
    "moneda", "nombre_organismo", "nombre_unidad", "codigo_region", "region_comprador", "direccion_entrega",
    "fechas_fuente", "condiciones_fuente", "normalizacion_version",
)


def version_preseleccion() -> str:
    return f"{VERSION_MOTOR}|{VERSION_REGLAS}|{cargar_catalogo()['version']}"


def evaluar(datos: dict, *, ahora: datetime | None = None) -> dict:
    """Evalúa ficha e ítems; la región del comprador no confirma el lugar del servicio."""
    resultado = evaluar_preseleccion({**datos, "documentos": []}, ahora=ahora)
    ubicacion = resultado["criterios"]["ubicacion"]
    region = datos.get("codigo_region")
    ubicacion["comprador"] = {"codigo_region": region, "region": datos.get("region_comprador"),
        "uso": "Referencia administrativa; no confirma dónde se prestará el servicio."}
    pertinencia = resultado["criterios"]["pertinencia"]
    items = datos.get("items") or []
    # Una capacitación para usar un equipo o la palabra taller en una compra de
    # materiales no contratan un salón. Una línea hotelera concreta o desconocida
    # siempre impide excluir el paquete completo por sus otros productos.
    if (not resultado["entrada_parcial"] and not pertinencia["directa"] and isinstance(items, list) and items
            and all(descripcion_producto_ajeno(i, PRODUCTOS_AJENOS_COMPRA_AGIL) for i in items)):
        evidencias = [{"codigo": "producto_ajeno", "fuente": f"items[{n}].codigo_producto",
            "motivo": "Las líneas publicadas corresponden a " + descripcion_producto_ajeno(i, PRODUCTOS_AJENOS_COMPRA_AGIL)
                + "; no se identifica contratación de servicios del hotel.",
            "evidencia": f"{i['codigo_producto']}: {i.get('nombre_producto') or i.get('descripcion') or ''}"}
            for n, i in enumerate(items[:10])]
        pertinencia.update(resultado="no_cumple", motivo=evidencias[0]["motivo"],
                           exclusiones_evidentes=evidencias)
    clasificacion, motivo, pilar = clasificar_pilares(resultado["criterios"])
    resultado.update(
        clasificacion=clasificacion, motivo=motivo, pilar_decisivo=pilar,
        version_motor=f"{VERSION_MOTOR}+{VERSION_REGLAS}",
        huella_entrada=hashlib.sha256(json.dumps(
            [resultado["huella_entrada"], VERSION_REGLAS, region], ensure_ascii=False).encode()).hexdigest(),
    )
    return resultado


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
    return or_(CompraAgil.preseleccion.is_(None), CompraAgil.preseleccion["version"].astext.is_(None),
               CompraAgil.preseleccion["version"].astext != version)


def contar_pendientes(db: Session) -> int:
    ahora = datetime.now(CHILE).replace(tzinfo=None)
    return db.scalar(select(func.count()).select_from(CompraAgil).where(
        _sin_evaluacion_vigente(version_preseleccion()),
        or_(CompraAgil.fecha_cierre.is_(None), CompraAgil.fecha_cierre > ahora),
    ))


def pendientes(db: Session, limite: int = LIMITE_POR_LOTE) -> list[int]:
    """Abiertas sin evaluación guardada, o evaluadas con otra versión del motor o del catálogo."""
    ahora = datetime.now(CHILE).replace(tzinfo=None)
    return list(db.scalars(select(CompraAgil.id).where(
        _sin_evaluacion_vigente(version_preseleccion()),
        or_(CompraAgil.fecha_cierre.is_(None), CompraAgil.fecha_cierre > ahora),
    ).order_by(CompraAgil.fecha_publicacion.desc().nullslast(), CompraAgil.id).limit(limite)))


async def evaluar_compras_agiles(db: Session, ids=None, actor=None, limite: int = LIMITE_POR_LOTE) -> dict:
    """Evalúa y guarda en filtradas. FiltradasNoDisponible deja las compras pendientes."""
    ids = list(dict.fromkeys(ids)) if ids is not None else await plan_pendientes(db, limite)
    entradas = cargar_entradas(db, ids)
    if not entradas:
        return {"evaluadas": [], "pendientes": 0}
    version = version_preseleccion()
    lote = []
    for datos in entradas.values():
        lote.append({"datos": datos, "resultado": evaluar(datos),
                     "hash_fuente": firma(datos), "documentos_version": []})
    semaforo = asyncio.Semaphore(2)

    async def guardar(parte):
        async with semaforo:
            return parte, await filtradas.operar("guardar", {"lote": parte, "perfil": cargar_catalogo(), "actor": actor})
    partes = [lote[i:i + TAMANO_GUARDADO] for i in range(0, len(lote), TAMANO_GUARDADO)]
    tareas = [asyncio.create_task(guardar(parte)) for parte in partes]
    evaluadas, errores = [], []
    try:
        for siguiente in asyncio.as_completed(tareas):
            try:
                parte, respuesta = await siguiente
            except (filtradas.FiltradasNoDisponible, HTTPException) as exc:
                errores.append(exc)
                continue
            evaluadas += _registrar(db, parte, respuesta, version)
            # Se confirma cada grupo: si el turno se corta, lo guardado en filtradas no se repite.
            db.commit()
    finally:
        for tarea in tareas:
            tarea.cancel()
        await asyncio.gather(*tareas, return_exceptions=True)
    if errores and not evaluadas:
        raise errores[0]
    return {"evaluadas": evaluadas, "pendientes": contar_pendientes(db), "sin_guardar": len(lote) - len(evaluadas),
            "sincronizada": bool(evaluadas) and await _sincronizar(db)}


async def plan_pendientes(db: Session, limite: int = LIMITE_POR_LOTE) -> list[int]:
    """Reconcilia también evaluaciones que filtradas invalidó al cambiar el perfil.

    La marca local puede seguir al día aunque el perfil activo de filtradas haya
    cambiado desde otra modalidad. Leer el estado remoto evita dejarlas ocultas.
    """
    locales = pendientes(db, limite)
    if locales:
        return locales
    ahora = datetime.now(CHILE).replace(tzinfo=None)
    filas = db.execute(select(CompraAgil.id, CompraAgil.codigo_externo, CompraAgil.raw_id).where(
        or_(CompraAgil.fecha_cierre.is_(None), CompraAgil.fecha_cierre > ahora),
    ).order_by(CompraAgil.id)).all()
    fuentes = {f.codigo_externo: f.raw_id for f in filas}
    por_codigo = {f.codigo_externo: f.id for f in filas}
    sin_vigencia = []
    for offset in range(0, len(filas), 100):
        pagina = filas[offset:offset + 100]
        codigos = [f.codigo_externo for f in pagina]
        guardadas = await filtradas.operar("listar", {"codigos": codigos,
            "fuentes": {c: fuentes[c] for c in codigos}, "limite": 100, "offset": 0})
        vigentes = {f["codigo_externo"] for f in guardadas.get("filas", [])
                    if f.get("estado_seleccion") != "pendiente_evaluacion"}
        sin_vigencia.extend(por_codigo[c] for c in codigos if c not in vigentes)
        if len(sin_vigencia) >= limite:
            break
    return sin_vigencia[:limite]


def _registrar(db: Session, parte: list[dict], respuesta: dict, version: str) -> list[dict]:
    """Anota en Core las compras que filtradas aceptó; sin commit."""
    guardadas = {e["codigo"]: e["evaluacion_id"] for e in respuesta.get("evaluadas", [])}
    evaluadas = []
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
    return evaluadas


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
