from datetime import datetime
from decimal import Decimal

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session
from sqlalchemy import delete
from ..models.licitacion import Licitacion
from ..models.licitacion_item import LicitacionItem


def convertir_fecha(valor):
    if not valor:
        return None

    fecha = datetime.fromisoformat(valor)

    # Nuestra tabla conserva por ahora fechas sin zona horaria.
    # No eliminamos una zona silenciosamente si llega una.
    if fecha.tzinfo is not None:
        raise ValueError(
            "Se recibió una fecha con zona horaria; "
            "su conversión todavía no está definida."
        )

    return fecha

#upsert: si el código no existe, inserta; si ya existe, actualiza la misma fila.
def guardar_licitacion(
    db: Session,
    raw_id: int,
    datos: dict,
) -> int:
    codigo = datos.get("codigo_externo")

    if not codigo:
        raise ValueError("El detalle no contiene codigo_externo.")

    comprador = datos.get("comprador") or {}
    monto = datos.get("monto_estimado")

    valores = {
        "codigo_externo": codigo,
        "raw_id": raw_id,
        "nombre": datos.get("nombre"),
        "descripcion": datos.get("descripcion"),
        "codigo_estado": datos.get("codigo_estado"),
        "estado": datos.get("estado"),
        "monto_estimado": (
            Decimal(str(monto)) if monto is not None else None
        ),
        "moneda": datos.get("moneda"),
        "fecha_publicacion": convertir_fecha(
            datos.get("fecha_publicacion")
        ),
        "fecha_cierre": convertir_fecha(datos.get("fecha_cierre")),
        "codigo_organismo": comprador.get("codigo_organismo"),
        "nombre_organismo": comprador.get("nombre_organismo"),
        "codigo_unidad": comprador.get("codigo_unidad"),
        "nombre_unidad": comprador.get("nombre_unidad"),
        "region_comprador": comprador.get("region"),
        "comuna_comprador": comprador.get("comuna"),
    }

    sentencia = insert(Licitacion).values(**valores)

    sentencia = sentencia.on_conflict_do_update(
        index_elements=["codigo_externo"],
        set_={
            campo: sentencia.excluded[campo]
            for campo in valores
            if campo != "codigo_externo"
        },
    ).returning(Licitacion.id)

    return db.execute(sentencia).scalar_one()

def guardar_items(
    db: Session,
    licitacion_id: int,
    items: list[dict],
) -> int:
    correlativos_vistos = set()

    for item in items:
        correlativo = item.get("correlativo")

        if (
            not isinstance(correlativo, int)
            or isinstance(correlativo, bool)
            or correlativo < 1
        ):
            raise ValueError(
                "Cada ítem debe tener un correlativo entero positivo."
            )

        if correlativo in correlativos_vistos:
            raise ValueError(
                f"El detalle contiene el correlativo repetido: {correlativo}."
            )

        correlativos_vistos.add(correlativo)

        cantidad = item.get("cantidad")

        valores = {
            "licitacion_id": licitacion_id,
            "correlativo": correlativo,
            "codigo_producto": item.get("codigo_producto"),
            "nombre_producto": item.get("nombre_producto"),
            "descripcion": item.get("descripcion"),
            "cantidad": (
                Decimal(str(cantidad)) if cantidad is not None else None
            ),
            "unidad_medida": item.get("unidad_medida"),
        }

        sentencia = insert(LicitacionItem).values(**valores)

        sentencia = sentencia.on_conflict_do_update(
            constraint="uq_licitacion_item_correlativo",
            set_={
                campo: sentencia.excluded[campo]
                for campo in valores
                if campo not in {"licitacion_id", "correlativo"}
            },
        )

        db.execute(sentencia)
    borrar_ausentes = delete(LicitacionItem).where(
        LicitacionItem.licitacion_id == licitacion_id
    )

    if correlativos_vistos:
        borrar_ausentes = borrar_ausentes.where(
            LicitacionItem.correlativo.not_in(
                sorted(correlativos_vistos)
            )
        )

    db.execute(borrar_ausentes)

    return len(items)
