import asyncio
from urllib.parse import parse_qs

import httpx
import pytest

from app.services.bases_mercado_publico import descargar_bases, BasesNoDisponibles, MAX_BYTES

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
