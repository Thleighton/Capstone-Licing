"""Completa evidencia geográfica desde el RAW actual, sin HTTP ni cambios al origen."""
import json

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from .database import engine
from .models.licitacion import Licitacion
from .models.raw import RawMercadoPublico
from .services.ubicacion import extraer_ubicacion


def reprocesar_ubicaciones(db):
    ultimo_id, actualizadas, omitidas = 0, 0, 0
    while True:
        filas = db.execute(select(
            Licitacion.id, Licitacion.raw_id, Licitacion.ubicacion_servicio,
            RawMercadoPublico.respuesta,
        ).join(RawMercadoPublico, Licitacion.raw_id == RawMercadoPublico.id)
          .where(Licitacion.id > ultimo_id).order_by(Licitacion.id).limit(100)).all()
        if not filas:
            break
        for fila in filas:
            ultimo_id = fila.id
            evidencia = extraer_ubicacion(fila.respuesta, fila.raw_id)
            if evidencia == fila.ubicacion_servicio:
                omitidas += 1
                continue
            resultado = db.execute(update(Licitacion).where(
                Licitacion.id == fila.id, Licitacion.raw_id == fila.raw_id,
            ).values(ubicacion_servicio=evidencia).execution_options(synchronize_session=False))
            actualizadas += resultado.rowcount
        db.commit()
    return {"actualizadas": actualizadas, "sin_cambios": omitidas}


if __name__ == "__main__":
    with Session(engine) as db:
        print(json.dumps(reprocesar_ubicaciones(db), ensure_ascii=False))
