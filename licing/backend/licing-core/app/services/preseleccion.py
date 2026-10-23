"""Preselección conservadora sobre datos guardados; sin escrituras ni llamadas externas."""
from datetime import datetime
from functools import cache
import hashlib
import json
from pathlib import Path
import re
import unicodedata
from zoneinfo import ZoneInfo

CHILE = ZoneInfo("America/Santiago")
CATALOGO = Path(__file__).resolve().parents[1] / "data" / "preseleccion_hotel_v1.json"
MAX_CAMPO = 12000
MAX_ITEMS = 200


def normalizar_texto(texto: str) -> str:
    texto = re.sub(r"\br\s*\.\s*m\s*\.", "RM", texto, flags=re.I)
    return "".join(c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c)).lower()


@cache
def cargar_catalogo() -> dict:
    return json.loads(CATALOGO.read_text(encoding="utf-8"))


@cache
def _patrones():
    c = cargar_catalogo()
    grupos = [(g, [re.compile(p) for p in g["patrones"]]) for g in c["grupos"]]
    ambiguedades = [(a, re.compile(a["patron"])) for a in c["ambiguedades"]]
    lugares = {}
    for comuna in c["comunas_rm"]:
        lugares[normalizar_texto(comuna)] = ("rm", comuna, "Metropolitana")
    for alias, nombre in c["aliases_rm"].items():
        lugares[alias] = ("rm", nombre, "Metropolitana")
    for ciudad, region in c["ciudades_fuera_rm"].items():
        lugares[normalizar_texto(ciudad)] = ("fuera_rm", ciudad, region)
    for region in c["regiones_fuera_rm"]:
        nombre = normalizar_texto(region).replace("’", "'")
        for prefijo in ("region de ", "region del ", "region de la "):
            lugares[prefijo + nombre] = ("fuera_rm", None, region)
    patron_lugares = re.compile(r"\b(?:" + "|".join(re.escape(x) for x in sorted(lugares, key=len, reverse=True)) + r")\b")
    return grupos, ambiguedades, lugares, patron_lugares


def _campos(datos: dict):
    campos, parcial = [], False
    for nombre in ("nombre", "descripcion"):
        valor = datos.get(nombre)
        if isinstance(valor, str) and valor.strip():
            parcial |= len(valor) > MAX_CAMPO
            campos.append((nombre, valor[:MAX_CAMPO]))
    items = datos.get("items") or []
    parcial |= len(items) > MAX_ITEMS
    for n, item in enumerate(items[:MAX_ITEMS]):
        for nombre in ("nombre_producto", "descripcion", "categoria"):
            valor = item.get(nombre)
            if isinstance(valor, str) and valor.strip():
                parcial |= len(valor) > MAX_CAMPO
                campos.append((f"items[{n}].{nombre}", valor[:MAX_CAMPO]))
    return campos, parcial


def textos_servicio(datos: dict) -> list[dict]:
    """Excluye nombres y domicilios administrativos del comprador."""
    return [{"fuente": fuente, "texto": texto} for fuente, texto in _campos(datos)[0]]


def _fragmento(texto: str, inicio: int, fin: int) -> str:
    return texto[max(0, inicio - 110):min(len(texto), fin + 150)].strip()


def detectar_pertinencia(datos: dict) -> dict:
    grupos, ambiguedades, _, _ = _patrones()
    coincidencias, dudas = [], []
    for fuente, texto in _campos(datos)[0]:
        normal = normalizar_texto(texto)
        for grupo, patrones in grupos:
            for patron in patrones:
                m = patron.search(normal)
                if m:
                    coincidencias.append({"grupo": grupo["id"], "nivel": grupo["nivel"], "fuente": fuente,
                        "termino": m.group(), "evidencia": _fragmento(texto, m.start(), m.end())})
        # Un código UNSPSC genérico no identifica el objeto concreto de la contratación.
        if not fuente.endswith(("categoria", "nombre_producto")):
            for regla, patron in ambiguedades:
                m = patron.search(normal)
                if m:
                    dudas.append({"codigo": regla["id"], "motivo": regla["motivo"], "fuente": fuente,
                        "evidencia": _fragmento(texto, m.start(), m.end())})
    directas = [x for x in coincidencias if x["nivel"] == "directa"
        and not x["fuente"].endswith(("categoria", "nombre_producto"))]
    # El título de una línea genérica puede ser la única información disponible: conserva para revisar.
    return {"grupos": sorted({x["grupo"] for x in coincidencias}), "directa": bool(directas),
        "coincidencias": coincidencias[:100], "ambiguedades": dudas[:30]}


_SERVICIO = re.compile(r"\b(?:servicios?|alojamiento|hospedaje|hoteles?|habitacion(?:es)?|estadia|salon(?:es)?|salas?|recintos?|espacios?|auditorios?|jornadas?|eventos?|reunion(?:es)?|seminarios?|encuentros?|ceremonias?|realizara|desarrollara)\b")
_RELACION = re.compile(r"(?:\ben\s+(?:(?:la|el)\s+)?(?:(?:ciudad|comuna|region|centro|casco historico)\s+(?:de|del)\s+)?|\b(?:ciudad|comuna|region|centro)\s+de\s+|\b(?:ubicacion|lugar)\s+(?:de\s+)?(?:prestacion|ejecucion|realizacion|servicio|evento)\s*:\s*)$")
_NEGACION = re.compile(r"\b(?:fuera de|excepto|excluy\w*|distint[oa]s? de|no\s+(?:(?:se\s+)?\w+\s+){0,4}en)\b")
_ADMINISTRATIVO = re.compile(r"\b(?:domicilio|direccion|oficinas?|sede|comprador|unidad de compra|factur(?:as?|acion)|entrega de (?:ofertas?|antecedentes|documentos))\b")


def detectar_ubicacion(datos: dict) -> dict:
    _, _, lugares, patron = _patrones()
    evidencias, ambiguas = [], []
    comunas_ambiguas = {normalizar_texto(x) for x in cargar_catalogo()["comunas_ambiguas"]}
    for fuente, texto in _campos(datos)[0]:
        if fuente.endswith(("categoria", "nombre_producto")):
            continue
        normal = normalizar_texto(texto).replace("’", "'")
        for m in patron.finditer(normal):
            antes = normal[max(0, m.start() - 160):m.start()]
            antes = re.split(r"[;\n.!?]", antes)[-1]
            # No deduce el lugar por una mención del comprador o por una ciudad sin relación al servicio.
            relacion = _RELACION.search(antes)
            continuacion = bool(re.search(r"\b(?:y|o)\s+$", antes) and evidencias
                and evidencias[-1]["fuente"] == fuente)
            if not ((relacion and (_SERVICIO.search(antes) or re.search(r"(?:prestacion|ejecucion|realizacion)\s*:\s*$", antes))) or continuacion):
                continue
            tipo, comuna, region = lugares[m.group()]
            registro = {"cobertura": tipo, "comuna": comuna, "region": region,
                "fuente": fuente, "evidencia": _fragmento(texto, m.start(), m.end())}
            extranjero = m.group() == "santiago" and re.match(r"\s+(?:de compostela|del estero|de cuba)", normal[m.end():])
            dudosa = (_NEGACION.search(antes) or _ADMINISTRATIVO.search(antes) or extranjero
                or (m.group() in comunas_ambiguas and not re.search(r"metropolitana|melipilla|\brm\b", normal)))
            (ambiguas if dudosa else evidencias).append(registro)
    tipos = {e["cobertura"] for e in evidencias}
    if tipos == {"rm", "fuera_rm"}:
        estado = "mixta"
    elif ambiguas:
        estado = "ambigua"
    elif tipos:
        estado = next(iter(tipos))
    else:
        estado = "sin_determinar"
    # Una dirección de entrega/visita puede ser administrativa: se expone solo como pista.
    pistas = [{"fuente": campo, "texto": datos[campo][:500]} for campo in ("direccion_entrega", "direccion_visita")
        if isinstance(datos.get(campo), str) and datos[campo].strip()]
    # No descarta un paquete por el lugar de una sola línea cuando hay otros servicios sin localizar.
    if estado == "fuera_rm":
        if any(re.search(r"\b(?:todo el pais|a nivel nacional|cobertura nacional|diversas regiones|distintas regiones|varias ciudades)\b", normalizar_texto(t)) for _, t in _campos(datos)[0]):
            estado = "ambigua"
        items_hotel = {x["fuente"].split(".")[0] for x in detectar_pertinencia(datos)["coincidencias"]
            if x["nivel"] == "directa" and x["fuente"].startswith("items[")}
        items_localizados = {e["fuente"].split(".")[0] for e in evidencias if e["fuente"].startswith("items[")}
        if len(items_hotel) > 1 and items_hotel - items_localizados:
            estado = "ambigua"
    return {"estado": estado, "evidencias": evidencias[:50], "menciones_ambiguas": ambiguas[:30], "pistas": pistas}


def _fecha(valor):
    if isinstance(valor, str):
        valor = datetime.fromisoformat(valor.replace("Z", "+00:00"))
    if not isinstance(valor, datetime):
        return None
    return valor.replace(tzinfo=CHILE) if valor.tzinfo is None else valor.astimezone(CHILE)


def evaluar_vigencia(datos: dict, ahora: datetime) -> dict:
    estado = normalizar_texto(str(datos.get("estado") or "")).strip()
    codigo = datos.get("codigo_estado")
    cerrados = {"cerrada", "desierta", "adjudicada", "revocada", "suspendida", "cancelada"}
    abierta = estado in {"publicada", "activa"} or codigo == 5
    cerrada = estado in cerrados or codigo in {6, 7, 8, 18, 19}
    try:
        cierre = _fecha(datos.get("fecha_cierre"))
    except (ValueError, TypeError):
        return {"resultado": "sin_informacion", "motivo": "La fecha de cierre guardada no es interpretable."}
    if abierta and cerrada:
        return {"resultado": "sin_informacion", "motivo": "El estado y su código se contradicen; actualizar la fuente."}
    if cierre is not None and cierre <= ahora:
        return {"resultado": "no_cumple", "motivo": "La fecha de cierre guardada ya pasó.", "fecha_cierre": cierre.isoformat()}
    if cerrada:
        return {"resultado": "no_cumple", "motivo": "El estado guardado no permite presentar ofertas."}
    if not abierta or cierre is None:
        return {"resultado": "sin_informacion", "motivo": "Falta estado abierto o fecha de cierre para comprobar vigencia."}
    return {"resultado": "cumple", "motivo": "Publicada y con cierre futuro según los datos guardados.", "fecha_cierre": cierre.isoformat()}


def evaluar_preseleccion(datos: dict, *, ahora: datetime | None = None) -> dict:
    if re.search(r"-COT\d*$", str(datos.get("codigo_externo") or ""), re.I):
        raise ValueError("Esta etapa admite solamente licitaciones normales, no Compra Ágil.")
    ahora = ahora or datetime.now(CHILE)
    if ahora.tzinfo is None:
        raise ValueError("La hora de evaluación debe indicar su zona horaria.")
    ahora = ahora.astimezone(CHILE)
    campos, parcial = _campos(datos)
    vigencia = evaluar_vigencia(datos, ahora)
    ubicacion = detectar_ubicacion(datos)
    pertinencia = detectar_pertinencia(datos)
    territorial = ("cumple" if ubicacion["estado"] == "rm" else
        "no_cumple" if ubicacion["estado"] == "fuera_rm" and not parcial else "sin_informacion")
    rubro = "cumple" if pertinencia["directa"] and not pertinencia["ambiguedades"] else "sin_informacion"
    if vigencia["resultado"] == "no_cumple":
        clasificacion, motivo = "descartada", vigencia["motivo"]
    elif territorial == "no_cumple":
        clasificacion, motivo = "descartada", "El servicio identificado se solicita fuera de la Región Metropolitana."
    elif vigencia["resultado"] == territorial == rubro == "cumple" and not parcial:
        clasificacion, motivo = "preseleccionada", "Oportunidad vigente, con servicio potencialmente hotelero y ubicación identificada en la RM."
    else:
        clasificacion = "revision_manual"
        motivo = "Conservar: hay información insuficiente o ambigua para completar la preselección."
    entrada = {"campos": campos, "estado": datos.get("estado"), "codigo_estado": datos.get("codigo_estado"),
        "fecha_cierre": str(datos.get("fecha_cierre")), "raw_id": datos.get("raw_id")}
    return {
        "codigo_externo": datos.get("codigo_externo"), "catalogo_version": cargar_catalogo()["version"],
        "clasificacion": clasificacion, "motivo": motivo, "evaluado_en": ahora.isoformat(),
        "fuente_raw_id": datos.get("raw_id"), "entrada_parcial": parcial,
        "huella_entrada": hashlib.sha256(json.dumps(entrada, sort_keys=True, ensure_ascii=False).encode()).hexdigest(),
        "criterios": {"vigencia": vigencia, "ubicacion": {"resultado": territorial, **ubicacion},
            "pertinencia": {"resultado": rubro, **pertinencia}},
        "semantica": {"estado": "no_solicitada"},
        "modo": "simulacion", "decision_postular": False,
    }
