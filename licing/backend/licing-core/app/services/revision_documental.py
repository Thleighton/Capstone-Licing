"""Motivos orientativos; un fallo de lectura no demuestra incumplimiento."""
from .pdf_bases import MOTIVOS_PDF

MOTIVOS_DESCARGA = {
    "archivo_vacio": "La descarga devolvió un archivo vacío (0 bytes).",
    "respuesta_no_pdf": "La descarga no devolvió un PDF reconocible; podría ser una página de error o un archivo dañado.",
    "sin_descarga_publica": "La ficha no ofrece una descarga pública de bases que se haya podido usar.",
    "acceso_restringido": "Mercado Público restringió la descarga; los documentos no pudieron comprobarse.",
    "limite_tamano": "El documento supera los 3 MB admitidos por la descarga automática.",
    "error_temporal": "No se pudo completar la descarga o su guardado; requiere reintento o revisión.",
}


def incidencia_descarga(codigo):
    return {"codigo": codigo, "motivo": MOTIVOS_DESCARGA.get(codigo,
        "No se pudo obtener un PDF verificado de esta licitación; requiere revisión.")}


def incidencia_documento(doc):
    estado = doc.get("estado_extraccion")
    if not doc.get("vigente", True) or estado == "extraido":
        return None
    cobertura = doc.get("cobertura") or {}
    codigo = cobertura.get("motivo_codigo") or {
        "sin_texto": "sin_texto_legible", "parcial": "lectura_parcial", "error": "error_lectura"
    }.get(estado, "error_lectura")
    return {"documento_id": doc["id"], "nombre": doc.get("nombre") or f"Documento {doc['id']}",
            "codigo": codigo, "motivo": MOTIVOS_PDF.get(codigo, MOTIVOS_PDF["error_lectura"]),
            "paginas_pendientes": cobertura.get("paginas_pendientes", [])}


def evaluar_documentacion(datos):
    incidencias = [i for d in datos.get("documentos") or [] if (i := incidencia_documento(d))]
    if datos.get("incidencia_documental"):
        incidencias.append(datos["incidencia_documental"])
    if incidencias:
        primera = incidencias[0]
        prefijo = f"{primera['nombre']}: " if primera.get("nombre") else ""
        motivo = prefijo + primera["motivo"]
        if len(incidencias) > 1:
            motivo += f" Hay {len(incidencias)} incidencias documentales para revisar."
        return {"resultado": "sin_informacion", "requiere_revision": True,
                "motivo": motivo, "incidencias": incidencias}
    return {"resultado": "cumple" if datos.get("documentos") else "sin_informacion",
            "requiere_revision": False, "incidencias": [],
            "motivo": "Sin fallos de lectura registrados." if datos.get("documentos") else "Todavía no hay documentos leídos."}
