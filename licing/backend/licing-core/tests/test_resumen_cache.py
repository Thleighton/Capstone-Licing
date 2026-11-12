from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import text

from app.auth import usuario_actual
from app.main import app
from app.models.licitacion import Licitacion
from app.models.compra_agil import CompraAgil
from app.models.raw import RawMercadoPublico
from app.services import resumen_gemini as ia
from app.services import filtradas
from app.api.preseleccion import cargar_entradas, firma_fuente
from app.services import compra_agil_preseleccion as ca


@pytest.fixture(params=['licitacion', 'compra_agil'])
def oportunidad(request, integration_db, client, monkeypatch):
    db = integration_db
    tipo = request.param
    codigo = '100-1-LE26' if tipo == 'licitacion' else '100-1-COT26'
    raw = RawMercadoPublico(fuente='licitaciones' if tipo == 'licitacion' else 'compra_agil',
        tipo_consulta='detalle_codigo' if tipo == 'licitacion' else 'detalle_compra_agil',
        codigo_externo=codigo, respuesta={'codigo': codigo}, http_status=200,
        consultado_en=datetime.now(timezone.utc) - timedelta(minutes=2))
    db.add(raw); db.flush()
    model = Licitacion if tipo == 'licitacion' else CompraAgil
    fila = model(codigo_externo=codigo, raw_id=raw.id, nombre='Arriendo de salón para seminario',
        descripcion='Salón en Santiago para 40 personas y coffee break.', estado='publicada',
        fecha_cierre=datetime(2099, 1, 1), moneda='CLP', normalizado_en=datetime.now(timezone.utc))
    if tipo == 'licitacion':
        fila.codigo_estado = 5
    db.add(fila); db.flush()
    identificador = fila.id
    cargar = lambda: (cargar_entradas(db, [identificador]) if tipo == 'licitacion'
                     else ca.cargar_entradas(db, [identificador])).get(str(identificador))
    if tipo == 'compra_agil':
        fila.preseleccion = {'version': ca.version_preseleccion(), 'clasificacion': 'revision_manual',
                             'firma': ca.firma(cargar())}
    db.commit()
    app.dependency_overrides[usuario_actual] = lambda: {
        'id': '11111111-1111-4111-8111-111111111111', 'rol': 'encargado_licitaciones', 'activo': True,
    }
    monkeypatch.setattr(filtradas, 'operar', AsyncMock(return_value={'criterios': [], 'evaluacion': None}))
    route = f'/api/preseleccion/{identificador}/resumen-ia' if tipo == 'licitacion' else f'/api/compras-agiles/{identificador}/resumen-ia'
    detail = f'/api/preseleccion/{identificador}' if tipo == 'licitacion' else f'/api/compras-agiles/{identificador}'
    def body(clasificacion='revision_manual'):
        return {'clasificacion': clasificacion,
                'hash_fuente': firma_fuente(cargar()) if tipo == 'licitacion' else ca.firma(cargar())}
    return db, fila, tipo, cargar, route, detail, body


def lectura():
    return {'sintesis': 'Solicita un salón con coffee break.', 'alertas': [],
            'generado_en': datetime.now(timezone.utc).isoformat(), 'modelo': 'prueba'}


def test_reutiliza_ia_guardada_en_otras_solicitudes_y_al_abrir_la_ficha(oportunidad, client, monkeypatch):
    db, fila, tipo, cargar, route, detail, body = oportunidad
    generar = AsyncMock(return_value=lectura())
    monkeypatch.setattr(ia, 'generar', generar)
    primero = client.post(route, json=body())
    assert primero.status_code == 200, primero.text
    assert primero.json()['cache'] is False
    segundo = client.post(route, json=body())
    assert segundo.status_code == 200, segundo.text
    assert segundo.json()['cache'] is True
    assert segundo.json()['resumen'] == primero.json()['resumen']
    generar.assert_awaited_once()
    visible = client.get(detail)
    assert visible.status_code == 200, visible.text
    guardada = visible.json()['resumen_ia'] if tipo == 'licitacion' else visible.json()['compra_agil']['resumen_ia']
    assert guardada['resumen'] == primero.json()['resumen']
    db.refresh(fila)
    assert set(fila.resumen_ia) == {'firma', 'version_cache', 'resumen'}


def test_reglas_clasificacion_y_verificacion_no_consumen_otra_llamada(oportunidad, client, monkeypatch):
    db, fila, tipo, cargar, route, detail, body = oportunidad
    generar = AsyncMock(return_value=lectura()); monkeypatch.setattr(ia, 'generar', generar)
    assert client.post(route, json=body()).status_code == 200
    fila.normalizado_en = datetime.now(timezone.utc) + timedelta(minutes=1)
    if tipo == 'compra_agil':
        fila.preseleccion = {**fila.preseleccion, 'clasificacion': 'preseleccionada'}
    db.commit()
    monkeypatch.setattr(ia, 'PROMPT_VERSION', 'otra-version-del-prompt')
    respuesta = client.post(route, json=body('preseleccionada'))
    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()['cache'] is True
    generar.assert_awaited_once()


@pytest.mark.parametrize('campo,valor', [('nombre', 'Salón para 80 asistentes'), ('moneda', 'USD')])
def test_cambio_de_la_ficha_oculta_y_reemplaza_el_analisis_anterior(oportunidad, client, monkeypatch, campo, valor):
    db, fila, tipo, cargar, route, detail, body = oportunidad
    generar = AsyncMock(side_effect=[lectura(), {**lectura(), 'sintesis': 'Nuevo análisis actualizado.'}])
    monkeypatch.setattr(ia, 'generar', generar)
    assert client.post(route, json=body()).status_code == 200
    setattr(fila, campo, valor); db.commit()
    visible = client.get(detail)
    cache = visible.json()['resumen_ia'] if tipo == 'licitacion' else visible.json()['compra_agil']['resumen_ia']
    assert cache is None
    respuesta = client.post(route, json=body())
    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()['cache'] is False and generar.await_count == 2
    db.refresh(fila)
    assert fila.resumen_ia['resumen']['sintesis'] == 'Nuevo análisis actualizado.'


def test_preserva_resumenes_del_formato_anterior_sin_generar_otra_vez(oportunidad, client, monkeypatch):
    db, fila, tipo, cargar, route, detail, body = oportunidad
    fuente = ia.fuente_resumen(fila, cargar(), tipo, 'preseleccionada')
    previa = lectura()
    fila.resumen_ia = {'firma': ia.huella(fuente), 'resumen': previa}; db.commit()
    generar = AsyncMock(); monkeypatch.setattr(ia, 'generar', generar)
    respuesta = client.post(route, json=body())
    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json() == {'cache': True, 'resumen': previa}
    generar.assert_not_awaited()
    db.refresh(fila)
    assert fila.resumen_ia['version_cache'] == 2


def test_solicitudes_concurrentes_no_generan_dos_analisis(oportunidad, client, monkeypatch):
    from app.database import engine
    db, fila, tipo, cargar, route, detail, body = oportunidad
    generar = AsyncMock(); monkeypatch.setattr(ia, 'generar', generar)
    namespace = 710265 if tipo == 'licitacion' else 710266
    with engine.begin() as bloqueo:
        assert bloqueo.scalar(text('SELECT pg_try_advisory_xact_lock(:ns,:id)'), {'ns': namespace, 'id': fila.id})
        respuesta = client.post(route, json=body())
        assert respuesta.status_code == 423, respuesta.text
    generar.assert_not_awaited()


def test_no_guarda_una_respuesta_ia_si_la_fuente_cambia_mientras_se_genera(oportunidad, client, monkeypatch):
    db, fila, tipo, cargar, route, detail, body = oportunidad
    async def cambia(_):
        fila.nombre = 'El comprador modificó la solicitud'
        db.commit()
        return lectura()
    monkeypatch.setattr(ia, 'generar', cambia)
    respuesta = client.post(route, json=body())
    assert respuesta.status_code == 409, respuesta.text
    db.refresh(fila)
    assert fila.resumen_ia is None


def test_no_genera_ni_muestra_analisis_de_una_oportunidad_vencida(oportunidad, client, monkeypatch):
    db, fila, tipo, cargar, route, detail, body = oportunidad
    fila.fecha_cierre = datetime(2000, 1, 1); db.commit()
    generar = AsyncMock(); monkeypatch.setattr(ia, 'generar', generar)
    respuesta = client.post(route, json=body())
    assert respuesta.status_code == 410, respuesta.text
    generar.assert_not_awaited()


def test_firma_ia_distingue_cambios_de_items_y_no_ids_internos():
    fila = Licitacion(codigo_externo='100-1-LE26', nombre='Salón', fecha_cierre=datetime(2099, 1, 1))
    entrada = {'items': [{'id': 1, 'licitacion_id': 9, 'descripcion': '40 asistentes'}]}
    firma = ia.firma_ficha(fila, entrada)
    assert ia.firma_ficha(fila, {'items': [{'id': 2, 'licitacion_id': 20, 'descripcion': '40 asistentes'}]}) == firma
    assert ia.firma_ficha(fila, {'items': [{'id': 1, 'licitacion_id': 9, 'descripcion': '80 asistentes'}]}) != firma
