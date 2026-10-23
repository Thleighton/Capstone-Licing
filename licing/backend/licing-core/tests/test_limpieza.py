import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import select, text, func
from sqlalchemy.exc import ProgrammingError

from app.config import settings
from app.models.licitacion import Licitacion
from app.models.raw import RawMercadoPublico
from app.services import ingesta_lote as lotes
from app.services.limpieza import ausencia_confirmada, eliminar_no_disponibles, motivo_no_disponible
from app.services.procesamiento import procesar_detalle_guardado


def detalle(codigo, **cambios):
    return {"CodigoExterno": codigo, "CodigoEstado": 5, "Estado": "Publicada",
            "Fechas": {"FechaCierre": "2099-12-01T15:00:00"},
            "Items": {"Cantidad": 1, "Listado": [{"Correlativo": 1}]}, **cambios}


def raw(db, codigo, contenido):
    fila = RawMercadoPublico(fuente="licitaciones", tipo_consulta="detalle_codigo",
                            codigo_externo=codigo, respuesta=contenido, http_status=200)
    db.add(fila)
    db.flush()
    return fila


@pytest.mark.parametrize("datos,esperado", [
    ({"CodigoEstado": 6}, "estado_no_disponible"),
    ({"CodigoEstado": "19"}, "estado_no_disponible"),
    ({"Estado": "Adjudicada"}, "estado_no_disponible"),
    ({"CodigoEstado": 5}, None), ({"CodigoEstado": 999}, None),
    ({"FechaCierre": "2026-10-23T16:59:59-03:00"}, "fecha_cierre"),
    ({"FechaCierre": "2026-10-23T20:00:00Z"}, "fecha_cierre"),
    ({"FechaCierre": "2026-10-23T17:00:01"}, None),
    ({"Fechas": {"FechaCierre": "2026-10-23T17:00:00"}}, "fecha_cierre"),
    ({"FechaCierre": "infinity"}, None), ({"FechaCierre": "2026-99-23"}, None), ({}, None),
])
def test_disponibilidad_y_limite_horario(datos, esperado):
    assert motivo_no_disponible(datos, datetime(2026, 10, 23, 20, tzinfo=timezone.utc)) == esperado


@pytest.mark.parametrize("respuesta", [
    {}, {"Cantidad": False, "Listado": []}, {"Cantidad": "0", "Listado": []},
    {"Cantidad": 0, "Listado": [], "Codigo": 10500, "Mensaje": "Fallo de API"},
])
def test_error_de_api_no_confirma_ausencia(respuesta):
    assert ausencia_confirmada(respuesta) is False


def test_purga_completa_preserva_vigentes_y_es_idempotente(integration_db):
    db = integration_db
    codigo = "BORRAR-" + uuid4().hex[:8]
    r = raw(db, codigo, detalle(codigo))
    lic_id = procesar_detalle_guardado(db, r)["licitacion_id"]
    raw(db, codigo, detalle(codigo, Nombre="Otra versión"))
    codigo_vigente = "VIGENTE-" + uuid4().hex[:8]
    r_vigente = raw(db, codigo_vigente, detalle(codigo_vigente))
    vigente_id = procesar_detalle_guardado(db, r_vigente)["licitacion_id"]
    db.get(Licitacion, lic_id).fecha_cierre = datetime(2000, 1, 1)
    db.flush()
    assert eliminar_no_disponibles(db) == {"licitaciones": 1, "items": 1, "raw": 2}
    db.expire_all()
    assert db.get(Licitacion, lic_id) is None
    assert db.get(Licitacion, vigente_id) is not None
    assert eliminar_no_disponibles(db) == {"licitaciones": 0, "items": 0, "raw": 0}


@pytest.mark.parametrize("contenido,eliminado", [
    ({"CodigoEstado": 18}, True), ({"Estado": "Suspendida"}, True),
    ({"FechaCierre": "2000-01-01T00:00:00Z"}, True),
    ({"FechaCierre": "2000-99-01T00:00:00"}, False),
    ({"FechaCierre": "yesterday"}, False), ({}, False),
])
def test_raw_pendiente_y_fechas_invalidas(integration_db, contenido, eliminado):
    db = integration_db
    codigo = "PEND-" + uuid4().hex[:8]
    identificador = raw(db, codigo, contenido).id
    assert eliminar_no_disponibles(db)["raw"] == int(eliminado)
    db.expire_all()
    assert (db.get(RawMercadoPublico, identificador) is None) == eliminado


def test_raw_antiguo_vencido_no_borra_extension_vigente(integration_db):
    db = integration_db
    codigo = "EXT-" + uuid4().hex[:8]
    raw(db, codigo, detalle(codigo, Fechas={"FechaCierre": "2000-01-01T00:00:00"}))
    reciente = raw(db, codigo, detalle(codigo))
    lic_id = procesar_detalle_guardado(db, reciente)["licitacion_id"]
    assert eliminar_no_disponibles(db)["licitaciones"] == 0
    assert db.get(Licitacion, lic_id) is not None


@pytest.mark.parametrize("respuesta", [
    {"Cantidad": 0, "Listado": []},
    {"Cantidad": 1, "Listado": ["cerrada"]},
    {"Cantidad": 1, "Listado": [{"CodigoEstado": 6, "Estado": "Cerrada"}]},
])
def test_confirmacion_por_codigo_y_respuesta_invalida(integration_db, monkeypatch, respuesta):
    db = integration_db
    monkeypatch.setattr(settings, "mp_pausa_detalles_segundos", 0.001)
    codigo = "FUENTE-" + uuid4().hex[:8]
    r = raw(db, codigo, detalle(codigo))
    r.verificado_en = datetime(2000, 1, 1, tzinfo=timezone.utc)
    lic_id = procesar_detalle_guardado(db, r)["licitacion_id"]
    db.commit()
    cliente = AsyncMock()
    cliente.licitaciones_activas.return_value = {"Listado": []}
    if respuesta.get("Listado") and isinstance(respuesta["Listado"][0], dict):
        respuesta = {**respuesta, "Listado": [{**respuesta["Listado"][0], "CodigoExterno": codigo}]}
    cliente.licitacion_por_codigo.return_value = respuesta
    resultado = asyncio.run(lotes._ejecutar_ingesta_lote_con_bloqueo(db, cliente))
    db.expire_all()
    inexistente = respuesta["Cantidad"] == 0 or isinstance(respuesta["Listado"][0], dict)
    assert (db.get(Licitacion, lic_id) is None) == inexistente
    assert bool(resultado["descartadas"]) == inexistente
    assert bool(resultado["errores"]) != inexistente


def test_error_http_no_elimina_y_estado_cerrada_si_elimina(integration_db, monkeypatch):
    db = integration_db
    monkeypatch.setattr(settings, "mp_pausa_detalles_segundos", 0.001)
    codigo = "HTTP-" + uuid4().hex[:8]
    r = raw(db, codigo, detalle(codigo))
    r.verificado_en = datetime(2000, 1, 1, tzinfo=timezone.utc)
    lic_id = procesar_detalle_guardado(db, r)["licitacion_id"]
    db.commit()
    cliente = AsyncMock()
    cliente.licitaciones_activas.return_value = {"Listado": []}
    request = httpx.Request("GET", "https://example.test")
    cliente.licitacion_por_codigo.side_effect = httpx.HTTPStatusError(
        "fallo", request=request, response=httpx.Response(503, request=request))
    resultado = asyncio.run(lotes._ejecutar_ingesta_lote_con_bloqueo(db, cliente))
    assert resultado["errores"] and db.get(Licitacion, lic_id) is not None
    cliente.licitacion_por_codigo.side_effect = None
    cliente.licitacion_por_codigo.return_value = {"Cantidad": 1, "Listado": [
        detalle(codigo, CodigoEstado=6, Estado="Cerrada")]}
    # El historial de error de la primera consulta no afecta esta comprobación directa.
    from app.services.limpieza import LicitacionNoDisponible
    with pytest.raises(LicitacionNoDisponible):
        asyncio.run(lotes.obtener_o_descargar_detalle(db, cliente, codigo, forzar_descarga=True))
    eliminar_no_disponibles(db, codigo, confirmada=True)
    db.expire_all()
    assert db.get(Licitacion, lic_id) is None


@pytest.mark.parametrize("rol", ["anon", "authenticated"])
def test_funcion_no_es_rpc_publica(integration_db, rol):
    db = integration_db
    assert db.scalar(text("SELECT has_function_privilege(:rol, "
        "'public.purgar_licitaciones_no_disponibles(text,boolean)', 'EXECUTE')"), {"rol": rol}) is False
