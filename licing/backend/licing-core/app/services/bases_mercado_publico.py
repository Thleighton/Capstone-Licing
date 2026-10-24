"""Descarga acotada de la ficha pública, sin evadir desafíos.

Obtiene el PDF del botón «Descarga bases» y los anexos de «Antecedentes para incluir en la oferta»
(VerAntecedentes). No consulta «Archivos adjuntos» (ViewAttachment), protegido con reCAPTCHA.
No equivale a descargar todos los anexos. El portal puede no ofrecer estos botones.
"""
import asyncio
import re
from contextlib import asynccontextmanager
from html.parser import HTMLParser
from urllib.parse import quote, urljoin, urlsplit

import httpx

from .lectura_office import FORMATOS
from .pdf_bases import MAX_BYTES

HOST = "www.mercadopublico.cl"
PATH = "/Procurement/Modules/RFB/DetailsAcquisition.aspx"
PATH_ANEXOS = "/Procurement/Modules/Attachment/VerAntecedentes.aspx"
# Solo estas dos páginas: ViewAttachment.aspx exige reCAPTCHA y queda fuera.
RUTAS = {PATH.lower(), PATH_ANEXOS.lower()}
TARGET = "descargar_pdf_baseFirmada"
CATEGORIAS = {"grvAdministrativo": "administrativo", "grvTecnico": "tecnico", "grvEconomico": "economico"}
MAX_PAGINAS_ANEXOS = 10
MAX_ANEXOS = 20


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
        self.anexos = {}

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
        # Cada fila de anexos repite el mismo enlace en dos botones.
        href = a.get("href") or ""
        if tag == "input" and "verantecedentes.aspx" in href.lower():
            self.anexos.setdefault(href, CATEGORIAS.get((a.get("id") or "").split("_")[0], "otro"))

    def handle_endtag(self, tag):
        if tag == "span":
            self.en_codigo = False

    def handle_data(self, data):
        if self.en_codigo:
            self.codigo += data


class _Anexos(HTMLParser):
    """Grilla de VerAntecedentes: nombre, descripción, fecha y botón «Ver» por fila."""
    CAMPOS = {"SourceFileName": "nombre", "FileDescription": "descripcion", "FileDate": "fecha"}

    def __init__(self):
        super().__init__()
        self.campos = {}
        self.action = ""
        self.filas = {}
        self.actual = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "form":
            self.action = a.get("action", "")
        if tag == "input" and a.get("type", "").lower() == "hidden" and a.get("name"):
            self.campos[a["name"]] = a.get("value", "")
        if m := re.fullmatch(r"grdAttachment_(ctl\d+)_grdLbl(\w+)", a.get("id") or ""):
            if m[2] in self.CAMPOS:
                self.actual = (m[1], self.CAMPOS[m[2]])
        if tag == "input" and (m := re.fullmatch(r"grdAttachment\$(ctl\d+)\$grdIbtnView", a.get("name") or "")):
            self.filas.setdefault(m[1], {})["boton"] = m[0]

    def handle_endtag(self, tag):
        if tag == "span":
            self.actual = None

    def handle_data(self, data):
        if self.actual:
            fila = self.filas.setdefault(self.actual[0], {})
            fila[self.actual[1]] = (fila.get(self.actual[1], "") + data).strip()


def url_bases(codigo):
    if not re.fullmatch(r"\d+-\d+-[A-Z]+\d+", codigo):
        raise BasesNoDisponibles("codigo_invalido")
    return f"https://{HOST}{PATH}?idlicitacion={codigo}"


def _url_permitida(url):
    p = urlsplit(str(url))
    if (p.scheme != "https" or p.hostname != HOST or p.port not in (None, 443)
            or p.username or p.password or p.path.lower() not in RUTAS):
        raise BasesNoDisponibles("redireccion_no_admitida")


def _html(cuerpo):
    # Un desafío anti-bot detiene la descarga: no se intenta resolverlo ni rodearlo.
    if b"captcha" in cuerpo.lower():
        raise BasesNoDisponibles("acceso_restringido")
    return cuerpo.decode("utf-8", errors="replace")


async def _pedir(cliente, metodo, url, datos=None, limite=MAX_BYTES):
    # Validar cada salto ANTES de enviarlo: ni SSRF ni cookies a otros dominios.
    try:
        async with asyncio.timeout(15):
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
    except (httpx.HTTPError, TimeoutError):
        raise BasesNoDisponibles("error_temporal") from None


def _validar(contenido, extension):
    if not contenido:
        raise BasesNoDisponibles("archivo_vacio")
    if not contenido.startswith(FORMATOS[extension][1]):
        raise BasesNoDisponibles("respuesta_no_pdf" if extension == "pdf" else "respuesta_no_reconocida")


@asynccontextmanager
async def sesion(transporte=None):
    # Una sesión por turno: la ficha y sus anexos comparten cookies ASP.NET.
    async with httpx.AsyncClient(timeout=10, transport=transporte,
                                 headers={"User-Agent": "LICING/1.0 (bases publicas)"}) as cliente:
        yield cliente


async def abrir_ficha(cliente, codigo):
    origen = url_bases(codigo)
    html, url = await _pedir(cliente, "GET", origen, limite=2 * 1024 * 1024)
    ficha = _Ficha()
    ficha.feed(_html(html))
    if ficha.codigo.strip().upper() != codigo:
        raise BasesNoDisponibles("ficha_no_verificada")
    ficha.url, ficha.origen = url, origen
    return ficha


async def descargar_bases_ficha(cliente, ficha):
    if not ficha.campos.get("__VIEWSTATE"):
        raise BasesNoDisponibles("formulario_no_admitido")
    campos = {**ficha.campos, "__EVENTTARGET": TARGET, "__EVENTARGUMENT": ""}
    pdf, _ = await _pedir(cliente, "POST", urljoin(ficha.url, ficha.action or ficha.url), campos)
    _validar(pdf, "pdf")
    return {"contenido": pdf, "url_origen": ficha.origen, "nombre": f"Bases_{ficha.codigo.strip()}.pdf",
            "tipo": "otro", "extension": "pdf"}


async def listar_anexos(cliente, ficha):
    anexos = []
    for href, categoria in list(ficha.anexos.items())[:MAX_PAGINAS_ANEXOS]:
        html, url = await _pedir(cliente, "GET", urljoin(ficha.url, href), limite=1024 * 1024)
        pagina = _Anexos()
        pagina.feed(_html(html))
        for fila in pagina.filas.values():
            if not fila.get("boton") or not fila.get("nombre"):
                continue
            # Clave estable por anexo: permite versionarlo y no volver a bajarlo si no cambió.
            anexos.append({**fila, "categoria": categoria, "action": urljoin(url, pagina.action or url),
                           "campos": pagina.campos, "url_origen": f"{ficha.origen}#anexo={categoria}/{quote(fila['nombre'], safe='')}"})
    return anexos[:MAX_ANEXOS]


def extension(nombre):
    return nombre.rpartition(".")[2].lower() if "." in nombre else ""


async def descargar_anexo(cliente, anexo):
    ext = extension(anexo["nombre"])
    if ext not in FORMATOS:
        raise BasesNoDisponibles("formato_no_admitido")
    campos = {**anexo["campos"], anexo["boton"] + ".x": "8", anexo["boton"] + ".y": "8"}
    contenido, _ = await _pedir(cliente, "POST", anexo["action"], campos)
    _validar(contenido, ext)
    return {"contenido": contenido, "url_origen": anexo["url_origen"], "nombre": anexo["nombre"][:180],
            "tipo": "anexo", "extension": ext}


async def descargar_bases(codigo, *, transporte=None):
    try:
        async with asyncio.timeout(25), sesion(transporte) as cliente:
            ficha = await abrir_ficha(cliente, codigo)
            if not ficha.boton:
                raise BasesNoDisponibles("sin_descarga_publica")
            return await descargar_bases_ficha(cliente, ficha)
    except TimeoutError:
        raise BasesNoDisponibles("error_temporal") from None
