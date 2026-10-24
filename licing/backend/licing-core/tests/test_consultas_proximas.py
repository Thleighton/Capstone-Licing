"""Los plazos del dashboard solo proceden de selecciones vigentes del hotel."""
import asyncio
import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import Response

from app.api import consultas
from app.api.preseleccion import firma_fuente
from app.services import filtradas


def preparar(monkeypatch, estados):
    candidatas = [SimpleNamespace(id=n, codigo_externo=f"TEST-{n}", raw_id=n + 100)
        for n in range(1, len(estados) + 1)]
    entradas = {str(f.id): vars(f) for f in candidatas}
    monkeypatch.setattr(consultas, "cargar_entradas", lambda db, ids: entradas)
    filas = [{"id": f.id, "codigo_externo": f.codigo_externo, "fuente_raw_id": f.raw_id,
        "hash_fuente": firma_fuente(entradas[str(f.id)]), "estado_seleccion": estado}
        for f, estado in zip(candidatas, estados)]
    return candidatas, filas


def ejecutar(candidatas):
    return asyncio.run(consultas._proximas_filtradas(None, candidatas))


def test_solo_incluye_posibles_y_revisiones_conservando_el_orden_de_cierre(monkeypatch):
    candidatas, filas = preparar(monkeypatch, ["descartada", "revision_manual", "pendiente_evaluacion",
        "preseleccionada", "estado_desconocido"])
    monkeypatch.setattr(filtradas, "operar", AsyncMock(return_value={"filas": list(reversed(filas))}))
    proximas, disponible = ejecutar(candidatas)
    assert disponible
    assert [(f.id, estado) for f, estado in proximas] == [(2, "revision_manual"), (4, "preseleccionada")]


def test_incluye_todas_las_elegibles_sin_limite_de_cuatro_y_consulta_todas_las_paginas(monkeypatch):
    candidatas, filas = preparar(monkeypatch, ["descartada"] * 100 + ["revision_manual"] * 7)
    operar = AsyncMock(side_effect=[{"filas": filas[:100]}, {"filas": filas[100:]}])
    monkeypatch.setattr(filtradas, "operar", operar)
    proximas, disponible = ejecutar(candidatas)
    assert disponible
    assert [f.id for f, _ in proximas] == list(range(101, 108))
    assert [call.args[1]["offset"] for call in operar.call_args_list] == [0, 100]


@pytest.mark.parametrize("cambio", [{"hash_fuente": "version_anterior"}, {"fuente_raw_id": 999},
    {"codigo_externo": "OTRA"}, {"hash_fuente": None}])
def test_no_muestra_evaluaciones_de_otras_reglas_o_fuentes(monkeypatch, cambio):
    candidatas, filas = preparar(monkeypatch, ["preseleccionada", "revision_manual"])
    filas[0].update(cambio)
    monkeypatch.setattr(filtradas, "operar", AsyncMock(return_value={"filas": filas}))
    proximas, disponible = ejecutar(candidatas)
    assert disponible
    assert [f.id for f, _ in proximas] == [2]


def test_si_filtradas_falla_no_reemplaza_por_licitaciones_generales(monkeypatch):
    candidatas, _ = preparar(monkeypatch, ["preseleccionada"])
    monkeypatch.setattr(filtradas, "operar", AsyncMock(side_effect=filtradas.FiltradasNoDisponible("Sin conexión")))
    assert ejecutar(candidatas) == ([], False)


def test_si_no_hay_evaluaciones_no_inventa_candidatas(monkeypatch):
    candidatas, _ = preparar(monkeypatch, ["preseleccionada"])
    monkeypatch.setattr(filtradas, "operar", AsyncMock(return_value={"filas": []}))
    assert ejecutar(candidatas) == ([], True)


def test_sin_cierres_abiertos_no_consulta_filtradas(monkeypatch):
    operar = AsyncMock()
    monkeypatch.setattr(filtradas, "operar", operar)
    assert ejecutar([]) == ([], True)
    operar.assert_not_called()


def test_carga_fuentes_solo_para_oportunidades_y_revisiones(monkeypatch):
    candidatas, filas = preparar(monkeypatch, ["descartada"] * 100 + ["preseleccionada", "revision_manual"])
    consultas_fuente = []
    def cargar(db, ids):
        consultas_fuente.append(set(ids))
        return {str(f.id): vars(f) for f in candidatas if f.id in ids}
    monkeypatch.setattr(consultas, "cargar_entradas", cargar)
    monkeypatch.setattr(filtradas, "operar", AsyncMock(side_effect=[{"filas": filas[:100]}, {"filas": filas[100:]}]))
    proximas, disponible = ejecutar(candidatas)
    assert disponible
    assert consultas_fuente == [{101, 102}]
    assert [f.id for f, _ in proximas] == [101, 102]


def test_no_carga_items_si_todas_estan_descartadas(monkeypatch):
    candidatas, filas = preparar(monkeypatch, ["descartada"] * 10)
    def no_cargar(*args):
        pytest.fail("No hay selecciones para las que cargar ítems o documentos")
    monkeypatch.setattr(consultas, "cargar_entradas", no_cargar)
    monkeypatch.setattr(filtradas, "operar", AsyncMock(return_value={"filas": filas}))
    assert ejecutar(candidatas) == ([], True)


def test_sql_del_resumen_no_ocupa_el_hilo_del_bucle_async(monkeypatch):
    hilo = threading.get_ident()
    def resumen(db, ahora):
        assert threading.get_ident() != hilo
        return {"total": 0}, []
    monkeypatch.setattr(consultas, "_resumen_dashboard", resumen)
    response = Response()
    resultado = asyncio.run(consultas.dashboard(response, None))
    assert resultado == {"total": 0, "proximas": [], "proximas_disponibles": True}
    assert response.headers["Cache-Control"] == "no-store"
