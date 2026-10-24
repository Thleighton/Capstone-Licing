import asyncio
import hashlib
from unittest.mock import AsyncMock, Mock

from app.services import ingesta_documental as servicio
from app.api import preseleccion, cron
from app.config import settings
from app.services.bases_mercado_publico import BasesNoDisponibles

CODIGO = '123-1-LE26'
PDF = b'%PDF-1.7 ejemplo'


def preparar(monkeypatch, *, hashes=None, fallo=None):
    monkeypatch.setattr(settings, 'mp_descarga_portal_habilitada', True)
    tarea = {'id': 1, 'codigo': CODIGO, 'token': 'reserva', 'hashes': hashes or []}
    reservar = Mock(return_value=tarea)
    finalizar = Mock()
    guardar = AsyncMock(return_value={'id': 1})
    monkeypatch.setattr(servicio.origen, 'reservar', reservar)
    monkeypatch.setattr(servicio.origen, 'finalizar', finalizar)
    monkeypatch.setattr(servicio.origen, 'guardar', guardar)
    descarga = AsyncMock(side_effect=fallo) if fallo else AsyncMock(return_value={
        'contenido': PDF, 'nombre': 'bases.pdf', 'tipo': 'otro', 'url_origen': 'https://www.mercadopublico.cl/'})
    monkeypatch.setattr(servicio, 'descargar_bases', descarga)
    extraer = AsyncMock(return_value={'cobertura': {}, 'hash_archivo': hashlib.sha256(PDF).hexdigest(), 'estado_extraccion': 'extraido'})
    monkeypatch.setattr(servicio, 'run_in_threadpool', extraer)
    evaluar = AsyncMock()
    monkeypatch.setattr(preseleccion, 'evaluar_lote', evaluar)
    return finalizar, guardar, extraer, evaluar


def test_descarga_guarda_en_origen_y_reevalua(monkeypatch):
    finalizar, guardar, _, evaluar = preparar(monkeypatch)
    r = asyncio.run(servicio.procesar_documentos(Mock()))
    assert r['procesados'] == 1 and not r['anexos_completos']
    assert guardar.call_args.kwargs['token'] == 'reserva'
    assert not guardar.call_args.kwargs['extraccion']['cobertura']['bases_completas_confirmadas']
    assert finalizar.call_args.args[-1] == 'descargada'
    evaluar.assert_awaited_once()


def test_hash_identico_no_reextrae_ni_duplica(monkeypatch):
    _, guardar, extraer, evaluar = preparar(monkeypatch, hashes=[hashlib.sha256(PDF).hexdigest()])
    r = asyncio.run(servicio.procesar_documentos(Mock()))
    assert r['reutilizado']
    extraer.assert_not_called(); guardar.assert_not_called(); evaluar.assert_awaited_once()


def test_fallo_programa_reintento_sin_dar_por_leidas_las_bases(monkeypatch):
    finalizar, guardar, extraer, evaluar = preparar(monkeypatch, fallo=BasesNoDisponibles('acceso_restringido'))
    r = asyncio.run(servicio.procesar_documentos(Mock()))
    assert r == {'pendiente': True, 'motivo': 'acceso_restringido'}
    assert finalizar.call_args.args[-1] == 'acceso_restringido'
    guardar.assert_not_called(); extraer.assert_not_called(); evaluar.assert_awaited_once()


def test_cron_espera_documentos_en_paralelo_sin_frenar_ingesta(monkeypatch):
    async def escenario():
        iniciada = asyncio.Event()
        async def documentos():
            iniciada.set()
            return {'pendiente': True, 'motivo': 'sin_descarga_publica'}
        async def ingesta(**_):
            await iniciada.wait()
            return {'procesados': 1}
        monkeypatch.setattr(settings, 'documentos_automaticos', True)
        monkeypatch.setattr(cron, 'correr_documentos', documentos)
        monkeypatch.setattr(cron, 'correr_lote', ingesta)
        return await asyncio.wait_for(cron.ingesta_programada(limite=1, db=Mock()), 1)
    r = asyncio.run(escenario())
    assert r['procesados'] == 1 and r['documentos']['pendiente']


def test_documentos_privados(client):
    assert client.post('/api/preseleccion/documentos/obtener').status_code == 401


def test_no_accede_al_portal_ni_a_storage_si_el_canal_no_esta_confirmado(monkeypatch):
    monkeypatch.setattr(settings, 'mp_descarga_portal_habilitada', False)
    descargar = AsyncMock()
    storage = AsyncMock()
    monkeypatch.setattr(servicio, 'descargar_bases', descargar)
    monkeypatch.setattr(servicio.origen, 'storage', storage)
    db = Mock()
    r = asyncio.run(servicio.procesar_documentos(db))
    assert r == {'pendiente': True, 'motivo': 'canal_descarga_no_confirmado'}
    assert asyncio.run(servicio.correr_documentos()) == r
    descargar.assert_not_called(); storage.assert_not_called(); db.assert_not_called()


def test_filtradas_caida_no_impide_confirmar_ingesta_documental(monkeypatch):
    finalizar, guardar, _, evaluar = preparar(monkeypatch)
    evaluar.side_effect = RuntimeError('Filtradas no disponible')
    r = asyncio.run(servicio.procesar_documentos(Mock()))
    assert r['procesados'] == 1 and r['evaluacion']['pendiente']
    assert finalizar.call_args.args[-1] == 'descargada'
    guardar.assert_awaited_once()


def test_turno_documental_corto_libera_reserva_y_devuelve_control_al_cron(monkeypatch):
    finalizar, guardar, _, _ = preparar(monkeypatch)
    monkeypatch.setattr(settings, 'documentos_timeout_segundos', 0.02)
    db=Mock()
    contexto=Mock();contexto.__enter__=Mock(return_value=db);contexto.__exit__=Mock(return_value=False)
    monkeypatch.setattr(servicio, 'SessionLocal', Mock(return_value=contexto))
    monkeypatch.setattr(servicio.origen, 'storage', AsyncMock(return_value={}))
    async def descarga_lenta(*_):
        await asyncio.sleep(1)
    monkeypatch.setattr(servicio,'descargar_bases',descarga_lenta)
    r=asyncio.run(asyncio.wait_for(servicio.correr_documentos(),0.3))
    assert r=={'pendiente':True,'motivo':'tiempo_turno_agotado'}
    assert finalizar.call_args.args[-1]=='error_temporal'
    guardar.assert_not_called()
