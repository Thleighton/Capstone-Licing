"""Módulo Bases y documentos (E4 análisis de bases/TDR, E5 admisibilidad).
Responsable: Miguel Mancilla.

Hoy devuelve un resultado SIMULADO para que el frontend ya use el flujo real
(navegador -> API Python -> respuesta). Aquí se conectará el motor IA/NLP:
carga de PDF, extracción de servicios, fechas críticas y presupuesto máximo."""
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..core.auth import usuario_actual

router = APIRouter(prefix="/api/analisis", tags=["analisis"])

_EJEMPLOS = {
    "alojamiento": {
        "titulo": "Alojamiento de delegación",
        "servicio": "20 habitaciones por 3 noches",
        "participantes": "40 personas",
    },
    "seminario": {
        "titulo": "Seminario y coffee break",
        "servicio": "Salón, proyección y coffee break",
        "participantes": "80 personas",
    },
}


class PedidoSimulacion(BaseModel):
    ejemplo: Literal["alojamiento", "seminario"]


@router.post("/simular")
def simular(pedido: PedidoSimulacion, _usuario: dict = Depends(usuario_actual)):
    return {
        **_EJEMPLOS[pedido.ejemplo],
        "presupuesto": "Por confirmar en las bases",
        "documentos": "Oferta técnica, económica y antecedentes administrativos",
        "pendientes": "disponibilidad, fechas exactas y condiciones de pago.",
        "simulado": True,
    }
