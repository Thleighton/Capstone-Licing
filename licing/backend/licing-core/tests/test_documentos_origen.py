import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select, text

from app.models.licitacion import Licitacion
from app.models.licitacion_documento import LicitacionDocumento
from app.models.raw import RawMercadoPublico
from app.services import documentos_origen as origen
from app.services.limpieza import eliminar_no_disponibles
from app.api.preseleccion import cargar_entradas, firma_fuente


@pytest.fixture
def lic(integration_db, monkeypatch):
    db = integration_db
    raw = RawMercadoPublico(fuente='licitaciones', tipo_consulta='detalle_codigo', codigo_externo='123-1-LE26',
        respuesta={'CodigoExterno': '123-1-LE26'}, http_status=200, consultado_en=datetime.now(timezone.utc))
    db.add(raw); db.flush()
    fila = Licitacion(codigo_externo='123-1-LE26', raw_id=raw.id, nombre='Salón', codigo_estado=5,
                     fecha_cierre=datetime(2099,1,1))
    db.add(fila); db.commit()
    monkeypatch.setattr(origen, 'storage', AsyncMock(return_value={'guardado': True}))
    return fila


def extraccion(huella='a'*64):
    return {'hash_archivo': huella, 'version_extractor': 'prueba', 'estado_extraccion': 'extraido',
        'paginas': 2, 'cobertura': {}, 'paginas_texto': [
            {'pagina': 1, 'texto': 'Servicio de salón en Santiago.'},
            {'pagina': 2, 'texto': 'Se requiere desayuno para 40 personas.'}]}


def guardar(db, lic, huella='a'*64):
    return asyncio.run(origen.guardar(db, lic.id, 'Bases.pdf', 'bases_tecnicas',
        'https://www.mercadopublico.cl/bases', b'%PDF-prueba', extraccion(huella)))


def test_documento_se_guarda_junto_a_licitacion_sin_repetir_texto(integration_db, lic):
    guardado = guardar(integration_db, lic)
    doc = integration_db.get(LicitacionDocumento, guardado['id'])
    assert doc.licitacion_id == lic.id
    assert 'Se requiere desayuno' in doc.texto_extraido
    assert 'paginas_texto' not in doc.cobertura
    assert origen.cargar(integration_db, [lic.id])[lic.id][0]['paginas_texto'] == extraccion()['paginas_texto']
    origen.storage.assert_awaited_once()


def test_hash_repetido_no_duplica_y_version_cambiada_se_conserva(integration_db, lic):
    a = guardar(integration_db, lic)
    assert guardar(integration_db, lic)['id'] == a['id']
    b = guardar(integration_db, lic, 'b'*64)
    assert b['id'] != a['id']
    assert integration_db.get(LicitacionDocumento, b['id']).version == 2


def test_control_de_descarga_no_cambia_firma_pero_documento_si(integration_db, lic):
    def firma(): return firma_fuente(cargar_entradas(integration_db, [lic.id])[str(lic.id)])
    inicial = firma()
    tarea = origen.reservar(integration_db)
    assert tarea['id'] == lic.id and firma() == inicial
    assert origen.reservar(integration_db) is None
    guardar(integration_db, lic)
    assert firma() != inicial
    origen.finalizar(integration_db, tarea, 'descargada')
    assert origen.reservar(integration_db) is None


def test_limpieza_de_licitacion_elimina_documentos(integration_db, lic):
    doc = guardar(integration_db, lic)
    eliminar_no_disponibles(integration_db, lic.codigo_externo, confirmada=True)
    integration_db.flush(); integration_db.expire_all()
    assert integration_db.get(LicitacionDocumento, doc['id']) is None


def test_estado_error_persiste_para_reintentar(integration_db, lic):
    tarea = origen.reservar(integration_db)
    origen.finalizar(integration_db, tarea, 'sin_descarga_publica')
    integration_db.refresh(lic)
    assert lic.ingesta_documental['estado'] == 'sin_descarga_publica'
    assert origen.reservar(integration_db) is None


def test_sin_storage_no_se_crea_registro_falso(integration_db, lic, monkeypatch):
    monkeypatch.setattr(origen, 'storage', AsyncMock(side_effect=origen.StorageNoDisponible('Sin conexión')))
    with pytest.raises(origen.StorageNoDisponible): guardar(integration_db, lic)
    assert list(integration_db.scalars(select(LicitacionDocumento))) == []


def test_anexo_versiona_su_origen_sin_retirar_bases_y_continua_la_captura(integration_db, lic):
    tarea = origen.reservar(integration_db)
    ficha = 'https://www.mercadopublico.cl/ficha'
    def automatico(huella, url, captura, extension='pdf', fecha=None):
        datos = {**extraccion(huella), 'cobertura': {'origen_captura': captura, 'fecha_portal': fecha}}
        return asyncio.run(origen.guardar(integration_db, lic.id, 'Documento', 'anexo', url, b'x', datos,
                                          token=tarea['token'], extension=extension))
    bases = automatico('a'*64, ficha, 'portal_bases')
    automatico('b'*64, ficha + '#anexo=tecnico/A.docx', 'portal_anexos', 'docx', '09-10-2026 16:17:05')
    nueva = automatico('c'*64, ficha + '#anexo=tecnico/A.docx', 'portal_anexos', 'docx', '10-10-2026 10:00:00')
    vigentes = {d.id: d for d in integration_db.scalars(select(LicitacionDocumento).where(LicitacionDocumento.vigente))}
    assert set(vigentes) == {bases['id'], nueva['id']}
    assert vigentes[nueva['id']].storage_path == f"123-1-LE26/{'c'*64}.docx" and vigentes[nueva['id']].version == 2
    origen.finalizar(integration_db, tarea, 'pendiente_continuar', [{'nombre': 'B.zip', 'codigo': 'formato_no_admitido'}])
    siguiente = origen.reservar(integration_db)
    assert siguiente['id'] == lic.id and siguiente['continuacion']
    assert {(ficha, None), (ficha + '#anexo=tecnico/A.docx', '10-10-2026 10:00:00')} <= siguiente['fuentes']
    origen.finalizar(integration_db, siguiente, 'descargada', [{'nombre': 'C.rar', 'codigo': 'formato_no_admitido'}])
    integration_db.refresh(lic)
    assert lic.ingesta_documental['estado'] == 'descargada' and 'omitidos' not in lic.ingesta_documental
    assert [o['nombre'] for o in lic.ingesta_documental['incidencia_documental']['omitidos']] == ['B.zip', 'C.rar']
    assert origen.incidencias(integration_db, [lic.id])[lic.id][0]['codigo'] == 'documentos_omitidos'
