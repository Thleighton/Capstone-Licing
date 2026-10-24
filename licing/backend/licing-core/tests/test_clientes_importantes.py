import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import Response

from app.api import preseleccion
from app.api.consultas import LicitacionResumen
from app.services import filtradas
from app.services.clientes_importantes import identificar_clientes_importantes, listar_clientes_importantes
from app.services.preseleccion import CHILE, evaluar_preseleccion


@pytest.mark.parametrize("nombre,cliente", [
    ("Ministerio de Educación", "mineduc"), ("SUBSECRETARIA DE EDUCACION", "mineduc"),
    ("Subsecretaría de Educación Superior", "mineduc"), ("Subsecretaría de Educación Parvularia", "mineduc"),
    ("Ministerio de Salud", "minsal"), ("Subsecretaría de Salud Pública", "minsal"),
    ("SUBSECRETARIA DE REDES ASISTENCIALES", "minsal"),
    ("Universidad de Chile - Facultad de Ciencias Veterinarias y Pecuarias", "uchile"),
    ("UNIVERSIDAD DE CHILE FACULTAD DE MEDICINA", "uchile"),
    ("Universidad de Chile, Facultad de Ciencias Químicas y Farmacéuticas", "uchile"),
    ("JUNJI DIRECCION REGIONAL METROPOLITANA", "junji"),
    ("Junta Nacional de Jardines Infantiles", "junji"),
    ("JUNAEB", "junaeb"), ("Junta Nacional de Auxilio Escolar y Becas", "junaeb"),
    ("Ministerio de Justicia", "justicia"), ("Ministerio de Justicia y Derechos Humanos", "justicia"),
])
def test_reconoce_los_organismos_y_sus_unidades(nombre, cliente):
    assert [c["id"] for c in identificar_clientes_importantes({"nombre_organismo": nombre})] == [cliente]


def test_identifica_por_unidad_compradora_y_no_duplica_al_organismo():
    r = identificar_clientes_importantes({"nombre_organismo": "Universidad de Chile",
        "nombre_unidad": "Universidad de Chile Facultad de Medicina"})
    assert len(r) == 1
    assert identificar_clientes_importantes({"nombre_unidad": "JUNJI"})[0]["id"] == "junji"


@pytest.mark.parametrize("datos", [
    {"nombre_organismo": "Universidad Católica de Chile"},
    {"nombre_organismo": "Universidad de Santiago de Chile"},
    {"nombre_organismo": "Otro comprador", "descripcion": "Servicios para JUNJI y Mineduc"},
    {"nombre_organismo": "Otro comprador", "nombre": "Congreso de la Universidad de Chile"},
    {"nombre_organismo": "Facultad de Medicina"}, {"nombre_organismo": None, "nombre_unidad": 12},
])
def test_no_atribuye_importancia_por_otras_universidades_o_por_el_objeto(datos):
    assert identificar_clientes_importantes(datos) == []


@pytest.mark.parametrize("cambios", [{}, {"nombre": "Alojamiento en Valparaíso"},
    {"nombre": "Compra de computadores"}, {"fecha_cierre": "2020-01-01"}])
def test_la_importancia_comercial_no_modifica_la_clasificacion(cambios):
    datos = {"codigo_externo": "100-1-LE26", "estado": "Publicada", "codigo_estado": 5,
        "fecha_cierre": "2026-12-01T12:00:00", "nombre": "Alojamiento en Santiago", **cambios}
    ahora = datetime(2026, 10, 24, 12, tzinfo=CHILE)
    normal = evaluar_preseleccion(datos, ahora=ahora)
    importante = evaluar_preseleccion({**datos, "nombre_organismo": "JUNJI"}, ahora=ahora)
    assert normal["clasificacion"] == importante["clasificacion"]
    assert normal["criterios"] == importante["criterios"]
    assert importante["cliente_estrategico"][0]["id"] == "junji"


def test_catalogo_autenticado_expone_los_seis_clientes_y_su_alcance(client_usuario):
    r = client_usuario.get("/api/clientes")
    assert r.status_code == 200
    assert {c["id"] for c in r.json()["clientes"]} == {"mineduc", "minsal", "uchile", "junji", "junaeb", "justicia"}
    assert all(c["alcance"] for c in r.json()["clientes"])
    assert "patron" not in r.text


def test_listado_y_detalle_de_licitaciones_incluyen_distintivo_actual():
    datos = dict.fromkeys(LicitacionResumen.model_fields)
    datos.update(id=1, codigo_externo="100-1-LE26", nombre_organismo="Subsecretaría de Salud Pública")
    r = LicitacionResumen(**datos).model_dump()
    assert r["clientes_importantes"][0]["id"] == "minsal"


def test_enriquece_revision_guardada_sin_reevaluar_o_escribir(monkeypatch):
    datos = {"id": 1, "codigo_externo": "100-1-LE26", "raw_id": 25, "nombre_organismo": "JUNJI", "nombre_unidad": "Departamento de Compras"}
    fila = {"id": 1, "codigo_externo": datos["codigo_externo"], "fuente_raw_id": 25,
        "hash_fuente": preseleccion.firma_fuente(datos), "estado_seleccion": "revision_manual"}
    db = MagicMock()
    db.execute.side_effect = [MagicMock(all=lambda: [(datos["codigo_externo"], 25)]), MagicMock(all=lambda: [(1, 25)])]
    db.scalars.return_value = [1]
    monkeypatch.setattr(preseleccion, "cargar_entradas", lambda db, ids: {"1": datos})
    operar = AsyncMock(return_value={"filas": [fila], "total": 1})
    monkeypatch.setattr(filtradas, "operar", operar)
    r = asyncio.run(preseleccion.listar(Response(), clasificacion="revision_manual", q="", limite=25, offset=0, db=db))
    assert r["filas"][0]["clientes_importantes"][0]["id"] == "junji"
    assert r["filas"][0]["estado_seleccion"] == "revision_manual"
    assert r["filas"][0]["nombre_organismo"] == "JUNJI"
    assert r["filas"][0]["nombre_unidad"] == "Departamento de Compras"
    assert [call.args[0] for call in operar.call_args_list] == ["listar"]
    db.commit.assert_not_called()


def test_la_lista_publica_no_muta_el_catalogo_compartido():
    clientes = listar_clientes_importantes()
    clientes[0]["nombre"] = "Cambiado"
    assert listar_clientes_importantes()[0]["nombre"] == "Ministerio de Educación"
