from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from app.auth import usuario_actual
from app.main import app
from app.models.licitacion import Licitacion
from app.models.raw import RawMercadoPublico
from app.services import filtradas
from app.api.preseleccion import firma_fuente

USER={'id':'11111111-1111-4111-8111-111111111111','rol':'encargado_licitaciones','activo':True}

@pytest.fixture
def fila(integration_db, client):
    db=integration_db
    raw=RawMercadoPublico(fuente='licitaciones',tipo_consulta='detalle_codigo',codigo_externo='123-1-LE26',
        respuesta={'CodigoExterno':'123-1-LE26'},http_status=200,consultado_en=datetime.now(timezone.utc))
    db.add(raw); db.flush()
    lic=Licitacion(codigo_externo='123-1-LE26',raw_id=raw.id,nombre='Arriendo de salón en Santiago',
        estado='Publicada',codigo_estado=5,fecha_cierre=datetime(2099,1,1))
    db.add(lic); db.commit()
    app.dependency_overrides[usuario_actual]=lambda:USER
    return lic


def test_rutas_privadas_sin_token(client):
    assert client.get('/api/preseleccion').status_code==401
    assert client.post('/api/preseleccion/evaluar',json={'ids':[1]}).status_code==401


def test_reevaluacion_guarda_evidencia_y_actor(client, fila, monkeypatch):
    operar=AsyncMock(side_effect=[{}, {}, {'evaluadas':[{'evaluacion_id':3}]}]); monkeypatch.setattr(filtradas,'operar',operar)
    response=client.post('/api/preseleccion/evaluar',json={'ids':[fila.id]})
    assert response.status_code==200,response.text
    operacion,payload=operar.call_args_list[2].args
    assert operacion=='guardar' and payload['actor']==USER['id']
    resultado=payload['lote'][0]['resultado']
    assert resultado['clasificacion']=='preseleccionada'
    assert resultado['semantica']['estado']=='pendiente'


def test_falla_filtradas_no_borra_fuente(client,fila,monkeypatch,integration_db):
    monkeypatch.setattr(filtradas,'operar',AsyncMock(side_effect=filtradas.FiltradasNoDisponible('Temporalmente no disponible')))
    assert client.post('/api/preseleccion/evaluar',json={'ids':[fila.id]}).status_code==503
    assert integration_db.get(Licitacion,fila.id) is not None


def test_documento_invalido_no_llega_a_storage(client,fila,monkeypatch):
    mock=AsyncMock();monkeypatch.setattr(filtradas,'operar',mock)
    response=client.post(f'/api/preseleccion/{fila.id}/documentos',json={'nombre':'base.pdf','contenido_base64':'bm90IHBkZg=='})
    assert response.status_code==422
    mock.assert_not_called()


def test_cambio_raw_durante_evaluacion_no_se_persiste(client,fila,monkeypatch,integration_db):
    async def operar(op,datos):
        if op=='sincronizar_fuente':
            return {}
        assert op=='documentos'
        raw=RawMercadoPublico(fuente='licitaciones',tipo_consulta='detalle_codigo',codigo_externo=fila.codigo_externo,
          respuesta={'cambio':True},http_status=200,consultado_en=datetime.now(timezone.utc))
        integration_db.add(raw);integration_db.flush();fila.raw_id=raw.id;integration_db.flush()
        return {}
    monkeypatch.setattr(filtradas,'operar',operar)
    assert client.post('/api/preseleccion/evaluar',json={'ids':[fila.id]}).status_code==409


def test_fecha_verificacion_no_invalida_revision():
    assert firma_fuente({'raw_id':1,'fuente_verificada_en':'antes'})==firma_fuente({'raw_id':1,'fuente_verificada_en':'despues'})
    assert firma_fuente({'raw_id':1})!=firma_fuente({'raw_id':2})
