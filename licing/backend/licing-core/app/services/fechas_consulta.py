"""Rangos inclusivos de cierre, en la hora local que conserva Core."""
from datetime import date, datetime, time

from fastapi import HTTPException


def filtrar_cierre(consulta, columna, desde: date | None, hasta: date | None):
    if desde and hasta and desde > hasta:
        raise HTTPException(422, "La fecha desde no puede ser posterior a la fecha hasta")
    if desde:
        consulta = consulta.where(columna >= datetime.combine(desde, time.min))
    if hasta:
        consulta = consulta.where(columna <= datetime.combine(hasta, time.max))
    return consulta
