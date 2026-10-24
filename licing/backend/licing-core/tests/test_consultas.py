from datetime import datetime, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo
from unittest.mock import AsyncMock

import pytest

from app.models.ejecucion_ingesta import EjecucionIngesta
from app.models.licitacion import Licitacion
from app.models.licitacion_item import LicitacionItem
from app.models.raw import RawMercadoPublico


@pytest.fixture
def datos(integration_db, monkeypatch):
    db = integration_db
    ahora = datetime.now(ZoneInfo("America/Santiago")).replace(tzinfo=None)
    filas = []
    for n, estado in enumerate(["Publicada", "Publicada", "Adjudicada", "Publicada"]):
        codigo = f"TEST-CONSULTA-{n}"
        raw = RawMercadoPublico(fuente="licitaciones", tipo_consulta="detalle_codigo", codigo_externo=codigo,
                               respuesta={"CodigoExterno": codigo}, http_status=200, consultado_en=datetime.now(timezone.utc) - timedelta(days=2 if n == 0 else 0))
        db.add(raw)
        db.flush()
        fila = Licitacion(codigo_externo=codigo, raw_id=raw.id, nombre="Alojamiento" if n != 2 else "Seminario",
                          estado=estado, monto_estimado=None if n == 0 else Decimal("123.45"), moneda="USD",
                          fecha_publicacion=ahora - timedelta(days=n), fecha_cierre=ahora + timedelta(days=1 if n == 0 else -1 if n == 3 else 10),
                          nombre_organismo="Hotel test", nombre_unidad="Unidad test", region_comprador="Metropolitana" if n == 0 else "Los Lagos")
        db.add(fila)
        db.flush()
        filas.append(fila)
    db.add_all([
        LicitacionItem(licitacion_id=filas[0].id, correlativo=2, posicion_fuente=2, nombre_producto="Segundo", cantidad=2),
        LicitacionItem(licitacion_id=filas[0].id, correlativo=1, posicion_fuente=1, nombre_producto="Primero", cantidad=1),
        EjecucionIngesta(limite_detalles=1, estado="parcial", descargados=1, procesados=0, errores=[{"mensaje": "dato interno"}]),
    ])
    db.commit()
    from app.api.preseleccion import cargar_entradas, firma_fuente
    from app.services import filtradas
    entradas = cargar_entradas(db, [f.id for f in filas])
    selecciones = [{"id": f.id, "codigo_externo": f.codigo_externo, "fuente_raw_id": f.raw_id,
        "estado_seleccion": "preseleccionada" if n == 0 else "revision_manual",
        "hash_fuente": firma_fuente(entradas[str(f.id)])} for n, f in enumerate(filas)]
    monkeypatch.setattr(filtradas, "operar", AsyncMock(return_value={"filas": selecciones}))
    return filas


def test_listado_paginado_y_campos_de_core(client_usuario, datos):
    r = client_usuario.get("/api/licitaciones?limite=1&offset=1")
    assert r.status_code == 200, r.text
    listado = r.json()
    assert listado["total"] == 4 and len(listado["items"]) == 1
    assert listado["items"][0]["codigo_externo"] == datos[1].codigo_externo
    assert listado["items"][0]["moneda"] == "USD"
    assert listado["items"][0]["fecha_cierre"].endswith("-03:00") or listado["items"][0]["fecha_cierre"].endswith("-04:00")
    assert "descartada_filtro" not in listado["items"][0]


def test_busqueda_region_y_abiertas(client_usuario, datos):
    r = client_usuario.get("/api/licitaciones", params={"q": "ALOJAMIENTO", "region": "metropolitana", "solo_abiertas": True})
    assert r.json()["total"] == 1
    assert r.json()["items"][0]["monto_estimado"] is None
    assert client_usuario.get("/api/licitaciones?solo_abiertas=true").json()["total"] == 2
    assert client_usuario.get("/api/licitaciones?q=%25").json()["total"] == 0
    assert client_usuario.get("/api/licitaciones?offset=999").json()["items"] == []


def test_detalle_con_items_ordenados(client_usuario, datos):
    r = client_usuario.get(f"/api/licitaciones/{datos[0].id}")
    assert r.status_code == 200, r.text
    assert [i["correlativo"] for i in r.json()["items"]] == [1, 2]
    assert client_usuario.get("/api/licitaciones/999999999").status_code == 404


def test_dashboard_considera_toda_la_base_y_fechas(client_usuario, datos):
    r = client_usuario.get("/api/dashboard")
    assert r.status_code == 200, r.text
    resumen = r.json()
    assert resumen["total"] == 4
    assert resumen["abiertas"] == 2 and resumen["cierran_pronto"] == 1
    assert resumen["nuevas"] == 3
    assert len(resumen["publicaciones"]) == 7
    assert sum(d["cantidad"] for d in resumen["publicaciones"]) == 4
    assert sum(d["cantidad"] for d in resumen["estados"]) == 4
    assert [d["id"] for d in resumen["proximas"]] == [datos[0].id, datos[1].id]
    assert [d["estado_seleccion"] for d in resumen["proximas"]] == ["preseleccionada", "revision_manual"]
    assert resumen["proximas_disponibles"] is True


def test_historial_sin_datos_internos(client_usuario, datos):
    r = client_usuario.get("/api/ingestas")
    assert r.status_code == 200
    assert r.json()[0]["estado"] == "parcial"
    assert r.json()[0]["n_errores"] == 1
    assert "dato interno" not in r.text


def test_reprocesar_no_cuenta_como_nueva(client_usuario, datos, integration_db):
    raw = RawMercadoPublico(fuente="licitaciones", tipo_consulta="detalle_codigo",
                           codigo_externo=datos[0].codigo_externo, respuesta={}, http_status=200,
                           consultado_en=datetime.now(timezone.utc))
    integration_db.add(raw)
    integration_db.flush()
    datos[0].raw_id = raw.id
    integration_db.commit()
    assert client_usuario.get("/api/dashboard").json()["nuevas"] == 3


def test_base_vacia(client_usuario, integration_db):
    assert client_usuario.get("/api/licitaciones").json()["total"] == 0
    r = client_usuario.get("/api/dashboard")
    assert r.status_code == 200, r.text
    assert r.json()["total"] == 0 and r.json()["proximas"] == []


@pytest.mark.parametrize("query", ["limite=0", "limite=501", "offset=-1"])
def test_limites_de_paginacion(client_usuario, query):
    assert client_usuario.get("/api/licitaciones?" + query).status_code == 422
