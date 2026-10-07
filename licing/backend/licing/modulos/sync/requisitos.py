"""Reglas PROVISORIAS de extracción de requisitos (mismas que ingestar_mp_csv).
Las reemplazará el motor IA/NLP (E4); mantener la misma forma de salida."""
import re

_TIPOS = ["jornada", "seminario", "capacitación", "capacitacion", "taller", "congreso",
          "encuentro", "reunión", "reunion", "ceremonia", "conferencia"]
_PERSONAS = re.compile(r"(\d+)\s*personas")
_HABITACIONES = re.compile(r"(\d+)\s*habitaciones")


def servicio_de(t: str) -> str | None:
    if re.search(r"coffee", t):
        return "Coffee break"
    if re.search(r"almuerzo", t):
        return "Almuerzo"
    if re.search(r"\bcena", t):
        return "Cena"
    if re.search(r"c[oó]ctel|coctel", t):
        return "Cóctel"
    if re.search(r"alojamiento|habitaci", t):
        return "Alojamiento"
    if re.search(r"sal[oó]n", t):
        return "Arriendo de salón"
    return None


def _primer_numero(patron: re.Pattern, texto: str) -> int | None:
    m = patron.search(texto)
    return int(m.group(1)) if m and int(m.group(1)) else None


def extraer_requisitos(nombre: str | None, descripcion: str | None, items: list[dict]) -> dict:
    partes = [nombre or "", descripcion or ""] + [f"{i.get('nombre_producto')} {i.get('descripcion')}" for i in items]
    texto = " ".join(partes).lower()
    personas = [int(m.group(1)) for m in _PERSONAS.finditer(texto)]
    tipo = next((t for t in _TIPOS if t in texto), None)
    servicios = []
    for i in items:
        d = f"{i.get('descripcion') or ''} {i.get('nombre_producto') or ''}".lower()
        s = servicio_de(d)
        if not s:
            continue
        servicios.append({
            "servicio": s, "item": i.get("correlativo"), "cantidad": i.get("cantidad"),
            "personas": _primer_numero(_PERSONAS, d), "habitaciones": _primer_numero(_HABITACIONES, d),
        })
    n_asist = max(personas) if personas else None
    return {
        "tipo_evento": tipo, "n_asistentes": n_asist, "servicios_req": servicios,
        "confianza_nlp": 0.5 if n_asist and tipo else 0.3,
    }
