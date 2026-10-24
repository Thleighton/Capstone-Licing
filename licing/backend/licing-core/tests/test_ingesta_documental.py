import asyncio
import hashlib
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from app.services import ingesta_documental as servicio
from app.api import preseleccion, cron
from app.config import settings
from app.services.bases_mercado_publico import BasesNoDisponibles

CODIGO = '123-1-LE26'
PDF = b'%PDF-1.7 ejemplo'
FICHA = 'https://www.mercadopublico.cl/Procurement/Modules/RFB/DetailsAcquisition.aspx?idlicitacion=' + CODIGO


def anexo(nombre='Anexo.docx', fecha='09-10-2026 16:17:05'):
    return {'nombre': nombre, 'fecha': fecha, 'categoria': 'tecnico', 'descripcion': 'Anexo Técnico',
            'url_origen': f'{FICHA}#anexo=tecnico/{nombre}'}


def bajar_anexo(_, a):
    if a['nombre'].endswith('.zip'):
        raise BasesNoDisponibles('formato_no_admitido')
    return {'contenido': b'PK\x03\x04' + a['nombre'].encode(), 'nombre': a['nombre'], 'tipo': 'anexo',
            'url_origen': a['url_origen'], 'extension': 'docx'}


def preparar(monkeypatch, *, hashes=None, fallo=None, boton=True, anexos=(), fuentes=(), continuacion=False,
             anexos_habilitados=True):
    monkeypatch.setattr(settings, 'mp_descarga_portal_habilitada', True)
    monkeypatch.setattr(settings, 'mp_descarga_anexos_habilitada', anexos_habilitados)
    tarea = {'id': 1, 'codigo': CODIGO, 'token': 'reserva', 'hashes': list(hashes or []),
             'fuentes': set(fuentes), 'continuacion': continuacion}
    reservar = Mock(return_value=tarea)
    finalizar = Mock()
    guardar = AsyncMock(return_value={'id': 1})
    monkeypatch.setattr(servicio.origen, 'reservar', reservar)
    monkeypatch.setattr(servicio.origen, 'finalizar', finalizar)
    monkeypatch.setattr(servicio.origen, 'guardar', guardar)
    @asynccontextmanager
    async def sesion():
        yield Mock()
    monkeypatch.setattr(servicio.portal, 'sesion', sesion)
    ficha = SimpleNamespace(boton=boton, origen=FICHA)
    monkeypatch.setattr(servicio.portal, 'abrir_ficha',
                        AsyncMock(side_effect=fallo) if fallo else AsyncMock(return_value=ficha))
    monkeypatch.setattr(servicio.portal, 'descargar_bases_ficha', AsyncMock(side_effect=lambda *_: {
        'contenido': PDF, 'nombre': 'bases.pdf', 'tipo': 'otro', 'url_origen': FICHA, 'extension': 'pdf'}))
    monkeypatch.setattr(servicio.portal, 'listar_anexos', AsyncMock(return_value=list(anexos)))
    monkeypatch.setattr(servicio.portal, 'descargar_anexo', AsyncMock(side_effect=bajar_anexo))
    extraer = AsyncMock(side_effect=lambda _, contenido, *__: {
        'cobertura': {}, 'hash_archivo': hashlib.sha256(contenido).hexdigest(), 'estado_extraccion': 'extraido'})
    monkeypatch.setattr(servicio, 'run_in_threadpool', extraer)
    evaluar = AsyncMock()
    monkeypatch.setattr(preseleccion, 'evaluar_lote', evaluar)
    return finalizar, guardar, extraer, evaluar


def test_descarga_guarda_en_origen_y_reevalua(monkeypatch):
    finalizar, guardar, _, evaluar = preparar(monkeypatch)
    r = asyncio.run(servicio.procesar_documentos(Mock()))
    assert r['procesados'] == 1 and r['guardados'] == 1 and not r['anexos_completos']
    assert guardar.call_args.kwargs['token'] == 'reserva' and guardar.call_args.kwargs['extension'] == 'pdf'
    assert not guardar.call_args.kwargs['extraccion']['cobertura']['bases_completas_confirmadas']
    assert finalizar.call_args.args[2] == 'descargada'
    evaluar.assert_awaited_once()


def test_hash_identico_no_reextrae_ni_duplica(monkeypatch):
    _, guardar, extraer, evaluar = preparar(monkeypatch, hashes=[hashlib.sha256(PDF).hexdigest()])
    r = asyncio.run(servicio.procesar_documentos(Mock()))
    assert r['reutilizados'] == 1 and r['guardados'] == 0
    extraer.assert_not_called(); guardar.assert_not_called(); evaluar.assert_awaited_once()


def test_fallo_programa_reintento_sin_dar_por_leidas_las_bases(monkeypatch):
    finalizar, guardar, extraer, evaluar = preparar(monkeypatch, fallo=BasesNoDisponibles('acceso_restringido'))
    r = asyncio.run(servicio.procesar_documentos(Mock()))
    assert r == {'pendiente': True, 'motivo': 'acceso_restringido'}
    assert finalizar.call_args.args[2] == 'acceso_restringido'
    guardar.assert_not_called(); extraer.assert_not_called(); evaluar.assert_awaited_once()


def test_guarda_bases_y_anexos_y_registra_los_omitidos(monkeypatch):
    finalizar, guardar, extraer, _ = preparar(monkeypatch, anexos=[anexo(), anexo('Planilla.zip')])
    r = asyncio.run(servicio.procesar_documentos(Mock()))
    assert r['guardados'] == 2 and r['omitidos'] == [{'nombre': 'Planilla.zip', 'codigo': 'formato_no_admitido'}]
    assert finalizar.call_args.args[2:] == ('descargada', r['omitidos'])
    datos = guardar.call_args_list[1].kwargs
    assert datos['extension'] == 'docx' and datos['tipo'] == 'anexo' and datos['url_origen'].endswith('Anexo.docx')
    assert datos['extraccion']['cobertura']['origen_captura'] == 'portal_anexos'
    assert datos['extraccion']['cobertura']['fecha_portal'] == '09-10-2026 16:17:05'
    assert extraer.call_args_list[0].args[0] is servicio.extraer_pdf
    assert extraer.call_args_list[1].args[0] is servicio.extraer_office


def test_sin_boton_guarda_anexos_y_no_vuelve_a_bajar_los_que_no_cambiaron(monkeypatch):
    sin_cambio, nuevo = anexo('A.docx'), anexo('B.docx')
    preparar(monkeypatch, boton=False, anexos=[sin_cambio, nuevo],
             fuentes=[(sin_cambio['url_origen'], sin_cambio['fecha'])])
    r = asyncio.run(servicio.procesar_documentos(Mock()))
    assert r['guardados'] == 1 and r['reutilizados'] == 1
    servicio.portal.descargar_bases_ficha.assert_not_awaited()
    assert servicio.portal.descargar_anexo.await_args.args[1] is nuevo


def test_bases_ya_guardadas_se_omiten_solo_al_continuar_la_ficha(monkeypatch):
    preparar(monkeypatch, fuentes=[(FICHA, None)], continuacion=True)
    assert asyncio.run(servicio.procesar_documentos(Mock()))['reutilizados'] == 1
    servicio.portal.descargar_bases_ficha.assert_not_awaited()
    # En una revisión posterior las bases se consultan de nuevo para detectar cambios.
    preparar(monkeypatch, fuentes=[(FICHA, None)])
    asyncio.run(servicio.procesar_documentos(Mock()))
    servicio.portal.descargar_bases_ficha.assert_awaited_once()


def test_sin_tiempo_deja_el_resto_de_la_ficha_para_otro_turno(monkeypatch):
    finalizar, guardar, _, _ = preparar(monkeypatch, anexos=[anexo('A.docx'), anexo('B.docx')])
    async def bases_lentas(*_):
        await asyncio.sleep(0.6)
        return {'contenido': PDF, 'nombre': 'bases.pdf', 'tipo': 'otro', 'url_origen': FICHA, 'extension': 'pdf'}
    monkeypatch.setattr(servicio.portal, 'descargar_bases_ficha', bases_lentas)
    async def turno():
        plazo = asyncio.get_running_loop().time() + servicio.MARGEN_DOCUMENTO + 0.5
        return await servicio.procesar_documentos(Mock(), plazo=plazo)
    r = asyncio.run(turno())
    assert r['guardados'] == 1 and r['pendientes'] == 2
    assert finalizar.call_args.args[2] == 'pendiente_continuar'
    guardar.assert_awaited_once()


def test_limite_de_documentos_omite_el_resto_sin_perder_lo_guardado(monkeypatch):
    finalizar, guardar, _, _ = preparar(monkeypatch, anexos=[anexo()])
    guardar.side_effect = [{'id': 1}, servicio.origen.LimiteDocumentos()]
    r = asyncio.run(servicio.procesar_documentos(Mock()))
    assert r['guardados'] == 1 and r['omitidos'] == [{'nombre': 'Anexo.docx', 'codigo': 'limite_documentos'}]
    assert finalizar.call_args.args[2] == 'descargada'


def test_acceso_restringido_en_un_anexo_detiene_el_turno(monkeypatch):
    finalizar, guardar, _, _ = preparar(monkeypatch, anexos=[anexo()])
    servicio.portal.descargar_anexo.side_effect = BasesNoDisponibles('acceso_restringido')
    r = asyncio.run(servicio.procesar_documentos(Mock()))
    assert r == {'pendiente': True, 'motivo': 'acceso_restringido'}
    assert finalizar.call_args.args[2] == 'acceso_restringido'
    guardar.assert_awaited_once()


def test_sin_documentos_utilizables_registra_el_motivo(monkeypatch):
    finalizar, _, _, _ = preparar(monkeypatch, boton=False, anexos=[anexo('Planilla.zip')])
    assert asyncio.run(servicio.procesar_documentos(Mock())) == {'pendiente': True, 'motivo': 'formato_no_admitido'}
    assert finalizar.call_args.args[2] == 'formato_no_admitido'
    preparar(monkeypatch, boton=False, anexos=[anexo()], anexos_habilitados=False)
    assert asyncio.run(servicio.procesar_documentos(Mock())) == {'pendiente': True, 'motivo': 'sin_descarga_publica'}
    servicio.portal.listar_anexos.assert_not_awaited()


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
    abrir = AsyncMock()
    storage = AsyncMock()
    monkeypatch.setattr(servicio.portal, 'abrir_ficha', abrir)
    monkeypatch.setattr(servicio.origen, 'storage', storage)
    db = Mock()
    r = asyncio.run(servicio.procesar_documentos(db))
    assert r == {'pendiente': True, 'motivo': 'canal_descarga_no_confirmado'}
    assert asyncio.run(servicio.correr_documentos()) == r
    abrir.assert_not_called(); storage.assert_not_called(); db.assert_not_called()


def test_filtradas_caida_no_impide_confirmar_ingesta_documental(monkeypatch):
    finalizar, guardar, _, evaluar = preparar(monkeypatch)
    evaluar.side_effect = RuntimeError('Filtradas no disponible')
    r = asyncio.run(servicio.procesar_documentos(Mock()))
    assert r['procesados'] == 1 and r['evaluacion']['pendiente']
    assert finalizar.call_args.args[2] == 'descargada'
    guardar.assert_awaited_once()


def test_turno_documental_corto_libera_reserva_y_devuelve_control_al_cron(monkeypatch):
    finalizar, guardar, _, _ = preparar(monkeypatch)
    monkeypatch.setattr(settings, 'documentos_timeout_segundos', 0.02)
    db=Mock()
    contexto=Mock();contexto.__enter__=Mock(return_value=db);contexto.__exit__=Mock(return_value=False)
    monkeypatch.setattr(servicio, 'SessionLocal', Mock(return_value=contexto))
    monkeypatch.setattr(servicio.origen, 'storage', AsyncMock(return_value={}))
    async def ficha_lenta(*_):
        await asyncio.sleep(1)
    monkeypatch.setattr(servicio.portal, 'abrir_ficha', ficha_lenta)
    r=asyncio.run(asyncio.wait_for(servicio.correr_documentos(),0.3))
    assert r=={'pendiente':True,'motivo':'tiempo_turno_agotado'}
    assert finalizar.call_args.args[-1]=='error_temporal'
    guardar.assert_not_called()
