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
VERSION_MOTOR = "reglas-salones-23"
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

    if grupo == "alojamiento":
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

            if not (contratacion or personas):
                return True

        return bool(
            re.match(
                r"\s+(?:(?:de|para)\s+)?"
                r"(?:infraestructura virtualizada|servidores?|"
                r"maquinas virtuales|sitios? web|datos|aplicaciones?)\b",
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
    r"|\bservicios?\s+(?:hoteleros?\b|de\s+(?:alojamiento|hospedaje|banqueteria|catering|alimentacion|cof+e+e?\s*[- ]?breaks?)\b)"
    r"|\b(?:se\s+)?(?:requiere|requieren|solicita|solicitan|contrata|contratar)\s+"
    r"(?:el\s+)?(?:alojamiento|hospedaje|salon(?:es)?|coffee\s*break)\b"
    r"|\b(?:alojamiento|hospedaje|coffee\s*break|almuerzos?|desayunos?|cenas?|colaciones?)"
    r"\s+para\s+(?:(?:los|las)\s+)?(?:\d+\s+)?(?:personas|participantes|asistentes|delegaciones|pacientes|funcionarios)\b"
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
    if re.search(r"\b(?:alojamiento|hospedaje|estadia)\s+(?:en|para)\s+", normal):
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
    r"(?:operaciones|maquinas|clases|cuna|espera|era|tratamiento|"
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
_ALOJAMIENTO_SALONES = re.compile(
    r"\b(?:alojamientos?|hospedajes?|estadias?|habitacion(?:es)?|"
    r"casa\s+de\s+acogida|hoteleria|hoteles?)\b"
)
_COMIDA_SALONES = re.compile(
    r"\b(?:cof+e+e?\s*[- ]?breaks?|banqueteria|catering|alimentacion|"
    r"almuerzos?|desayunos?|cenas?|coctel(?:es)?|cocktails?)\b"
)
_DOCENCIA_OBLIGATORIA = re.compile(
    r"\b(?:proveedor|oferente|adjudicatario)\b[^.;\n]{0,80}"
    r"\b(?:debe|debera|obligatoriamente)\b[^.;\n]{0,80}"
    r"\b(?:impartir|dictar|certificar|ser\s+otec|ser\s+otic)\b"
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


def _evaluar_perfil_salones(datos, campos, base):
    """Evalúa el alcance comercial del hotel sin crear otro pilar."""
    hotel = normalizar_texto(
        cargar_catalogo().get("hotel", {}).get("nombre") or "Hotel Plaza San Francisco"
    )
    validas, rechazadas, genericas, fijas = [], [], [], []
    alojamientos, comidas, clinicas, obligaciones = [], [], [], []
    hay_evento = False
    estados = {e.get("fuente"): e.get("estado") for e in base.get("evaluacion_items", [])}

    for fuente, texto in campos:
        if fuente.endswith("categoria"):
            continue
        normal, mapa = _texto_con_mapa(texto)
        producto_generico = fuente.endswith("nombre_producto")
        if not producto_generico:
            for actividad in _EVENTO_SALONES.finditer(normal):
                clausula_evento = _clausula_local(normal, actividad.start())
                es_taller_mecanico = actividad.group().startswith("taller") and bool(
                    re.search(
                        r"\b(?:maquinarias?|fiscal|mantencion|mantenimiento|"
                        r"reparacion|mecanica|vehiculos?)\b",
                        clausula_evento,
                    )
                )
                if not es_taller_mecanico:
                    hay_evento = True
            for patron, destino, codigo in (
                (_ALOJAMIENTO_SALONES, alojamientos, "alojamiento_sin_salon"),
                (_COMIDA_SALONES, comidas, "alimentacion_sin_salon"),
                (re.compile(r"\b(?:procedimientos?\s+endovasculares?|prestaciones\s+medicas|servicios?\s+quirurgicos|hospitalizar|hospitalizacion)\b"), clinicas, "objeto_clinico"),
                (_DOCENCIA_OBLIGATORIA, obligaciones, "docencia_integral"),
            ):
                m = patron.search(normal)
                if (
                    m
                    and not _mencion_negada(normal, m.start())
                    and not _mencion_de_item_ajeno(datos, fuente, m, normal)
                ):
                    destino.append(_evidencia_perfil(fuente, texto, normal, mapa, m, codigo, "Objeto identificado en el contexto de la solicitud."))
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
            servicio_asociado = bool(_COMIDA_SALONES.search(clausula))
            if (
                _SALA_EVENTO.search(clausula)
                or (arriendo and (evento or es_salon))
                or (es_salon and (evento or servicio_asociado))
            ):
                if estados.get(_unidad(fuente)) == "objeto_ajeno" and not (arriendo or evento):
                    genericas.append(registro)
                    continue
                registro.update(grupo="salones", nivel="directa", termino=m.group())
                validas.append(registro)
            else:
                genericas.append(registro)

    genericas_concretas = [e for e in genericas if not e["fuente"].endswith("nombre_producto")]
    if not alojamientos and not validas:
        for n, item in enumerate(datos.get("items") or []):
            codigo = _codigo_producto(item)
            if codigo in {"30222507", "90111501", "90111801"}:
                alojamientos.append({
                    "codigo": "alojamiento_sin_salon", "fuente": f"items[{n}].codigo_producto",
                    "evidencia": f"{codigo}: {item.get('nombre_producto') or 'Categoría de alojamiento'}",
                    "motivo": "La categoría indica alojamiento y no se identifica contratación de salón.",
                })
    unidades_fijas = {_unidad(e["fuente"]) for e in fijas}
    libres = [e for e in validas if _unidad(e["fuente"]) not in unidades_fijas]
    resultado, codigo = "sin_informacion", "alcance_indeterminado"
    motivo = "Falta confirmar si se contrata un salón para eventos que pueda ofrecer el hotel."
    evidencias = []
    if validas:
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
    elif fijas and (comidas or rechazadas):
        resultado, codigo, motivo, evidencias = "no_cumple", "servicio_en_tercero", "Se solicita prestar el servicio en una sede de tercero, sin contratación del salón del hotel.", fijas
    elif rechazadas and not genericas_concretas:
        resultado, codigo, motivo, evidencias = "no_cumple", "espacio_no_eventos", rechazadas[0]["motivo"], rechazadas
    elif clinicas and not genericas_concretas and not hay_evento:
        resultado, codigo, motivo, evidencias = "no_cumple", "objeto_clinico", "El objeto es una prestación o infraestructura clínica, no un salón para eventos.", clinicas
    elif genericas and (
        hay_evento
        or any(
            _SALON_CONTRATADO.search(normalizar_texto(e.get("evidencia", "")))
            for e in genericas
        )
    ):
        codigo, motivo, evidencias = "espacio_por_confirmar", "Se menciona un espacio o categoría, pero falta confirmar el arriendo o uso de un salón para un evento en el hotel.", genericas
    elif alojamientos:
        resultado, codigo, motivo, evidencias = "no_cumple", "alojamiento_sin_salon", "Se solicita alojamiento o acogida sin contratación de salón para eventos; está fuera del alcance comercial definido.", alojamientos
    elif comidas:
        codigo, motivo, evidencias = "alimentacion_salon_por_confirmar", "Se solicita catering, coffee break o banquetería, pero no se confirma el lugar. Revisar si el hotel puede ofrecer su salón junto con el servicio.", comidas
    elif base.get("evaluacion_items") and all(
        e.get("estado") == "objeto_ajeno" for e in base["evaluacion_items"]
    ):
        resultado, codigo, evidencias = "no_cumple", "objeto_ajeno", [
            e["evidencia"] for e in base["evaluacion_items"] if e.get("evidencia")
        ]
        motivo = evidencias[0]["motivo"] if evidencias else "Los ítems no solicitan un salón para eventos ni servicios asociados."
    elif base.get("exclusiones_evidentes") or _evidencia_objeto_ajeno(campos):
        exclusiones = base.get("exclusiones_evidentes") or [_evidencia_objeto_ajeno(campos)]
        resultado, codigo, motivo, evidencias = "no_cumple", "objeto_ajeno", exclusiones[0]["motivo"], exclusiones
    elif hay_evento:
        codigo, motivo = "evento_sin_espacio_definido", "La actividad podría requerir espacio, pero no se identifica qué salón se contrata ni si puede ofrecerlo el hotel."
    elif datos.get("items"):
        resultado, codigo = "no_cumple", "sin_salon_identificado"
        motivo = "Los ítems no identifican contratación de un salón ni servicios asociados a un evento del hotel."
    else:
        codigo, motivo = "alcance_indeterminado", "La ficha no entrega suficiente información para confirmar si podría requerir un salón para eventos; se conserva para revisión."
    return {
        "grupos": ["salones"] if libres else [], "directa": bool(libres),
        "coincidencias": libres[:100], "ambiguedades": evidencias[:30] if resultado == "sin_informacion" else [],
        "exclusiones_evidentes": ([{**e, "codigo": codigo, "motivo": motivo} for e in evidencias[:30]] if resultado == "no_cumple" else []),
        "evaluacion_items": [
            {**e, "estado": "salon_eventos" if _unidad(e["fuente"]) in {_unidad(x["fuente"]) for x in libres} else "fuera_alcance_salones" if resultado == "no_cumple" else "por_verificar_perfil_salones" if e.get("estado") in {"servicio_hotelero", "potencial_hotelero"} else e.get("estado")}
            for e in base.get("evaluacion_items", [])
        ],
        "resultado_perfil": resultado, "motivo_perfil": motivo,
        "perfil": "salones_eventos_en_hotel", "menciones_espacio_rechazadas": rechazadas[:30],
        "alimentacion_complementaria": bool(libres and comidas),
        "alojamiento_no_decisivo": bool(alojamientos),
        "evidencias_limitadas": len(libres) > 100 or len(rechazadas) > 30,
        "truncada": len(libres) > 100,
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
    if (cargar_catalogo().get("perfil_comercial") or {}).get("id") == "salones_eventos_en_hotel":
        perfil = _evaluar_perfil_salones(datos, campos, resultado)
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
    r"\b(?:servicios?|alojamiento|hospedaje|hotel(?:es)?|"
    r"hoteleria|habitacion(?:es)?|estadia|salon(?:es)?|"
    r"salas?|recintos?|espacios?|auditorios?|jornadas?|"
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
    r"\b(?:(?:servicios? de )?"
    r"(?:alojamiento|hospedaje|hoteleria)|"
    r"(?:arriendo|alquiler) de (?:un |una )?"
    r"(?:salon(?:es)?|salas?))\s*[-:–]?\s*$"
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
        if x["nivel"] == "directa"
        and not x["fuente"].endswith(("categoria", "nombre_producto"))
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

        if (
            local["directa"]
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
        if pertinencia.get("perfil") == "salones_eventos_en_hotel"
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
        if pertinencia.get("perfil") == "salones_eventos_en_hotel"
        else (
            pertinencia["exclusiones_evidentes"][0]["motivo"]
            if rubro == "no_cumple"
            else (
                "Se solicita alojamiento, salones, alimentación o una combinación de estos servicios."
                if rubro == "cumple"
                else (
                    "Falta aclarar si se contrata un servicio del hotel: "
                    + pertinencia["ambiguedades"][0]["motivo"]
                    if pertinencia["ambiguedades"]
                    else "La ficha no identifica una solicitud concreta de alojamiento, salones o alimentación."
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
        and pertinencia.get("perfil") == "salones_eventos_en_hotel"
        and pertinencia.get("resultado_perfil") == "cumple"
        and bool(pertinencia.get("directa"))
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

    documentacion["bloquea_preseleccion"] = False

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
