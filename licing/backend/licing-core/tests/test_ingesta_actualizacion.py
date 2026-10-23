import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock
from uuid import uuid4
from zoneinfo import ZoneInfo

import httpx
import pytest
from sqlalchemy import select

from app.config import settings
from app.models.ejecucion_ingesta import EjecucionIngesta
from app.models.licitacion import Licitacion
from app.models.raw import RawMercadoPublico
from app.services import ingesta_lote as lotes
from app.services.normalizacion import VERSION_NORMALIZACION, normalizar_licitacion
from app.services.persistencia import convertir_fecha
from app.services.procesamiento import procesar_detalle_guardado


def detalle(codigo, cierre="2030-01-01T12:00:00", estado="Publicada", codigo_estado=5):
    return {"CodigoExterno": codigo, "Nombre": "Servicio", "Estado": estado,
            "CodigoEstado": codigo_estado, "Fechas": {"FechaCierre": cierre},
            "Items": {"Cantidad": 1, "Listado": [{"Correlativo": 1, "NombreProducto": "Servicio"}]}}


def guardar(db, codigo, contenido, antiguo=False, procesar=False):
    fecha = datetime.now(timezone.utc) - timedelta(days=2 if antiguo else 0)
    raw = RawMercadoPublico(fuente="licitaciones", tipo_consulta="detalle_codigo",
        codigo_externo=codigo, respuesta=contenido, http_status=200,
        consultado_en=fecha, verificado_en=fecha)
    db.add(raw)
    db.commit()
    if procesar:
        procesar_detalle_guardado(db, raw)
        db.commit()
    return raw


@pytest.fixture
def cliente(monkeypatch):
    monkeypatch.setattr(settings, "mp_pausa_detalles_segundos", 0.001)
    return AsyncMock()


@pytest.mark.parametrize("primero,esperado", [(False, ["N", "R"]), (True, ["R", "N"])])
def test_alterna_nuevos_y_actualizaciones(primero, esperado):
    assert lotes.alternar_codigos(["N"], ["R"], 2, primero) == esperado
    assert lotes.alternar_codigos(["N", "N2"], [], 2, primero) == ["N", "N2"]
    assert lotes.alternar_codigos(["N"], ["R"], 1, primero) == esperado[:1]


@pytest.mark.parametrize("valor", [
    {"Comprador": []}, {"Fechas": ""}, {"Items": []},
    {"Items": {"Listado": {}}}, {"Items": {"Listado": [1]}},
])
def test_datos_malformados_son_errores_controlados(valor):
    with pytest.raises(ValueError):
        normalizar_licitacion(valor)


def test_fecha_con_offset_se_convierte_a_chile():
    assert convertir_fecha("2026-10-23T20:00:00+00:00").isoformat() == "2026-10-23T17:00:00"
    assert convertir_fecha("2026-07-01T20:00:00+00:00").isoformat() == "2026-07-01T16:00:00"
    assert convertir_fecha("2026-10-23T17:00:00").isoformat() == "2026-10-23T17:00:00"


def test_error_http_no_expone_ticket():
    request = httpx.Request("GET", "https://example.test/?ticket=SECRETO")
    exc = httpx.HTTPStatusError("ticket=SECRETO", request=request, response=httpx.Response(429, request=request))
    error = lotes.error_de_codigo("CODIGO", exc)
    assert error["status_code"] == 429
    assert "SECRETO" not in str(error) and "ticket" not in str(error)


def test_cierra_conexion_si_falla_adquirir_bloqueo(monkeypatch):
    from unittest.mock import Mock
    conexion = Mock()
    conexion.execute.side_effect = RuntimeError("fallo")
    monkeypatch.setattr(lotes.engine, "connect", lambda: conexion)
    with pytest.raises(RuntimeError):
        asyncio.run(lotes.ejecutar_ingesta_lote(Mock(), AsyncMock()))
    conexion.close.assert_called_once()


@pytest.mark.parametrize("adquirido", [False, True])
def test_bloqueo_concurrente_y_liberacion_ante_fallo(monkeypatch, adquirido):
    from unittest.mock import Mock
    conexion = Mock()
    conexion.execute.return_value.scalar_one.return_value = adquirido
    monkeypatch.setattr(lotes, "engine", Mock(connect=Mock(return_value=conexion)))
    interno = AsyncMock(side_effect=RuntimeError("fallo del lote"))
    monkeypatch.setattr(lotes, "_ejecutar_ingesta_lote_con_bloqueo", interno)
    with pytest.raises(RuntimeError if adquirido else lotes.EjecucionEnCursoError):
        asyncio.run(lotes.ejecutar_ingesta_lote(Mock(), AsyncMock()))
    assert conexion.execute.call_count == (2 if adquirido else 1)
    assert interno.await_count == int(adquirido)
    conexion.close.assert_called_once()


def test_un_payload_invalido_no_acapara_los_siguientes_turnos(integration_db, cliente):
    db = integration_db
    malo, bueno = "TEST-M-" + uuid4().hex[:8], "TEST-B-" + uuid4().hex[:8]
    cliente.licitaciones_activas.return_value = {"Cantidad": 2, "Listado": [{"CodigoExterno": malo}, {"CodigoExterno": bueno}]}
    def responder(codigo):
        d = detalle(codigo)
        if codigo == malo:
            d["Items"]["Cantidad"] = 2
        return {"Cantidad": 1, "Listado": [d]}
    cliente.licitacion_por_codigo.side_effect = responder
    primera = asyncio.run(lotes._ejecutar_ingesta_lote_con_bloqueo(db, cliente, 1))
    assert primera["procesados"] == 0
    segunda = asyncio.run(lotes._ejecutar_ingesta_lote_con_bloqueo(db, cliente, 1))
    assert segunda["plan"]["codigos_a_descargar"] == [bueno]
    assert segunda["procesados"] == 1
    assert segunda["plan"]["pospuestos_por_error"] == 1


def test_reintento_vencido_descarga_una_version_nueva(integration_db, cliente):
    db = integration_db
    codigo = "TEST-REINTENTO-" + uuid4().hex[:8]
    malo = detalle(codigo)
    malo["Items"]["Cantidad"] = 2
    original = guardar(db, codigo, malo, antiguo=True)
    db.add(EjecucionIngesta(limite_detalles=1, estado="error",
        inicio=datetime.now(timezone.utc)-timedelta(hours=2),
        errores=[{"codigo_externo": codigo, "tipo": "ValueError", "normalizacion_version": VERSION_NORMALIZACION}]))
    db.commit()
    cliente.licitaciones_activas.return_value = {"Listado": [{"CodigoExterno": codigo}]}
    cliente.licitacion_por_codigo.return_value = {"Listado": [detalle(codigo)], "Cantidad": 1}
    r = asyncio.run(lotes._ejecutar_ingesta_lote_con_bloqueo(db, cliente, 1))
    assert r["procesados"] == 1 and r["descargados"] == 1
    lic = db.scalars(select(Licitacion).where(Licitacion.codigo_externo == codigo)).one()
    assert lic.raw_id != original.id and db.get(RawMercadoPublico, original.id).respuesta == malo


def test_elimina_vencida_aunque_no_figure_en_activas(integration_db, cliente):
    db = integration_db
    codigo = "TEST-CIERRE-" + uuid4().hex[:8]
    cierre = (datetime.now(ZoneInfo("America/Santiago")).replace(tzinfo=None)-timedelta(hours=1)).isoformat()
    raw = guardar(db, codigo, detalle(codigo), antiguo=True, procesar=True)
    lic = db.scalars(select(Licitacion).where(Licitacion.codigo_externo == codigo)).one()
    id_original = lic.id
    raw_id = raw.id
    lic.fecha_cierre = convertir_fecha(cierre)
    db.commit()
    cliente.licitaciones_activas.return_value = {"Listado": []}
    cliente.licitacion_por_codigo.return_value = {"Listado": [detalle(codigo, cierre, "Cerrada", 6)], "Cantidad": 1}
    r = asyncio.run(lotes._ejecutar_ingesta_lote_con_bloqueo(db, cliente, 1))
    assert r["limpieza"]["licitaciones"] == 1
    assert r["procesados"] == 0
    db.expire_all()
    lic = db.get(Licitacion, id_original)
    assert lic is None and db.get(RawMercadoPublico, raw_id) is None
    cliente.licitacion_por_codigo.assert_not_awaited()


def test_refresco_identico_no_duplica_raw_ni_lo_hace_nuevo(integration_db, cliente):
    db = integration_db
    codigo = "TEST-IDENTICO-" + uuid4().hex[:8]
    d = detalle(codigo)
    raw = guardar(db, codigo, d, antiguo=True, procesar=True)
    fecha_original = raw.consultado_en
    cliente.licitaciones_activas.return_value = {"Listado": []}
    cliente.licitacion_por_codigo.return_value = {"Listado": [d], "Cantidad": 1}
    r = asyncio.run(lotes._ejecutar_ingesta_lote_con_bloqueo(db, cliente, 1))
    assert r["actualizados"] == 1
    db.refresh(raw)
    assert raw.consultado_en == fecha_original
    assert raw.verificado_en > fecha_original
    assert len(db.scalars(select(RawMercadoPublico).where(RawMercadoPublico.codigo_externo == codigo)).all()) == 1


def test_timeout_conserva_avance_y_cierra_historial(integration_db, cliente, monkeypatch):
    db = integration_db
    a, b = "TEST-T-A-" + uuid4().hex[:8], "TEST-T-B-" + uuid4().hex[:8]
    monkeypatch.setattr(settings, "mp_lote_timeout_segundos", 0.5)
    cliente.licitaciones_activas.return_value = {"Listado": [{"CodigoExterno": a}, {"CodigoExterno": b}]}
    async def responder(codigo):
        if codigo == b:
            await asyncio.sleep(2)
        return {"Listado": [detalle(codigo)], "Cantidad": 1}
    cliente.licitacion_por_codigo.side_effect = responder
    r = asyncio.run(lotes._ejecutar_ingesta_lote_con_bloqueo(db, cliente, 2))
    assert r["procesados"] == 1 and r["interrumpido"] is True
    assert db.get(EjecucionIngesta, r["ejecucion_id"]).estado == "interrumpida"
    assert db.scalars(select(Licitacion).where(Licitacion.codigo_externo == a)).one()

