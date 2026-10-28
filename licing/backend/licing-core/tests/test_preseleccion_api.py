from datetime import datetime, timezone
from decimal import Decimal
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
    assert client.get('/api/preseleccion/plan').status_code==401
    assert client.post('/api/preseleccion/evaluar',json={'ids':[1]}).status_code==401
    assert client.get('/api/preseleccion/pendientes-documentales').status_code==401


def test_listado_por_dia_de_cierre(client, fila, integration_db, monkeypatch):
    fila.fecha_cierre = datetime(2099, 5, 10, 23, 59, 59, 999999)
    integration_db.commit()
    operar = AsyncMock(return_value={"filas": [], "total": 0})
    monkeypatch.setattr(filtradas, 'operar', operar)
    respuesta = client.get('/api/preseleccion', params={'cierre_desde': '2099-05-10', 'cierre_hasta': '2099-05-10'})
    assert respuesta.status_code == 200, respuesta.text
    assert operar.call_args.args[1]['codigos'] == [fila.codigo_externo]
    respuesta = client.get('/api/preseleccion', params={'cierre_desde': '2099-05-11'})
    assert respuesta.status_code == 200, respuesta.text
    assert operar.call_args.args[1]['codigos'] == []
    assert client.get('/api/preseleccion', params={'cierre_desde': '2099-05-11', 'cierre_hasta': '2099-05-10'}).status_code == 422


def test_busqueda_conserva_institucion_en_oportunidades(client, fila, integration_db, monkeypatch):
    fila.nombre_organismo = 'Ministerio de Salud'
    integration_db.commit()
    operar = AsyncMock(return_value={'filas': [], 'total': 0})
    monkeypatch.setattr(filtradas, 'operar', operar)
    assert client.get('/api/preseleccion', params={'q': 'SALUD'}).status_code == 200
    assert operar.call_args.args[1]['codigos'] == [fila.codigo_externo]
    assert operar.call_args.args[1]['q'] == ''
    assert client.get('/api/preseleccion', params={'q': 'otra institucion'}).status_code == 200
    assert operar.call_args.args[1]['codigos'] == []


def test_listado_muestra_presupuesto_y_datos_actuales_de_core(client, fila, integration_db, monkeypatch):
    from app.api.preseleccion import cargar_entradas
    fila.monto_estimado = Decimal('1285000.75')
    fila.moneda = 'USD'
    fila.estimacion = 2
    fila.visibilidad_monto = 1
    fila.fecha_publicacion = datetime(2026, 10, 28, 12)
    fila.descripcion = 'Arriendo de salón para seminario de 40 asistentes.'
    fila.tipo = 'LE'
    integration_db.commit()
    entrada = cargar_entradas(integration_db, [fila.id])[str(fila.id)]
    monkeypatch.setattr(filtradas, 'operar', AsyncMock(return_value={'filas': [{
        'id': fila.id, 'codigo_externo': fila.codigo_externo, 'fuente_raw_id': fila.raw_id,
        'hash_fuente': firma_fuente(entrada), 'estado_seleccion': 'preseleccionada',
        'monto_estimado': '1', 'moneda': 'CLP', 'tipo': 'desactualizado',
    }], 'total': 1}))
    respuesta = client.get('/api/preseleccion')
    assert respuesta.status_code == 200, respuesta.text
    datos = respuesta.json()['filas'][0]
    assert datos['monto_estimado'] == '1285000.75' and datos['moneda'] == 'USD'
    assert datos['estimacion'] == 2 and datos['visibilidad_monto'] == 1
    assert datos['fecha_publicacion'] == '2026-10-28T12:00:00-03:00'
    assert datos['fecha_cierre'].startswith('2099-01-01T00:00:00')
    assert datos['tipo'] == 'LE' and datos['estado'] == 'Publicada'
    assert datos['descripcion'] == fila.descripcion


@pytest.mark.parametrize('monto,esperado', [(None, None), (Decimal('0'), '0')])
def test_listado_distingue_monto_ausente_de_cero(client, fila, integration_db, monkeypatch, monto, esperado):
    fila.monto_estimado = monto
    fila.moneda = None
    fila.estimacion = 1
    fila.visibilidad_monto = 0
    integration_db.commit()
    monkeypatch.setattr(filtradas, 'operar', AsyncMock(return_value={'filas': [{
        'id': fila.id, 'codigo_externo': fila.codigo_externo, 'fuente_raw_id': fila.raw_id,
    }], 'total': 1}))
    respuesta = client.get('/api/preseleccion')
    assert respuesta.status_code == 200, respuesta.text
    datos = respuesta.json()['filas'][0]
    assert datos['monto_estimado'] == esperado and datos['moneda'] is None
    assert datos['estimacion'] == 1 and datos['visibilidad_monto'] == 0


def test_reevaluacion_guarda_evidencia_y_actor(client, fila, monkeypatch):
    operar=AsyncMock(side_effect=[{}, {'evaluadas':[{'evaluacion_id':3}]}]); monkeypatch.setattr(filtradas,'operar',operar)
    response=client.post('/api/preseleccion/evaluar',json={'ids':[fila.id]})
    assert response.status_code==200,response.text
    operacion,payload=operar.call_args_list[1].args
    assert operacion=='guardar' and payload['actor']==USER['id']
    resultado=payload['lote'][0]['resultado']
    assert resultado['clasificacion']=='preseleccionada'


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


def test_plan_omite_resultados_vigentes_y_detecta_reglas_nuevas(client, fila, monkeypatch, integration_db):
    from app.api import preseleccion
    datos = preseleccion.cargar_entradas(integration_db, [fila.id])[str(fila.id)]
    operar = AsyncMock(return_value={'filas': [{'id': fila.id, 'hash_fuente': firma_fuente(datos),
        'estado_seleccion': 'revision_manual'}], 'total': 1})
    monkeypatch.setattr(filtradas, 'operar', operar)
    r = client.get('/api/preseleccion/plan')
    assert r.status_code == 200, r.text
    assert r.json()['ids'] == []
    assert r.headers['cache-control'] == 'no-store'
    monkeypatch.setattr(preseleccion, 'VERSION_MOTOR', 'reglas-nuevas')
    r = client.get('/api/preseleccion/plan')
    assert r.json()['ids'] == [fila.id]
    assert all(c.args[0] == 'listar' for c in operar.call_args_list)


def test_plan_incluye_fuentes_aun_no_evaluadas(client, fila, monkeypatch):
    monkeypatch.setattr(filtradas, 'operar', AsyncMock(return_value={'filas': [], 'total': 0}))
    r = client.get('/api/preseleccion/plan')
    assert r.status_code == 200, r.text
    assert r.json()['ids'] == [fila.id]


def test_lote_grande_carga_raw_en_una_consulta_y_guarda_en_partes_acotadas(client, fila, monkeypatch, integration_db):
    import asyncio
    from sqlalchemy import event
    db = integration_db
    filas = [fila] + [Licitacion(codigo_externo=f'123-{n}-LE26', raw_id=fila.raw_id,
        nombre='Arriendo de salón en Santiago', estado='Publicada', codigo_estado=5,
        fecha_cierre=datetime(2099, 1, 1)) for n in range(2, 46)]
    db.add_all(filas[1:]); db.flush()
    ids = [f.id for f in filas]
    en_curso = maximo = 0
    async def persistir(operacion, datos):
        nonlocal en_curso, maximo
        if operacion == 'sincronizar_fuente':
            return {}
        en_curso += 1; maximo = max(maximo, en_curso)
        await asyncio.sleep(0)
        en_curso -= 1
        assert 1 <= len(datos['lote']) <= 20
        return {'evaluadas': [{'codigo': e['datos']['codigo_externo']} for e in datos['lote']]}
    operar = AsyncMock(side_effect=persistir)
    monkeypatch.setattr(filtradas, 'operar', operar)
    consultas = []
    def consulta(conn, cursor, statement, parameters, context, executemany):
        if 'FROM raw_mercado_publico' in statement:
            consultas.append(statement)
    conexion = db.connection()
    event.listen(conexion, 'before_cursor_execute', consulta)
    try:
        r = client.post('/api/preseleccion/evaluar', json={'ids': ids})
    finally:
        event.remove(conexion, 'before_cursor_execute', consulta)
    assert r.status_code == 200, r.text
    assert len(r.json()['evaluadas']) == 45
    assert len(consultas) == 1
    assert maximo == 2
    assert [c.args[0] for c in operar.call_args_list].count('sincronizar_fuente') == 1


def test_lote_no_guarda_ni_sincroniza_si_falta_una_fuente(client, fila, monkeypatch):
    operar = AsyncMock()
    monkeypatch.setattr(filtradas, 'operar', operar)
    r = client.post('/api/preseleccion/evaluar', json={'ids': [fila.id, 99999999]})
    assert r.status_code == 404
    operar.assert_not_called()


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
