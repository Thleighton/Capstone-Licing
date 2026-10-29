"""Lectura acotada de bases y anexos públicos, sin evadir desafíos.

Obtiene el PDF del botón «Descarga bases» y los anexos de «Antecedentes para incluir en la oferta»
(VerAntecedentes) y anexos ingresados. Los archivos se solicitan uno a uno; nunca se usa
«Descargar seleccionados». Si el portal solicita CAPTCHA, el análisis se detiene.
"""
import asyncio
import re
import weakref
from contextlib import asynccontextmanager
from html import unescape
from html.parser import HTMLParser
from urllib.parse import quote, unquote, urljoin, urlsplit

import httpx

from ..config import settings
from .lectura_office import FORMATOS
from .pdf_bases import MAX_BYTES

HOST = "www.mercadopublico.cl"
PATH = "/Procurement/Modules/RFB/DetailsAcquisition.aspx"
PATH_ANEXOS = "/Procurement/Modules/Attachment/VerAntecedentes.aspx"
PATH_ADJUNTOS = "/Procurement/Modules/Attachment/ViewAttachment.aspx"
PATH_ADJUNTOS_LISTA = "/Procurement/Modules/Attachment/ViewAttachmentLC.aspx"
RUTAS = {PATH.lower(), PATH_ANEXOS.lower(), PATH_ADJUNTOS.lower(), PATH_ADJUNTOS_LISTA.lower()}
TARGET = "descargar_pdf_baseFirmada"
CATEGORIAS = {"grvAdministrativo": "administrativo", "grvTecnico": "tecnico", "grvEconomico": "economico"}
MAX_PAGINAS_ANEXOS = 10
MAX_ANEXOS = 20
_LIMITADORES_POR_LOOP = weakref.WeakKeyDictionary()


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
        self.adjuntos_url = ""

    def _capturar_adjuntos(self, valor):
        original = unescape(str(valor or "")).replace("\\/", "/").replace("\\u002f", "/").replace("\\u002F", "/")
        original = original.replace("\\u0026", "&").replace("\\u003f", "?").replace("\\u003d", "=")
        # Las fichas antiguas enlazan la grilla con ViewAttachment.aspx y las
        # actuales con ViewAttachmentLC.aspx. Si aparecen ambas, preferir LC.
        patron = r"(?:(?:https?://www\.mercadopublico\.cl)?/)?Procurement/Modules/Attachment/ViewAttachment(?:LC)?\.aspx\?[^'\"\s<>]+"
        for candidato in (original, unquote(original), unquote(unquote(original))):
            matches = list(re.finditer(patron, candidato, re.I))
            if matches:
                m = next((m for m in matches if "viewattachmentlc.aspx" in m.group(0).lower()), matches[0])
                valor_url = m.group(0).rstrip(");,}")
                partes = urlsplit(valor_url)
                nueva_url = (partes.path + ("?" + partes.query if partes.query else "")
                             if partes.scheme else "/" + valor_url.lstrip("/"))
                if self.adjuntos_url and "viewattachmentlc.aspx" in self.adjuntos_url.lower():
                    return
                self.adjuntos_url = nueva_url
                return
            m = re.search(r"ViewAttachment(?:LC)?\.aspx\?[^'\"\s<>]+", candidato, re.I)
            if m:
                if self.adjuntos_url and "viewattachmentlc.aspx" in self.adjuntos_url.lower():
                    return
                self.adjuntos_url = "/Procurement/Modules/Attachment/" + m.group(0).rstrip(");,}")
                return

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        for valor in a.values():
            self._capturar_adjuntos(valor)
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
        self._capturar_adjuntos(data)
        if self.en_codigo:
            self.codigo += data


class _Anexos(HTMLParser):
    """Grilla de VerAntecedentes: nombre, descripción, fecha y botón «Ver» por fila."""
    CAMPOS = {"SourceFileName": "nombre", "FileName": "nombre", "FileDescription": "descripcion",
              "FileDate": "fecha", "FileType": "tipo", "FileSize": "tamano"}

    def __init__(self):
        super().__init__()
        self.campos = {}
        self.action = ""
        self.filas = {}
        self.actual = None
        self.fila_actual = None
        self.celdas = []
        self.celda = None
        self.numero_fila = 0

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "tr":
            self.numero_fila += 1
            row_id = re.search(r"grdAttachment_(ctl\d+)", a.get("id") or "")
            self.fila_actual = row_id[1] if row_id else f"row_{self.numero_fila}"
            self.celdas = []
            self.celda = None
        if tag == "td":
            self.celda = []
        if tag == "form":
            self.action = a.get("action", "")
        if tag == "input" and a.get("type", "").lower() == "hidden" and a.get("name"):
            self.campos[a["name"]] = a.get("value", "")
        if m := re.search(r"(?:^|_)grdAttachment_(ctl\d+)_grdLbl(\w+)$", a.get("id") or ""):
            if m[2] in self.CAMPOS:
                self.actual = (m[1], self.CAMPOS[m[2]])
        nombre_input = a.get("name") or ""
        if tag == "input" and (m := re.search(r"((?:[\w-]+\$)*grdAttachment\$(ctl\d+)\$grdIbtnView)$", nombre_input)):
            self.filas.setdefault(m[2], {})["boton"] = m[1]
        if tag == "input" and (m := re.search(r"(?:^|_)grdAttachment_(ctl\d+)_grdIbtnView$", a.get("id") or "")):
            self.filas.setdefault(m[1], {})["boton"] = f"grdAttachment${m[1]}$grdIbtnView"
        # Mercado Público muestra el icono «Ver» como un enlace directo en
        # algunas versiones y como ImageButton en otras.
        for valor in (a.get("href") or "", a.get("onclick") or ""):
            valor = unescape(valor).replace("\\/", "/").replace("\\u0026", "&")
            # El «Ver» puede incluir la ruta completa o solo el nombre del
            # endpoint. Cada fila trae su propio `enc`; no reutilizar el `enc`
            # de ViewAttachmentLC, que identifica la grilla completa.
            enlace = re.search(
                r"(?:(?:https?://www\.mercadopublico\.cl)?/)?(?:Procurement/Modules/Attachment/)?ViewAttachment(?:LC)?\.aspx\?[^'\"\s<>]+",
                valor, re.I)
            if enlace and self.fila_actual:
                ruta = enlace[0]
                if not re.match(r"https?://", ruta, re.I) and not ruta.startswith("/"):
                    ruta = "/Procurement/Modules/Attachment/" + ruta
                self.filas.setdefault(self.fila_actual, {})["url_archivo"] = ruta
        # Algunas versiones exponen el ImageButton solo dentro de __doPostBack/onclick.
        for valor in (a.get("href") or "", a.get("onclick") or ""):
            evento = re.search(r"((?:[\w-]+\$)*grdAttachment\$(ctl\d+)\$grdIbtnView)", unescape(valor))
            if evento:
                self.filas.setdefault(evento[2], {})["boton"] = evento[1]
        nombre_control = a.get("name") or a.get("id") or ""
        fila = re.search(r"grdAttachment(?:\$|_)(ctl\d+)", nombre_control)
        if fila:
            self.fila_actual = fila[1]
            if tag == "input" and ("view" in nombre_control.lower() or
                    (a.get("type", "").lower() == "image" and "ver" in (a.get("alt", "") + a.get("title", "")).lower())):
                self.filas.setdefault(self.fila_actual, {})["boton"] = (a.get("name") if "$" in nombre_control
                    else f"grdAttachment${self.fila_actual}$grdIbtnView")

    def handle_endtag(self, tag):
        if tag == "td" and self.celda is not None:
            self.celdas.append(" ".join("".join(self.celda).split()))
            self.celda = None
        if tag == "tr":
            if self.fila_actual and (self.filas.get(self.fila_actual, {}).get("boton") or
                                     self.filas.get(self.fila_actual, {}).get("url_archivo")) and len(self.celdas) >= 4:
                celdas = self.celdas
                fila = self.filas.setdefault(self.fila_actual, {})
                if not fila.get("nombre"):
                    offset = 1 if not celdas[0] or celdas[0].lower() in {"sel.", "sel", ""} else 0
                    if len(celdas) - offset >= 3:
                        fila.update(nombre=celdas[offset], tipo=celdas[offset + 1], descripcion=celdas[offset + 2])
                        if len(celdas) > offset + 4:
                            fila["fecha"] = celdas[offset + 4]
        if tag == "span":
            self.actual = None

    def handle_data(self, data):
        if self.celda is not None:
            self.celda.append(data)
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
    return cuerpo.decode("utf-8", errors="replace")


def _captcha_solicitado(cuerpo):
    texto = cuerpo[:1024 * 1024].decode("utf-8", errors="ignore").lower()
    return any(marca in texto for marca in (
        "captcha", "recaptcha", "ingrese el texto de la imagen", "ingrese el código de la imagen",
    ))


def _acceso_denegado(cuerpo):
    """Reconoce la página de bloqueo del portal, incluso cuando responde HTTP 200."""
    texto = cuerpo[:1024 * 1024].decode("utf-8", errors="ignore").lower()
    return "acceso denegado" in texto or "robot.png" in texto


async def _pedir(cliente, metodo, url, datos=None, limite=MAX_BYTES):
    # Validar cada salto ANTES de enviarlo: ni SSRF ni cookies a otros dominios.
    loop = asyncio.get_running_loop()
    estado = _LIMITADORES_POR_LOOP.get(loop)
    if estado is None:
        estado = {"lock": asyncio.Lock(), "ultima_peticion": None}
        _LIMITADORES_POR_LOOP[loop] = estado
    try:
        async with estado["lock"]:
            ultima = estado["ultima_peticion"]
            if ultima is not None:
                espera = settings.mp_pausa_documental_segundos - (loop.time() - ultima)
                if espera > 0:
                    await asyncio.sleep(espera)
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
                                cuerpo = await r.aread()
                                if _captcha_solicitado(cuerpo):
                                    raise BasesNoDisponibles("captcha_requerido")
                                raise BasesNoDisponibles("acceso_portal")
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
            finally:
                estado["ultima_peticion"] = loop.time()
    except (httpx.HTTPError, TimeoutError):
        raise BasesNoDisponibles("error_temporal") from None


def _validar(contenido, extension):
    if not contenido:
        raise BasesNoDisponibles("archivo_vacio")
    if not contenido.startswith(FORMATOS[extension][1]):
        if _captcha_solicitado(contenido):
            raise BasesNoDisponibles("captcha_requerido")
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
    if ficha.adjuntos_url:
        ficha.adjuntos_url = urljoin(f"https://{HOST}", ficha.adjuntos_url)
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


async def listar_adjuntos_ingresados(cliente, ficha):
    if not ficha.adjuntos_url:
        return []
    html, url = await _pedir(cliente, "GET", ficha.adjuntos_url, limite=2 * 1024 * 1024)
    pagina = _Anexos()
    pagina.feed(_html(html))
    if not pagina.filas and _captcha_solicitado(html):
        raise BasesNoDisponibles("captcha_requerido")
    if not pagina.filas and _acceso_denegado(html):
        raise BasesNoDisponibles("acceso_portal")
    adjuntos = []
    for fila in pagina.filas.values():
        nombre = fila.get("nombre")
        boton = fila.get("boton")
        if not nombre or not (boton or fila.get("url_archivo")):
            continue
        url_archivo = fila.get("url_archivo")
        if url_archivo:
            url_archivo = urljoin(url, url_archivo)
        adjuntos.append({**fila, "categoria": "adjunto_ingresado", "action": urljoin(url, pagina.action or url),
                         "campos": pagina.campos,
                         "url_archivo": url_archivo,
                         # The encrypted `enc` URL is transient; keep a stable source link.
                         "url_origen": f"{ficha.origen}#archivo={quote(nombre, safe='')}",
                         "extension": extension(nombre)})
    return adjuntos[:MAX_ANEXOS]


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


async def descargar_adjunto_ingresado(cliente, anexo):
    ext = anexo.get("extension") or extension(anexo["nombre"])
    if ext not in FORMATOS:
        raise BasesNoDisponibles("formato_no_admitido")
    if anexo.get("url_archivo"):
        contenido, _ = await _pedir(cliente, "GET", anexo["url_archivo"])
        _validar(contenido, ext)
        return {"contenido": contenido, "url_origen": anexo["url_origen"],
                "nombre": anexo["nombre"][:180], "tipo": "anexo", "extension": ext}
    if not anexo.get("boton"):
        raise BasesNoDisponibles("respuesta_no_reconocida")
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
