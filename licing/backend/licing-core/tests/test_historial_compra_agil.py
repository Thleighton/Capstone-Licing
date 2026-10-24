from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from unittest.mock import AsyncMock, create_autospec

from app.api import ingesta
from app.database import engine, get_db
from app.main import app
from app.models.ejecucion_compra_agil import EjecucionCompraAgil


URL_HISTORIAL = "/ingesta/compra-agil/lote/ejecuciones"


@pytest.fixture
def entorno_historial_compra_agil():
    with engine.connect() as conexion:
        transaccion = conexion.begin()

        db = Session(
            bind=conexion,
            join_transaction_mode="create_savepoint",
        )

        overrides_anteriores = app.dependency_overrides.copy()

        def reemplazar_db():
            yield db

        app.dependency_overrides[get_db] = reemplazar_db

        def crear_ejecucion(**valores):
            datos = {
                "paginas_solicitadas": 1,
                "maximo_detalles": 1,
                "estado": "completada",
            }
            datos.update(valores)

            ejecucion = EjecucionCompraAgil(**datos)
            db.add(ejecucion)
            db.commit()
            db.refresh(ejecucion)

            return ejecucion

        try:
            with TestClient(app) as client:
                yield {
                    "db": db,
                    "client": client,
                    "crear": crear_ejecucion,
                }
        finally:
            app.dependency_overrides.clear()
            app.dependency_overrides.update(overrides_anteriores)
            db.close()
            transaccion.rollback()


def test_listado_incluye_ejecucion_creada(
    entorno_historial_compra_agil,
):
    entorno = entorno_historial_compra_agil
    client = entorno["client"]

    antes = client.get(URL_HISTORIAL)
    assert antes.status_code == 200, antes.text
    total_anterior = antes.json()["total"]

    ejecucion = entorno["crear"]()

    respuesta = client.get(
        URL_HISTORIAL,
        params={
            "limite": 1,
            "desplazamiento": total_anterior,
        },
    )

    assert respuesta.status_code == 200, respuesta.text

    datos = respuesta.json()
    assert datos["total"] == total_anterior + 1
    assert datos["limite"] == 1
    assert datos["desplazamiento"] == total_anterior
    assert len(datos["items"]) == 1

    detalle = client.get(f"{URL_HISTORIAL}/{ejecucion.id}")
    assert detalle.status_code == 200, detalle.text
    assert detalle.json()["id"] == ejecucion.id

    assert "resultados" not in datos["items"][0]
    assert "errores" not in datos["items"][0]


def test_filtra_por_estado(entorno_historial_compra_agil):
    entorno = entorno_historial_compra_agil
    client = entorno["client"]

    antes = client.get(
        URL_HISTORIAL,
        params={"estado": "error"},
    )
    assert antes.status_code == 200, antes.text
    total_anterior = antes.json()["total"]

    entorno["crear"](estado="completada")
    entorno["crear"](estado="error")

    respuesta = client.get(
        URL_HISTORIAL,
        params={"estado": "error"},
    )

    assert respuesta.status_code == 200, respuesta.text

    datos = respuesta.json()
    assert datos["total"] == total_anterior + 1
    assert all(
        item["estado"] == "error"
        for item in datos["items"]
    )


def test_pagina_y_ordena_ejecuciones(
    entorno_historial_compra_agil,
):
    entorno = entorno_historial_compra_agil
    db = entorno["db"]
    client = entorno["client"]

    ultima = (
        db.query(EjecucionCompraAgil)
        .order_by(EjecucionCompraAgil.inicio.desc())
        .first()
    )

    base = datetime.now(timezone.utc)

    if ultima is not None:
        base = max(base, ultima.inicio)

    primera = entorno["crear"](
        inicio=base + timedelta(seconds=1),
    )
    segunda = entorno["crear"](
        inicio=base + timedelta(seconds=2),
    )

    respuesta = client.get(
        URL_HISTORIAL,
        params={"limite": 1, "desplazamiento": 0},
    )
    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["items"][0]["id"] == segunda.id

    respuesta = client.get(
        URL_HISTORIAL,
        params={"limite": 1, "desplazamiento": 1},
    )
    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["items"][0]["id"] == primera.id


def test_detalle_incluye_resultados_y_errores(
    entorno_historial_compra_agil,
):
    entorno = entorno_historial_compra_agil

    errores = [
        {
            "tipo": "http_status",
            "http_status": 429,
            "mensaje": "Lote detenido.",
        }
    ]

    ejecucion = entorno["crear"](
        estado="error",
        detenido_por_error_api=True,
        detenido_por_429=True,
        errores=errores,
    )

    respuesta = entorno["client"].get(
        f"{URL_HISTORIAL}/{ejecucion.id}"
    )

    assert respuesta.status_code == 200, respuesta.text

    datos = respuesta.json()
    assert datos["id"] == ejecucion.id
    assert datos["estado"] == "error"
    assert datos["detenido_por_429"] is True
    assert datos["errores"] == errores
    assert datos["resultados"] == []
    assert datos["listados_raw_ids"] == []


def test_detalle_inexistente_devuelve_404(
    entorno_historial_compra_agil,
):
    entorno = entorno_historial_compra_agil
    db = entorno["db"]

    ultima = (
        db.query(EjecucionCompraAgil)
        .order_by(EjecucionCompraAgil.id.desc())
        .first()
    )

    id_inexistente = 1 if ultima is None else ultima.id + 1

    respuesta = entorno["client"].get(
        f"{URL_HISTORIAL}/{id_inexistente}"
    )

    assert respuesta.status_code == 404


@pytest.mark.parametrize(
    "parametros",
    [
        {"estado": "desconocido"},
        {"limite": 0},
        {"limite": 101},
        {"desplazamiento": -1},
    ],
)
def test_rechaza_filtros_invalidos(
    entorno_historial_compra_agil,
    parametros,
):
    respuesta = entorno_historial_compra_agil["client"].get(
        URL_HISTORIAL,
        params=parametros,
    )

    assert respuesta.status_code == 422

def test_endpoint_ejecutar_respeta_firma_del_servicio(
    entorno_historial_compra_agil,
    monkeypatch,
):
    entorno = entorno_historial_compra_agil

    servicio = create_autospec(
        ingesta.ejecutar_lote_compra_agil,
        spec_set=True,
    )
    servicio.return_value = {
        "ejecucion_id": 123,
        "detalles_procesados": 0,
        "errores": [],
    }

    cliente = AsyncMock(spec=ingesta.CompraAgilClient)

    monkeypatch.setattr(
        ingesta,
        "ejecutar_lote_compra_agil",
        servicio,
    )
    monkeypatch.setattr(
        ingesta,
        "CompraAgilClient",
        lambda: cliente,
    )

    respuesta = entorno["client"].post(
        "/ingesta/compra-agil/lote/ejecutar",
        params={
            "paginas": 1,
            "maximo_detalles": 1,
            "pausa_entre_detalles": 5,
            "tamano_pagina": 10,
        },
    )

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["ejecucion_id"] == 123

    servicio.assert_awaited_once_with(
        db=entorno["db"],
        client=cliente,
        paginas=1,
        maximo_detalles=1,
        pausa_entre_detalles=5,
        region=None,
        tamano_pagina=10,
    )

    cliente.cerrar.assert_awaited_once()