import asyncio
from urllib.parse import parse_qs

import httpx
import pytest

from app.services.bases_mercado_publico import (descargar_bases, BasesNoDisponibles, MAX_BYTES, abrir_ficha,
    descargar_anexo, descargar_adjunto_ingresado, listar_adjuntos_ingresados, listar_anexos, sesion)

CODIGO = "564162-152-L126"
FICHA = f'''<form action="DetailsAcquisition.aspx?qs=ejemplo">
<input type="hidden" name="__VIEWSTATE" value="token&amp;1">
<input type="hidden" name="__EVENTVALIDATION" value="validar">
<span id="lblNumLicitacion">{CODIGO}</span>
<a id="descargar_pdf_baseFirmada">Descarga bases</a></form>'''


def test_descarga_preserva_formulario_y_cookie():
    llamadas = []
    def responder(req):
        llamadas.append(req)
        if req.method == "GET":
            return httpx.Response(200, text=FICHA, headers={"set-cookie": "sesion=prueba; Path=/; Secure"})
        assert req.headers["cookie"] == "sesion=prueba"
        formulario = parse_qs(req.content.decode())
        assert formulario["__VIEWSTATE"] == ["token&1"]
        assert formulario["__EVENTTARGET"] == ["descargar_pdf_baseFirmada"]
        return httpx.Response(200, content=b"%PDF-1.7 ejemplo")
    r = asyncio.run(descargar_bases(CODIGO, transporte=httpx.MockTransport(responder)))
    assert r["contenido"].startswith(b"%PDF-") and len(llamadas) == 2
    assert r["url_origen"].endswith("idlicitacion=" + CODIGO)


@pytest.mark.parametrize("url", ["http://www.mercadopublico.cl/", "https://otro.test/a", "https://127.0.0.1/a",
 "https://www.mercadopublico.cl@otro.test/a", "https://www.mercadopublico.cl:444/a"])
def test_no_sigue_redireccion_fuera_de_ficha(url):
    llamadas = []
    def responder(req):
        llamadas.append(req)
        return httpx.Response(302, headers={"location": url})
    with pytest.raises(BasesNoDisponibles, match="redireccion_no_admitida"):
        asyncio.run(descargar_bases(CODIGO, transporte=httpx.MockTransport(responder)))
    assert len(llamadas) == 1


@pytest.mark.parametrize("html,motivo", [
 (FICHA.replace(CODIGO, "1-2-LE26"), "ficha_no_verificada"),
 ("<html>Verifica que no eres un robot</html>", "ficha_no_verificada"),
 (FICHA.replace("descargar_pdf_baseFirmada", "otro"), "sin_descarga_publica"),
 (FICHA.replace("__VIEWSTATE", "otro"), "formulario_no_admitido"),
])
def test_no_descarga_ficha_equivocada_o_sin_acceso(html, motivo):
    def responder(req):
        assert req.method == "GET"
        return httpx.Response(200, text=html)
    with pytest.raises(BasesNoDisponibles, match=motivo):
        asyncio.run(descargar_bases(CODIGO, transporte=httpx.MockTransport(responder)))


@pytest.mark.parametrize("contenido,motivo", [(b"", "archivo_vacio"), (b"<html>captcha</html>", "respuesta_no_pdf"),
 (b"%PDF-" + b"a" * MAX_BYTES, "limite_tamano")])
def test_no_guarda_html_ni_pdf_fuera_de_limite(contenido, motivo):
    def responder(req):
        return httpx.Response(200, text=FICHA) if req.method == "GET" else httpx.Response(200, content=contenido)
    with pytest.raises(BasesNoDisponibles, match=motivo):
        asyncio.run(descargar_bases(CODIGO, transporte=httpx.MockTransport(responder)))


def test_no_consulta_codigos_inyectados():
    with pytest.raises(BasesNoDisponibles, match="codigo_invalido"):
        asyncio.run(descargar_bases("123-1-LE26&otro=1"))


def test_limita_y_clasifica_error_temporal():
    def responder(req):
        raise httpx.ReadTimeout("No exponer detalles", request=req)
    with pytest.raises(BasesNoDisponibles, match="error_temporal"):
        asyncio.run(descargar_bases(CODIGO, transporte=httpx.MockTransport(responder)))


HREF = '../Attachment/VerAntecedentes.aspx?enc=abc%3d'
FICHA_ANEXOS = f'''<form action="DetailsAcquisition.aspx?qs=ejemplo">
<input type="hidden" name="__VIEWSTATE" value="token">
<span id="lblNumLicitacion">{CODIGO}</span>
<input type="image" id="imgAdjuntos" onclick="open('../Attachment/ViewAttachment.aspx?enc=protegido')">
<input type="image" id="grvTecnico_ctl02_grvDescargar" class="fancyAdjunto" href="{HREF}">
<input type="image" id="grvTecnico_ctl02_grvDescargarLink" class="fancyAdjunto" href="{HREF}"></form>'''
ANTECEDENTES = '''<form name="form1" method="post" action="./VerAntecedentes.aspx?enc=abc%3d" id="form1">
<input type="hidden" name="__VIEWSTATE" id="__VIEWSTATE" value="estado">
<table id="grdAttachment"><tr><th>Anexo</th></tr>
<tr><td><span id="grdAttachment_ctl02_grdLblSourceFileName">Anexo técnico.docx</span></td>
<td><span id="grdAttachment_ctl02_grdLblFileDescription">Especificaciones</span></td>
<td><span id="grdAttachment_ctl02_grdLblFileDate">09-10-2026 16:17:05</span></td>
<td><input type="image" name="grdAttachment$ctl02$grdIbtnView" id="grdAttachment_ctl02_grdIbtnView"></td></tr>
<tr><td><span id="grdAttachment_ctl03_grdLblSourceFileName">Planilla.zip</span></td>
<td><input type="image" name="grdAttachment$ctl03$grdIbtnView" id="grdAttachment_ctl03_grdIbtnView"></td></tr>
</table></form>'''


def listar(responder):
    async def flujo():
        async with sesion(httpx.MockTransport(responder)) as cliente:
            ficha = await abrir_ficha(cliente, CODIGO)
            return ficha, await listar_anexos(cliente, ficha)
    return asyncio.run(flujo())


def test_descarga_anexos_de_antecedentes_sin_tocar_adjuntos_protegidos():
    llamadas = []
    def responder(req):
        llamadas.append(req)
        if req.url.path.lower().endswith('detailsacquisition.aspx'):
            return httpx.Response(200, text=FICHA_ANEXOS)
        assert req.url.path.lower().endswith('verantecedentes.aspx')
        if req.method == 'GET':
            return httpx.Response(200, text=ANTECEDENTES)
        formulario = parse_qs(req.content.decode())
        assert formulario['__VIEWSTATE'] == ['estado'] and 'grdAttachment$ctl02$grdIbtnView.x' in formulario
        return httpx.Response(200, content=b'PKdocx')
    async def flujo():
        async with sesion(httpx.MockTransport(responder)) as cliente:
            ficha = await abrir_ficha(cliente, CODIGO)
            anexos = await listar_anexos(cliente, ficha)
            return ficha, anexos, await descargar_anexo(cliente, anexos[0])
    ficha, anexos, descarga = asyncio.run(flujo())
    assert not ficha.boton and [a['nombre'] for a in anexos] == ['Anexo técnico.docx', 'Planilla.zip']
    assert anexos[0]['categoria'] == 'tecnico' and anexos[0]['fecha'] == '09-10-2026 16:17:05'
    assert anexos[0]['url_origen'].endswith('idlicitacion=' + CODIGO + '#anexo=tecnico/Anexo%20t%C3%A9cnico.docx')
    assert descarga['extension'] == 'docx' and descarga['tipo'] == 'anexo' and descarga['contenido'].startswith(b'PK')
    assert not any('viewattachment' in str(r.url).lower() for r in llamadas)
    # Los dos botones de la fila apuntan a la misma ventana: se consulta una sola vez.
    assert sum(r.method == 'GET' and 'verantecedentes' in str(r.url).lower() for r in llamadas) == 1


@pytest.mark.parametrize("respuesta,motivo", [
 (lambda: httpx.Response(200, text='<script src="https://www.google.com/recaptcha/enterprise.js"></script>'), "acceso_restringido"),
 (lambda: httpx.Response(302, headers={"location": "/Procurement/Modules/Attachment/ViewAttachment.aspx?enc=x"}), "redireccion_no_admitida"),
 (lambda: httpx.Response(429), "acceso_restringido"),
])
def test_desafio_o_salto_a_adjuntos_protegidos_detiene_la_lista(respuesta, motivo):
    def responder(req):
        if req.url.path.lower().endswith('detailsacquisition.aspx'):
            return httpx.Response(200, text=FICHA_ANEXOS)
        return respuesta()
    with pytest.raises(BasesNoDisponibles, match=motivo):
        listar(responder)


@pytest.mark.parametrize("nombre,contenido,motivo", [
 ("Planilla.zip", b"PK", "formato_no_admitido"),
 ("Anexo.docx", b"<html>error</html>", "respuesta_no_reconocida"),
 ("Anexo.doc", b"PK", "respuesta_no_reconocida"),
 ("Anexo.xlsx", b"", "archivo_vacio"),
])
def test_anexo_fuera_de_formato_no_se_acepta(nombre, contenido, motivo):
    llamadas = []
    def responder(req):
        llamadas.append(req)
        return httpx.Response(200, content=contenido)
    anexo = {"nombre": nombre, "boton": "grdAttachment$ctl02$grdIbtnView", "campos": {"__VIEWSTATE": "estado"},
             "action": "https://www.mercadopublico.cl/Procurement/Modules/Attachment/VerAntecedentes.aspx?enc=a",
             "url_origen": "https://www.mercadopublico.cl/ficha#anexo=tecnico/x"}
    async def flujo():
        async with sesion(httpx.MockTransport(responder)) as cliente:
            return await descargar_anexo(cliente, anexo)
    with pytest.raises(BasesNoDisponibles, match=motivo):
        asyncio.run(flujo())
    assert len(llamadas) == (0 if motivo == "formato_no_admitido" else 1)


def test_lista_adjuntos_ingresados_y_enlace_directo_ver():
    html_ficha = FICHA.replace('</form>',
        '<input type="image" id="imgAdjuntos" '
        'onclick="open(\'/Procurement/Modules/Attachment/ViewAttachmentLC.aspx?enc=lista\')"></form>')
    html_lista = '''<form action="ViewAttachmentLC.aspx?enc=lista"><table>
    <tr><th>Sel.</th><th>Anexo</th><th>Tipo</th><th>Descripción</th><th>Tamaño</th><th>Fecha</th><th>Acciones</th></tr>
    <tr><td></td><td><span id="grdAttachment_ctl02_grdLblSourceFileName">Bases Hotel.pdf</span></td>
    <td>Otros Anexos</td><td>Bases administrativas</td><td>2640 KB</td><td>21-10-2026</td>
    <td><a href="/Procurement/Modules/Attachment/ViewAttachment.aspx?enc=archivo">Ver</a></td></tr>
    </table></form>'''
    llamadas = []
    def responder(req):
        llamadas.append(req)
        if req.url.path.lower().endswith('detailsacquisition.aspx'):
            return httpx.Response(200, text=html_ficha)
        if req.url.path.lower().endswith('viewattachmentlc.aspx'):
            return httpx.Response(200, text=html_lista)
        assert req.url.path.lower().endswith('viewattachment.aspx')
        return httpx.Response(200, content=b'%PDF-1.7 archivo')
    async def flujo():
        async with sesion(httpx.MockTransport(responder)) as cliente:
            ficha = await abrir_ficha(cliente, CODIGO)
            adjuntos = await listar_adjuntos_ingresados(cliente, ficha)
            archivo = await descargar_adjunto_ingresado(cliente, adjuntos[0])
            return ficha, adjuntos, archivo
    ficha, adjuntos, archivo = asyncio.run(flujo())
    assert ficha.adjuntos_url.endswith('ViewAttachmentLC.aspx?enc=lista')
    assert [a['nombre'] for a in adjuntos] == ['Bases Hotel.pdf']
    assert archivo['contenido'].startswith(b'%PDF-')
    assert [r.method for r in llamadas] == ['GET', 'GET', 'GET']
