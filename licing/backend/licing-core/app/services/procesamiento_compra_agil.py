from decimal import Decimal, InvalidOperation

from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from ..models.compra_agil import CompraAgil
from ..models.compra_agil_item import CompraAgilItem
from ..models.raw import RawMercadoPublico
from .normalizacion_compra_agil import normalizar_compra_agil


def _decimal_no_negativo(valor, campo: str) -> Decimal | None:
    if valor is None:
        return None

    if isinstance(valor, bool):
        raise ValueError(f"{campo} no admite valores booleanos.")

    try:
        numero = Decimal(str(valor))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{campo} debe ser numérico.") from exc

    if not numero.is_finite() or numero < 0:
        raise ValueError(f"{campo} debe ser finito y no negativo.")

    return numero


def procesar_compra_agil_guardada(
    db: Session,
    registro: RawMercadoPublico,
) -> dict:
    if (
        registro.fuente != "compra_agil"
        or registro.tipo_consulta != "compra_agil_detalle"
    ):
        raise ValueError("El registro no es un detalle de Compra Ágil.")

    respuesta = registro.respuesta

    if (
        not isinstance(respuesta, dict)
        or respuesta.get("success") != "OK"
        or not isinstance(respuesta.get("payload"), dict)
    ):
        raise ValueError("El crudo no contiene un detalle exitoso.")

    datos = normalizar_compra_agil(respuesta["payload"])

    if datos["codigo_externo"] != registro.codigo_externo:
        raise ValueError("El código del detalle no coincide con el crudo.")

    fechas = datos["fechas"]
    presupuesto = datos["presupuesto"]
    comprador = datos["comprador"]
    entrega = datos["entrega"]
    convocatoria = datos["convocatoria"]

    valores = {
        "codigo_externo": datos["codigo_externo"],
        "raw_id": registro.id,
        "nombre": datos["nombre"],
        "descripcion": datos["descripcion"],
        "estado": datos["estado"],
        "estado_glosa": datos["estado_glosa"],
        "codigo_estado": datos["codigo_estado"],
        "fecha_publicacion_original": fechas["fecha_publicacion"],
        "fecha_cierre_original": fechas["fecha_cierre"],
        "fecha_ultimo_cambio_original": fechas["fecha_ultimo_cambio"],
        "fecha_cancelacion_original": fechas["fecha_cancelacion"],
        "tipo_presupuesto": presupuesto["tipo"],
        "moneda": presupuesto["moneda"],
        "presupuesto_estimado": _decimal_no_negativo(
            presupuesto["estimado"], "presupuesto_estimado"
        ),
        "monto_disponible": _decimal_no_negativo(
            presupuesto["disponible"], "monto_disponible"
        ),
        "monto_disponible_clp": _decimal_no_negativo(
            presupuesto["disponible_clp"], "monto_disponible_clp"
        ),
        "rut_comprador": comprador["rut"],
        "nombre_organismo": comprador["nombre_organismo"],
        "nombre_unidad": comprador["nombre_unidad"],
        "codigo_region": comprador["codigo_region"],
        "region_comprador": comprador["region"],
        "direccion_entrega": entrega["direccion"],
        "plazo_entrega_dias": entrega["plazo_dias"],
        "numero_convocatoria": convocatoria["numero"],
        "fecha_cierre_primer_llamado_original": (
            convocatoria["fecha_cierre_primer_llamado"]
        ),
        "fecha_cierre_segundo_llamado_original": (
            convocatoria["fecha_cierre_segundo_llamado"]
        ),
        "id_orden_compra": datos["id_orden_compra"],
    }

    items = [
        {
            **item,
            "cantidad": _decimal_no_negativo(
                item["cantidad"],
                f"cantidad del ítem {item['posicion']}",
            ),
        }
        for item in datos["items"]
    ]

    sentencia = insert(CompraAgil).values(valores)

    sentencia = sentencia.on_conflict_do_update(
        index_elements=["codigo_externo"],
        set_={
            campo: sentencia.excluded[campo]
            for campo in valores
            if campo != "codigo_externo"
        },
    ).returning(CompraAgil.id)

    compra_agil_id = db.execute(sentencia).scalar_one()

    posiciones = []

    for item in items:
        valores_item = {
            "compra_agil_id": compra_agil_id,
            **item,
        }

        sentencia_item = insert(CompraAgilItem).values(valores_item)

        sentencia_item = sentencia_item.on_conflict_do_update(
            constraint="uq_compra_agil_item_posicion",
            set_={
                campo: sentencia_item.excluded[campo]
                for campo in valores_item
                if campo not in ("compra_agil_id", "posicion")
            },
        )

        db.execute(sentencia_item)
        posiciones.append(item["posicion"])

    borrar_ausentes = delete(CompraAgilItem).where(
        CompraAgilItem.compra_agil_id == compra_agil_id
    )

    if posiciones:
        borrar_ausentes = borrar_ausentes.where(
            CompraAgilItem.posicion.not_in(posiciones)
        )

    db.execute(borrar_ausentes)

    return {
        "compra_agil_id": compra_agil_id,
        "codigo_externo": datos["codigo_externo"],
        "raw_id": registro.id,
        "procesado": True,
        "items_procesados": len(items),
    }