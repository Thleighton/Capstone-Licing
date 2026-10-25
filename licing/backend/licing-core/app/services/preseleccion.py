"""Preselección conservadora sobre datos guardados; sin escrituras ni llamadas externas."""
from datetime import datetime
from functools import cache
import hashlib
import json
from pathlib import Path
import re
from .ubicacion import _texto_busqueda
from zoneinfo import ZoneInfo
from .revision_documental import evaluar_documentacion
from .clientes_importantes import identificar_clientes_importantes

CHILE = ZoneInfo("America/Santiago")
CATALOGO = Path(__file__).resolve().parents[1] / "data" / "preseleccion_hotel_v1.json"
VERSION_MOTOR = "reglas-hotel-8"
PILARES = ("vigencia", "ubicacion", "pertinencia")
MAX_CAMPO = 30000
MAX_ITEMS = 1000
MAX_DOCUMENTOS = 10
MAX_PAGINAS = 120
MAX_TEXTO_TOTAL = 500000


def _texto_con_mapa(texto):
    normal, mapa = _texto_busqueda(texto)
    salida, posiciones = [], []
    for caracter, posicion in zip(normal, mapa):
        if caracter in "\u200b\ufeff":
            continue
        caracter = "\n" if caracter in "\r\n" else " " if caracter.isspace() else caracter
        if salida and caracter == salida[-1] and caracter in {" ", "\n"}:
            posiciones[-1] = (posiciones[-1][0], posicion[1])
        else:
            salida.append(caracter.replace("’", "'"))
            posiciones.append(posicion)
    return "".join(salida), posiciones


def normalizar_texto(texto: str) -> str:
    return _texto_con_mapa(texto)[0]


def _entrada_segura(datos):
    """Una forma inválida de la fuente se conserva como duda, sin detener el lote."""
    problemas = []
    if not isinstance(datos, dict):
        return {}, ["entrada: se esperaba un objeto"]
    datos = dict(datos)

    def texto(objeto, campo, ruta):
        if objeto.get(campo) is not None and not isinstance(objeto[campo], str):
            problemas.append(f"{ruta}{campo}: se esperaba texto")
            objeto[campo] = None

    def listado(objeto, campo, limite, ruta):
        valor = objeto.get(campo)
        if valor is None:
            return []
        if not isinstance(valor, list):
            problemas.append(f"{ruta}{campo}: se esperaba una lista")
            return []
        if len(valor) > limite:
            problemas.append(f"{ruta}{campo}: se superó el límite de lectura")
        resultado = []
        for n, item in enumerate(valor[:limite]):
            if isinstance(item, dict):
                resultado.append((n, dict(item)))
            else:
                problemas.append(f"{ruta}{campo}[{n}]: se esperaba un objeto")
                resultado.append((n, {}))
        return resultado

    for campo in ("nombre", "descripcion", "nombre_organismo", "nombre_unidad",
                  "direccion_entrega", "direccion_visita", "estado", "codigo_externo"):
        texto(datos, campo, "")
    codigo = datos.get("codigo_estado")
    if codigo is not None and type(codigo) is not int:
        problemas.append("codigo_estado: se esperaba un entero")
        datos["codigo_estado"] = None
    items = listado(datos, "items", MAX_ITEMS, "")
    datos["items"] = []
    for n, item in items:
        for campo in ("nombre_producto", "descripcion", "categoria"):
            texto(item, campo, f"items[{n}].")
        datos["items"].append(item)
    documentos = listado(datos, "documentos", MAX_DOCUMENTOS, "")
    datos["documentos"] = []
    for n, doc in documentos:
        if doc.get("vigente") is False:
            datos["documentos"].append(doc)
            continue
        if not isinstance(doc.get("vigente", True), bool):
            problemas.append(f"documentos[{n}].vigente: se esperaba un booleano")
            doc["vigente"] = True
        if doc.get("id") is None:
            problemas.append(f"documentos[{n}].id: identificador ausente")
            doc["id"] = f"sin_identificador_{n}"
        texto(doc, "nombre", f"documentos[{n}].")
        texto(doc, "estado_extraccion", f"documentos[{n}].")
        if doc.get("cobertura") is not None and not isinstance(doc["cobertura"], dict):
            problemas.append(f"documentos[{n}].cobertura: se esperaba un objeto")
            doc["cobertura"] = {}
        if isinstance(doc.get("cobertura"), dict):
            doc["cobertura"] = dict(doc["cobertura"])
            texto(doc["cobertura"], "motivo_codigo", f"documentos[{n}].cobertura.")
        paginas = listado(doc, "paginas_texto", MAX_PAGINAS, f"documentos[{n}].")
        doc["paginas_texto"] = []
        for p, pagina in paginas:
            texto(pagina, "texto", f"documentos[{n}].paginas_texto[{p}].")
            if type(pagina.get("pagina")) is not int or pagina["pagina"] < 1:
                problemas.append(f"documentos[{n}].paginas_texto[{p}].pagina: número ausente o inválido")
                pagina["pagina"] = "sin_numero"
            doc["paginas_texto"].append(pagina)
        datos["documentos"].append(doc)
    incidencia = datos.get("incidencia_documental")
    if incidencia is not None and (not isinstance(incidencia, dict)
            or not isinstance(incidencia.get("motivo"), str)):
        problemas.append("incidencia_documental: motivo ausente o inválido")
        datos["incidencia_documental"] = {"codigo": "dato_invalido",
            "motivo": "La incidencia documental guardada necesita revisión."}
    return datos, problemas


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
    patron_lugares = re.compile(r"(?<!\w)(?:" + "|".join(re.escape(x) for x in sorted(lugares, key=len, reverse=True)) + r")(?!\w)")
    return grupos, ambiguedades, lugares, patron_lugares


def _campos(datos: dict):
    datos, problemas = _entrada_segura(datos)
    campos, parcial, total = [], bool(problemas), 0

    def agregar(fuente, valor):
        nonlocal parcial, total
        if not isinstance(valor, str) or not valor.strip():
            return
        limite = min(MAX_CAMPO, max(0, MAX_TEXTO_TOTAL - total))
        parcial |= len(valor) > limite
        if limite:
            texto = valor[:limite]
            campos.append((fuente, texto))
            total += len(texto)

    for nombre in ("nombre", "descripcion"):
        agregar(nombre, datos.get(nombre))
    for n, item in enumerate(datos["items"]):
        for nombre in ("nombre_producto", "descripcion", "categoria"):
            agregar(f"items[{n}].{nombre}", item.get(nombre))
    for doc in datos["documentos"]:
        if not doc.get("vigente", True) or doc.get("estado_extraccion") != "extraido":
            continue
        for pagina in doc.get("paginas_texto") or []:
            agregar(f"documentos[{doc['id']}].paginas[{pagina['pagina']}]", pagina.get("texto"))
    return campos, parcial


def textos_servicio(datos: dict) -> list[dict]:
    """Excluye nombres y domicilios administrativos del comprador."""
    return [{"fuente": fuente, "texto": texto} for fuente, texto in _campos(datos)[0]]


def _fragmento(texto: str, inicio: int, fin: int, posiciones=None) -> str:
    if posiciones is None:
        _, posiciones = _texto_con_mapa(texto)
    if not posiciones:
        return ""
    a = posiciones[min(inicio, len(posiciones)-1)][0]
    b = posiciones[min(fin-1, len(posiciones)-1)][1]
    return texto[max(0, a - 110):min(len(texto), b + 150)].strip()


def _mencion_ajena(grupo, m, normal):
    """Desambiguación local: no borra otro servicio hotelero del mismo texto."""
    antes = re.split(r"[.;\n]", normal[:m.start()])[-1][-120:]
    despues = normal[m.end():]
    if grupo == "alojamiento":
        return bool(re.match(r"\s+(?:(?:de|para)\s+)?(?:infraestructura virtualizada|servidores?|maquinas virtuales|sitios? web|datos|aplicaciones?)\b", despues))
    if grupo == "salones":
        return bool(re.search(r"\b(?:sillas?|mesas?|muebles?|mobiliario)\s+(?:(?:de|para)\s+)(?:el\s+|los\s+)?$", antes))
    if grupo == "actividades":
        return bool((re.fullmatch(r"jornadas?|taller(?:es)?", m.group())
                     and (re.match(r"\s+(?:normal|extraordinaria|laboral|particular|mecanico)\b", despues)
                          or re.search(r"\b(?:mecanico|mecanica|fuera de|reparaciones? en)\s+$", antes)))
                    or (m.group().startswith("capacitacion") and re.search(r"\bcursos? de\s+$", antes))
                    or (m.group().startswith("reunion") and re.search(r"\bmesas?\s+(?:de\s+)?$", antes)))
    return grupo == "alimentacion_asociada" and bool(
        re.search(r"\b(?:sin|no se requiere|no incluye)\s+(?:servicio de\s+)?$", antes)
        or (re.fullmatch(r"alimentacion", m.group()) and re.match(r"\s+(?:enteral|parenteral|electrica)\b", despues)))


def _ambiguedad_administrativa(regla, m, normal):
    # La orden de compra formaliza también servicios; no implica comprar bienes.
    if regla != "compra_bienes_obras":
        return False
    antes = normal[max(0, m.start()-40):m.start()]
    return ((m.group() == "compra" and bool(re.search(r"\borden(?:es)? de\s+$", antes)))
            or (m.group() == "suministro" and bool(re.search(r"\bservicio de\s+$", antes))
                and bool(re.match(r"\s+de\s+(?:cof+e+e?\s*[- ]?breaks?|coctel(?:es)?|banqueteria|catering|alimentacion|desayunos?|almuerzos?|cenas?)\b", normal[m.end():]))))


def detectar_pertinencia(datos: dict, *, campos=None) -> dict:
    grupos, ambiguedades, _, _ = _patrones()
    coincidencias, dudas = [], []
    lectura_truncada = False
    campos = _campos(datos)[0] if campos is None else campos
    for fuente, texto in campos:
        # Las categorías amplias no describen el objeto contratado y sus
        # repeticiones no deben agotar el límite de evidencias del servicio.
        if fuente.endswith("categoria"):
            continue
        normal, mapa = _texto_con_mapa(texto)
        for grupo, patrones in grupos:
            for patron in patrones:
                for n, m in enumerate(patron.finditer(normal)):
                    if n > 100:
                        lectura_truncada = True
                        break
                    nivel = grupo["nivel"]
                    if _mencion_ajena(grupo["id"], m, normal):
                        continue
                    if re.fullmatch(r"hotel(?:es)?|hoteleria", m.group()):
                        antes = re.split(r"[.;\n]", normal[:m.start()])[-1][-120:]
                        despues = re.split(r"[.;\n]", normal[m.end():], maxsplit=1)[0][:120]
                        contratacion = re.search(r"\b(?:requiere|requieren|solicita|solicitan|contrata|contratar|contratacion|arriendo|alquiler|reservas?|servicios? de)\b", antes)
                        destino = re.search(r"\bpara\s+(?:\d+\s+)?(?:personas|participantes|delegaciones|funcionarios|alojar|hospedar)\b", despues)
                        if not (contratacion or destino):
                            nivel = "contexto"
                    coincidencias.append({"grupo": grupo["id"], "nivel": nivel, "fuente": fuente,
                        "termino": m.group(), "inicio": mapa[m.start()][0], "fin": mapa[m.end()-1][1],
                        "evidencia": _fragmento(texto, m.start(), m.end(), mapa)})
        # Un código UNSPSC genérico no identifica el objeto concreto de la contratación.
        if not fuente.endswith(("categoria", "nombre_producto")):
            for regla, patron in ambiguedades:
                m = next((m for m in patron.finditer(normal)
                          if not _ambiguedad_administrativa(regla["id"], m, normal)), None)
                if m is not None:
                    dudas.append({"codigo": regla["id"], "motivo": regla["motivo"], "fuente": fuente,
                        "evidencia": _fragmento(texto, m.start(), m.end(), mapa)})
    for fuente, texto in campos:
        if re.search(r"\b(?:sin|no se requiere|no incluye)\s+(?:servicio de )?(?:alojamiento|hospedaje|salon|habitacion)", normalizar_texto(texto)):
            dudas.append({"codigo": "servicio_negado", "motivo": "La mención contiene una negación; revisar su alcance.", "fuente": fuente, "evidencia": texto[:500]})
    directas = [x for x in coincidencias if x["nivel"] == "directa"
        and not x["fuente"].endswith(("categoria", "nombre_producto"))]
    exclusiones = []
    senales = any(x["nivel"] != "complemento" and x["grupo"] in {"alojamiento", "salones", "actividades", "alimentacion_asociada"}
                  and not x["fuente"].endswith("categoria") for x in coincidencias)
    items = datos.get("items") or []
    segmentos = cargar_catalogo().get("segmentos_producto_ajenos", {})
    familias = cargar_catalogo().get("familias_producto_ajenas", {})
    especiales = cargar_catalogo().get("codigos_producto_ajenos", {})
    def objeto_ajeno(item):
        codigo = item.get("codigo_producto")
        if not isinstance(codigo, str):
            return None
        if codigo in especiales:
            return especiales[codigo]
        if re.fullmatch(r"\d{8}", codigo):
            return familias.get(codigo[:4]) or segmentos.get(codigo[:2])
        return None
    # Todas las líneas deben tener un código conocido ajeno; una línea desconocida
    # conserva la oportunidad completa.
    lineas_ajenas = bool(items) and all(objeto_ajeno(i) for i in items)
    # Excluir requiere un objeto ajeno explícito, nunca solo ausencia de palabras clave.
    # Cualquier señal de un paquete hotelero mantiene el caso para desambiguación.
    if senales and lineas_ajenas:
        # Una palabra hotelera dentro de líneas que son todas ajenas no confirma el servicio.
        objetos = sorted({objeto_ajeno(i) for i in items})
        dudas.insert(0, {"codigo": "lineas_ajenas", "fuente": "items",
            "motivo": "Todas las líneas publicadas corresponden a " + ", ".join(objetos[:5])
                + "; la mención de servicios del hotel puede no ser lo contratado.",
            "evidencia": "; ".join(f"{i['codigo_producto']}: {i.get('nombre_producto') or objeto_ajeno(i)}"
                for i in items[:10])})
    if not senales:
        for regla in cargar_catalogo().get("exclusiones_evidentes", []):
            for fuente, texto in campos:
                if fuente.endswith(("categoria", "nombre_producto")):
                    continue
                normal, mapa = _texto_con_mapa(texto)
                m = re.search(regla["patron"], normal)
                if m:
                    exclusiones.append({"codigo": regla["id"], "motivo": regla["motivo"],
                        "fuente": fuente, "evidencia": _fragmento(texto, m.start(), m.end(), mapa)})
        if lineas_ajenas:
            for n, item in enumerate(items[:10]):
                codigo = item["codigo_producto"]
                exclusiones.append({"codigo": "producto_ajeno", "fuente": f"items[{n}].codigo_producto",
                    "motivo": "Las líneas publicadas corresponden a " + objeto_ajeno(item)
                        + "; no se identifica contratación de servicios del hotel.",
                    "evidencia": f"{codigo}: {item.get('nombre_producto') or item.get('descripcion') or objeto_ajeno(item)}"})
    # El título de una línea genérica puede ser la única información disponible: conserva para revisar.
    return {"grupos": sorted({x["grupo"] for x in coincidencias}), "directa": bool(directas),
        "coincidencias": coincidencias[:100], "ambiguedades": dudas[:30],
        "exclusiones_evidentes": exclusiones[:30],
        "truncada": lectura_truncada or len(coincidencias) > 100 or len(dudas) > 30 or len(exclusiones) > 30}


def detectar_cliente(datos):
    # Prioridad comercial, nunca una condición para excluir compradores nuevos.
    return identificar_clientes_importantes(datos)


def extraer_requisitos(campos):
    """Hallazgos con evidencia; no convierte cantidades de ítem en asistentes."""
    patrones = {
        "cantidad": r"\b\d{1,5}(?:[.,]\d{3})?\s+(?:personas|asistentes|participantes|habitaciones|noches|salones|salas)\b",
        "montaje": r"\b(?:tipo|montaje(?:\s+tipo)?|disposicion(?:\s+tipo)?)\s+(?:auditorio|escuela|imperial|coctel|banquete|u)\b",
        "fecha_servicio": r"\b(?:evento|jornada|seminario|alojamiento|estadia|servicio)\b[^.;\n]{0,100}?\b(?:\d{1,2}[/\-]\d{1,2}[/\-]\d{4}|\d{1,2}\s+de\s+(?:enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre)(?:\s+de\s+\d{4})?)\b",
        "oferta_parcial": r"\b(?:ofertas? parciales?|adjudicacion por (?:linea|item)|ofertar por (?:linea|item))\b",
        "requisito_proveedor": r"\b(?:obligatori[oa]|debera|debe)\b[^.;\n]{0,100}?\b(?:otec|otic|relator|certificacion|productora)\b",
    }
    hallazgos = []
    for fuente, texto in campos:
        normal, mapa = _texto_con_mapa(texto)
        for tipo, patron in patrones.items():
            for m in re.finditer(patron, normal):
                inicio, fin = mapa[m.start()][0], mapa[m.end()-1][1]
                hallazgos.append({"tipo": tipo, "fuente": fuente, "inicio": inicio, "fin": fin,
                                  "texto": texto[inicio:fin], "contexto": _fragmento(texto, m.start(), m.end(), mapa),
                                  "estado": "por_revisar"})
                if len(hallazgos) == 100:
                    return {"hallazgos": hallazgos, "truncada": True}
    return {"hallazgos": hallazgos, "truncada": False}


_SERVICIO = re.compile(r"\b(?:servicios?|alojamiento|hospedaje|hotel(?:es)?|hoteleria|habitacion(?:es)?|estadia|salon(?:es)?|salas?|recintos?|espacios?|auditorios?|jornadas?|eventos?|reunion(?:es)?|seminarios?|encuentros?|ceremonias?|realizara|desarrollara|cof+e+e?\s*[- ]?breaks?|coctel(?:es)?|cocktails?|banqueteria|catering|alimentacion|desayunos?|almuerzos?|cenas?|colaciones?|refrigerios?)\b")
_ROTULO_LUGAR = re.compile(r"\b(?:ubicacion|lugar|direccion|comuna|region)\s+(?:(?:de|del)\s+)?(?:(?:la|el)\s+)?(?:prestacion|ejecucion|realizacion|servicio|evento)\s*:\s*$")
_RELACION = re.compile(r"(?:\b(?:en|para|derivad[oa]s? a)\s+(?:(?:la|el)\s+)?(?:(?:ciudad|comuna|region|centro|casco historico)\s+(?:de|del)\s+)?|\b(?:ciudad|comuna|region|centro)\s+de\s+)$")
_LUGAR_EN_TITULO = re.compile(r"\b(?:(?:servicios? de )?(?:alojamiento|hospedaje|hoteleria)|(?:arriendo|alquiler) de (?:un |una )?(?:salon(?:es)?|salas?))\s*[-:–]?\s*$")
_NEGACION = re.compile(r"\b(?:fuera de|excepto|excluy\w*|distint[oa]s? de|no\s+(?:(?:se\s+)?\w+\s+){0,4}en)\b")
_ADMINISTRATIVO = re.compile(r"\b(?:domicilio|direccion|oficinas?|sede|comprador|unidad de compra|factur(?:as?|acion)|entrega de (?:ofertas?|antecedentes|documentos))\b")
_DESTINO_EXTRANJERO = re.compile(r"^\s*,?\s*(?:argentina|peru|brasil|bolivia|colombia|ecuador|mexico|espana|estados unidos|uruguay|paraguay|venezuela)\b")


def detectar_ubicacion(datos: dict, *, campos=None, pertinencia=None) -> dict:
    datos, _ = _entrada_segura(datos)
    _, _, lugares, patron = _patrones()
    evidencias, ambiguas = [], []
    comunas_ambiguas = {normalizar_texto(x) for x in cargar_catalogo()["comunas_ambiguas"]}
    campos = _campos(datos)[0] if campos is None else campos
    for fuente, texto in campos:
        if fuente.endswith(("categoria", "nombre_producto")):
            continue
        normal, mapa = _texto_con_mapa(texto)
        for m in patron.finditer(normal):
            antes = normal[max(0, m.start() - 160):m.start()]
            antes = re.split(r"[;\n.!?]", antes)[-1]
            # No deduce el lugar por una mención del comprador o por una ciudad sin relación al servicio.
            despues = re.split(r"[;\n.!?]", normal[m.end():], maxsplit=1)[0][:160]
            rotulo = bool(_ROTULO_LUGAR.search(antes))
            relacion = _RELACION.search(antes)
            continuacion = bool(re.search(r"(?:\b(?:y|o)|[,/–-])\s+$", antes) and evidencias
                and evidencias[-1]["fuente"] == fuente
                and not re.search(r"[;\n.!?]", texto[evidencias[-1]["fin"]:mapa[m.start()][0]]))
            if not (rotulo or _LUGAR_EN_TITULO.search(antes) or (relacion and (_SERVICIO.search(antes) or _SERVICIO.search(despues))) or continuacion):
                continue
            tipo, comuna, region = lugares[m.group()]
            registro = {"cobertura": tipo, "comuna": comuna, "region": region,
                "fuente": fuente, "evidencia": _fragmento(texto, m.start(), m.end(), mapa),
                "inicio": mapa[m.start()][0], "fin": mapa[m.end()-1][1],
                "contexto_local": antes + m.group() + despues, "lugar_explicito": rotulo}
            extranjero = (m.group() == "santiago" and re.match(r"\s+(?:de compostela|del estero|de cuba)", normal[m.end():]))
            extranjero = extranjero or (m.group() == "san miguel" and re.match(r"\s+de tucuman\b", normal[m.end():]))
            extranjero = extranjero or _DESTINO_EXTRANJERO.match(normal[m.end():])
            dudosa = (_NEGACION.search(antes) or (_ADMINISTRATIVO.search(antes) and not rotulo) or extranjero
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
    if pertinencia is None:
        pertinencia = detectar_pertinencia(datos, campos=campos)
    vinculo = _vincular_servicio(pertinencia=pertinencia, evidencias=evidencias)
    # No combina el alojamiento de una línea con la ciudad de otra ni descarta líneas sin localizar.
    if estado in {"rm", "fuera_rm"} and not vinculo["completo"] and vinculo["unidades_hoteleras"]:
        estado = "ambigua"
    if estado in {"rm", "fuera_rm"}:
        if any(re.search(r"\b(?:todo el pais|a nivel nacional|cobertura nacional|diversas regiones|distintas regiones|varias ciudades)\b", normalizar_texto(t)) for _, t in campos):
            estado = "ambigua"
    return {"estado": estado, "alcance": "santiago_y_region_metropolitana",
        "vinculo_servicio": vinculo, "evidencias": evidencias[:50],
        "menciones_ambiguas": ambiguas[:30], "pistas": pistas,
        "truncada": len(evidencias) > 50 or len(ambiguas) > 30}


def _unidad(fuente):
    if fuente.startswith("items["):
        return fuente.split(".")[0]
    if fuente.startswith("documentos["):
        return fuente
    return "cabecera"


def _vincular_servicio(pertinencia, evidencias):
    directas = [x for x in pertinencia["coincidencias"] if x["nivel"] == "directa"
        and not x["fuente"].endswith(("categoria", "nombre_producto"))]
    unidades = {_unidad(x["fuente"]) for x in directas}
    # El título general no representa una línea adicional a los ítems concretos.
    requeridas = {u for u in unidades if u.startswith("items[")} or unidades
    localizadas = set()
    for e in evidencias:
        unidad = _unidad(e["fuente"])
        if unidad not in unidades:
            continue
        local = detectar_pertinencia({"descripcion": e["contexto_local"]})
        actividad = re.search(r"\b(?:eventos?|jornadas?|seminarios?|reunion(?:es)?|conferencias?|encuentros?)\b", e["contexto_local"])
        if local["directa"] or e["lugar_explicito"] or actividad:
            localizadas.add(unidad)
    return {"completo": bool(requeridas) and requeridas <= localizadas,
        "unidades_hoteleras": sorted(requeridas), "unidades_localizadas": sorted(localizadas),
        "motivo": "La ubicación debe corresponder al servicio hotelero de la misma línea o contexto."}


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


def clasificar_pilares(criterios):
    """Solo estos tres resultados deciden; un rechazo explícito prevalece a una duda."""
    for codigo in PILARES:
        if criterios[codigo]["resultado"] == "no_cumple":
            return "descartada", criterios[codigo]["motivo"], codigo
    for codigo in PILARES:
        if criterios[codigo]["resultado"] != "cumple":
            return "revision_manual", criterios[codigo]["motivo"], codigo
    return ("preseleccionada", "Cumple los tres pilares: abierta y con plazo, servicio en la RM y alojamiento, salones o alimentación.", None)


def evaluar_preseleccion(datos: dict, *, ahora: datetime | None = None) -> dict:
    # Licitaciones y Compras Ágiles comparten los tres pilares; la Compra Ágil no trae bases.
    datos, problemas = _entrada_segura(datos)
    ahora = ahora or datetime.now(CHILE)
    if ahora.tzinfo is None:
        raise ValueError("La hora de evaluación debe indicar su zona horaria.")
    ahora = ahora.astimezone(CHILE)
    # Las bases son una fuente complementaria. Los errores al conseguirlas o leerlas
    # no anulan evidencia suficiente de la ficha y sus ítems.
    utilizables = {**datos, "documentos": [d for n, d in enumerate(datos.get("documentos", []))
        if not any(p.startswith(f"documentos[{n}].") for p in problemas)]}
    campos, parcial = _campos(utilizables)
    parcial |= any(not p.startswith(("documentos", "incidencia_documental")) for p in problemas)
    vigencia = evaluar_vigencia(datos, ahora)
    pertinencia = detectar_pertinencia(datos, campos=campos)
    ubicacion = detectar_ubicacion(datos, campos=campos, pertinencia=pertinencia)
    parcial |= pertinencia["truncada"] or ubicacion["truncada"]
    documentacion = evaluar_documentacion(datos)
    territorial = ("cumple" if ubicacion["estado"] == "rm" and not parcial else
        "no_cumple" if ubicacion["estado"] == "fuera_rm" and not parcial else "sin_informacion")
    rubro = ("no_cumple" if pertinencia["exclusiones_evidentes"] and not parcial else
        "cumple" if pertinencia["directa"] and not pertinencia["ambiguedades"] and not parcial else "sin_informacion")
    motivo_ubicacion = (
        "El lugar de prestación del servicio está identificado en la Región Metropolitana." if territorial == "cumple" else
        "El servicio identificado se solicita fuera de la Región Metropolitana." if territorial == "no_cumple" else
        "La lectura de la fuente es incompleta; falta confirmar el lugar de prestación del servicio." if parcial else
        "El lugar del servicio es mixto o ambiguo; falta confirmar su cobertura en la RM." if ubicacion["estado"] in {"mixta", "ambigua"} else
        "No se identifica dónde debe prestarse el servicio; la dirección del comprador no confirma el lugar.")
    motivo_servicio = (
        pertinencia["exclusiones_evidentes"][0]["motivo"] if rubro == "no_cumple" else
        "Se solicita alojamiento, salones, alimentación o una combinación de estos servicios." if rubro == "cumple" else
        "La lectura de la fuente es incompleta; falta confirmar el servicio contratado." if parcial else
        "Falta aclarar si se contrata un servicio del hotel: " + pertinencia["ambiguedades"][0]["motivo"] if pertinencia["ambiguedades"] else
        "La ficha no identifica una solicitud concreta de alojamiento, salones o alimentación.")
    criterios = {"vigencia": vigencia,
        "ubicacion": {"resultado": territorial, "motivo": motivo_ubicacion, **ubicacion},
        "pertinencia": {"resultado": rubro, "motivo": motivo_servicio, **pertinencia}}
    clasificacion, motivo, pilar_decisivo = clasificar_pilares(criterios)
    documentacion["bloquea_preseleccion"] = False
    entrada = {"campos": campos, "estado": datos.get("estado"), "codigo_estado": datos.get("codigo_estado"),
        "fecha_cierre": str(datos.get("fecha_cierre")), "raw_id": datos.get("raw_id"),
        "documentacion": documentacion, "calidad_datos": problemas,
        "version_motor": VERSION_MOTOR, "catalogo_version": cargar_catalogo()["version"]}
    return {
        "version_motor": VERSION_MOTOR,
        "codigo_externo": datos.get("codigo_externo"), "catalogo_version": cargar_catalogo()["version"],
        "clasificacion": clasificacion, "motivo": motivo, "evaluado_en": ahora.isoformat(),
        "fuente_raw_id": datos.get("raw_id"), "entrada_parcial": parcial,
        "calidad_datos": {"resultado": "sin_informacion" if parcial else "cumple",
            "incidencias": problemas[:30], "lectura_acotada": parcial},
        "cobertura": "parcial" if datos.get("documentos") else "sin_bases",
        "requisitos_detectados": extraer_requisitos(campos),
        "cliente_estrategico": detectar_cliente(datos),
        "huella_entrada": hashlib.sha256(json.dumps(entrada, sort_keys=True, ensure_ascii=False).encode()).hexdigest(),
        "orden_pilares": list(PILARES), "pilar_decisivo": pilar_decisivo,
        "criterios": criterios, "documentacion": documentacion,
        "semantica": {"estado": "pendiente", "motivo": "Esta etapa aplica reglas; no ejecuta embeddings ni LLM."},
        "modo": "preseleccion", "decision_postular": False,
    }
