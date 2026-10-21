from sqlalchemy.orm import Session

from ..models.raw import RawMercadoPublico
from .normalizacion import normalizar_licitacion
from .persistencia import guardar_licitacion, guardar_items


def procesar_detalle_guardado(
    db: Session,
    registro: RawMercadoPublico,
) -> dict:
    if registro.tipo_consulta != "detalle_codigo":
        raise ValueError("El registro no corresponde a un detalle.")

    datos = normalizar_licitacion(registro.respuesta)

    cantidad_declarada = datos["cantidad_items_declarada"]
    cantidad_observada = datos["cantidad_items_observada"]

    if (
        not isinstance(cantidad_declarada, int)
        or isinstance(cantidad_declarada, bool)
        or cantidad_declarada < 0
        or cantidad_declarada != cantidad_observada
    ):
        raise ValueError(
            "No se procesa el detalle: la cantidad de ítems "
            "declarada falta o no coincide con la lista recibida."
        )

    if datos["codigo_externo"] != registro.codigo_externo:
        raise ValueError(
            "El código del detalle no coincide con el registro crudo."
        )

    licitacion_id = guardar_licitacion(
        db=db,
        raw_id=registro.id,
        datos=datos,
    )

    items_procesados = guardar_items(
        db=db,
        licitacion_id=licitacion_id,
        items=datos["items"],
    )

    return {
        "licitacion_id": licitacion_id,
        "codigo_externo": datos["codigo_externo"],
        "raw_id": registro.id,
        "procesado": True,
        "items_procesados": items_procesados,
    }