"""Evidencia geográfica del objeto comprado; no certifica el lugar del servicio.

Catálogo territorial: https://www.bcn.cl/siit/mapoteca/comunas
Las menciones, negaciones y direcciones de visita requieren revisión contextual.
"""
import re
import unicodedata

VERSION_UBICACION = "ubicacion-texto-2"
MAX_EVIDENCIAS = 64

REGIONES = {
    "15": ("Arica y Parinacota",), "01": ("Tarapacá",),
    "02": ("Antofagasta",), "03": ("Atacama",), "04": ("Coquimbo",),
    "05": ("Valparaíso",), "06": ("O'Higgins", "O’Higgins", "O Higgins"),
    "07": ("Maule",), "16": ("Ñuble",), "08": ("Biobío", "Bío Bío", "Bio-Bio"),
    "09": ("Araucanía",), "14": ("Los Ríos",), "10": ("Los Lagos",),
    "11": ("Aysén", "Aisén"), "12": ("Magallanes",),
    "13": ("Región Metropolitana de Santiago", "Región Metropolitana", "R.M.", "RM"),
}

COMUNAS_RM = (
    "Alhué", "Buin", "Calera de Tango", "Cerrillos", "Cerro Navia", "Colina",
    "Conchalí", "Curacaví", "El Bosque", "El Monte", "Estación Central",
    "Huechuraba", "Independencia", "Isla de Maipo", "La Cisterna", "La Florida",
    "La Granja", "Lampa", "La Pintana", "La Reina", "Las Condes", "Lo Barnechea",
    "Lo Espejo", "Lo Prado", "Macul", "Maipú", "María Pinto", "Melipilla", "Ñuñoa",
    "Padre Hurtado", "Paine", "Pedro Aguirre Cerda", "Peñaflor", "Peñalolén",
    "Pirque", "Providencia", "Pudahuel", "Puente Alto", "Quilicura", "Quinta Normal",
    "Recoleta", "Renca", "San Bernardo", "San Joaquín", "San José de Maipo",
    "San Miguel", "San Pedro", "San Ramón", "Santiago", "Talagante", "Tiltil", "Vitacura",
)


def _texto_busqueda(texto):
    """Conserva el mapa al texto original, incluso con acentos descompuestos."""
    salida, posiciones = [], []
    for indice, caracter in enumerate(texto):
        normalizado = "".join(c for c in unicodedata.normalize("NFKD", caracter.casefold())
                              if not unicodedata.combining(c))
        if not normalizado and posiciones:
            posiciones[-1] = (posiciones[-1][0], indice + 1)
        for c in normalizado:
            salida.append(c)
            posiciones.append((indice, indice + 1))
    return "".join(salida), posiciones


def _patron(alias):
    normalizado = _texto_busqueda(alias)[0]
    patron = re.escape(normalizado).replace(r"\ ", r"\s+")
    if alias == "Tiltil":
        patron = r"til\s*til"
    if alias == "San Pedro":
        patron += r"(?!\s+de\s+(?:atacama|la\s+paz)\b)"
    return r"(?<!\w)" + patron + r"(?!\w)"


CATALOGO = [("region", codigo, None, re.compile("|".join(
    _patron(alias) for alias in sorted(aliases, key=len, reverse=True))))
    for codigo, aliases in REGIONES.items()]
CATALOGO += [("comuna", "13", nombre, re.compile(_patron(nombre))) for nombre in COMUNAS_RM]
# Reconocer topónimos completos antes de sus palabras parciales.
TOPONIMOS = (("San Pedro de Atacama", "02"), ("San Pedro de la Paz", "08"),
             ("Santiago de Compostela", None), ("Santiago del Estero", None), ("Santiago de Cuba", None))


def _campos(detalle):
    for campo in ("Nombre", "Descripcion", "DireccionEntrega", "DireccionVisita"):
        if isinstance(detalle.get(campo), str) and detalle[campo].strip():
            yield campo, detalle[campo]
    items = detalle.get("Items")
    listado = items.get("Listado") if isinstance(items, dict) else None
    for posicion, item in enumerate(listado if isinstance(listado, list) else [], 1):
        if not isinstance(item, dict):
            continue
        for campo in ("NombreProducto", "Descripcion"):
            if isinstance(item.get(campo), str) and item[campo].strip():
                yield f"Items.Listado[{posicion - 1}].{campo}", item[campo]


def extraer_ubicacion(detalle, raw_id=None):
    regiones, comunas, evidencias = set(), set(), []
    total = 0
    for campo, texto in _campos(detalle):
        normalizado, posiciones = _texto_busqueda(texto)
        hallazgos = []
        completos = [(m.start(), m.end(), nombre, region) for nombre, region in TOPONIMOS
                     for m in re.finditer(_patron(nombre), normalizado)]
        for a, b, nombre, region in completos:
            if region:
                hallazgos.append((posiciones[a][0], posiciones[b-1][1], "comuna", region, nombre))
        for tipo, region, comuna, patron in CATALOGO:
            for match in patron.finditer(normalizado):
                if any(a <= match.start() and b >= match.end() for a, b, _, _ in completos):
                    continue
                inicio, fin = posiciones[match.start()][0], posiciones[match.end() - 1][1]
                hallazgos.append((inicio, fin, tipo, region, comuna))
        for inicio, fin, tipo, region, comuna in sorted(hallazgos):
            # El nombre completo de la región no demuestra una comuna concreta.
            if tipo == "comuna" and any(t == "region" and a <= inicio and b >= fin
                                        for a, b, t, _, _ in hallazgos):
                continue
            regiones.add(region)
            if comuna:
                comunas.add(comuna)
            total += 1
            if len(evidencias) < MAX_EVIDENCIAS:
                evidencias.append({"campo": campo, "inicio": inicio, "fin": fin,
                    "texto": texto[inicio:fin], "contexto": texto[max(0, inicio-120):fin+120],
                    "tipo": tipo, "region_candidata": region, "comuna_candidata": comuna,
                    "uso": "visita" if campo == "DireccionVisita" else
                           "entrega" if campo == "DireccionEntrega" else "mencion"})
    return {"version": VERSION_UBICACION, "raw_id": raw_id,
            "estado": "por_revisar" if total else "no_informada",
            "regiones_candidatas": sorted(regiones), "comunas_candidatas": sorted(comunas),
            "evidencias": evidencias, "truncada": total > len(evidencias)}
