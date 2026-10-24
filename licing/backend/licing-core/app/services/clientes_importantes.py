"""Distinción comercial por comprador; no interviene en los tres pilares."""
from functools import cache
import json
from pathlib import Path
import re

from .ubicacion import _texto_busqueda


ALCANCES = {
    "mineduc": "Ministerio de Educación y todas sus subsecretarías.",
    "minsal": "Ministerio de Salud y todas sus subsecretarías.",
    "uchile": "Universidad de Chile y todas sus facultades.",
    "junji": "Junta Nacional de Jardines Infantiles (JUNJI).",
    "junaeb": "Junta Nacional de Auxilio Escolar y Becas (JUNAEB).",
    "justicia": "Ministerio de Justicia, incluida su denominación Ministerio de Justicia y Derechos Humanos.",
}


@cache
def _catalogo():
    ruta = Path(__file__).resolve().parents[1] / "data" / "preseleccion_hotel_v1.json"
    clientes = json.loads(ruta.read_text(encoding="utf-8"))["clientes_estrategicos"]
    return [({"id": c["id"], "nombre": c["nombre"], "alcance": ALCANCES[c["id"]]},
             re.compile(c["patron"])) for c in clientes]


def listar_clientes_importantes():
    return [dict(cliente) for cliente, _ in _catalogo()]


def identificar_clientes_importantes(datos):
    # Solo organismo y unidad compradora; mencionar al cliente en las bases no basta.
    nombres = [_texto_busqueda(datos[campo])[0] for campo in ("nombre_organismo", "nombre_unidad")
               if isinstance(datos.get(campo), str) and datos[campo].strip()]
    return [{**cliente, "confirmacion": "por_nombre"} for cliente, patron in _catalogo()
            if any(patron.search(nombre) for nombre in nombres)]
