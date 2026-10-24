"""Descarga acotada del botón público «Descarga bases», sin evadir desafíos.

No equivale a descargar todos los anexos. El portal puede no ofrecer este botón.
"""
import asyncio
import re
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

import httpx

from .pdf_bases import MAX_BYTES

HOST = "www.mercadopublico.cl"
PATH = "/Procurement/Modules/RFB/DetailsAcquisition.aspx"
TARGET = "descargar_pdf_baseFirmada"


class BasesNoDisponibles(Exception):
    def __init__(self, motivo):
        self.motivo = motivo
        super().__init__(motivo)


class _Ficha(HTMLParser):
    def __init__(self):
        super().__init__()
        self.campos = {}
        self.codigo = ""
        self.en_codigo = False
        self.boton = False
        self.action = ""

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "form":
            self.action = a.get("action", "")
        if tag == "input" and a.get("type", "").lower() == "hidden" and a.get("name"):
            self.campos[a["name"]] = a.get("value", "")
        if tag == "span" and a.get("id") == "lblNumLicitacion":
            self.en_codigo = True
        if a.get("id") == TARGET:
            self.boton = True

    def handle_endtag(self, tag):
        if tag == "span":
            self.en_codigo = False

    def handle_data(self, data):
        if self.en_codigo:
            self.codigo += data


def url_bases(codigo):
    if not re.fullmatch(r"\d+-\d+-[A-Z]+\d+", codigo):
        raise BasesNoDisponibles("codigo_invalido")
    return f"https://{HOST}{PATH}?idlicitacion={codigo}"


def _url_permitida(url):
    p = urlsplit(str(url))
    if (p.scheme != "https" or p.hostname != HOST or p.port not in (None, 443)
            or p.username or p.password or p.path.lower() != PATH.lower()):
        raise BasesNoDisponibles("redireccion_no_admitida")


async def _pedir(cliente, metodo, url, datos=None, limite=MAX_BYTES):
    # Validar cada salto ANTES de enviarlo: ni SSRF ni cookies a otros dominios.
    for _ in range(4):
        _url_permitida(url)
        async with cliente.stream(metodo, url, data=datos, follow_redirects=False) as r:
            if r.status_code in (301, 302, 303, 307, 308):
                destino = r.headers.get("location")
                if not destino:
                    raise BasesNoDisponibles("respuesta_invalida")
                url = urljoin(str(r.url), destino)
                if r.status_code in (301, 302, 303):
                    metodo, datos = "GET", None
                continue
            if r.status_code in (401, 403, 429):
                raise BasesNoDisponibles("acceso_restringido")
            if r.status_code == 404:
                raise BasesNoDisponibles("sin_ficha")
            r.raise_for_status()
            cuerpo = bytearray()
            async for bloque in r.aiter_bytes():
                cuerpo.extend(bloque)
                if len(cuerpo) > limite:
                    raise BasesNoDisponibles("limite_tamano")
            return bytes(cuerpo), str(r.url)
    raise BasesNoDisponibles("demasiadas_redirecciones")


async def descargar_bases(codigo, *, transporte=None):
    origen = url_bases(codigo)
    try:
        async with asyncio.timeout(25):
            async with httpx.AsyncClient(timeout=10, transport=transporte,
                                         headers={"User-Agent": "LICING/1.0 (bases publicas)"}) as cliente:
                html, url = await _pedir(cliente, "GET", origen, limite=2 * 1024 * 1024)
                ficha = _Ficha()
                ficha.feed(html.decode("utf-8", errors="replace"))
                if ficha.codigo.strip().upper() != codigo:
                    raise BasesNoDisponibles("ficha_no_verificada")
                if not ficha.boton:
                    raise BasesNoDisponibles("sin_descarga_publica")
                if not ficha.campos.get("__VIEWSTATE"):
                    raise BasesNoDisponibles("formulario_no_admitido")
                ficha.campos.update(__EVENTTARGET=TARGET, __EVENTARGUMENT="")
                pdf, _ = await _pedir(cliente, "POST", urljoin(url, ficha.action or url), ficha.campos)
                if not pdf:
                    raise BasesNoDisponibles("archivo_vacio")
                if not pdf.startswith(b"%PDF-"):
                    raise BasesNoDisponibles("respuesta_no_pdf")
                return {"contenido": pdf, "url_origen": origen,
                        "nombre": f"Bases_{codigo}.pdf", "tipo": "otro"}
    except (httpx.HTTPError, TimeoutError):
        raise BasesNoDisponibles("error_temporal") from None
