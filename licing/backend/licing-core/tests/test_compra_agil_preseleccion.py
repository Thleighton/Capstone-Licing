import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

import pytest
from fastapi import HTTPException

from app.api import ingesta
from app.auth import usuario_actual
from app.config import settings
from app.main import app
from app.models.compra_agil import CompraAgil
from app.services import compra_agil_preseleccion as preseleccion
from app.services import filtradas
from app.services.compra_agil_persistencia import guardar_raw, procesar_compra_guardada
from tests.conftest import USUARIO

CHILE = ZoneInfo("America/Santiago")
USUARIO_ID = "11111111-1111-4111-8111-111111111111"


def ahora():
    return datetime.now(CHILE).replace(tzinfo=None, microsecond=0)


# Fijo para todo el módulo: el mismo detalle debe producir el mismo RAW.
MOMENTO = ahora()


def detalle(codigo, nombre="Coffee break para jornada en Santiago", cierre=None, productos=None):
    cierre = cierre or MOMENTO + timedelta(days=2)
    return {
        "codigo": codigo, "nombre": nombre, "descripcion": "Servicio para 40 personas en Santiago.",
        "estado": {"id_estado": 2, "codigo": "publicada", "glosa": "Publicada"},
        "fechas": {"fecha_publicacion": MOMENTO.strftime("%Y-%m-%d %H:%M"), "fecha_cierre": cierre.strftime("%Y-%m-%d %H:%M"),
                   "fecha_ultimo_cambio": MOMENTO.strftime("%Y-%m-%d %H:%M")},
        "presupuesto": {"moneda": "CLP", "monto_disponible": 450000, "monto_disponible_clp": 450000},
        "institucion": {"organismo_comprador": "Ministerio de Salud", "unidad_compra": "Subsecretaría", "region": 13,
                        "nombre_region": "Región Metropolitana de Santiago"},
        "entrega": {"direccion_entrega": "Monjitas 689, Santiago"},
        "productos_solicitados": productos if productos is not None else [
            {"codigo_producto": 90101603, "nombre": "Coffee break", "descripcion": "Para 40 personas", "cantidad": 40,
             "unidad_medida": "EA"}],
    }


def guardar(db, codigo, **cambios):
    registro = guardar_raw(db, codigo, detalle(codigo, **cambios))
    resultado = procesar_compra_guardada(db, registro)
    db.commit()
    return db.get(CompraAgil, resultado["compra_agil_id"])


def filtradas_falsa(evaluadas=None):
    """Responde como lf_operar: guardar devuelve los códigos aceptados."""
    async def operar(operacion, datos=None):
        if operacion == "guardar":
            aceptadas = evaluadas if evaluadas is not None else [e["datos"]["codigo_externo"] for e in datos["lote"]]
            return {"evaluadas": [{"codigo": c, "evaluacion_id": n + 1} for n, c in enumerate(aceptadas)]}
        return {}
    return AsyncMock(side_effect=operar)


@pytest.fixture
def db(integration_db):
    return integration_db


def test_entrada_con_columnas_de_filtradas(db):
    compra = guardar(db, "9001-1-COT26")
    datos = preseleccion.cargar_entradas(db, [compra.id])[str(compra.id)]
    assert datos["modalidad"] == "compra_agil" and datos["codigo_estado"] is None
    assert datos["monto_estimado"] == "450000" and datos["moneda"] == "CLP"
    assert datos["fecha_cierre"].endswith(("-03:00", "-04:00"))
    assert datos["url_oficial"] == "https://buscador.mercadopublico.cl/ficha?code=9001-1-COT26"
    assert datos["items"] == [{"posicion_fuente": 1, "correlativo": 1, "codigo_producto": "90101603",
                               "nombre_producto": "Coffee break", "descripcion": "Para 40 personas",
                               "cantidad": "40", "unidad_medida": "EA"}]
    assert datos["documentos_version"] == [] and "preseleccion" not in datos


def test_evalua_sincroniza_su_modalidad_y_registra_la_version(db, monkeypatch):
    compras = [guardar(db, f"9002-{n}-COT26") for n in range(25)]
    operar = filtradas_falsa()
    monkeypatch.setattr(filtradas, "operar", operar)
    r = asyncio.run(preseleccion.evaluar_compras_agiles(db, actor=USUARIO_ID))
    llamadas = [c.args for c in operar.call_args_list]
    assert llamadas[0][0] == "sincronizar_fuente" and llamadas[0][1]["modalidad"] == "compra_agil"
    assert set(llamadas[0][1]["codigos"]) >= {c.codigo_externo for c in compras}
    guardados = [datos for operacion, datos in llamadas if operacion == "guardar"]
    assert [len(g["lote"]) for g in guardados] == [20, 5] and guardados[0]["actor"] == USUARIO_ID
    primera = guardados[0]["lote"][0]
    assert primera["resultado"]["clasificacion"] == "preseleccionada" and primera["documentos_version"] == []
    assert len(r["evaluadas"]) == 25 and r["pendientes"] == 0
    db.expire_all()
    marca = db.get(CompraAgil, compras[0].id).preseleccion
    assert marca["version"] == preseleccion.version_preseleccion() and marca["clasificacion"] == "preseleccionada"
    assert marca["firma"] == preseleccion.firma(preseleccion.cargar_entradas(db, [compras[0].id])[str(compras[0].id)])
    assert preseleccion.pendientes(db) == []


def test_ajena_queda_evaluada_pero_no_preseleccionada(db, monkeypatch):
    compra = guardar(db, "9003-1-COT26", nombre="Compra de resmas de papel", productos=[
        {"codigo_producto": 14111507, "nombre": "Papel para impresora", "cantidad": 10, "unidad_medida": "EA"}])
    monkeypatch.setattr(filtradas, "operar", filtradas_falsa())
    r = asyncio.run(preseleccion.evaluar_compras_agiles(db, [compra.id]))
    assert r["evaluadas"][0]["clasificacion"] != "preseleccionada"


def test_omitida_por_filtradas_o_sin_conexion_sigue_pendiente(db, monkeypatch):
    compra = guardar(db, "9004-1-COT26")
    monkeypatch.setattr(filtradas, "operar", filtradas_falsa(evaluadas=[]))
    r = asyncio.run(preseleccion.evaluar_compras_agiles(db, [compra.id]))
    assert r["evaluadas"] == [] and r["sin_guardar"] == 1 and compra.id in preseleccion.pendientes(db)
    monkeypatch.setattr(filtradas, "operar", AsyncMock(side_effect=filtradas.FiltradasNoDisponible("sin conexión")))
    with pytest.raises(filtradas.FiltradasNoDisponible):
        asyncio.run(preseleccion.evaluar_compras_agiles(db, [compra.id]))
    db.expire_all()
    assert db.get(CompraAgil, compra.id).preseleccion is None


def test_raw_nuevo_o_reglas_nuevas_vuelven_a_pendiente(db, monkeypatch):
    compra = guardar(db, "9005-1-COT26")
    monkeypatch.setattr(filtradas, "operar", filtradas_falsa())
    asyncio.run(preseleccion.evaluar_compras_agiles(db, [compra.id]))
    # El mismo RAW conserva la evaluación.
    guardar(db, "9005-1-COT26")
    db.expire_all()
    assert db.get(CompraAgil, compra.id).preseleccion is not None
    guardar(db, "9005-1-COT26", nombre="Coffee break y almuerzo en Santiago")
    db.expire_all()
    assert db.get(CompraAgil, compra.id).preseleccion is None
    asyncio.run(preseleccion.evaluar_compras_agiles(db, [compra.id]))
    monkeypatch.setattr(preseleccion, "VERSION_MOTOR", "reglas-hotel-siguiente")
    assert compra.id in preseleccion.pendientes(db)


def test_vencidas_no_se_evaluan(db):
    compra = guardar(db, "9006-1-COT26")
    compra.fecha_cierre = ahora() - timedelta(minutes=1)
    db.commit()
    assert compra.id not in preseleccion.pendientes(db)


def test_lote_incluye_preseleccion_y_no_falla_si_filtradas_no_responde(db, monkeypatch):
    monkeypatch.setattr(settings, "cron_secret", "secreto")
    monkeypatch.setattr(settings, "filtradas_url", "https://filtradas.example.test")
    monkeypatch.setattr(ingesta, "ejecutar_compras_agiles", AsyncMock(return_value={"procesados": 1}))
    monkeypatch.setattr(ingesta, "evaluar_compras_agiles", AsyncMock(return_value={"evaluadas": [1], "pendientes": 0}))
    r = asyncio.run(ingesta.correr_lote_compras_agiles(db, 5))
    assert r == {"procesados": 1, "preseleccion": {"evaluadas": [1], "pendientes": 0}}
    perfil = HTTPException(409, "Los datos cambiaron o la operación requiere revisión. Actualiza y vuelve a intentarlo.")
    monkeypatch.setattr(ingesta, "evaluar_compras_agiles", AsyncMock(side_effect=perfil))
    assert asyncio.run(ingesta.correr_lote_compras_agiles(db, 5))["preseleccion"]["pendiente"] is True
    monkeypatch.setattr(ingesta, "evaluar_compras_agiles",
                        AsyncMock(side_effect=filtradas.FiltradasNoDisponible("No se pudo acceder")))
    assert asyncio.run(ingesta.correr_lote_compras_agiles(db, 5))["preseleccion"] == {
        "pendiente": True, "motivo": "No se pudo acceder"}


@pytest.fixture
def usuario(client):
    app.dependency_overrides[usuario_actual] = lambda: {**USUARIO, "id": USUARIO_ID}
    return client


def test_listado_marca_desactualizadas_y_agrega_datos_de_core(usuario, db, monkeypatch):
    vigente, cambiada = guardar(db, "9007-1-COT26"), guardar(db, "9007-2-COT26")
    monkeypatch.setattr(filtradas, "operar", filtradas_falsa())
    asyncio.run(preseleccion.evaluar_compras_agiles(db, [vigente.id, cambiada.id]))
    db.expire_all()
    firmas = {c.id: c.preseleccion["firma"] for c in (db.get(CompraAgil, vigente.id), db.get(CompraAgil, cambiada.id))}
    guardar(db, "9007-2-COT26", nombre="Almuerzo en Santiago")
    filas = [{"id": c.id, "codigo_externo": c.codigo_externo, "estado_seleccion": "preseleccionada",
              "hash_fuente": firmas[c.id], "fuente_raw_id": c.raw_id} for c in (vigente, cambiada)]
    operar = AsyncMock(return_value={"filas": filas, "total": 2})
    monkeypatch.setattr(filtradas, "operar", operar)
    r = usuario.get("/api/compras-agiles/preseleccion", params={"clasificacion": "preseleccionada"})
    assert r.status_code == 200, r.text
    assert operar.call_args.args[1]["clasificacion"] == "preseleccionada"
    assert set(operar.call_args.args[1]["codigos"]) >= {"9007-1-COT26", "9007-2-COT26"}
    estados = {f["codigo_externo"]: f["estado_seleccion"] for f in r.json()["filas"]}
    assert estados == {"9007-1-COT26": "preseleccionada", "9007-2-COT26": "pendiente_evaluacion"}
    assert r.json()["filas"][0]["clientes_importantes"][0]["id"] == "minsal"
    assert r.json()["pendientes"] >= 1


def test_evaluar_y_detalle_desde_la_sesion(usuario, db, monkeypatch):
    compra = guardar(db, "9008-1-COT26")
    operar = filtradas_falsa()
    monkeypatch.setattr(filtradas, "operar", operar)
    r = usuario.post("/api/compras-agiles/preseleccion/evaluar", json={"ids": [compra.id]})
    assert r.status_code == 200, r.text
    assert operar.call_args.args[1]["actor"] == USUARIO_ID
    assert usuario.post("/api/compras-agiles/preseleccion/evaluar", json={"ids": [999999999]}).status_code == 404
    db.expire_all()
    firma = db.get(CompraAgil, compra.id).preseleccion["firma"]
    monkeypatch.setattr(filtradas, "operar", AsyncMock(return_value={"hash_fuente": firma, "criterios": []}))
    detalle_r = usuario.get(f"/api/compras-agiles/{compra.id}/preseleccion")
    assert detalle_r.status_code == 200 and detalle_r.json()["fuente_actualizada"] is True
    monkeypatch.setattr(filtradas, "operar", AsyncMock(side_effect=filtradas.FiltradasNoDisponible("x")))
    assert usuario.get(f"/api/compras-agiles/{compra.id}/preseleccion").json()["fuente_actualizada"] is False
    assert usuario.get("/api/compras-agiles/preseleccion").status_code == 503


def test_rutas_de_preseleccion_requieren_sesion(client):
    assert client.get("/api/compras-agiles/preseleccion").status_code == 401
    assert client.post("/api/compras-agiles/preseleccion/evaluar").status_code == 401
