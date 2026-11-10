"""Preselección conservadora sobre datos guardados; sin escrituras ni llamadas externas."""

from datetime import datetime
from functools import cache
import hashlib
import json
from pathlib import Path
import re
from zoneinfo import ZoneInfo

from .ubicacion import _texto_busqueda
from .revision_documental import evaluar_documentacion
from .clientes_importantes import identificar_clientes_importantes

CHILE = ZoneInfo("America/Santiago")
CATALOGO = Path(__file__).resolve().parents[1] / "data" / "preseleccion_hotel_v1.json"
VERSION_MOTOR = "reglas-hotel-45"
PILARES = ("vigencia", "ubicacion", "pertinencia")
MAX_CAMPO = 30000
MAX_ITEMS = 1000
MAX_DOCUMENTOS = 10
MAX_PAGINAS = 120
MAX_TEXTO_TOTAL = 500000

# Solo disparan revisión cuando hay un error de una letra y contexto hotelero.
# Las coincidencias aproximadas nunca cuentan como servicio directo.
TERMINOS_SERVICIO_TOLERANTES = frozenset({
    "salon", "salones", "sala", "salas", "arriendo", "arriendos",
    "arrendamiento", "arrendamientos", "alquiler", "alquileres",
    "banqueteria", "catering", "coctel", "cocteles", "coffee",
})
CONTEXTO_SERVICIO_TOLERANTE = re.compile(
    r"\b(?:servicio|servicios|arriendo|arrendamiento|alquiler|reserva|"
    r"salones?|salas?|"
    r"eventos?|jornadas?|seminarios?|capacitaciones?|congresos?|"
    r"participantes?|asistentes?|funcionarios?|delegaciones?|personas?|"
    r"banqueteria|catering|coffee|break|alimentacion|almuerzo|cena|"
    r"desayuno|coctel|noches?)\b"
)


def _texto_con_mapa(texto):
    normal, mapa = _texto_busqueda(texto)
    salida, posiciones = [], []

    for caracter, posicion in zip(normal, mapa):
        if caracter in "\u200b\ufeff":
            continue

        caracter = (
            "\n" if caracter in "\r\n" else " " if caracter.isspace() else caracter
        )

        if salida and caracter == salida[-1] and caracter in {" ", "\n"}:
            posiciones[-1] = (posiciones[-1][0], posicion[1])
        else:
            salida.append(caracter.replace("’", "'"))
            posiciones.append(posicion)

    return "".join(salida), posiciones


def normalizar_texto(texto: str) -> str:
    return _texto_con_mapa(texto)[0]


def _distancia_una_edicion(a: str, b: str) -> bool:
    """Acepta una inserción, omisión, sustitución o transposición adyacente."""
    if a == b or abs(len(a) - len(b)) > 1:
        return False

    if len(a) == len(b):
        diferencias = [i for i, (x, y) in enumerate(zip(a, b)) if x != y]
        if len(diferencias) == 1:
            return True
        return (
            len(diferencias) == 2
            and diferencias[1] == diferencias[0] + 1
            and a[diferencias[0]] == b[diferencias[1]]
            and a[diferencias[1]] == b[diferencias[0]]
        )

    corto, largo = (a, b) if len(a) < len(b) else (b, a)
    i = j = errores = 0
    while i < len(corto) and j < len(largo):
        if corto[i] == largo[j]:
            i += 1
            j += 1
        else:
            errores += 1
            j += 1
            if errores > 1:
                return False
    return True


def _posibles_errores_servicio(normal, fuente, texto, mapa):
    """Detecta typos cercanos como duda, nunca como coincidencia comercial."""
    if fuente.endswith(("categoria", "nombre_producto")):
        return []

    resultado = []
    vistos = set()
    for token in re.finditer(r"\b[a-z0-9]+\b", normal):
        palabra = token.group()
        if palabra in TERMINOS_SERVICIO_TOLERANTES or len(palabra) < 5:
            continue

        candidatos = [
            termino for termino in TERMINOS_SERVICIO_TOLERANTES
            if _distancia_una_edicion(palabra, termino)
        ]
        if not candidatos:
            continue

        inicio_contexto = max(0, token.start() - 100)
        fin_contexto = min(len(normal), token.end() + 120)
        contexto = normal[inicio_contexto:fin_contexto]
        if not CONTEXTO_SERVICIO_TOLERANTE.search(contexto):
            continue

        clave = (fuente, palabra, token.start())
        if clave in vistos:
            continue
        vistos.add(clave)
        inicio = mapa[token.start()][0]
        fin = mapa[token.end() - 1][1]
        evidencia = _fragmento(texto, token.start(), token.end(), mapa)
        resultado.append({
            "codigo": "posible_error_ortografico",
            "motivo": (
                "Hay una palabra cercana a un servicio hotelero, pero puede ser "
                "un error de escritura; confirmar el texto antes de descartar."
            ),
            "fuente": fuente,
            "termino_detectado": texto[inicio:fin],
            "terminos_posibles": sorted(candidatos),
            "evidencia": evidencia,
        })
        if len(resultado) >= 8:
            break
    return resultado


def _entrada_segura(datos):
    """Una forma inválida de la fuente se conserva como duda, sin detener el lote."""
    problemas = []

    if not isinstance(datos, dict):
        problemas.append("entrada: se esperaba un objeto")
        datos = {}

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

    for campo in (
        "nombre",
        "descripcion",
        "nombre_organismo",
        "nombre_unidad",
        "direccion_entrega",
        "direccion_visita",
        "estado",
        "codigo_externo",
    ):
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
            texto(
                doc["cobertura"],
                "motivo_codigo",
                f"documentos[{n}].cobertura.",
            )

        paginas = listado(
            doc,
            "paginas_texto",
            MAX_PAGINAS,
            f"documentos[{n}].",
        )
        doc["paginas_texto"] = []

        for p, pagina in paginas:
            texto(
                pagina,
                "texto",
                f"documentos[{n}].paginas_texto[{p}].",
            )

            if type(pagina.get("pagina")) is not int or pagina["pagina"] < 1:
                problemas.append(
                    f"documentos[{n}].paginas_texto[{p}].pagina: "
                    "número ausente o inválido"
                )
                pagina["pagina"] = "sin_numero"

            doc["paginas_texto"].append(pagina)

        datos["documentos"].append(doc)

    incidencia = datos.get("incidencia_documental")

    if incidencia is not None and (
        not isinstance(incidencia, dict)
        or not isinstance(incidencia.get("motivo"), str)
    ):
        problemas.append("incidencia_documental: motivo ausente o inválido")
        datos["incidencia_documental"] = {
            "codigo": "dato_invalido",
            "motivo": ("La incidencia documental guardada necesita revisión."),
        }

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
        lugares[normalizar_texto(comuna)] = (
            "rm",
            comuna,
            "Metropolitana",
        )

    for alias, nombre in c["aliases_rm"].items():
        lugares[alias] = ("rm", nombre, "Metropolitana")

    for ciudad, region in c["ciudades_fuera_rm"].items():
        lugares[normalizar_texto(ciudad)] = (
            "fuera_rm",
            ciudad,
            region,
        )

    # Cubrir comunas fuera de la RM, no solo capitales y ciudades más comunes.
    # Esto evita marcar como oportunidad un salón cuyo lugar de prestación sí
    # está informado, pero cuyo topónimo no estaba en la lista corta anterior.
    for region, comunas in c.get("comunas_fuera_rm", {}).items():
        for comuna in comunas:
            lugares.setdefault(normalizar_texto(comuna), ("fuera_rm", comuna, region))

    for alias, region in c.get("aliases_regiones_fuera_rm", {}).items():
        lugares[normalizar_texto(alias)] = ("fuera_rm", None, region)

    for region in c["regiones_fuera_rm"]:
        nombre = normalizar_texto(region).replace("’", "'")

        for prefijo in ("region de ", "region del ", "region de la "):
            lugares[prefijo + nombre] = (
                "fuera_rm",
                None,
                region,
            )

    patron_lugares = re.compile(
        r"(?<!\w)(?:"
        + "|".join(re.escape(x) for x in sorted(lugares, key=len, reverse=True))
        + r")(?!\w)"
    )

    return grupos, ambiguedades, lugares, patron_lugares


def _campos(datos: dict):
    datos, problemas = _entrada_segura(datos)
    campos, parcial, total = [], bool(problemas), 0

    def agregar(fuente, valor):
        nonlocal parcial, total

        if not isinstance(valor, str) or not valor.strip():
            return

        limite = min(
            MAX_CAMPO,
            max(0, MAX_TEXTO_TOTAL - total),
        )
        parcial |= len(valor) > limite

        if limite:
            texto = valor[:limite]
            campos.append((fuente, texto))
            total += len(texto)

    for nombre in ("nombre", "descripcion"):
        agregar(nombre, datos.get(nombre))

    for n, item in enumerate(datos["items"]):
        for nombre in ("nombre_producto", "descripcion", "categoria"):
            agregar(
                f"items[{n}].{nombre}",
                item.get(nombre),
            )

    for doc in datos["documentos"]:
        if not doc.get("vigente", True) or doc.get("estado_extraccion") != "extraido":
            continue

        for pagina in doc.get("paginas_texto") or []:
            agregar(
                f"documentos[{doc['id']}].paginas[{pagina['pagina']}]",
                pagina.get("texto"),
            )

    return campos, parcial


def textos_servicio(datos: dict) -> list[dict]:
    """Excluye nombres y domicilios administrativos del comprador."""
    return [{"fuente": fuente, "texto": texto} for fuente, texto in _campos(datos)[0]]


def _fragmento(
    texto: str,
    inicio: int,
    fin: int,
    posiciones=None,
) -> str:
    if posiciones is None:
        _, posiciones = _texto_con_mapa(texto)

    if not posiciones:
        return ""

    a = posiciones[min(inicio, len(posiciones) - 1)][0]
    b = posiciones[min(fin - 1, len(posiciones) - 1)][1]

    return texto[max(0, a - 110) : min(len(texto), b + 150)].strip()


def _mencion_ajena(grupo, m, normal):
    """Desambiguación local: no borra otro servicio hotelero del mismo texto."""
    antes = re.split(
        r"[.;\n]",
        normal[: m.start()],
    )[
        -1
    ][-120:]
    despues = normal[m.end() :]

    if grupo == "alimentacion_asociada" and re.fullmatch(r"alimentacion", m.group()):
        if _alimentacion_no_hotelera(_clausula_local(normal, m.start())):
            return True

    if grupo == "alojamiento":
        if re.match(r"\s+(?:hospitalarias?|clinicas?|sanitarias?)\b", despues):
            return True
        if re.fullmatch(r"residencia(?: temporal)?", m.group()):
            # Un electrodoméstico destinado a una residencia no contrata estadías.
            contratacion = re.search(
                r"\b(?:requiere|requieren|solicita|solicitan|"
                r"contrata|contratar|contratacion|arriendo|"
                r"alquiler|reservas?)"
                r"\s+(?:(?:de|un|una|el|la)\s+)*$",
                antes,
            )
            personas = re.search(
                r"\bpara\s+(?:(?:los|las)\s+)?(?:\d+\s+)?"
                r"(?:personas|participantes|asistentes|"
                r"delegaciones|funcionarios|estudiantes|"
                r"alumnos|pacientes|internos)\b",
                despues[:120],
            )

            if re.match(
                r"\s+(?:(?:de|para)\s+)?(?:sanitarias?|estudiantiles?|de menores|"
                r"hospitalarias?|clinicas?|para adultos mayores)\b",
                despues,
            ):
                return True

            if not (contratacion or personas):
                return True

        return bool(
            re.match(
                r"\s+(?:(?:de|para)\s+)?"
                r"(?:infraestructura virtualizada|servidores?|"
                r"maquinas virtuales|sitios? web|web|cloud|nube|datos|aplicaciones?)\b",
                despues,
            )
        )

    if grupo == "salones":
        return bool(
            re.search(
                r"\b(?:sillas?|mesas?|muebles?|mobiliario)"
                r"\s+(?:(?:de|para)\s+)(?:el\s+|los\s+)?$",
                antes,
            )
        )

    if grupo == "actividades":
        return bool(
            (
                re.fullmatch(r"jornadas?|taller(?:es)?", m.group())
                and (
                    re.match(
                        r"\s+(?:normal|extraordinaria|laboral|"
                        r"particular|mecanico)\b",
                        despues,
                    )
                    or re.search(
                        r"\b(?:mecanico|mecanica|fuera de|" r"reparaciones? en)\s+$",
                        antes,
                    )
                )
            )
            or (
                m.group().startswith("capacitacion")
                and re.search(r"\bcursos? de\s+$", antes)
            )
            or (
                m.group().startswith("reunion")
                and re.search(r"\bmesas?\s+(?:de\s+)?$", antes)
            )
        )

    if grupo == "alimentacion_asociada":
        if re.search(
            r"\b(?:sin|no se requiere|no incluye)" r"\s+(?:servicio de\s+)?$",
            antes,
        ):
            return True

        if m.group() == "alimentacion":
            return bool(
                re.match(
                    r"\s+(?:enteral|parenteral|electrica)\b",
                    despues,
                )
                or re.search(
                    r"\b(?:tension|voltaje|fuentes?|cables?|"
                    r"conector(?:es)?|adaptador(?:es)?|puertos?)"
                    r"\s+de\s+$",
                    antes,
                )
                or re.match(
                    r"\s*[:=]?\s*(?:(?:a|de)\s+)?"
                    r"\d+(?:[.,]\d+)?"
                    r"(?:\s*[-/–]\s*\d+(?:[.,]\d+)?)?"
                    r"\s*(?:v(?:ac|dc)?|voltios?|watts?|w|hz)\b",
                    despues,
                )
            )

    return False


def _ambiguedad_administrativa(regla, m, normal):
    # La orden de compra formaliza también servicios; no implica comprar bienes.
    if regla != "compra_bienes_obras":
        return False

    antes = normal[max(0, m.start() - 40) : m.start()]

    return (
        m.group() == "compra" and bool(re.search(r"\borden(?:es)? de\s+$", antes))
    ) or (
        m.group() == "suministro"
        and bool(re.search(r"\bservicio de\s+$", antes))
        and bool(
            re.match(
                r"\s+de\s+(?:cof+e+e?\s*[- ]?breaks?|"
                r"coctel(?:es)?|banqueteria|catering|"
                r"alimentacion|desayunos?|almuerzos?|cenas?)\b",
                normal[m.end() :],
            )
        )
    )


_SERVICIO_EXPLICITO = re.compile(
    r"\b(?:arriendo|arrendamiento|alquiler|reserva)\s+(?:de\s+)?"
    r"(?:(?:un|una|los|las)\s+)?(?:salon(?:es)?|salas?|recintos?|espacios?|auditorios?)\b"
    r"|\bservicios?\s+de\s+(?:banqueteria|catering|alimentacion|cof+e+e?\s*[- ]?breaks?)\b"
    r"|\b(?:se\s+)?(?:requiere|requieren|solicita|solicitan|contrata|contratar)\s+"
    r"(?:el\s+)?(?:salon(?:es)?|coffee\s*break)\b"
    r"|\b(?:coffee\s*break|almuerzos?|desayunos?|cenas?|colaciones?)"
    r"\s+para\s+(?:(?:los|las)\s+)?(?:\d+\s+)?(?:personas|participantes|asistentes|delegaciones|pacientes|funcionarios)\b"
)


def _alimentacion_no_hotelera(clausula):
    return bool(
        _ALIMENTACION_ELECTRICA.search(clausula)
        or _ALIMENTACION_PAGO_ELECTRONICO.search(clausula)
        or _ALIMENTACION_CLINICA.search(clausula)
        or _ALIMENTACION_EQUIPOS.search(clausula)
        or _ALIMENTACION_ANIMAL.search(clausula)
        or _ALIMENTACION_CENTRAL_INSUMOS.search(clausula)
        or _ALIMENTACION_PERSONAL.search(clausula)
        or _ALIMENTACION_INSTITUCIONAL.search(clausula)
        or (
            _COMPRA_BIENES.search(clausula)
            and _BIENES_NO_HOTELEROS.search(clausula)
            and not _SERVICIO_EXPLICITO.search(clausula)
        )
    )


def _clausula_local(normal, inicio):
    antes = normal[:inicio]
    a = max((m.end() for m in re.finditer(r"[.;\n]", antes)), default=0)
    fin = re.search(r"[.;\n]", normal[inicio:])
    b = inicio + fin.start() if fin else len(normal)
    return normal[a:b]


def _codigo_producto(item):
    valor = item.get("codigo_producto")
    if isinstance(valor, bool):
        return ""
    if isinstance(valor, (str, int)):
        return str(valor).strip()
    return ""


def _objeto_ajeno_item(item):
    catalogo = cargar_catalogo()
    codigo = _codigo_producto(item)
    if codigo in catalogo.get("codigos_producto_protegidos", {}):
        return None
    if codigo in catalogo.get("codigos_producto_ajenos", {}):
        return catalogo["codigos_producto_ajenos"][codigo]
    if re.fullmatch(r"\d{8}", codigo):
        return catalogo.get("familias_producto_ajenas", {}).get(
            codigo[:4]
        ) or catalogo.get("segmentos_producto_ajenos", {}).get(codigo[:2])
    return None


@cache
def _reglas_objeto_ajeno():
    catalogo = cargar_catalogo()
    return [
        (regla, re.compile(regla["patron"]))
        for regla in (
            catalogo.get("objetos_bienes", [])
            + catalogo.get("exclusiones_evidentes", [])
        )
    ]


def _evidencia_objeto_ajeno(campos):
    for fuente, texto in campos:
        if fuente.endswith("categoria"):
            continue
        normal, mapa = _texto_con_mapa(texto)
        for regla, patron in _reglas_objeto_ajeno():
            m = patron.search(normal)
            if m:
                return {
                    "codigo": regla["id"],
                    "motivo": regla["motivo"],
                    "fuente": fuente,
                    "evidencia": _fragmento(texto, m.start(), m.end(), mapa),
                }
    return None


def _mencion_negada(normal, inicio):
    antes = normal[max(0, inicio - 100) : inicio]
    return bool(
        re.search(
            r"\b(?:sin|no\s+(?:se\s+)?(?:requiere|requieren|incluye|incluyen|considera|contempla))"
            r"\s+(?:(?:el|la)\s+)?(?:servicios?\s+de\s+)?$",
            antes,
        )
    )


def _servicio_concreto_en_item(normal):
    if _SERVICIO_EXPLICITO.search(normal):
        return True
    if re.search(r"\bcof+e+e?\s*[- ]?breaks?\b", normal):
        return True
    return bool(
        re.search(r"\b(?:capacitacion|jornada|seminario|evento|reunion)\b", normal)
        and re.search(
            r"\b(?:con|incluye|incluyen)\s+(?:servicio\s+de\s+)?(?:almuerzos?|desayunos?|cenas?|alimentacion)\b",
            normal,
        )
    )


def _evidencia_item_en_contexto(datos, propios, codigo):
    for regla in cargar_catalogo().get("reglas_contexto_items", []):
        if regla.get("codigos") and codigo not in regla["codigos"]:
            continue
        for campo in ("nombre", "descripcion"):
            cabecera = datos.get(campo)
            if not isinstance(cabecera, str):
                continue
            if not re.search(
                regla["patron_cabecera"], normalizar_texto(cabecera[:MAX_CAMPO])
            ):
                continue
            for fuente, texto in propios:
                if fuente.endswith("categoria"):
                    continue
                normal, mapa = _texto_con_mapa(texto)
                m = re.search(regla["patron_item"], normal)
                if m:
                    return {
                        "codigo": regla["id"],
                        "motivo": regla["motivo"],
                        "fuente": fuente,
                        "fuente_contexto": campo,
                        "contexto": cabecera[:500],
                        "evidencia": _fragmento(texto, m.start(), m.end(), mapa),
                    }
    return None


def _mencion_de_item_ajeno(datos, fuente, m, normal):
    unidad = re.match(r"items\[(\d+)\]\.", fuente)
    if unidad is None:
        return False
    n = int(unidad.group(1))
    items = datos.get("items") or []
    if n >= len(items) or not _objeto_ajeno_item(items[n]):
        return False
    # Los nombres genéricos no prueban servicio; una descripción concreta sí.
    if fuente.endswith("nombre_producto"):
        return True
    return not _servicio_concreto_en_item(_clausula_local(normal, m.start()))


def _mencion_en_compra_de_bienes(normal: str, inicio: int) -> bool:
    """Desambigua bienes y servicios dentro de la misma cláusula."""
    clausula = _clausula_local(normal, inicio)
    hay_bienes = any(
        re.search(regla["patron"], clausula)
        for regla in cargar_catalogo().get("objetos_bienes", [])
    )
    return bool(hay_bienes and not _SERVICIO_EXPLICITO.search(clausula))


def _evaluar_objetos_por_item(datos, campos, directas):
    evaluaciones = []
    protegidos = cargar_catalogo().get("codigos_producto_protegidos", {})
    unidades_servicio = {_unidad(x["fuente"]) for x in directas}
    for n, item in enumerate(datos.get("items") or []):
        unidad = f"items[{n}]"
        codigo = _codigo_producto(item)
        registro = {
            "fuente": unidad,
            "codigo_producto": codigo,
            "estado": "indeterminado",
            "evidencia": None,
        }
        if unidad in unidades_servicio:
            registro["estado"] = "servicio_hotelero"
        elif codigo in protegidos:
            registro["estado"] = "potencial_hotelero"
        else:
            razon = _objeto_ajeno_item(item)
            if razon:
                registro["estado"] = "objeto_ajeno"
                registro["evidencia"] = {
                    "codigo": "producto_ajeno",
                    "fuente": unidad + ".codigo_producto",
                    "motivo": (
                        "La línea corresponde a "
                        + razon
                        + "; no identifica contratación de servicios del hotel."
                    ),
                    "evidencia": f"{codigo}: {item.get('nombre_producto') or item.get('descripcion') or razon}",
                }
            else:
                propios = [(f, t) for f, t in campos if f.startswith(unidad + ".")]
                evidencia = _evidencia_objeto_ajeno(
                    propios
                ) or _evidencia_item_en_contexto(datos, propios, codigo)
                if evidencia:
                    registro["estado"] = "objeto_ajeno"
                    registro["evidencia"] = evidencia
        evaluaciones.append(registro)
    return evaluaciones


_ESPACIO_SALONES = re.compile(
    r"\bsalon(?:es)?\b|\bsalas?\b|\bauditorios?\b|\brecintos?\b|"
    r"\bespacios?(?:\s+fisicos?)?\b|"
    r"\bcentros?\s+de\s+(?:eventos?|convenciones?)\b"
)
_EVENTO_SALONES = re.compile(
    r"\b(?:eventos?|seminarios?|congresos?|jornadas?|reunion(?:es)?|"
    r"conferencias?|capacitacion(?:es)?|taller(?:es)?|ceremonias?|"
    r"convencion(?:es)?|encuentros?|actividades?|celebraciones?|"
    r"conmemoraciones?|festivales?|galas?|aniversarios?|ferias?)\b"
)
_SALA_EVENTO = re.compile(
    r"\bsalas?\s+(?:de|para)\s+(?:reunion(?:es)?|eventos?|capacitacion|"
    r"conferencias?|seminarios?|jornadas?)\b"
)
_USO_CLINICO = re.compile(
    r"\b(?:para|destinad[oa]s?\s+a)\s+(?:(?:la|el|los|las)\s+)?"
    r"(?:(?:realizar|efectuar|practicar)\s+)?"
    r"(?:procedimientos?\s+(?:endovasculares?|medicos?|quirurgicos?|"
    r"diagnosticos?|clinicos?)|hospitalizacion|hospitalizar|cirugias?|"
    r"atencion\s+clinica)\b"
)
_NO_ESPACIO_EVENTO = re.compile(
    r"\bsalon(?:es)?\s+de\s+belleza\b|\bsalas?\s+(?:de\s+)?"
    r"(?:operaciones|maquinas|servidores?|clases|cuna|espera|era|tratamiento|"
    r"procedimientos?|estimulacion(?:\s+multisensorial)?|rehabilitacion|"
    r"duplicado)\b|"
    r"\brecintos?\s+(?:clinicos?|hospitalarios?|fiscales?)\b|"
    r"\bbodegas?\b|\b(?:areas?|taller(?:es)?)\s+de\s+maquinarias?\b"
)
_BIENES_SALONES = re.compile(
    r"\b(?:compra|adquisicion|suministro|adq\.?|sum\.?)\b[^.;\n]{0,100}"
    r"\b(?:mobiliario|sillas?|mesas?|muebles?|equipos?|equipamiento|"
    r"proyectores?|computadores?|hardware|discos?\s+duros?|ssd|pintura|"
    r"microesferas|insumos?|utiles?)\b"
)
_SALON_CONTRATADO = re.compile(
    r"\b(?:arriendo|arrendamiento|alquiler|reserva|uso)\s+(?:de\s+)?"
    r"(?:(?:un|una|el|la|los|las)\s+)?"
    r"(?:salon(?:es)?|salas?|auditorios?|recintos?|espacios?)\b"
)
_NO_EVENTO_TERMINO = re.compile(
    r"\b(?:capacitacion|jornada|seminario|evento|reunion|conferencia|"
    r"congreso|encuentro|taller)\b"
)
_SEDE_TERCERO_SALONES = re.compile(
    r"\b(?:salon(?:es)?|salas?|auditorios?)\s+(?:municipal(?:es)?|"
    r"del?\s+(?:hospital|colegio|liceo|establecimiento|municipio)|"
    r"de\s+(?:la\s+)?(?:universidad|institucion|escuela|municipalidad))\b|"
    r"\b(?:en|dentro\s+de|en\s+dependencias\s+de)\s+"
    r"(?:el|la|los|las)\s+(?:oficinas?|colegio|escuela|hospital|liceo)\b|"
    r"\b(?:lugar|recinto|sede)\s+(?:sera|seran|es|son|lo\s+proporciona|"
    r"proporcionad[oa]\s+por)\s+(?:(?:el|la)\s+)?"
    r"(?:comprador|institucion|organismo|municipalidad)\b"
)
_HOTEL_SEDE_SALONES = re.compile(
    r"\b(?:salon(?:es)?\s+del?|salas?\s+del?|"
    r"evento\s+se\s+realizara\s+en\s+(?:el\s+)?|"
    r"lugar\s+del\s+evento\s*:\s*(?:el\s+)?)\s*hotel\s+"
    r"(?!en\b|de\b|para\b|que\b)[a-z0-9][^.;\n]{0,90}"
)
_SEDE_ALTERNATIVA = re.compile(
    r"\b(?:a\s+eleccion\s+del\s+proveedor|proveedor\s+(?:debera|debe|"
    r"podra)\s+(?:ofrecer|proponer|proporcionar)\s+(?:el\s+)?salon|"
    r"o\s+(?:en\s+)?(?:un\s+)?hotel)\b"
)
_COMIDA_SALONES = re.compile(
    r"\b(?:cof+e+e?\s*[- ]?breaks?|banqueteria|catering|alimentacion|"
    r"almuerzos?|desayunos?|cenas?|coctel(?:es)?|cocktails?)\b"
)
_ALIMENTACION_ELECTRICA = re.compile(
    r"\b(?:alimentacion\s+(?:electrica|ininterrumpida)|"
    r"sistema\s+de\s+alimentacion\s+ininterrumpida|"
    r"ups|tableros?\s+electricos?|bypass)\b|"
    r"\b(?:tension|voltaje|fuentes?|cables?|conector(?:es)?|adaptador(?:es)?|puerto(?:s)?)"
    r"\s+de\s+alimentacion\b|"
    r"\balimentacion\s*[:=]?\s*(?:de\s+)?\d+(?:[.,]\d+)?"
    r"(?:\s*[-/]\s*\d+(?:[.,]\d+)?)?\s*(?:v(?:ac|dc)?|voltios?|w|watts?|hz)\b"
)
_ALIMENTACION_CLINICA = re.compile(
    r"\b(?:alimentacion|nutricion)\b[^.;\n]{0,120}"
    r"\b(?:parenteral|enteral|npt|electrolitos?|lipidos?)\b|"
    r"\b(?:bolsas?|soluciones?)\b[^.;\n]{0,100}"
    r"\b(?:alimentacion|nutricion)\b[^.;\n]{0,80}"
    r"\b(?:parenteral|enteral|npt)\b"
)
_ALIMENTACION_EQUIPOS = re.compile(
    r"\b(?:mantencion|mantenimiento|reparacion|reparativo|preventivo|"
    r"preventiva|correctivo|correctiva)\b[^.;\n]{0,140}"
    r"\b(?:equipos?|maquinarias?)\b[^.;\n]{0,100}"
    r"\bcentral\s+(?:de\s+)?alimentacion\b|"
    r"\bcentral\s+(?:de\s+)?alimentacion\b[^.;\n]{0,140}"
    r"\b(?:equipos?|maquinarias?|mantencion|mantenimiento|reparacion)\b"
)
_ALIMENTACION_ANIMAL = re.compile(
    r"\b(?:forraje|alimentacion|alimentos?)\b[^.;\n]{0,100}"
    r"\b(?:animal|apicola|ganado|ovino|caprino|cabras?|abejas?)\b|"
    r"\b(?:animal|apicola|ganado|ovino|caprino|cabras?|abejas?)\b"
    r"[^.;\n]{0,100}\b(?:forraje|alimentacion|alimentos?)\b"
)
_ALIMENTACION_CENTRAL_INSUMOS = re.compile(
    r"\b(?:productos?|insumos?|suministro|adquisicion|compra|"
    r"quimicos?|detergentes?|desinfectantes?|aseo|limpieza|"
    r"dosificadores?|inocuidad)\b[^.;\n]{0,280}"
    r"\b(?:unidad\s+(?:de\s+)?(?:alimentacion|central de produccion)|"
    r"central\s+(?:de\s+)?alimentacion|sedile|ucp)\b|"
    r"\b(?:unidad\s+(?:de\s+)?(?:alimentacion|central de produccion)|"
    r"central\s+(?:de\s+)?alimentacion|sedile|ucp)\b[^.;\n]{0,200}"
    r"\b(?:productos?|insumos?|quimicos?|detergentes?|desinfectantes?|"
    r"aseo|limpieza|dosificadores?|inocuidad|mantencion|mantenimiento|equipos?)\b"
)
_ALIMENTACION_PERSONAL = re.compile(
    r"\b(?:contratacion|provision|suministro|dotacion)\b"
    r"[^.;\n]{0,100}\b(?:auxiliar(?:es)?|personal|puestos?|cargos?)\b"
    r"[^.;\n]{0,100}\b(?:alimentacion|nutricion)\b|"
    r"\bservicios?\s+aux(?:iliar(?:es)?)?\.?\s+(?:para|de)\s+"
    r"(?:alimentacion|nutricion)\b|"
    r"\b(?:aux(?:iliar(?:es)?)?|personal|puestos?|cargos?)\s+"
    r"(?:de|para)\s+(?:servicio\s+de\s+)?(?:alimentacion|nutricion)\b|"
    r"\b(?:auxiliar(?:es)?|personal auxiliar|dotacion de personal|"
    r"puestos? de trabajo|cargos? de auxiliar(?:es)?)\b"
    r"[^.;\n]{0,100}\b(?:central|servicio|area)\s+(?:de\s+)?"
    r"(?:alimentacion|nutricion)\b"
)
_ALIMENTACION_INSTITUCIONAL = re.compile(
    r"\b(?:alimentacion|servicio de alimentacion|suministro de alimentos?)\b"
    r"[^.;\n]{0,140}\b(?:pacientes?|brigadas?|bases? operativas?|"
    r"establecimientos? educacionales?|escuelas?|casinos? institucionales?|"
    r"casinos?\s+(?:de|del|de la|de los|de las)\s+"
    r"(?:empresa|institucion|organismo|hospital|ejercito|igm|comida)\b)\b|"
    r"\b(?:pacientes?|brigadas?|bases? operativas?|establecimientos? "
    r"educacionales?|escuelas?|casinos? institucionales?|"
    r"casinos?\s+(?:de|del|de la|de los|de las)\s+"
    r"(?:empresa|institucion|organismo|hospital|ejercito|igm|comida)\b)\b"
    r"[^.;\n]{0,140}\b(?:alimentacion|servicio de alimentacion|"
    r"suministro de alimentos?)\b"
)
_COMPRA_BIENES = re.compile(r"\b(?:adquisicion|adq\.?|compra|suministro|sum\.?|materiales? para)\b")
_BIENES_NO_HOTELEROS = re.compile(
    r"\b(?:mobiliario|materiales? (?:de|para) oficina|insumos? (?:de|para) oficina|"
    r"articulos? (?:de|para) oficina|utiles? (?:de|para) oficina|"
    r"materiales? (?:de|para) aseo|productos? (?:de|para) aseo|"
    r"insumos? (?:de|para) aseo|articulos? (?:de|para) aseo|"
    r"detergentes?|desinfectantes?|abarrotes|mercaderias|viveres|"
    r"cafe soluble|cafe instantaneo|productos alimenticios|"
    r"alimentos no perecibles)\b"
)
_ALIMENTACION_PAGO_ELECTRONICO = re.compile(
    r"\b(?:tarjetas?|aplicaciones?|vales?|bonos?)\b[^.;\n]{0,120}"
    r"\b(?:alimentacion|alimentos?|compra(?:r)? alimentos?)\b|"
    r"\b(?:alimentacion|alimentos?)\b[^.;\n]{0,120}"
    r"\b(?:tarjetas?|aplicaciones?|vales?|bonos?)\b"
)
_OBRA_ESPACIO_REUNION = re.compile(
    r"\b(?:recuperacion|restauracion|reparacion|remodelacion|construccion|"
    r"mantencion|mantenimiento|mejoramiento|habilitacion)\b[^.;\n]{0,100}"
    r"\b(?:salon(?:es)?|salas?\s+de\s+reuniones?)\b|"
    r"\b(?:salon(?:es)?|salas?\s+de\s+reuniones?)\b[^.;\n]{0,100}"
    r"\b(?:recuperacion|restauracion|reparacion|remodelacion|construccion|"
    r"mantencion|mantenimiento|mejoramiento|habilitacion)\b"
)
_DOCENCIA_OBLIGATORIA = re.compile(
    r"\b(?:proveedor|oferente|adjudicatario)\b[^.;\n]{0,80}"
    r"\b(?:debe|debera|obligatoriamente)\b[^.;\n]{0,80}"
    r"\b(?:impartir|dictar|certificar|ser\s+otec|ser\s+otic)\b"
)
_PRODUCCION_EVENTOS = re.compile(
    r"\b(?:servicios? de\s+)?(?:produccion|organizacion)\s+"
    r"(?:(?:integral|diversos?|grandes?)\s+)*(?:de|para)?\s*eventos?\b|"
    r"\bproduccion\s+y\s+ejecucion\s+de\s+(?:diversos?|grandes?)?\s*eventos?\b"
)


def _evidencia_perfil(fuente, texto, normal, mapa, coincidencia, codigo, motivo):
    inicio = mapa[coincidencia.start()][0]
    fin = mapa[coincidencia.end() - 1][1]
    return {
        "codigo": codigo,
        "motivo": motivo,
        "fuente": fuente,
        "inicio": inicio,
        "fin": fin,
        "evidencia": texto[max(0, inicio - 100):min(len(texto), fin + 220)].strip(),
    }


def _sede_fijada_salones(normal, hotel_objetivo):
    coincidencia = _SEDE_TERCERO_SALONES.search(normal)
    if coincidencia is None:
        hotel = _HOTEL_SEDE_SALONES.search(normal)
        if hotel and hotel_objetivo not in hotel.group():
            coincidencia = hotel
    if coincidencia is None or _SEDE_ALTERNATIVA.search(normal):
        return None
    clausula = _clausula_local(normal, coincidencia.start())
    if re.search(
        r"\b(?:domicilio|facturacion|entrega\s+de\s+ofertas|"
        r"direccion\s+del\s+comprador|oficinas\s+administrativas)\b",
        clausula,
    ):
        return None
    return coincidencia


def _evaluar_perfil_hotel(datos, campos, base):
    """Evalúa el alcance comercial del hotel sin crear otro pilar."""
    hotel = normalizar_texto(
        cargar_catalogo().get("hotel", {}).get("nombre") or "Hotel Plaza San Francisco"
    )
    validas, rechazadas, genericas, fijas = [], [], [], []
    comidas, comidas_directas = [], []
    clinicas, obligaciones, producciones = [], [], []
    hay_evento = False
    estados = {e.get("fuente"): e.get("estado") for e in base.get("evaluacion_items", [])}

    for fuente, texto in campos:
        if fuente.endswith("categoria"):
            continue
        normal, mapa = _texto_con_mapa(texto)
        producto_generico = fuente.endswith("nombre_producto")
        produccion = _PRODUCCION_EVENTOS.search(normal)
        if produccion and not _mencion_negada(normal, produccion.start()):
            producciones.append(_evidencia_perfil(
                fuente, texto, normal, mapa, produccion, "produccion_eventos",
                "El ítem o descripción contrata organización y ejecución de eventos, no por sí sola un servicio del hotel.",
            ))
        if not producto_generico:
            for actividad in _EVENTO_SALONES.finditer(normal):
                clausula_evento = _clausula_local(normal, actividad.start())
                # “sala de reuniones” describe el destino de un bien, no un evento.
                es_sala_reuniones = actividad.group().startswith("reunion") and bool(
                    re.search(
                        r"\b(?:salas?\s+de\s+reuniones?|mesas?\s+(?:de\s+)?reunion(?:es)?)\b",
                        clausula_evento,
                    )
                )
                es_taller_mecanico = actividad.group().startswith("taller") and bool(
                    re.search(
                        r"\b(?:maquinarias?|fiscal|mantencion|mantenimiento|"
                        r"reparacion|mecanica|vehiculos?)\b",
                        clausula_evento,
                    )
                )
                if not es_taller_mecanico and not (
                    es_sala_reuniones and fuente.startswith("items[")
                ):
                    hay_evento = True
            for patron, destino, codigo in (
                (_COMIDA_SALONES, comidas, "alimentacion_sin_salon"),
                (re.compile(r"\b(?:procedimientos?\s+endovasculares?|prestaciones\s+medicas|servicios?\s+quirurgicos|hospitalizar|hospitalizacion)\b"), clinicas, "objeto_clinico"),
                (_DOCENCIA_OBLIGATORIA, obligaciones, "docencia_integral"),
            ):
                m = next((c for c in patron.finditer(normal)
                    if not (codigo == "alimentacion_sin_salon"
                        and c.group() == "alimentacion"
                        and _alimentacion_no_hotelera(_clausula_local(normal, c.start())))), None)
                if (
                    m
                    and not _mencion_negada(normal, m.start())
                    and not _mencion_de_item_ajeno(datos, fuente, m, normal)
                ):
                    evidencia = _evidencia_perfil(fuente, texto, normal, mapa, m, codigo, "Objeto identificado en el contexto de la solicitud.")
                    destino.append(evidencia)
                    tiene_personas = bool(re.search(
                        r"\b\d+\s+(?:personas|participantes|asistentes|funcionarios)\b",
                        _clausula_local(normal, m.start()),
                    ))
                    servicio_alimentacion_en_ficha = (
                        codigo == "alimentacion_sin_salon"
                        and not fuente.startswith("items[")
                        and re.search(r"\bservicios?\s+de\s+alimentacion\b", normal)
                        and re.search(r"\balimentacion\b", _clausula_local(normal, m.start()))
                        and any(
                            re.search(r"\b\d+\s+(?:personas|participantes|asistentes|funcionarios)\b", texto_ficha)
                            for campo_ficha, texto_ficha in campos
                            if not campo_ficha.startswith("items[") and isinstance(texto_ficha, str)
                        )
                    )
                    es_coffee_break = bool(re.match(r"cof+e+e?\s*[- ]?breaks?", m.group()))
                    coffee_break_solicitado = (
                        codigo == "alimentacion_sin_salon"
                        and es_coffee_break
                        and (
                            _SERVICIO_EXPLICITO.search(_clausula_local(normal, m.start()))
                            or _patrones()[3].search(_clausula_local(normal, m.start()))
                        )
                    )
                    alimentacion_grupal_explicita = (
                        codigo == "alimentacion_sin_salon"
                        and m.group() == "alimentacion"
                        and servicio_alimentacion_en_ficha
                    )
                    if coffee_break_solicitado or alimentacion_grupal_explicita:
                        if servicio_alimentacion_en_ficha:
                            evidencia = next((
                                _evidencia_perfil(campo_ficha, texto_ficha, normal_ficha, mapa_ficha,
                                    m_ficha, "alimentacion_sin_salon", "Se solicita alimentación para un grupo de personas.")
                                for campo_ficha, texto_ficha in campos
                                if not campo_ficha.startswith("items[") and isinstance(texto_ficha, str)
                                for normal_ficha, mapa_ficha in [_texto_con_mapa(texto_ficha)]
                                for m_ficha in _COMIDA_SALONES.finditer(normal_ficha)
                                if m_ficha.group() == "alimentacion"
                                and re.search(
                                    r"\b\d+\s+(?:personas|participantes|asistentes|funcionarios)\b",
                                    _clausula_local(normal_ficha, m_ficha.start()),
                                )
                                and not _alimentacion_no_hotelera(_clausula_local(normal_ficha, m_ficha.start()))
                            ), evidencia)
                        comidas_directas.append(evidencia)
            m = _sede_fijada_salones(normal, hotel)
            if m:
                fijas.append(_evidencia_perfil(fuente, texto, normal, mapa, m, "sede_tercero", "El lugar está fijado en instalaciones de un tercero, no se ofrece el salón del hotel."))

        for m in _ESPACIO_SALONES.finditer(normal):
            clausula = _clausula_local(normal, m.start())
            antes = normal[:m.start()].rsplit(".", 1)[-1].rsplit(";", 1)[-1].rsplit("\n", 1)[-1]
            registro = _evidencia_perfil(fuente, texto, normal, mapa, m, "salon_eventos", "Posible contratación de un salón para eventos.")
            motivo = None
            if _mencion_negada(normal, m.start()):
                motivo = "La necesidad de salón está negada."
            elif _OBRA_ESPACIO_REUNION.search(clausula):
                motivo = "Se solicita recuperar, reparar o habilitar una sala; no contratar su arriendo para un evento."
            elif _NO_ESPACIO_EVENTO.search(clausula) or _USO_CLINICO.search(normal[m.end():m.end() + 200]):
                motivo = "El espacio se solicita para un uso clínico o especializado, no para un evento en el hotel."
            elif _BIENES_SALONES.search(clausula) and not _SALON_CONTRATADO.search(clausula):
                motivo = "La referencia al salón es el destino de bienes, no la contratación de ese espacio."
            elif _sede_fijada_salones(clausula, hotel):
                motivo = "Se identifica un salón o recinto de un tercero como lugar fijado de prestación."
            if motivo:
                registro.update(codigo="espacio_ajeno", motivo=motivo)
                rechazadas.append(registro)
                continue
            if producto_generico:
                genericas.append(registro)
                continue
            es_salon = bool(re.fullmatch(r"salon(?:es)?", m.group()))
            evento = bool(_EVENTO_SALONES.search(clausula))
            arriendo = bool(_SALON_CONTRATADO.search(clausula))
            m_comida = next((c for c in _COMIDA_SALONES.finditer(clausula)
                if not (c.group() == "alimentacion" and _alimentacion_no_hotelera(clausula))), None)
            servicio_asociado = bool(m_comida)
            salon_alquilado = arriendo and bool(
                re.match(r"salas?|salon(?:es)?|auditorios?", m.group())
            ) and not re.search(r"\bsalon(?:es)?\s+de\s+belleza\b", clausula)
            espacio_para_evento = m.group().startswith("espacio") and evento
            recinto_para_evento = m.group().startswith("recinto") and arriendo and evento
            if (
                (
                    _SALA_EVENTO.search(clausula)
                    and (
                        not fuente.startswith("items[")
                        or estados.get(_unidad(fuente)) != "objeto_ajeno"
                    )
                )
                or salon_alquilado
                or espacio_para_evento
                or recinto_para_evento
                or (
                    es_salon
                    and (evento or servicio_asociado)
                    and (estados.get(_unidad(fuente)) != "objeto_ajeno" or arriendo)
                )
            ):
                if estados.get(_unidad(fuente)) == "objeto_ajeno" and not (arriendo or evento):
                    genericas.append(registro)
                    continue
                registro.update(grupo="salones", nivel="directa", termino=m.group())
                validas.append(registro)
            else:
                genericas.append(registro)

    genericas_concretas = [e for e in genericas if not e["fuente"].endswith("nombre_producto")]
    items = base.get("evaluacion_items", [])
    items_ajenos = [e for e in items if e.get("estado") == "objeto_ajeno"]
    items_hoteleros = [
        e for e in validas
        if e.get("fuente", "").startswith("items[")
    ] + [
        e for e in comidas_directas
        if e.get("fuente", "").startswith("items[")
    ]
    ficha_hotelera_explicita = any(
        not e.get("fuente", "").startswith("items[")
        for e in validas + comidas_directas
    )
    # Los ítems concretos pesan más que las menciones genéricas de la ficha.
    peso_pertinencia = (
        5 * len(items_hoteleros)
        + 3 * int(ficha_hotelera_explicita)
        + int(hay_evento)
        - 4 * len(items_ajenos)
    )
    senales_ponderadas = {
        "servicio_hotelero_en_item": len(items_hoteleros),
        "servicio_hotelero_explicito_en_ficha": int(ficha_hotelera_explicita),
        "actividad_generica_en_ficha": int(hay_evento),
        "items_fuera_de_alcance": len(items_ajenos),
        "puntaje": peso_pertinencia,
    }
    unidades_fijas = {_unidad(e["fuente"]) for e in fijas}
    libres = [e for e in validas if _unidad(e["fuente"]) not in unidades_fijas]
    resultado, codigo = "sin_informacion", "alcance_indeterminado"
    motivo = "Falta confirmar si se contrata un salón para eventos o un servicio de alimentación asociado que pueda ofrecer el hotel."
    evidencias = []
    items_suficientemente_ajenos = bool(
        items
        and not items_hoteleros
        and not comidas
        and not ficha_hotelera_explicita
        and len(items_ajenos) == len(items)
        and not hay_evento
    )
    if items_suficientemente_ajenos:
        evidencias_items = [e.get("evidencia") for e in items_ajenos if e.get("evidencia")]
        if ficha_hotelera_explicita:
            codigo = "conflicto_ficha_items"
            motivo = (
                "La ficha menciona un servicio compatible, pero todos los ítems "
                "identificados corresponden a objetos ajenos al hotel. Revisar "
                "la discrepancia antes de clasificarla como oportunidad."
            )
            evidencias = evidencias_items[:30]
        else:
            resultado = "no_cumple"
            codigo = (
                evidencias_items[0].get("codigo")
                if evidencias_items and isinstance(evidencias_items[0], dict)
                else "items_fuera_alcance"
            )
            motivo = evidencias_items[0]["motivo"] if evidencias_items else (
                "Los ítems identificados no corresponden a salones ni servicios "
                "de alimentación para eventos."
            )
            evidencias = evidencias_items[:30]
    elif validas:
        if fijas and not libres:
            resultado, codigo = "no_cumple", "sede_tercero"
            motivo = "El evento o servicio está fijado en instalaciones de un tercero; no se solicita el salón del hotel."
            evidencias = fijas
        elif fijas:
            codigo = "sede_contradictoria"
            motivo = "Hay una solicitud de salón y una sede de tercero; falta aclarar qué líneas permiten ofrecer el espacio del hotel."
            evidencias = fijas
        elif obligaciones:
            codigo = "docencia_integral"
            motivo = "Además del espacio se exige impartir o certificar formación; falta confirmar el alcance que puede contratarse al hotel."
            evidencias = obligaciones
        else:
            resultado, codigo = "cumple", "salon_eventos"
            motivo = "Se solicita un salón para eventos; los servicios asociados solo aplican dentro de ese espacio del hotel."
            evidencias = validas
    elif comidas_directas and not fijas and not producciones:
        resultado, codigo = "cumple", "alimentacion_para_personas"
        motivo = "Se solicita un servicio de alimentación para participantes; confirmar en las bases si se presta en el hotel o como parte de un evento."
        evidencias = comidas_directas
    elif producciones:
        resultado, codigo = "no_cumple", "produccion_eventos"
        motivo = "Se contrata la producción u organización del evento; no se solicita por separado un salón del hotel. El catering dentro de este paquete no cambia el objeto principal."
        evidencias = producciones
    elif (
        base.get("evaluacion_items")
        and all(e.get("estado") == "objeto_ajeno" for e in base["evaluacion_items"])
        and not comidas
    ):
        resultado, codigo, evidencias = "no_cumple", "objeto_ajeno", [
            e["evidencia"] for e in base["evaluacion_items"] if e.get("evidencia")
        ]
        motivo = evidencias[0]["motivo"] if evidencias else "Los ítems corresponden a bienes ajenos a los servicios del hotel."
    elif any(
        duda.get("codigo") == "posible_error_ortografico"
        for duda in base.get("ambiguedades", [])
    ):
        codigo = "posible_error_ortografico"
        motivo = (
            "Una palabra podría referirse a un salón o servicio de "
            "eventos, pero parece tener un error de escritura. Revisar la ficha "
            "antes de descartarla."
        )
        evidencias = [
            duda for duda in base.get("ambiguedades", [])
            if duda.get("codigo") == "posible_error_ortografico"
        ]
    elif fijas and (comidas or rechazadas):
        resultado, codigo, motivo, evidencias = "no_cumple", "servicio_en_tercero", "Se solicita prestar el servicio en una sede de tercero, sin contratación del salón del hotel.", fijas
    elif rechazadas and not genericas_concretas and not any(
        e.get("motivo", "").startswith("La referencia al salón es el destino de bienes")
        for e in rechazadas
    ):
        resultado, codigo, motivo, evidencias = "no_cumple", "espacio_no_eventos", rechazadas[0]["motivo"], rechazadas
    elif clinicas and not genericas_concretas and not hay_evento:
        resultado, codigo, motivo, evidencias = "no_cumple", "objeto_clinico", "El objeto es una prestación o infraestructura clínica, no hospedaje ni un servicio para eventos del hotel.", clinicas
    elif comidas:
        codigo, motivo, evidencias = "alimentacion_salon_por_confirmar", "Se solicita catering, coffee break o banquetería, pero no se confirma el lugar. Revisar si el hotel puede ofrecer su salón junto con el servicio.", comidas
    elif (
        not items_hoteleros
        and not ficha_hotelera_explicita
        and not genericas
        and not hay_evento
        and _evidencia_objeto_ajeno([(f, t) for f, t in campos if not f.startswith("items[")])
    ):
        evidencia = _evidencia_objeto_ajeno([(f, t) for f, t in campos if not f.startswith("items[")])
        resultado, codigo, evidencias = "no_cumple", "objeto_ajeno", [evidencia]
        motivo = evidencia["motivo"]
    elif genericas and (
        hay_evento
        or any(
            _SALON_CONTRATADO.search(normalizar_texto(e.get("evidencia", "")))
            for e in genericas
        )
    ):
        codigo, motivo, evidencias = "espacio_por_confirmar", "Se menciona un espacio o categoría, pero falta confirmar el arriendo o uso de un salón para un evento en el hotel.", genericas
    elif comidas:
        codigo, motivo, evidencias = "alimentacion_salon_por_confirmar", "Se solicita catering, coffee break o banquetería, pero no se confirma el lugar. Revisar si el hotel puede ofrecer su salón junto con el servicio.", comidas
    elif (
        base.get("exclusiones_evidentes") or _evidencia_objeto_ajeno(campos)
    ) and not (genericas or comidas or rechazadas) and not (
        items and any(
            e.get("estado") != "objeto_ajeno"
            for e in base.get("evaluacion_items", [])
        )
    ):
        exclusiones = base.get("exclusiones_evidentes") or [_evidencia_objeto_ajeno(campos)]
        resultado, codigo, motivo, evidencias = "no_cumple", "objeto_ajeno", exclusiones[0]["motivo"], exclusiones
    elif hay_evento:
        codigo, motivo = "evento_sin_espacio_definido", "La actividad podría requerir espacio, pero no se identifica qué salón se contrata ni si puede ofrecerlo el hotel."
        if not evidencias:
            evidencias = next((
                [_evidencia_perfil(
                    fuente, texto, normal, mapa, actividad,
                    "evento_sin_espacio_definido",
                    "La actividad puede requerir un espacio; falta confirmar si se contrata un salón del hotel.",
                )]
                for fuente, texto in campos
                if not fuente.endswith(("categoria", "nombre_producto"))
                for normal, mapa in [_texto_con_mapa(texto)]
                for actividad in _EVENTO_SALONES.finditer(normal)
                if not _mencion_negada(normal, actividad.start())
            ), [])
    elif datos.get("items") and len(base.get("evaluacion_items", [])) == len(datos.get("items") or []) and all(
        e.get("estado") == "objeto_ajeno" for e in base.get("evaluacion_items", [])
    ) and not hay_evento:
        resultado, codigo = "no_cumple", "sin_salon_identificado"
        motivo = "Los ítems no identifican salones ni servicios de alimentación para eventos."
    elif datos.get("items"):
        codigo, motivo = "servicio_no_confirmado", "Los ítems disponibles no confirman un servicio del hotel. Revisar el alcance antes de descartarla."
    else:
        codigo, motivo = "alcance_indeterminado", "La ficha no entrega suficiente información para confirmar si podría requerir salones para eventos o servicios de alimentación; se conserva para revisión."
    return {
        "grupos": (["salones"] if libres else []) + (["alimentacion_asociada"] if comidas or comidas_directas else []),
        "directa": bool(libres or comidas_directas),
        "coincidencias": (libres + comidas_directas)[:100], "ambiguedades": evidencias[:30] if resultado == "sin_informacion" else [],
        "exclusiones_evidentes": ([{**e, "codigo": codigo, "motivo": motivo} for e in evidencias[:30]] if resultado == "no_cumple" else []),
        "evaluacion_items": [
            {**e, "estado": "servicio_hotel" if _unidad(e["fuente"]) in {_unidad(x["fuente"]) for x in comidas_directas} else "salon_eventos" if _unidad(e["fuente"]) in {_unidad(x["fuente"]) for x in libres} else "fuera_alcance_hotel" if resultado == "no_cumple" else "por_verificar_perfil_hotel" if e.get("estado") in {"servicio_hotelero", "potencial_hotelero"} else e.get("estado")}
            for e in base.get("evaluacion_items", [])
        ],
        "resultado_perfil": resultado, "motivo_perfil": motivo,
        "perfil": "servicios_hotel_eventos_y_alojamiento", "menciones_espacio_rechazadas": rechazadas[:30],
        "alimentacion_complementaria": bool(libres and comidas),
        "evidencias_limitadas": len(libres) > 100 or len(rechazadas) > 30,
        "truncada": bool(base.get("truncada") or len(libres) > 100),
        "ponderacion": senales_ponderadas,
    }


def detectar_pertinencia(datos: dict, *, campos=None) -> dict:
    datos, _ = _entrada_segura(datos)
    grupos, ambiguedades, _, _ = _patrones()
    coincidencias, dudas = [], []
    lectura_truncada = False
    campos = _campos(datos)[0] if campos is None else campos

    for fuente, texto in campos:
        # Las categorías amplias no describen el objeto contratado.
        if fuente.endswith("categoria"):
            continue

        normal, mapa = _texto_con_mapa(texto)
        dudas.extend(_posibles_errores_servicio(normal, fuente, texto, mapa))

        for grupo, patrones in grupos:
            for patron in patrones:
                for n, m in enumerate(patron.finditer(normal)):
                    if n > 100:
                        lectura_truncada = True
                        break

                    nivel = grupo["nivel"]

                    if nivel == "directa" and _mencion_negada(normal, m.start()):
                        continue

                    if _mencion_ajena(grupo["id"], m, normal):
                        continue

                    if _mencion_en_compra_de_bienes(normal, m.start()):
                        continue

                    if _mencion_de_item_ajeno(datos, fuente, m, normal):
                        continue

                    if re.fullmatch(
                        r"hotel(?:es)?|hoteleria",
                        m.group(),
                    ):
                        antes = re.split(
                            r"[.;\n]",
                            normal[: m.start()],
                        )[
                            -1
                        ][-120:]
                        despues = re.split(
                            r"[.;\n]",
                            normal[m.end() :],
                            maxsplit=1,
                        )[
                            0
                        ][:120]

                        contratacion = re.search(
                            r"\b(?:requiere|requieren|solicita|"
                            r"solicitan|contrata|contratar|"
                            r"contratacion|arriendo|alquiler|"
                            r"reservas?|servicios? de)\b",
                            antes,
                        )
                        destino = re.search(
                            r"\bpara\s+(?:\d+\s+)?"
                            r"(?:personas|participantes|delegaciones|"
                            r"funcionarios|alojar|hospedar)\b",
                            despues,
                        )

                        if not (contratacion or destino):
                            nivel = "contexto"

                    coincidencias.append(
                        {
                            "grupo": grupo["id"],
                            "nivel": nivel,
                            "fuente": fuente,
                            "termino": m.group(),
                            "inicio": mapa[m.start()][0],
                            "fin": mapa[m.end() - 1][1],
                            "evidencia": _fragmento(
                                texto,
                                m.start(),
                                m.end(),
                                mapa,
                            ),
                        }
                    )

        # Un nombre de producto genérico no identifica el objeto concreto.
        if not fuente.endswith(("categoria", "nombre_producto")):
            for regla, patron in ambiguedades:
                m = next(
                    (
                        m
                        for m in patron.finditer(normal)
                        if not _ambiguedad_administrativa(
                            regla["id"],
                            m,
                            normal,
                        )
                    ),
                    None,
                )

                if m is not None:
                    dudas.append(
                        {
                            "codigo": regla["id"],
                            "motivo": regla["motivo"],
                            "fuente": fuente,
                            "evidencia": _fragmento(
                                texto,
                                m.start(),
                                m.end(),
                                mapa,
                            ),
                        }
                    )

    for fuente, texto in campos:
        if re.search(
            r"\b(?:sin|no se requiere|no incluye)"
            r"\s+(?:servicio de )?"
            r"(?:alojamiento|hospedaje|salon|habitacion)",
            normalizar_texto(texto),
        ):
            dudas.append(
                {
                    "codigo": "servicio_negado",
                    "motivo": (
                        "La mención contiene una negación; " "revisar su alcance."
                    ),
                    "fuente": fuente,
                    "evidencia": texto[:500],
                }
            )

    directas = [
        x
        for x in coincidencias
        if x["nivel"] == "directa"
        and not x["fuente"].endswith(("categoria", "nombre_producto"))
    ]

    evaluaciones_items = _evaluar_objetos_por_item(datos, campos, directas)
    exclusiones = []
    # Una mención solo en el nombre genérico del producto no bloquea exclusiones.
    if not directas:
        if evaluaciones_items:
            if all(x["estado"] == "objeto_ajeno" for x in evaluaciones_items):
                exclusiones = [x["evidencia"] for x in evaluaciones_items]
        else:
            evidencia = _evidencia_objeto_ajeno(campos)
            if evidencia:
                exclusiones = [evidencia]

    # Un título genérico puede ser la única información disponible.
    resultado = {
        "grupos": sorted({x["grupo"] for x in coincidencias}),
        "directa": bool(directas),
        "coincidencias": coincidencias[:100],
        "ambiguedades": dudas[:30],
        "exclusiones_evidentes": exclusiones[:30],
        "evaluacion_items": evaluaciones_items,
        "evidencias_limitadas": (
            len(coincidencias) > 100 or len(dudas) > 30 or len(exclusiones) > 30
        ),
        # Limitar lo mostrado no significa haber dejado texto sin leer.
        "truncada": lectura_truncada or len(coincidencias) > 100,
    }
    if (cargar_catalogo().get("perfil_comercial") or {}).get("id") == "servicios_hotel_eventos_y_alojamiento":
        perfil = _evaluar_perfil_hotel(datos, campos, resultado)
        perfil["coincidencias_base"] = resultado["coincidencias"]
        perfil["ambiguedades_base"] = resultado["ambiguedades"]
        perfil["evaluacion_items_base"] = resultado["evaluacion_items"]
        return perfil
    return resultado


def detectar_cliente(datos):
    # Prioridad comercial; no excluye compradores nuevos.
    return identificar_clientes_importantes(datos)


def extraer_requisitos(campos):
    """Hallazgos con evidencia; no convierte cantidades de ítem en asistentes."""
    patrones = {
        "cantidad": (
            r"\b\d{1,5}(?:[.,]\d{3})?\s+"
            r"(?:personas|asistentes|participantes|"
            r"habitaciones|noches|salones|salas)\b"
        ),
        "montaje": (
            r"\b(?:tipo|montaje(?:\s+tipo)?|"
            r"disposicion(?:\s+tipo)?)\s+"
            r"(?:auditorio|escuela|imperial|coctel|banquete|u)\b"
        ),
        "fecha_servicio": (
            r"\b(?:evento|jornada|seminario|alojamiento|"
            r"estadia|servicio)\b[^.;\n]{0,100}?\b"
            r"(?:\d{1,2}[/\-]\d{1,2}[/\-]\d{4}|"
            r"\d{1,2}\s+de\s+(?:enero|febrero|marzo|abril|"
            r"mayo|junio|julio|agosto|septiembre|octubre|"
            r"noviembre|diciembre)(?:\s+de\s+\d{4})?)\b"
        ),
        "oferta_parcial": (
            r"\b(?:ofertas? parciales?|"
            r"adjudicacion por (?:linea|item)|"
            r"ofertar por (?:linea|item))\b"
        ),
        "requisito_proveedor": (
            r"\b(?:obligatori[oa]|debera|debe)\b"
            r"[^.;\n]{0,100}?\b"
            r"(?:otec|otic|relator|certificacion|productora)\b"
        ),
    }

    hallazgos = []

    for fuente, texto in campos:
        normal, mapa = _texto_con_mapa(texto)

        for tipo, patron in patrones.items():
            for m in re.finditer(patron, normal):
                inicio = mapa[m.start()][0]
                fin = mapa[m.end() - 1][1]

                hallazgos.append(
                    {
                        "tipo": tipo,
                        "fuente": fuente,
                        "inicio": inicio,
                        "fin": fin,
                        "texto": texto[inicio:fin],
                        "contexto": _fragmento(
                            texto,
                            m.start(),
                            m.end(),
                            mapa,
                        ),
                        "estado": "por_revisar",
                    }
                )

                if len(hallazgos) == 100:
                    return {
                        "hallazgos": hallazgos,
                        "truncada": True,
                    }

    return {"hallazgos": hallazgos, "truncada": False}


_SERVICIO = re.compile(
    r"\b(?:servicios?|alojamiento|hospedaje|hotel(?:es)?|hoteleria|habitacion(?:es)?|estadia|salon(?:es)?|"
    r"salas?|recintos?|espacios?|auditorios?|taller(?:es)?|jornadas?|"
    r"eventos?|reunion(?:es)?|seminarios?|encuentros?|"
    r"ceremonias?|realizara|desarrollara|"
    r"cof+e+e?\s*[- ]?breaks?|coctel(?:es)?|cocktails?|"
    r"banqueteria|catering|alimentacion|desayunos?|"
    r"almuerzos?|cenas?|colaciones?|refrigerios?)\b"
)

_ROTULO_LUGAR = re.compile(
    r"\b(?:ubicacion|lugar|direccion|comuna|region)"
    r"\s+(?:(?:de|del)\s+)?(?:(?:la|el)\s+)?"
    r"(?:prestacion|ejecucion|realizacion|servicio|evento)"
    r"\s*:\s*$"
)

_RELACION = re.compile(
    r"(?:\b(?:en|para|derivad[oa]s? a)"
    r"\s+(?:(?:la|el)\s+)?"
    r"(?:(?:ciudad|comuna|region|centro|casco historico)"
    r"\s+(?:de|del)\s+)?"
    r"|\b(?:ciudad|comuna|region|centro)\s+de\s+"
    r"|\bprovincias?\s+de\s+(?:(?:la|el)\s+)?)$"
)

_LUGAR_EN_TITULO = re.compile(
    r"\b(?:arriendo|alquiler) de (?:un |una )?"
    r"(?:salon(?:es)?|salas?)\s*[-:–]?\s*$"
)

_NEGACION = re.compile(
    r"\b(?:fuera de|excepto|excluy\w*|distint[oa]s? de|"
    r"no\s+(?:(?:se\s+)?\w+\s+){0,4}en)\b"
)

_ADMINISTRATIVO = re.compile(
    r"\b(?:domicilio|direccion|oficinas?|sede|comprador|"
    r"unidad de compra|factur(?:as?|acion)|"
    r"entrega de (?:ofertas?|antecedentes|documentos))\b"
)

_DESTINO_EXTRANJERO = re.compile(
    r"^\s*,?\s*(?:argentina|peru|brasil|bolivia|colombia|"
    r"ecuador|mexico|espana|estados unidos|uruguay|"
    r"paraguay|venezuela)\b"
)


def detectar_ubicacion(
    datos: dict,
    *,
    campos=None,
    pertinencia=None,
) -> dict:
    datos, _ = _entrada_segura(datos)
    _, _, lugares, patron = _patrones()
    evidencias, ambiguas = [], []

    comunas_ambiguas = {
        normalizar_texto(x) for x in cargar_catalogo()["comunas_ambiguas"]
    }

    campos = _campos(datos)[0] if campos is None else campos

    for fuente, texto in campos:
        if fuente.endswith(("categoria", "nombre_producto")):
            continue

        normal, mapa = _texto_con_mapa(texto)

        for m in patron.finditer(normal):
            antes = normal[max(0, m.start() - 160) : m.start()]
            antes = re.split(r"[;\n.!?]", antes)[-1]

            despues = re.split(
                r"[;\n.!?]",
                normal[m.end() :],
                maxsplit=1,
            )[
                0
            ][:160]

            rotulo = bool(_ROTULO_LUGAR.search(antes))
            relacion = _RELACION.search(antes)

            continuacion = bool(
                re.search(r"(?:\b(?:y|o)|[,/–-])\s+$", antes)
                and evidencias
                and evidencias[-1]["fuente"] == fuente
                and not re.search(
                    r"[;\n.!?]",
                    texto[evidencias[-1]["fin"] : mapa[m.start()][0]],
                )
            )

            if not (
                rotulo
                or _LUGAR_EN_TITULO.search(antes)
                or (relacion and (_SERVICIO.search(antes) or _SERVICIO.search(despues)))
                or continuacion
            ):
                continue

            tipo, comuna, region = lugares[m.group()]

            registro = {
                "cobertura": tipo,
                "comuna": comuna,
                "region": region,
                "fuente": fuente,
                "evidencia": _fragmento(
                    texto,
                    m.start(),
                    m.end(),
                    mapa,
                ),
                "inicio": mapa[m.start()][0],
                "fin": mapa[m.end() - 1][1],
                "contexto_local": antes + m.group() + despues,
                "lugar_explicito": rotulo,
            }

            extranjero = m.group() == "santiago" and re.match(
                r"\s+(?:de compostela|del estero|de cuba)",
                normal[m.end() :],
            )

            extranjero = extranjero or (
                m.group() == "san miguel"
                and re.match(
                    r"\s+de tucuman\b",
                    normal[m.end() :],
                )
            )

            extranjero = extranjero or _DESTINO_EXTRANJERO.match(normal[m.end() :])

            dudosa = (
                _NEGACION.search(antes)
                or (_ADMINISTRATIVO.search(antes) and not rotulo)
                or extranjero
                or (
                    m.group() in comunas_ambiguas
                    and not re.search(
                        r"metropolitana|melipilla|\brm\b",
                        normal,
                    )
                )
            )

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

    # Una dirección de entrega o visita puede ser administrativa.
    pistas = [
        {"fuente": campo, "texto": datos[campo][:500]}
        for campo in ("direccion_entrega", "direccion_visita")
        if (isinstance(datos.get(campo), str) and datos[campo].strip())
    ]

    if pertinencia is None:
        pertinencia = detectar_pertinencia(
            datos,
            campos=campos,
        )

    vinculo = _vincular_servicio(
        pertinencia=pertinencia,
        evidencias=evidencias,
    )

    # No combina el servicio de una línea con la ciudad de otra.
    if (
        estado in {"rm", "fuera_rm"}
        and not vinculo["completo"]
        and vinculo["unidades_hoteleras"]
    ):
        estado = "ambigua"

    # Una línea hotelera adicional sin lugar no queda descartada solo porque
    # otra línea del proceso indique una ciudad fuera de la RM.
    if estado == "fuera_rm":
        localizadas = set(vinculo["unidades_localizadas"])
        for indice, item in enumerate(datos.get("items") or []):
            unidad = f"items[{indice}]"
            if unidad in localizadas:
                continue
            texto_item = " ".join(
                str(item.get(campo) or "")
                for campo in ("nombre_producto", "descripcion")
            )
            normal_item = normalizar_texto(texto_item)
            if _COMIDA_SALONES.search(normal_item) or _ESPACIO_SALONES.search(normal_item):
                estado = "ambigua"
                break

    if estado in {"rm", "fuera_rm"}:
        if any(
            re.search(
                r"\b(?:todo el pais|a nivel nacional|"
                r"cobertura nacional|diversas regiones|"
                r"distintas regiones|varias ciudades)\b",
                normalizar_texto(t),
            )
            for _, t in campos
        ):
            estado = "ambigua"

    return {
        "estado": estado,
        "alcance": "santiago_y_region_metropolitana",
        "vinculo_servicio": vinculo,
        "evidencias": evidencias[:50],
        "menciones_ambiguas": ambiguas[:30],
        "pistas": pistas,
        "truncada": (len(evidencias) > 50 or len(ambiguas) > 30),
    }


def _unidad(fuente):
    if fuente.startswith("items["):
        return fuente.split(".")[0]

    if fuente.startswith("documentos["):
        return fuente

    return "cabecera"


def _vincular_servicio(pertinencia, evidencias):
    directas = [
        x
        for x in pertinencia["coincidencias"]
        if (
            x.get("nivel") == "directa"
        )
        and not x.get("fuente", "").endswith(("categoria", "nombre_producto"))
    ]

    unidades = {_unidad(x["fuente"]) for x in directas}

    # El título general no representa otra línea adicional.
    requeridas = {u for u in unidades if u.startswith("items[")} or unidades

    localizadas = set()

    for e in evidencias:
        unidad = _unidad(e["fuente"])

        if unidad not in unidades:
            continue

        local = detectar_pertinencia({"descripcion": e["contexto_local"]})
        actividad = re.search(
            r"\b(?:eventos?|jornadas?|seminarios?|"
            r"reunion(?:es)?|conferencias?|encuentros?)\b",
            e["contexto_local"],
        )
        otro_servicio = re.search(
            r"\b(?:alojamiento|hospedaje|habitaciones|coffee\s*break|"
            r"catering|alimentacion|traslados?)\b",
            e["contexto_local"],
        )

        servicio_salon_separado_de_ubicacion = (
            "salones" in (pertinencia.get("grupos") or [])
            and bool(otro_servicio)
            and not re.search(
                r"\b(?:salon(?:es)?|sala(?:s)?|auditorio(?:s)?|espacio(?:s)?)\b",
                e["contexto_local"],
            )
            and not bool(actividad)
        )
        if (
            (local["directa"] and not servicio_salon_separado_de_ubicacion)
            or e["lugar_explicito"]
            or (actividad and not otro_servicio)
        ):
            localizadas.add(unidad)

    return {
        "completo": (bool(requeridas) and requeridas <= localizadas),
        "unidades_hoteleras": sorted(requeridas),
        "unidades_localizadas": sorted(localizadas),
        "motivo": (
            "La ubicación debe corresponder al servicio hotelero "
            "de la misma línea o contexto."
        ),
    }


def _fecha(valor):
    if isinstance(valor, str):
        valor = datetime.fromisoformat(valor.replace("Z", "+00:00"))

    if not isinstance(valor, datetime):
        return None

    return (
        valor.replace(tzinfo=CHILE) if valor.tzinfo is None else valor.astimezone(CHILE)
    )


def evaluar_vigencia(datos: dict, ahora: datetime) -> dict:
    estado = normalizar_texto(str(datos.get("estado") or "")).strip()
    codigo = datos.get("codigo_estado")

    cerrados = {
        "cerrada",
        "desierta",
        "adjudicada",
        "revocada",
        "suspendida",
        "cancelada",
    }

    abierta = estado in {"publicada", "activa"} or codigo == 5
    cerrada = estado in cerrados or codigo in {6, 7, 8, 18, 19}

    try:
        cierre = _fecha(datos.get("fecha_cierre"))
    except (ValueError, TypeError):
        return {
            "resultado": "sin_informacion",
            "motivo": ("La fecha de cierre guardada no es interpretable."),
        }

    if abierta and cerrada:
        return {
            "resultado": "sin_informacion",
            "motivo": (
                "El estado y su código se contradicen; " "actualizar la fuente."
            ),
        }

    if cierre is not None and cierre <= ahora:
        return {
            "resultado": "no_cumple",
            "motivo": "La fecha de cierre guardada ya pasó.",
            "fecha_cierre": cierre.isoformat(),
        }

    if cerrada:
        return {
            "resultado": "no_cumple",
            "motivo": ("El estado guardado no permite presentar ofertas."),
        }

    if not abierta or cierre is None:
        return {
            "resultado": "sin_informacion",
            "motivo": (
                "Falta estado abierto o fecha de cierre " "para comprobar vigencia."
            ),
        }

    return {
        "resultado": "cumple",
        "motivo": ("Publicada y con cierre futuro " "según los datos guardados."),
        "fecha_cierre": cierre.isoformat(),
    }


def clasificar_pilares(criterios, *, candidato_salon_rm=False):
    """Solo estos tres resultados deciden; un rechazo explícito prevalece a una duda."""
    for codigo in PILARES:
        if criterios[codigo]["resultado"] == "no_cumple":
            return (
                "descartada",
                criterios[codigo]["motivo"],
                codigo,
            )

    for codigo in PILARES:
        if criterios[codigo]["resultado"] != "cumple":
            if (
                candidato_salon_rm
                and codigo == "ubicacion"
                and criterios[codigo]["resultado"] == "sin_informacion"
                and criterios["vigencia"]["resultado"] == "cumple"
                and criterios["pertinencia"]["resultado"] == "cumple"
            ):
                return (
                    "preseleccionada",
                    "Candidato para el hotel: se solicita directamente un salón y el comprador está en la RM. La ficha no confirma el lugar de ejecución; revisar las bases antes de cotizar.",
                    None,
                )
            return (
                "revision_manual",
                criterios[codigo]["motivo"],
                codigo,
            )

    return (
        "preseleccionada",
        "Cumple los tres pilares: está vigente, el evento se ubica en la RM "
        "y el salón solicitado es compatible con la oferta del hotel.",
        None,
    )


def evaluar_preseleccion(
    datos: dict,
    *,
    ahora: datetime | None = None,
) -> dict:
    # Licitaciones y Compras Ágiles comparten los tres pilares.
    datos, problemas = _entrada_segura(datos)
    ahora = ahora or datetime.now(CHILE)

    if ahora.tzinfo is None:
        raise ValueError("La hora de evaluación debe indicar su zona horaria.")

    ahora = ahora.astimezone(CHILE)

    # Las bases complementan la evidencia de la ficha y sus ítems.
    utilizables = {
        **datos,
        "documentos": [
            d
            for n, d in enumerate(datos.get("documentos", []))
            if not any(p.startswith(f"documentos[{n}].") for p in problemas)
        ],
    }

    campos, parcial = _campos(utilizables)

    parcial |= any(
        not p.startswith(("documentos", "incidencia_documental")) for p in problemas
    )

    vigencia = evaluar_vigencia(datos, ahora)
    pertinencia = detectar_pertinencia(
        datos,
        campos=campos,
    )
    ubicacion = detectar_ubicacion(
        datos,
        campos=campos,
        pertinencia=pertinencia,
    )

    parcial |= pertinencia["truncada"] or ubicacion["truncada"]

    documentacion = evaluar_documentacion(datos)

    territorial = (
        "cumple"
        if ubicacion["estado"] == "rm" and not parcial
        else (
            "no_cumple"
            if ubicacion["estado"] == "fuera_rm" and not parcial
            else "sin_informacion"
        )
    )

    rubro = (
        "sin_informacion"
        if parcial
        else pertinencia["resultado_perfil"]
        if pertinencia.get("perfil") == "servicios_hotel_eventos_y_alojamiento"
        else (
            "no_cumple"
            if pertinencia["exclusiones_evidentes"]
            else (
                "cumple"
                if pertinencia["directa"] and not pertinencia["ambiguedades"]
                else "sin_informacion"
            )
        )
    )

    motivo_ubicacion = (
        "El lugar de prestación del servicio está identificado "
        "en la Región Metropolitana."
        if territorial == "cumple"
        else (
            "El servicio identificado se solicita " "fuera de la Región Metropolitana."
            if territorial == "no_cumple"
            else (
                "La lectura de la fuente es incompleta; "
                "falta confirmar el lugar de prestación del servicio."
                if parcial
                else (
                    "El lugar del servicio es mixto o ambiguo; "
                    "falta confirmar su cobertura en la RM."
                    if ubicacion["estado"] in {"mixta", "ambigua"}
                    else (
                        "No se identifica dónde debe prestarse "
                        "el servicio; la dirección del comprador "
                        "no confirma el lugar."
                    )
                )
            )
        )
    )

    motivo_servicio = (
        "La lectura de la fuente es incompleta; falta confirmar el servicio contratado."
        if parcial
        else pertinencia["motivo_perfil"]
        if pertinencia.get("perfil") == "servicios_hotel_eventos_y_alojamiento"
        else (
            pertinencia["exclusiones_evidentes"][0]["motivo"]
            if rubro == "no_cumple"
            else (
                "Se solicita un salón para eventos o servicios de alimentación asociados."
                if rubro == "cumple"
                else (
                    "Falta aclarar si se contrata un servicio del hotel: "
                    + pertinencia["ambiguedades"][0]["motivo"]
                    if pertinencia["ambiguedades"]
                    else "La ficha no identifica una solicitud concreta de salones para eventos o alimentación asociada."
                )
            )
        )
    )

    criterios = {
        "vigencia": vigencia,
        "ubicacion": {
            "resultado": territorial,
            "motivo": motivo_ubicacion,
            **ubicacion,
        },
        "pertinencia": {
            "resultado": rubro,
            "motivo": motivo_servicio,
            **pertinencia,
        },
    }

    region_comprador = normalizar_texto(str(datos.get("region_comprador") or ""))
    candidato_salon_rm = (
        not parcial
        and pertinencia.get("perfil") == "servicios_hotel_eventos_y_alojamiento"
        and pertinencia.get("resultado_perfil") == "cumple"
        and any(x.get("grupo") == "salones" for x in pertinencia.get("coincidencias", []))
        and pertinencia.get("ponderacion", {}).get("actividad_generica_en_ficha", 0)
        and ubicacion["estado"] == "sin_determinar"
        and bool(re.search(r"\bmetropolitana\b", region_comprador))
    )
    criterios["ubicacion"]["comprador_en_rm"] = bool(
        re.search(r"\bmetropolitana\b", region_comprador)
    )
    criterios["ubicacion"]["sede_confirmada"] = territorial == "cumple"
    clasificacion, motivo, pilar_decisivo = clasificar_pilares(
        criterios, candidato_salon_rm=candidato_salon_rm
    )

    # Un documento incompleto solo debe frenar el descarte cuando la pertinencia
    # todavía sea dudosa. Una exclusión explícita del servicio prevalece para no
    # llenar revisión con compras claramente ajenas al hotel.
    documento_no_verificado = documentacion["requiere_revision"]
    servicio_ajeno_confirmado = (
        criterios["pertinencia"]["resultado"] == "no_cumple"
        and bool(criterios["pertinencia"].get("exclusiones_evidentes"))
    )
    bloqueo_por_pilar = (
        criterios["vigencia"]["resultado"] != "no_cumple"
        and criterios["ubicacion"]["resultado"] != "no_cumple"
    )
    bloquear_descarte = (
        documento_no_verificado and not servicio_ajeno_confirmado and bloqueo_por_pilar
    )
    if bloquear_descarte and clasificacion == "descartada":
        clasificacion = "revision_manual"
        motivo = "No se puede confirmar el descarte: hay documentos de la licitación sin lectura completa. Revisar las bases manualmente."
        pilar_decisivo = "documentacion"

    documentacion["bloquea_preseleccion"] = False
    documentacion["bloquea_descarte"] = bloquear_descarte

    entrada = {
        "campos": campos,
        "estado": datos.get("estado"),
        "codigo_estado": datos.get("codigo_estado"),
        "fecha_cierre": str(datos.get("fecha_cierre")),
        "raw_id": datos.get("raw_id"),
        "documentacion": documentacion,
        "calidad_datos": problemas,
        "version_motor": VERSION_MOTOR,
        "catalogo_version": cargar_catalogo()["version"],
    }

    return {
        "version_motor": VERSION_MOTOR,
        "codigo_externo": datos.get("codigo_externo"),
        "catalogo_version": cargar_catalogo()["version"],
        "clasificacion": clasificacion,
        "motivo": motivo,
        "pilar_decisivo": pilar_decisivo,
        "evaluado_en": ahora.isoformat(),
        "fuente_raw_id": datos.get("raw_id"),
        "entrada_parcial": parcial,
        "calidad_datos": {
            "resultado": ("sin_informacion" if parcial else "cumple"),
            "incidencias": problemas[:30],
            "lectura_acotada": parcial,
        },
        "cobertura": ("parcial" if datos.get("documentos") else "sin_bases"),
        "requisitos_detectados": extraer_requisitos(campos),
        "cliente_estrategico": detectar_cliente(datos),
        "huella_entrada": hashlib.sha256(
            json.dumps(
                entrada,
                sort_keys=True,
                ensure_ascii=False,
            ).encode()
        ).hexdigest(),
        "orden_pilares": list(PILARES),
        "pilar_decisivo": pilar_decisivo,
        "criterios": criterios,
        "documentacion": documentacion,
        "modo": "preseleccion",
    }
