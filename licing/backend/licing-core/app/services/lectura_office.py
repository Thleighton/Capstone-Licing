"""Lectura acotada de anexos Word y Excel (OOXML). Los .doc y .xls antiguos se conservan sin leer."""
import hashlib
import io
import json
import posixpath
import subprocess
import sys
import zipfile
from xml.etree import ElementTree as ET

from .pdf_bases import MAX_BYTES, MOTIVOS_PDF

VERSION_EXTRACTOR = "office-texto-1"
ZIP = b"PK\x03\x04"
OLE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
# Extensión → tipo MIME y firmas admitidas. Un .docx/.xlsx con contraseña llega como contenedor OLE.
FORMATOS = {
    "pdf": ("application/pdf", (b"%PDF-",)),
    "docx": ("application/vnd.openxmlformats-officedocument.wordprocessingml.document", (ZIP, OLE)),
    "xlsx": ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", (ZIP, OLE)),
    "doc": ("application/msword", (OLE,)),
    "xls": ("application/vnd.ms-excel", (OLE,)),
}
MAX_PARTES = 2000
MAX_PARTE = 20 * 1024 * 1024
MAX_DESCOMPRIMIDO = 60 * 1024 * 1024
MAX_HOJAS = 60
MAX_CARACTERES = 300000

MOTIVOS_OFFICE = {
    "documento_corrupto": "No se pudo abrir el documento; podría estar dañado o no ser un archivo de Office válido.",
    "documento_protegido": "El documento está protegido con contraseña y no se pudo leer.",
    "documento_sin_texto": "No se encontró texto legible en el documento.",
    "formato_sin_lector": "Formato antiguo de Office (.doc o .xls): se conservó el original, pero su texto requiere lectura manual.",
    "limite_texto": "El documento supera el texto admitido por el lector automático; solo se leyó una parte.",
}
MOTIVOS = {**MOTIVOS_PDF, **MOTIVOS_OFFICE}


class _LecturaNoViable(Exception):
    def __init__(self, codigo):
        self.codigo = codigo


def _resultado(estado, codigo=None, **cobertura):
    if codigo:
        cobertura.update(motivo_codigo=codigo, motivo=MOTIVOS[codigo], requiere_ocr_o_revision=True)
    return {"estado_extraccion": estado, "paginas": None, "paginas_texto": [],
            "cobertura": {"requiere_ocr_o_revision": False, **cobertura, "bases_completas_confirmadas": False}}


def extraer_office(contenido: bytes, extension: str) -> dict:
    if extension not in {"docx", "xlsx", "doc", "xls"}:
        raise ValueError("Formato de Office no admitido.")
    if not contenido or len(contenido) > MAX_BYTES:
        raise ValueError("El documento debe pesar entre 1 byte y 3 MB.")
    if extension in {"doc", "xls"}:
        salida = _resultado("sin_texto", "formato_sin_lector")
    else:
        # Aislamiento como en los PDF: un archivo costoso no consume sin límite el proceso de la API.
        try:
            proceso = subprocess.run([sys.executable, "-m", "app.services.lectura_office", extension],
                                     input=contenido, capture_output=True, timeout=5, check=False)
            salida = json.loads(proceso.stdout) if proceso.returncode == 0 else _resultado(
                "error", "limite_recursos" if proceso.returncode < 0 else "documento_corrupto")
        except subprocess.TimeoutExpired:
            salida = _resultado("error", "limite_tiempo")
        except ValueError:
            salida = _resultado("error", "documento_corrupto")
        if not isinstance(salida, dict) or salida.get("estado_extraccion") not in {"extraido", "parcial", "sin_texto", "error"}:
            salida = _resultado("error", "documento_corrupto")
    salida["cobertura"]["formato"] = extension
    salida.update(hash_archivo=hashlib.sha256(contenido).hexdigest(), bytes=len(contenido),
                  version_extractor=VERSION_EXTRACTOR)
    return salida


def _local(tag):
    return tag.rpartition("}")[2]


def _parte(libro, nombre):
    try:
        info = libro.getinfo(nombre)
    except KeyError:
        raise _LecturaNoViable("documento_corrupto") from None
    if info.file_size > MAX_PARTE:
        raise _LecturaNoViable("limite_recursos")
    with libro.open(info) as parte:
        return ET.fromstring(parte.read(MAX_PARTE + 1))


def _texto_docx(libro):
    # Recorrido iterativo: sin recursión profunda y sin repetir el texto alternativo (mc:Fallback).
    partes, pila = [], [_parte(libro, "word/document.xml")]
    while pila:
        nodo = pila.pop()
        if nodo is None:
            partes.append("\n")
            continue
        nombre = _local(nodo.tag)
        if nombre == "Fallback":
            continue
        if nombre == "t" and nodo.text:
            partes.append(nodo.text)
        elif nombre == "tab":
            partes.append("\t")
        elif nombre in {"br", "cr"}:
            partes.append("\n")
        elif nombre == "p":
            pila.append(None)
        pila.extend(reversed(nodo))
    return [("", "".join(partes))]


def _texto_rico(nodo):
    # Texto de una cadena de Excel, omitiendo la guía fonética (rPh).
    salida = []
    for hijo in nodo:
        if _local(hijo.tag) == "t":
            salida.append(hijo.text or "")
        elif _local(hijo.tag) == "r":
            salida.extend(t.text or "" for t in hijo if _local(t.tag) == "t")
    return "".join(salida)


def _celda(celda, compartidas):
    tipo = celda.get("t")
    if tipo == "inlineStr":
        return "".join(_texto_rico(h) for h in celda if _local(h.tag) == "is").strip()
    valor = next((h.text for h in celda if _local(h.tag) == "v"), None)
    if valor is None:
        return ""
    if tipo == "s":
        indice = int(valor) if valor.strip().isdigit() else -1
        return compartidas[indice].strip() if 0 <= indice < len(compartidas) else ""
    if tipo == "b":
        return "VERDADERO" if valor.strip() == "1" else "FALSO"
    return valor.strip()


def _texto_xlsx(libro):
    nombres = set(libro.namelist())
    compartidas = [_texto_rico(si) for si in _parte(libro, "xl/sharedStrings.xml")] \
        if "xl/sharedStrings.xml" in nombres else []
    destinos = {r.get("Id"): r.get("Target", "") for r in _parte(libro, "xl/_rels/workbook.xml.rels")}
    hojas = []
    for hoja in (n for n in _parte(libro, "xl/workbook.xml").iter() if _local(n.tag) == "sheet"):
        rid = next((v for k, v in hoja.attrib.items() if _local(k) == "id"), None)
        destino = destinos.get(rid, "")
        ruta = posixpath.normpath(destino.lstrip("/") if destino.startswith("/") else "xl/" + destino)
        if ruta in nombres:
            hojas.append((hoja.get("name") or f"Hoja {len(hojas) + 1}", ruta))
    salida = []
    for nombre, ruta in hojas[:MAX_HOJAS]:
        filas = []
        for fila in (n for n in _parte(libro, ruta).iter() if _local(n.tag) == "row"):
            celdas = [v for c in fila if _local(c.tag) == "c" and (v := _celda(c, compartidas))]
            if celdas:
                filas.append("\t".join(celdas))
        salida.append((f"Hoja: {nombre}\n", "\n".join(filas)))
    return salida


def _leer(formato, contenido):
    try:
        import resource
        # Límites del hijo en Linux/Vercel; no alteran el servidor principal.
        resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024))
        resource.setrlimit(resource.RLIMIT_CPU, (4, 4))
    except ImportError:
        pass
    if contenido.startswith(OLE):
        return _resultado("error", "documento_protegido")
    try:
        with zipfile.ZipFile(io.BytesIO(contenido)) as libro:
            partes = libro.infolist()
            if len(partes) > MAX_PARTES or sum(p.file_size for p in partes) > MAX_DESCOMPRIMIDO:
                raise _LecturaNoViable("limite_recursos")
            unidades = _texto_docx(libro) if formato == "docx" else _texto_xlsx(libro)
    except _LecturaNoViable as exc:
        return _resultado("error", exc.codigo)
    except Exception:
        return _resultado("error", "documento_corrupto")
    paginas, caracteres, recortado = [], 0, False
    for numero, (titulo, texto) in enumerate(unidades, 1):
        texto = (titulo + texto).replace("\x00", "")
        if caracteres + len(texto) > MAX_CARACTERES:
            texto, recortado = texto[:MAX_CARACTERES - caracteres], True
        caracteres += len(texto)
        paginas.append({"pagina": numero, "texto": texto})
        if recortado:
            break
    legible = any(len(p["texto"].strip()) >= 30 for p in paginas)
    estado = "sin_texto" if not legible else "parcial" if recortado else "extraido"
    codigo = {"sin_texto": "documento_sin_texto", "parcial": "limite_texto"}.get(estado)
    unidad = {"unidad": "documento"} if formato == "docx" else {
        "unidad": "hoja", "hojas": [t.removeprefix("Hoja: ").rstrip("\n") for t, _ in unidades]}
    salida = _resultado(estado, codigo, **unidad)
    salida.update(paginas=None if formato == "docx" else len(unidades) or None,
                  paginas_texto=paginas if legible else [])
    return salida


if __name__ == "__main__":
    try:
        # UTF-8 explícito: no depende de la codificación de la consola.
        sys.stdout.buffer.write(json.dumps(_leer(sys.argv[1], sys.stdin.buffer.read(MAX_BYTES + 1)),
                                           ensure_ascii=False).encode("utf-8"))
    except Exception:
        # No exponer texto documental ni excepciones del parser a los logs.
        sys.exit(1)
