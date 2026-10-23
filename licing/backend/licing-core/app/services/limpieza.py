"""La base operativa conserva únicamente oportunidades disponibles."""
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import text

from .persistencia import convertir_fecha

CHILE = ZoneInfo("America/Santiago")
ESTADOS_NO_DISPONIBLES = {"6", "7", "8", "18", "19"}
NOMBRES_NO_DISPONIBLES = {"cerrada", "desierta", "adjudicada", "revocada", "suspendida"}


class LicitacionNoDisponible(ValueError):
    pass


def ausencia_confirmada(respuesta):
    return (isinstance(respuesta, dict) and respuesta.get("Listado") == []
            and type(respuesta.get("Cantidad")) is int and respuesta["Cantidad"] == 0
            and not any(k in respuesta for k in ("Codigo", "Mensaje", "Error", "error")))


def motivo_no_disponible(detalle, ahora=None):
    if not isinstance(detalle, dict):
        return None
    codigo = str(detalle.get("CodigoEstado", "")).strip()
    estado = str(detalle.get("Estado", "")).strip().lower()
    if codigo in ESTADOS_NO_DISPONIBLES or (
        codigo in {"", "None"} and estado in NOMBRES_NO_DISPONIBLES
    ):
        return "estado_no_disponible"
    fechas = detalle.get("Fechas")
    valor = fechas.get("FechaCierre") if isinstance(fechas, dict) else None
    valor = valor or detalle.get("FechaCierre")
    try:
        cierre = convertir_fecha(valor)
    except (TypeError, ValueError):
        return None
    referencia = (ahora or datetime.now(CHILE)).astimezone(CHILE).replace(tzinfo=None)
    if cierre is not None and cierre <= referencia:
        return "fecha_cierre"
    return None


def eliminar_no_disponibles(db, codigo=None, confirmada=False):
    """Sin commit: el llamador confirma la eliminación completa en una transacción."""
    return db.execute(text(
        "SELECT public.purgar_licitaciones_no_disponibles(:codigo, :confirmada)"
    ), {"codigo": codigo, "confirmada": confirmada}).scalar_one()
