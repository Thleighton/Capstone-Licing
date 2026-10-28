import asyncio
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, Mock
from zoneinfo import ZoneInfo

import pytest
from alembic import command
from sqlalchemy import inspect, text
from sqlalchemy.exc import DBAPIError

from app.adopcion import REVISION_ACTUAL, registrar_esquema, verificar_esquema
from app.api import cron, ingesta
from app.auth import usuario_actual
from app.config import settings
from app.database import get_db
from app.main import app
from app.models.compra_agil import CompraAgil
from app.models.compra_agil_item import CompraAgilItem
from app.models.raw import RawMercadoPublico
from app.services.ingesta_lote import EjecucionEnCursoError
from tests.conftest import USUARIO
from tests.test_retiro_documental import configuracion

CHILE = ZoneInfo("America/Santiago")
SECRETO = "secreto-de-prueba"


@pytest.fixture
def compras(integration_db):
    db = integration_db
    ahora = datetime.now(CHILE).replace(tzinfo=None)
    filas = []
    for n, (nombre, region, cierre) in enumerate([
        ("Alojamiento para seminario", "Región Metropolitana de Santiago", ahora + timedelta(days=2)),
        ("Coffee break", "Región de Valparaíso", ahora + timedelta(days=1)),
        ("Arriendo de salón", "Región Metropolitana de Santiago", ahora - timedelta(hours=1)),
    ]):
        codigo = f"9{n}-1-COT26"
        raw = RawMercadoPublico(fuente="compra_agil", tipo_consulta="detalle_compra_agil", codigo_externo=codigo,
                                respuesta={"codigo": codigo}, http_status=200)
        db.add(raw)
        db.flush()
        fila = CompraAgil(codigo_externo=codigo, raw_id=raw.id, nombre=nombre, estado="publicada",
                          fecha_publicacion=ahora - timedelta(days=n), fecha_cierre=cierre, moneda="CLP",
                          monto_disponible_clp=Decimal("150000"), nombre_organismo="Ministerio de Educación",
                          nombre_unidad="Subsecretaría", region_comprador=region, codigo_region=13 if n != 1 else 5)
        db.add(fila)
        db.flush()
        filas.append(fila)
    db.add_all([CompraAgilItem(compra_agil_id=filas[0].id, posicion_fuente=2, nombre_producto="Segundo"),
                CompraAgilItem(compra_agil_id=filas[0].id, posicion_fuente=1, nombre_producto="Primero")])
    db.commit()
    return filas


def test_listado_con_filtros_y_enlace_publico(client_usuario, compras):
    r = client_usuario.get("/api/compras-agiles")
    assert r.status_code == 200, r.text
    datos = r.json()
    assert datos["total"] == 3 and [i["codigo_externo"] for i in datos["items"]] == ["90-1-COT26", "91-1-COT26", "92-1-COT26"]
    primera = datos["items"][0]
    assert primera["url_oficial"] == "https://buscador.mercadopublico.cl/ficha?code=90-1-COT26"
    assert primera["fecha_cierre"].endswith(("-03:00", "-04:00"))
    assert primera["clientes_importantes"][0]["id"] == "mineduc"
    assert r.headers["cache-control"] == "no-store"
    r = client_usuario.get("/api/compras-agiles", params={"q": "SALÓN", "region": "metropolitana"})
    assert [i["codigo_externo"] for i in r.json()["items"]] == ["92-1-COT26"]
    r = client_usuario.get("/api/compras-agiles", params={"solo_abiertas": True, "limite": 1, "offset": 1})
    assert r.json()["total"] == 2 and r.json()["items"][0]["codigo_externo"] == "91-1-COT26"


def test_detalle_con_items_ordenados(client_usuario, compras):
    r = client_usuario.get(f"/api/compras-agiles/{compras[0].id}")
    assert r.status_code == 200, r.text
    assert [i["nombre_producto"] for i in r.json()["items"]] == ["Primero", "Segundo"]
    assert r.json()["compra_agil"]["fuente_consultada_en"]
    assert client_usuario.get("/api/compras-agiles/999999999").status_code == 404


def test_fechas_incluyen_dia_completo_y_conservan_total(client_usuario, compras, integration_db):
    compras[0].fecha_cierre = datetime(2099, 5, 10, 0, 0)
    compras[1].fecha_cierre = datetime(2099, 5, 10, 23, 59, 59, 999999)
    compras[2].fecha_cierre = datetime(2099, 5, 11, 0, 0)
    integration_db.commit()
    respuesta = client_usuario.get("/api/compras-agiles", params={
        "cierre_desde": "2099-05-10", "cierre_hasta": "2099-05-10", "limite": 1,
    })
    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["total"] == 2
    assert len(respuesta.json()["items"]) == 1


def test_preseleccion_filtra_fechas_antes_de_paginar(client_usuario, compras, integration_db, monkeypatch):
    from app.services import filtradas
    compras[0].fecha_cierre = datetime(2099, 5, 10, 23, 59, 59)
    compras[1].fecha_cierre = datetime(2099, 5, 11)
    compras[2].fecha_cierre = None
    integration_db.commit()
    operar = AsyncMock(return_value={"filas": [], "total": 0})
    monkeypatch.setattr(filtradas, "operar", operar)
    respuesta = client_usuario.get("/api/compras-agiles/preseleccion", params={
        "cierre_desde": "2099-05-10", "cierre_hasta": "2099-05-10", "limite": 1, "offset": 1,
    })
    assert respuesta.status_code == 200, respuesta.text
    datos = operar.call_args.args[1]
    assert datos["codigos"] == [compras[0].codigo_externo]
    assert datos["limite"] == 1 and datos["offset"] == 1


@pytest.mark.parametrize("ruta", ["/api/compras-agiles", "/api/compras-agiles/preseleccion"])
def test_rechaza_rango_invertido(client_usuario, compras, ruta):
    respuesta = client_usuario.get(ruta, params={"cierre_desde": "2099-05-11", "cierre_hasta": "2099-05-10"})
    assert respuesta.status_code == 422


def test_resumen_para_el_dashboard(client_usuario, compras, integration_db):
    from app.services.compra_agil_preseleccion import version_preseleccion
    vigente = {"version": version_preseleccion(), "firma": "x"}
    compras[0].preseleccion = {**vigente, "clasificacion": "preseleccionada"}
    # Cerrada: su propuesta no cuenta entre las oportunidades abiertas.
    compras[2].preseleccion = {**vigente, "clasificacion": "revision_manual"}
    integration_db.commit()
    r = client_usuario.get("/api/compras-agiles/resumen")
    assert r.status_code == 200, r.text
    datos = r.json()
    assert (datos["total"], datos["abiertas"], datos["cierran_pronto"], datos["nuevas"]) == (3, 2, 1, 3)
    assert datos["preseleccion"] == {"preseleccionada": 1, "revision_manual": 0, "descartada": 0, "pendientes": 1}
    assert datos["carga_inicial_completa"] is False
    assert r.headers["cache-control"] == "no-store"
    clasificaciones = {i["codigo_externo"]: i["clasificacion"] for i in client_usuario.get("/api/compras-agiles").json()["items"]}
    assert clasificaciones == {"90-1-COT26": "preseleccionada", "91-1-COT26": None, "92-1-COT26": "revision_manual"}
    assert "preseleccion" not in client_usuario.get("/api/compras-agiles").json()["items"][0]


def test_consultas_requieren_sesion(client):
    assert client.get("/api/compras-agiles").status_code == 401
    assert client.get("/api/compras-agiles/resumen").status_code == 401


@pytest.mark.parametrize("metodo,ruta", [
    ("post", "/api/ingesta/compras-agiles/lote/ejecutar"), ("get", "/api/ingesta/compras-agiles/estado"),
    ("post", "/api/ingesta/compras-agiles/codigo/1-2-COT26"),
])
def test_rutas_de_ingesta_solo_para_administradores(client_usuario, metodo, ruta):
    assert getattr(client_usuario, metodo)(ruta).status_code == 403


@pytest.fixture
def admin(client):
    app.dependency_overrides[usuario_actual] = lambda: {**USUARIO, "rol": "administrador"}
    return client


def test_codigo_invalido_no_consulta_la_api(admin, monkeypatch):
    descargar = AsyncMock()
    monkeypatch.setattr(ingesta, "descargar_y_procesar", descargar)
    app.dependency_overrides[get_db] = lambda: Mock()
    assert admin.post("/api/ingesta/compras-agiles/codigo/..%2F1-2-LE26").status_code in {404, 422}
    assert admin.post("/api/ingesta/compras-agiles/codigo/1-2-LE26").status_code == 422
    descargar.assert_not_awaited()


def test_estado_de_sincronizacion(admin, integration_db):
    r = admin.get("/api/ingesta/compras-agiles/estado")
    assert r.status_code == 200, r.text
    assert set(r.json()) >= {"carga_inicial_completa", "cursor", "ventana", "pendientes", "compras_guardadas"}


def test_lote_en_curso_responde_409(admin, monkeypatch):
    monkeypatch.setattr(ingesta, "ejecutar_compras_agiles", AsyncMock(side_effect=EjecucionEnCursoError("en curso")))
    app.dependency_overrides[get_db] = lambda: Mock()
    assert admin.post("/api/ingesta/compras-agiles/lote/ejecutar").status_code == 409


@pytest.fixture
def cron_falso(client, monkeypatch):
    monkeypatch.setattr(settings, "cron_secret", SECRETO)
    monkeypatch.setattr(settings, "documentos_automaticos", False)
    # La preselección posterior al lote tiene sus propias pruebas.
    monkeypatch.setattr(settings, "filtradas_url", "")
    app.dependency_overrides[get_db] = lambda: Mock()
    llamadas = []

    async def compras(db, client, limite):
        llamadas.append(limite)
        return {"procesados": limite}
    monkeypatch.setattr(ingesta, "ejecutar_compras_agiles", compras)
    return llamadas


def test_cron_propio_de_compras_agiles(client, cron_falso):
    headers = {"Authorization": "Bearer " + SECRETO}
    assert client.post("/api/cron/compras-agiles").status_code == 401
    r = client.get("/api/cron/compras-agiles?limite=4", headers=headers)
    assert r.status_code == 200 and r.json() == {"procesados": 4}
    assert client.post("/api/cron/compras-agiles?limite=21", headers=headers).status_code == 422
    assert cron_falso == [4]


def test_cron_de_ingesta_suma_compras_agiles_en_paralelo(client, cron_falso, monkeypatch):
    monkeypatch.setattr(settings, "compras_agiles_automaticas", True)
    monkeypatch.setattr(cron, "SessionLocal", lambda: Mock(__enter__=Mock(return_value=Mock()), __exit__=Mock()))

    async def licitaciones(db, client, limite_detalles):
        return {"procesados": 1, "errores": []}
    monkeypatch.setattr(ingesta, "ejecutar_ingesta_lote", licitaciones)
    r = client.post("/api/cron/ingesta", headers={"Authorization": "Bearer " + SECRETO})
    assert r.status_code == 200, r.text
    assert r.json() == {"procesados": 1, "errores": [],
                        "compras_agiles": {"procesados": cron.LIMITE_COMPRAS_AGILES_AUTOMATICAS}}


def test_falla_de_compras_agiles_no_interrumpe_licitaciones(monkeypatch):
    async def escenario():
        monkeypatch.setattr(settings, "documentos_automaticos", False)
        monkeypatch.setattr(settings, "compras_agiles_automaticas", True)
        monkeypatch.setattr(cron, "SessionLocal", lambda: Mock(__enter__=Mock(return_value=Mock()), __exit__=Mock()))
        monkeypatch.setattr(cron, "correr_lote", AsyncMock(return_value={"procesados": 1}))
        monkeypatch.setattr(cron, "correr_compras_agiles", AsyncMock(side_effect=RuntimeError("sin tablas")))
        return await cron.ingesta_programada(limite=1, db=Mock())
    r = asyncio.run(escenario())
    assert r == {"procesados": 1, "compras_agiles": {"pendiente": True, "motivo": "error_temporal"}}


def test_esquema_incluye_compra_agil_con_rls(integration_db):
    c = integration_db.connection()
    assert verificar_esquema(c) == []
    tablas = dict(c.execute(text("""
        SELECT relname, relrowsecurity FROM pg_class WHERE relnamespace='public'::regnamespace
        AND relname IN ('compra_agil','compra_agil_item','compra_agil_pendiente','compra_agil_sincronizacion')
    """)).all())
    assert len(tablas) == 4 and all(tablas.values())
    assert c.execute(text("SELECT count(*) FROM compra_agil_sincronizacion")).scalar_one() == 1


def test_adopta_base_manual_anterior_a_compra_agil(integration_db):
    c = integration_db.connection()
    c.execute(text("DROP TABLE public.alembic_version"))
    c.execute(text("DROP FUNCTION public.purgar_compras_agiles_no_disponibles(text[], boolean)"))
    c.execute(text("DROP TABLE public.compra_agil_item, public.compra_agil, public.compra_agil_pendiente, "
                   "public.compra_agil_sincronizacion"))
    c.execute(text("ALTER TABLE public.ejecucion_ingesta DROP COLUMN fuente"))
    registrar_esquema(c)
    assert c.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == REVISION_ACTUAL
    assert {"compra_agil", "compra_agil_pendiente"} <= set(inspect(c).get_table_names(schema="public"))
    assert verificar_esquema(c) == []


def test_downgrade_se_niega_si_hay_compras_agiles(integration_db, compras):
    c = integration_db.connection()
    with pytest.raises(DBAPIError, match="Compra"):
        with c.begin_nested():
            command.downgrade(configuracion(c), "b5df9fcc5f0d")
    assert c.execute(text("SELECT count(*) FROM compra_agil")).scalar_one() == 3
