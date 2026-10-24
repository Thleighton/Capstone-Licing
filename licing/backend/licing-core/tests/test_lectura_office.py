import io
import zipfile

import pytest

from app.services.lectura_office import OLE, extraer_office
from app.services.revision_documental import incidencia_documento

W = ('xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
     'xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006"')
S = ('xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
     'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"')


def ooxml(partes):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as libro:
        for nombre, contenido in partes.items():
            libro.writestr(nombre, contenido)
    return buffer.getvalue()


def docx(cuerpo):
    return ooxml({'word/document.xml': f'<w:document {W}><w:body>{cuerpo}</w:body></w:document>'})


def xlsx():
    return ooxml({
        'xl/workbook.xml': f'<workbook {S}><sheets><sheet name="Oferta" sheetId="1" r:id="rId1"/>'
                           '<sheet name="Vacía" sheetId="2" r:id="rId2"/></sheets></workbook>',
        'xl/_rels/workbook.xml.rels': '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                                      '<Relationship Id="rId1" Type="hoja" Target="worksheets/sheet1.xml"/>'
                                      '<Relationship Id="rId2" Type="hoja" Target="/xl/worksheets/sheet2.xml"/></Relationships>',
        'xl/sharedStrings.xml': f'<sst {S}><si><t>Desayuno buffet</t></si>'
                                '<si><r><t>Almuerzo </t></r><r><t>ejecutivo</t></r><rPh><t>fonético</t></rPh></si></sst>',
        'xl/worksheets/sheet1.xml': f'<worksheet {S}><sheetData><row><c t="s"><v>0</v></c><c><v>120</v></c></row>'
                                    '<row><c t="s"><v>1</v></c><c t="inlineStr"><is><t>personas por jornada</t></is></c>'
                                    '<c t="b"><v>1</v></c></row></sheetData></worksheet>',
        'xl/worksheets/sheet2.xml': f'<worksheet {S}><sheetData/></worksheet>',
    })


def test_word_conserva_parrafos_y_tablas_sin_repetir_texto_alternativo():
    data = docx('<w:p><w:r><w:t>Servicio de coffee break para</w:t></w:r><w:r><w:tab/><w:t>80 personas en Santiago.</w:t></w:r></w:p>'
                '<w:tbl><w:tr><w:tc><w:p><w:r><w:t>Salón principal</w:t></w:r></w:p></w:tc></w:tr></w:tbl>'
                '<w:p><mc:AlternateContent><mc:Choice><w:r><w:t>Caja de texto</w:t></w:r></mc:Choice>'
                '<mc:Fallback><w:r><w:t>Caja de texto</w:t></w:r></mc:Fallback></mc:AlternateContent></w:p>')
    r = extraer_office(data, 'docx')
    texto = r['paginas_texto'][0]['texto']
    assert r['estado_extraccion'] == 'extraido' and r['paginas'] is None
    assert 'coffee break para\t80 personas' in texto and 'Salón principal' in texto
    assert texto.count('Caja de texto') == 1
    assert r['cobertura']['formato'] == 'docx' and r['cobertura']['bases_completas_confirmadas'] is False
    assert len(r['hash_archivo']) == 64


def test_excel_lee_cada_hoja_como_pagina():
    r = extraer_office(xlsx(), 'xlsx')
    assert r['estado_extraccion'] == 'extraido' and r['paginas'] == 2
    assert r['cobertura']['unidad'] == 'hoja' and r['cobertura']['hojas'] == ['Oferta', 'Vacía']
    texto = r['paginas_texto'][0]['texto']
    assert texto.startswith('Hoja: Oferta\n') and 'Desayuno buffet\t120' in texto
    assert 'Almuerzo ejecutivo\tpersonas por jornada\tVERDADERO' in texto and 'fonético' not in texto


def test_texto_excesivo_se_recorta_y_queda_parcial():
    r = extraer_office(docx(f'<w:p><w:r><w:t>{"servicio " * 40000}</w:t></w:r></w:p>'), 'docx')
    assert r['estado_extraccion'] == 'parcial' and r['cobertura']['motivo_codigo'] == 'limite_texto'
    assert len(r['paginas_texto'][0]['texto']) == 300000


@pytest.mark.parametrize('contenido,extension,estado,codigo', [
    (OLE + b'cifrado', 'docx', 'error', 'documento_protegido'),
    (b'PK\x03\x04roto', 'xlsx', 'error', 'documento_corrupto'),
    (OLE + b'antiguo', 'doc', 'sin_texto', 'formato_sin_lector'),
    (docx('<w:p><w:r><w:t>Anexo</w:t></w:r></w:p>'), 'docx', 'sin_texto', 'documento_sin_texto'),
    (ooxml({'word/document.xml': '<a/>', 'relleno.bin': b'\0' * (61 * 1024 * 1024)}), 'docx', 'error', 'limite_recursos'),
], ids=['protegido', 'corrupto', 'antiguo', 'sin_texto', 'zip_inflado'])
def test_documento_no_legible_queda_para_revision_con_motivo(contenido, extension, estado, codigo):
    r = extraer_office(contenido, extension)
    assert r['estado_extraccion'] == estado and r['paginas_texto'] == []
    assert r['cobertura']['motivo_codigo'] == codigo and r['cobertura']['requiere_ocr_o_revision']
    incidencia = incidencia_documento({'id': 1, 'nombre': 'Anexo', 'estado_extraccion': estado, 'cobertura': r['cobertura']})
    assert incidencia['codigo'] == codigo and incidencia['motivo'] == r['cobertura']['motivo']


@pytest.mark.parametrize('contenido,extension', [(b'', 'docx'), (b'PK', 'zip'), (b'P' * (3 * 1024 * 1024 + 1), 'xlsx')],
                         ids=['vacio', 'extension', 'tamano'])
def test_entrada_invalida(contenido, extension):
    with pytest.raises(ValueError):
        extraer_office(contenido, extension)
