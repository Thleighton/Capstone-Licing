"""Escritura de Compra Ágil: RAW, compra normalizada, ítems y limpieza. Sin commit."""
from datetime import datetime, timezone

from sqlalchemy import case, delete, func, null, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from ..models.compra_agil import CompraAgil
from ..models.compra_agil_item import CompraAgilItem
from ..models.raw import RawMercadoPublico
from .compra_agil_normalizacion import motivo_no_disponible, normalizar_compra_agil

FUENTE = "compra_agil"
# Distinto de detalle_codigo: las consultas de licitaciones nunca leen estos RAW.
TIPO_DETALLE = "detalle_compra_agil"
COLUMNAS = (
    "nombre", "descripcion", "id_estado", "estado", "estado_glosa", "estado_convocatoria",
    "fecha_publicacion", "fecha_cierre", "fecha_ultimo_cambio", "fecha_cancelacion",
    "moneda", "tipo_presupuesto", "presupuesto_estimado", "monto_disponible", "monto_disponible_clp",
    "rut_organismo", "nombre_organismo", "nombre_unidad", "codigo_region", "region_comprador",
    "direccion_entrega", "plazo_entrega_dias", "total_ofertas_recibidas", "id_orden_compra",
    "documentos", "fechas_fuente", "condiciones_fuente", "normalizacion_version",
)
COLUMNAS_ITEM = ("codigo_producto", "nombre_producto", "descripcion", "cantidad", "unidad_medida")


class CompraAgilNoDisponible(ValueError):
    pass


def eliminar_compras_no_disponibles(db: Session, codigos=None, confirmada=False) -> dict:
    """El llamador confirma la eliminación completa en una sola transacción."""
    return db.execute(text(
        "SELECT public.purgar_compras_agiles_no_disponibles(CAST(:codigos AS text[]), :confirmada)"
    ), {"codigos": list(codigos) if codigos is not None else None, "confirmada": confirmada}).scalar_one()


def guardar_raw(db: Session, codigo: str, detalle: dict) -> RawMercadoPublico:
    """Una respuesta idéntica solo actualiza la verificación, sin duplicar el JSON."""
    existente = db.scalars(select(RawMercadoPublico).where(
        RawMercadoPublico.fuente == FUENTE,
        RawMercadoPublico.tipo_consulta == TIPO_DETALLE,
        RawMercadoPublico.codigo_externo == codigo,
    ).order_by(RawMercadoPublico.id.desc()).limit(1)).first()
    if existente is not None and existente.respuesta == detalle:
        existente.verificado_en = datetime.now(timezone.utc)
        db.flush()
        return existente
    registro = RawMercadoPublico(
        fuente=FUENTE, tipo_consulta=TIPO_DETALLE, parametro_consulta=codigo,
        codigo_externo=codigo, respuesta=detalle, http_status=200, cantidad_resultados=1,
    )
    db.add(registro)
    db.flush()
    return registro


def guardar_compra_agil(db: Session, raw_id: int, datos: dict, cambio_sincronizado=None) -> int:
    valores = {
        "codigo_externo": datos["codigo_externo"],
        "raw_id": raw_id,
        **{campo: datos.get(campo) for campo in COLUMNAS},
        "normalizado_en": datetime.now(timezone.utc),
        "cambio_sincronizado": cambio_sincronizado or datos.get("fecha_ultimo_cambio"),
    }
    sentencia = insert(CompraAgil).values(**valores)
    actualizar = {campo: sentencia.excluded[campo] for campo in valores if campo != "codigo_externo"}
    # Un detalle descargado a mano no retrocede el cambio ya sincronizado desde el listado.
    actualizar["cambio_sincronizado"] = func.greatest(
        CompraAgil.cambio_sincronizado, sentencia.excluded.cambio_sincronizado,
    )
    # Una versión nueva del RAW invalida la preselección anterior; la misma la conserva.
    actualizar["preseleccion"] = case(
        (CompraAgil.raw_id == sentencia.excluded.raw_id, CompraAgil.preseleccion), else_=null(),
    )
    return db.execute(sentencia.on_conflict_do_update(
        index_elements=["codigo_externo"], set_=actualizar,
    ).returning(CompraAgil.id)).scalar_one()


def guardar_items(db: Session, compra_agil_id: int, items: list[dict]) -> int:
    posiciones = []
    for posicion, item in enumerate(items, 1):
        if item.get("posicion_fuente", posicion) != posicion:
            raise ValueError("La posición del producto no coincide con el orden del RAW.")
        posiciones.append(posicion)
    if items:
        sentencia = insert(CompraAgilItem).values([{
            "compra_agil_id": compra_agil_id, "posicion_fuente": posicion,
            **{campo: item.get(campo) for campo in COLUMNAS_ITEM},
        } for posicion, item in zip(posiciones, items)])
        db.execute(sentencia.on_conflict_do_update(
            constraint="uq_compra_agil_item_posicion",
            set_={campo: sentencia.excluded[campo] for campo in COLUMNAS_ITEM},
        ))
    borrar = delete(CompraAgilItem).where(CompraAgilItem.compra_agil_id == compra_agil_id)
    if posiciones:
        borrar = borrar.where(CompraAgilItem.posicion_fuente.not_in(posiciones))
    db.execute(borrar)
    return len(items)


def procesar_compra_guardada(db: Session, registro: RawMercadoPublico, cambio_sincronizado=None) -> dict:
    if registro.fuente != FUENTE or registro.tipo_consulta != TIPO_DETALLE:
        raise ValueError("El registro no corresponde a un detalle de Compra Ágil.")
    datos = normalizar_compra_agil(registro.respuesta)
    codigo = datos["codigo_externo"]
    if codigo != registro.codigo_externo:
        raise ValueError("El código del detalle no coincide con el registro crudo.")
    motivo = motivo_no_disponible(datos["estado"], datos["id_estado"], datos["fecha_cierre"])
    if motivo:
        eliminados = eliminar_compras_no_disponibles(db, [codigo], confirmada=True)
        return {"codigo_externo": codigo, "procesado": False, "eliminado": True, "motivo": motivo, **eliminados}
    compra_agil_id = guardar_compra_agil(db, registro.id, datos, cambio_sincronizado)
    return {
        "compra_agil_id": compra_agil_id,
        "codigo_externo": codigo,
        "raw_id": registro.id,
        "procesado": True,
        "items_procesados": guardar_items(db, compra_agil_id, datos["items"]),
    }
