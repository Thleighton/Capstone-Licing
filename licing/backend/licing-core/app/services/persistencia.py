from datetime import datetime, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session
from sqlalchemy import delete
from ..models.licitacion import Licitacion
from ..models.licitacion_item import LicitacionItem


def convertir_fecha(valor):
    if not valor:
        return None

    fecha = datetime.fromisoformat(valor)

    # Convertir a hora chilena antes de guardar en las columnas locales.
    if fecha.tzinfo is not None:
        fecha = fecha.astimezone(ZoneInfo("America/Santiago")).replace(tzinfo=None)

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
    ubicacion = datos.get("ubicacion_servicio")

    valores = {
        "codigo_externo": codigo,
        "raw_id": raw_id,
        "ubicacion_servicio": {**ubicacion, "raw_id": raw_id} if ubicacion else None,
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
        **{k: datos.get(k) for k in (
            "tipo", "codigo_tipo", "estimacion", "visibilidad_monto", "justificacion_monto",
            "direccion_comprador", "direccion_entrega", "direccion_visita", "fechas_fuente",
            "condiciones_fuente", "normalizacion_version",
        )},
        "normalizado_en": datetime.now(timezone.utc),
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
    posiciones_vistas = set()

    for posicion, item in enumerate(items, 1):
        correlativo = item.get("correlativo")

        if (
            not isinstance(correlativo, int)
            or isinstance(correlativo, bool)
            or correlativo < 1
        ):
            raise ValueError(
                "Cada ítem debe tener un correlativo entero positivo."
            )

        if item.get("posicion_fuente", posicion) != posicion:
            raise ValueError("La posición del ítem no coincide con el orden del RAW.")
        posiciones_vistas.add(posicion)

        cantidad = item.get("cantidad")

        valores = {
            "licitacion_id": licitacion_id,
            "correlativo": correlativo,
            "posicion_fuente": posicion,
            "codigo_producto": item.get("codigo_producto"),
            "nombre_producto": item.get("nombre_producto"),
            "descripcion": item.get("descripcion"),
            "cantidad": (
                Decimal(str(cantidad)) if cantidad is not None else None
            ),
            "unidad_medida": item.get("unidad_medida"),
            "codigo_categoria": item.get("codigo_categoria"),
            "categoria": item.get("categoria"),
            "estado_fuente": item.get("estado_fuente"),
            "adjudicacion_fuente": item.get("adjudicacion_fuente"),
        }

        sentencia = insert(LicitacionItem).values(**valores)

        sentencia = sentencia.on_conflict_do_update(
            constraint="uq_licitacion_item_posicion",
            set_={
                campo: sentencia.excluded[campo]
                for campo in valores
                if campo not in {"licitacion_id", "posicion_fuente"}
            },
        )

        db.execute(sentencia)
    borrar_ausentes = delete(LicitacionItem).where(
        LicitacionItem.licitacion_id == licitacion_id
    )

    if posiciones_vistas:
        borrar_ausentes = borrar_ausentes.where(
            LicitacionItem.posicion_fuente.not_in(
                sorted(posiciones_vistas)
            )
        )

    db.execute(borrar_ausentes)

    return len(items)

