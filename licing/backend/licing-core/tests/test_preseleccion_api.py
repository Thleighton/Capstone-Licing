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
    assert client.get('/api/preseleccion/pendientes-documentales').status_code==401


def test_reevaluacion_guarda_evidencia_y_actor(client, fila, monkeypatch):
    operar=AsyncMock(side_effect=[{}, {'evaluadas':[{'evaluacion_id':3}]}]); monkeypatch.setattr(filtradas,'operar',operar)
    response=client.post('/api/preseleccion/evaluar',json={'ids':[fila.id]})
    assert response.status_code==200,response.text
    operacion,payload=operar.call_args_list[1].args
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
    from app.services import documentos_origen
    def cargar(db, ids):
        raw=RawMercadoPublico(fuente='licitaciones',tipo_consulta='detalle_codigo',codigo_externo=fila.codigo_externo,
          respuesta={'cambio':True},http_status=200,consultado_en=datetime.now(timezone.utc))
        integration_db.add(raw);integration_db.flush();fila.raw_id=raw.id;integration_db.flush()
        return {}
    monkeypatch.setattr(documentos_origen,'cargar',cargar)
    operar=AsyncMock(return_value={})
    monkeypatch.setattr(filtradas,'operar',operar)
    assert client.post('/api/preseleccion/evaluar',json={'ids':[fila.id]}).status_code==409
    assert all(c.args[0]!='guardar' for c in operar.call_args_list)


def test_fecha_verificacion_no_invalida_revision():
    assert firma_fuente({'raw_id':1,'fuente_verificada_en':'antes'})==firma_fuente({'raw_id':1,'fuente_verificada_en':'despues'})
    assert firma_fuente({'raw_id':1})!=firma_fuente({'raw_id':2})


def test_pdf_vacio_queda_pendiente_aunque_filtradas_este_caida(client, fila, monkeypatch, integration_db):
    from app.services import documentos_origen
    storage=AsyncMock();monkeypatch.setattr(documentos_origen,'storage',storage)
    operar=AsyncMock(side_effect=filtradas.FiltradasNoDisponible('Temporal'))
    monkeypatch.setattr(filtradas,'operar',operar)
    r=client.post(f'/api/preseleccion/{fila.id}/documentos',json={'nombre':'vacio.pdf','contenido_base64':''})
    assert r.status_code==200,r.text
    assert r.json()['incidencia']['codigo']=='archivo_vacio'
    pendientes=client.get('/api/preseleccion/pendientes-documentales')
    assert pendientes.status_code==200,pendientes.text
    assert pendientes.json()['total']==1
    assert pendientes.json()['filas'][0]['id']==fila.id
    assert 'vacío' in pendientes.json()['filas'][0]['motivo_seleccion']
    storage.assert_not_called()
    assert integration_db.get(Licitacion,fila.id) is not None


def test_pendientes_documentales_permiten_ver_motivo_sin_evaluacion(client, fila, monkeypatch, integration_db):
    from app.services import documentos_origen
    documentos_origen.registrar_incidencia(integration_db,fila.id,'archivo_vacio')
    monkeypatch.setattr(filtradas,'operar',AsyncMock(side_effect=filtradas.FiltradasNoDisponible('Temporal')))
    r=client.get(f'/api/preseleccion/{fila.id}')
    assert r.status_code==200,r.text
    assert r.json()['evaluacion'] is None
    assert r.json()['incidencias_documentales'][0]['codigo']=='archivo_vacio'


def test_pdf_corrupto_guardado_se_muestra_pendiente_y_al_retirarlo_sale_de_la_vista(client, fila, monkeypatch, integration_db):
    from app.services import documentos_origen
    from app.services.pdf_bases import extraer_pdf
    from app.models.licitacion_documento import LicitacionDocumento
    import asyncio
    monkeypatch.setattr(documentos_origen,'storage',AsyncMock(return_value={}))
    contenido=b'%PDF-corrupto'
    extraccion=extraer_pdf(contenido)
    guardado=asyncio.run(documentos_origen.guardar(integration_db,fila.id,'Bases.pdf','bases_tecnicas',
        'https://www.mercadopublico.cl/bases',contenido,extraccion))
    r=client.get('/api/preseleccion/pendientes-documentales')
    assert r.status_code==200,r.text
    assert r.json()['filas'][0]['incidencias_documentales'][0]['codigo']=='pdf_corrupto'
    assert 'corrupto' in r.json()['filas'][0]['motivo_seleccion']
    monkeypatch.setattr(filtradas,'operar',AsyncMock(side_effect=filtradas.FiltradasNoDisponible('Temporal')))
    retirado=client.delete(f'/api/preseleccion/{fila.id}/documentos/{guardado["id"]}')
    assert retirado.status_code==200,retirado.text
    assert client.get('/api/preseleccion/pendientes-documentales').json()['total']==0
    assert integration_db.get(LicitacionDocumento,guardado['id']) is not None
    assert integration_db.get(Licitacion,fila.id) is not None
