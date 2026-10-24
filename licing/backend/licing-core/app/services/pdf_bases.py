"""Lectura acotada de PDF. El original se conserva fuera de Postgres."""
import hashlib
import json
import os
import subprocess
import sys

MAX_BYTES = 3 * 1024 * 1024
VERSION_EXTRACTOR = "pdf-texto-3"

MOTIVOS_PDF = {
    "pdf_corrupto": "No se pudo abrir el PDF; podría estar corrupto o tener una estructura no compatible.",
    "pdf_protegido": "El PDF está protegido y requiere una contraseña para leerlo.",
    "sin_paginas": "El PDF no contiene páginas que se puedan leer.",
    "sin_texto_legible": "No se encontró texto legible; el PDF podría estar vacío, escaneado o contener solo imágenes.",
    "lectura_parcial": "Solo se pudo leer parte del PDF; hay páginas pendientes de revisión.",
    "limite_paginas": "El PDF supera las 120 páginas admitidas por el lector automático.",
    "limite_tiempo": "La lectura superó el tiempo disponible; no se pudo comprobar el contenido completo.",
    "limite_recursos": "La lectura se interrumpió por los límites de procesamiento; requiere revisión manual.",
    "error_lectura": "No se pudo completar la lectura del PDF; la causa no pudo determinarse.",
}


def entorno_lector():
    # El hijo no hereda sys.path: en Vercel, Core se agrega desde api/index.py y no está en el directorio actual.
    return {**os.environ, "PYTHONPATH": os.pathsep.join(p for p in sys.path if p)}


class _LecturaNoViable(Exception):
    def __init__(self, codigo):
        self.codigo = codigo


def _error(codigo):
    return {"estado_extraccion": "error", "paginas": None, "paginas_texto": [],
            "cobertura": {"motivo_codigo": codigo, "motivo": MOTIVOS_PDF[codigo],
                          "requiere_ocr_o_revision": True, "bases_completas_confirmadas": False}}


def _explicar(salida):
    cobertura = salida.setdefault("cobertura", {})
    if salida["estado_extraccion"] in {"sin_texto", "parcial", "error"}:
        codigo = cobertura.get("motivo_codigo") or {
            "sin_texto": "sin_texto_legible", "parcial": "lectura_parcial", "error": "error_lectura"
        }[salida["estado_extraccion"]]
        cobertura.update(motivo_codigo=codigo, motivo=MOTIVOS_PDF.get(codigo, MOTIVOS_PDF["error_lectura"]),
                         requiere_ocr_o_revision=True)
    return salida


def extraer_pdf(contenido: bytes) -> dict:
    if not contenido or len(contenido) > MAX_BYTES:
        raise ValueError("El PDF debe pesar entre 1 byte y 3 MB.")
    if not contenido.startswith(b"%PDF-"):
        raise ValueError("El archivo no es un PDF.")
    # Aislamiento: un PDF costoso no consume sin límite el proceso de la API.
    try:
        proceso = subprocess.run([sys.executable, "-m", "app.services.pdf_bases"],
                                 input=contenido, capture_output=True, timeout=10, check=False, env=entorno_lector())
        salida = json.loads(proceso.stdout) if proceso.returncode == 0 else _error("limite_recursos" if proceso.returncode < 0 else "error_lectura")
    except subprocess.TimeoutExpired:
        salida = _error("limite_tiempo")
    except ValueError:
        salida = _error("error_lectura")
    if not isinstance(salida, dict) or salida.get("estado_extraccion") not in {"extraido", "parcial", "sin_texto", "error"}:
        salida = _error("error_lectura")
    salida = _explicar(salida)
    salida.update(hash_archivo=hashlib.sha256(contenido).hexdigest(), bytes=len(contenido),
                  version_extractor=VERSION_EXTRACTOR)
    return salida


def _leer(contenido):
    import io
    import resource
    # Límites del hijo en Linux/Vercel; no alteran el servidor principal.
    resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_CPU, (7, 7))
    try:
        return _leer_pypdf(contenido)
    except _LecturaNoViable as exc:
        return _error(exc.codigo)
    except Exception:
        try:
            return _leer_pdfium(contenido)
        except _LecturaNoViable as exc:
            return _error(exc.codigo)
        except Exception:
            return _error("pdf_corrupto")


def _leer_pypdf(contenido):
    import io
    from pypdf import PdfReader
    lector = PdfReader(io.BytesIO(contenido), strict=False)
    if lector.is_encrypted and not lector.decrypt(""):
        raise _LecturaNoViable("pdf_protegido")
    total = len(lector.pages)
    if total < 1:
        raise _LecturaNoViable("sin_paginas")
    if total > 120:
        raise _LecturaNoViable("limite_paginas")
    paginas, pendientes, caracteres = [], [], 0
    for numero, pagina in enumerate(lector.pages, 1):
        contenido_pagina = pagina.get_contents()
        if contenido_pagina is not None and len(contenido_pagina.get_data()) > 4 * 1024 * 1024:
            pendientes.append(numero)
            continue
        texto = (pagina.extract_text() or "").replace("\x00", "")
        if len(texto.strip()) < 30:
            pendientes.append(numero)
        if caracteres + len(texto) > 300000:
            pendientes.extend(range(numero, total + 1))
            break
        caracteres += len(texto)
        paginas.append({"pagina": numero, "texto": texto})
    legible = any(len(p["texto"].strip()) >= 30 for p in paginas)
    return {"estado_extraccion": "sin_texto" if not legible else "parcial" if pendientes else "extraido",
            "paginas": total, "paginas_texto": paginas,
            "cobertura": {"paginas_pendientes": sorted(set(pendientes)), "requiere_ocr_o_revision": bool(pendientes),
                          "bases_completas_confirmadas": False}}


def _leer_pdfium(contenido):
    # Segundo lector para bases con tablas de referencias dañadas. Tampoco hace OCR.
    import pypdfium2
    with pypdfium2.PdfDocument(contenido) as lector:
        total = len(lector)
        if total < 1:
            raise _LecturaNoViable("sin_paginas")
        if total > 120:
            raise _LecturaNoViable("limite_paginas")
        paginas, pendientes, caracteres = [], [], 0
        for numero in range(1, total + 1):
            try:
                with lector[numero-1] as pagina, pagina.get_textpage() as texto_pagina:
                    if texto_pagina.count_chars() > 300000:
                        pendientes.append(numero)
                        continue
                    texto = texto_pagina.get_text_bounded().replace("\x00", "")
                if len(texto.strip()) < 30:
                    pendientes.append(numero)
                if caracteres + len(texto) > 300000:
                    pendientes.extend(range(numero, total + 1))
                    break
                caracteres += len(texto)
                paginas.append({"pagina": numero, "texto": texto})
            except Exception:
                pendientes.append(numero)
        legible = any(len(p["texto"].strip()) >= 30 for p in paginas)
        return {"estado_extraccion": "sin_texto" if not legible else "parcial" if pendientes else "extraido",
                "paginas": total, "paginas_texto": paginas,
                "cobertura": {"lector": "pdfium", "paginas_pendientes": sorted(set(pendientes)),
                              "requiere_ocr_o_revision": bool(pendientes), "bases_completas_confirmadas": False}}


if __name__ == "__main__":
    try:
        print(json.dumps(_leer(sys.stdin.buffer.read(MAX_BYTES + 1)), ensure_ascii=False))
    except Exception:
        # No exponer texto documental ni excepciones del parser a los logs.
        sys.exit(1)
