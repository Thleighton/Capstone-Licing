import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
from fastapi import HTTPException

from app.api import cron
from app.api.preseleccion import cargar_entradas, firma_fuente
from app.config import settings
from app.models.raw import RawMercadoPublico
from app.services import filtradas, licitacion_preseleccion as cola
from app.services.preseleccion import CHILE, evaluar_preseleccion, version_filtro
from tests.test_preseleccion_api import fila


def test_version_antigua_produce_error_visible_aunque_el_rpc_responda_200(monkeypatch):
    cliente = httpx.AsyncClient
    monkeypatch.setattr(settings, 'cron_secret', 'secreto-de-prueba')
    monkeypatch.setattr(settings, 'filtradas_url', 'https://filtradas.invalid/')
    monkeypatch.setattr(httpx, 'AsyncClient', lambda **kw: cliente(**kw, transport=httpx.MockTransport(
        lambda r: httpx.Response(200, json={'evaluadas': [], 'omitidas_version': ['TEST-1']}))))
    with pytest.raises(HTTPException) as error:
        asyncio.run(filtradas.operar('guardar', {}))
    assert error.value.status_code == 409
    assert 'desactualizado' in error.value.detail


def aceptar(monkeypatch):
    async def operar(op, datos):
        if op != 'guardar':
            return {}
        return {'evaluadas': [{'codigo': e['datos']['codigo_externo'], 'evaluacion_id': 99} for e in datos['lote']]}
    monkeypatch.setattr(filtradas, 'operar', AsyncMock(side_effect=operar))


def test_guarda_marca_solo_despues_de_confirmar_y_no_invalida_su_firma(fila, integration_db, client, monkeypatch):
    db = integration_db
    aceptar(monkeypatch)
    assert fila.id in cola.pendientes(db)
    antes = firma_fuente(cargar_entradas(db, [fila.id])[str(fila.id)])
    r = client.post('/api/preseleccion/evaluar', json={'ids': [fila.id]})
    assert r.status_code == 200, r.text
    db.refresh(fila)
    assert fila.preseleccion['version'] == version_filtro()
    assert fila.preseleccion['evaluacion_id'] == 99
    assert fila.id not in cola.pendientes(db)
    assert firma_fuente(cargar_entradas(db, [fila.id])[str(fila.id)]) == antes
    fila.normalizacion_version = 'otra-normalizacion'
    db.commit()
    assert fila.id in cola.pendientes(db), 'una normalización nueva vuelve a entrar en la cola'


def test_no_confirma_fuente_modificada_durante_el_guardado(fila, integration_db, client, monkeypatch):
    db = integration_db
    async def operar(op, datos):
        if op != 'guardar': return {}
        nuevo = RawMercadoPublico(fuente='licitaciones', tipo_consulta='detalle_codigo',
            codigo_externo=fila.codigo_externo, respuesta={'cambio': True}, http_status=200)
        db.add(nuevo); db.flush(); fila.raw_id = nuevo.id; db.commit()
        return {'evaluadas': [{'codigo': fila.codigo_externo, 'evaluacion_id': 99}]}
    monkeypatch.setattr(filtradas, 'operar', AsyncMock(side_effect=operar))
    r = client.post('/api/preseleccion/evaluar', json={'ids': [fila.id]})
    assert r.status_code == 200, r.text
    assert r.json()['evaluadas'] == []
    db.refresh(fila)
    assert fila.preseleccion is None
    assert fila.id in cola.pendientes(db)


def test_preseleccion_avanza_aunque_el_turno_cancele_la_descarga(monkeypatch):
    async def escenario():
        monkeypatch.setattr(settings, 'cron_plazo_respuesta_segundos', 0.05)
        monkeypatch.setattr(settings, 'compras_agiles_automaticas', False)
        async def descargar(**kw):
            assert kw['evaluar_al_final'] is False
            await asyncio.sleep(2)
        monkeypatch.setattr(cron, 'correr_lote', descargar)
        monkeypatch.setattr(cron, 'preseleccionar_licitaciones_en_paralelo',
            AsyncMock(return_value={'evaluadas': [{'codigo': 'TEST-1'}], 'pendientes': 0}))
        return await cron.ingesta_programada(limite=1, db=Mock())
    r = asyncio.run(escenario())
    assert r['motivo'] == 'tiempo_turno_agotado'
    assert len(r['preseleccion_licitaciones']['evaluadas']) == 1


@pytest.mark.parametrize('nombre', [
    'Mantención de servidores y sistemas informáticos',
    'Compra de materiales eléctricos y transformadores',
    'Servicio de impresión de manuales y folletos',
    'Servicio de desarrollo de plataformas digitales',
])
def test_catalogo_activo_excluye_servicios_tecnicos_sin_linea_hotelera(nombre):
    r = evaluar_preseleccion({'codigo_externo': 'TEST-1-LE26', 'estado': 'Publicada', 'codigo_estado': 5,
        'fecha_cierre': '2099-01-01T12:00:00', 'nombre': nombre, 'items': []},
        ahora=datetime(2026, 11, 15, 12, tzinfo=CHILE))
    assert r['clasificacion'] == 'descartada', r


def test_catalogo_nuevo_conserva_un_salon_explicito_para_feria():
    r = evaluar_preseleccion({'codigo_externo': 'TEST-1-LE26', 'estado': 'Publicada', 'codigo_estado': 5,
        'fecha_cierre': '2099-01-01T12:00:00', 'nombre': 'Arriendo de salón para feria en Santiago', 'items': []},
        ahora=datetime(2026, 11, 15, 12, tzinfo=CHILE))
    assert r['clasificacion'] == 'preseleccionada', r
