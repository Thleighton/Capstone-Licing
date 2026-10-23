import io
import subprocess

import pytest
from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject

from app.services.pdf_bases import extraer_pdf, MAX_BYTES


def pdf(texto=None, protegido=False):
    writer = PdfWriter()
    page = writer.add_blank_page(width=600, height=800)
    if texto:
        font = DictionaryObject({NameObject('/Type'): NameObject('/Font'), NameObject('/Subtype'): NameObject('/Type1'), NameObject('/BaseFont'): NameObject('/Helvetica')})
        page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'): DictionaryObject({NameObject('/F1'): writer._add_object(font)})})
        stream = DecodedStreamObject(); stream.set_data(f'BT /F1 12 Tf 40 700 Td ({texto}) Tj ET'.encode())
        page[NameObject('/Contents')] = writer._add_object(stream)
    if protegido:
        writer.encrypt('secret')
    buffer = io.BytesIO(); writer.write(buffer)
    return buffer.getvalue()


def test_texto_y_evidencia_por_pagina():
    data = pdf('Arriendo de salon en Santiago para 50 personas.')
    result = extraer_pdf(data)
    assert result['estado_extraccion'] == 'extraido'
    assert result['paginas_texto'][0]['pagina'] == 1
    assert '50 personas' in result['paginas_texto'][0]['texto']
    assert len(result['hash_archivo']) == 64
    assert result['cobertura']['bases_completas_confirmadas'] is False


def test_escaneado_no_se_declara_leido():
    result = extraer_pdf(pdf())
    assert result['estado_extraccion'] == 'sin_texto'
    assert result['cobertura']['paginas_pendientes'] == [1]


@pytest.mark.parametrize('data', [b'not a PDF', b'%PDF-' + b'x' * MAX_BYTES])
def test_archivo_invalido(data):
    with pytest.raises(ValueError):
        extraer_pdf(data)


def test_protegido_o_corrupto_queda_pendiente():
    assert extraer_pdf(pdf(protegido=True))['estado_extraccion'] == 'error'
    assert extraer_pdf(b'%PDF-corrupto')['estado_extraccion'] == 'error'


def test_limite_de_tiempo(monkeypatch):
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired('pdf', 10)
    monkeypatch.setattr(subprocess, 'run', timeout)
    assert extraer_pdf(pdf())['estado_extraccion'] == 'error'
