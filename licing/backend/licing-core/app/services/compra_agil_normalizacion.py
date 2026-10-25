"""Normalización del detalle y del listado de la API Compra Ágil v2."""
import re
from copy import deepcopy
from datetime import datetime
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

from .normalizacion import limpiar_texto

VERSION_NORMALIZACION_COMPRA_AGIL = "1"
CHILE = ZoneInfo("America/Santiago")
PATRON_CODIGO = re.compile(r"\d+-\d+-COT\d+", re.IGNORECASE)
# id_estado de la API: 2 publicada, 3 cerrada, 4 proveedor seleccionado, 5 desierta, 6 cancelada.
ID_ESTADO_PUBLICADA = 2
IDS_NO_DISPONIBLES = {3, 4, 5, 6}
CONDICIONES_FUENTE = (
    "convocatoria", "entrega", "presupuesto", "orden_compra", "id_orden_compra",
    "resumen", "motivos", "flags",
)


def codigo_valido(valor) -> str | None:
    codigo = limpiar_texto(valor) if isinstance(valor, str) else None
    return codigo.upper() if codigo and PATRON_CODIGO.fullmatch(codigo) else None


def convertir_fecha_compra_agil(valor):
    """Fecha local de Chile sin zona, como el resto de Core.

    La API publica hora de Chile en todos sus campos, aunque algunos terminen en Z:
    el listado entrega «2026-10-26T08:00:00Z» como cierre del primer llamado y el
    detalle «2026-10-26 08:00» para el mismo instante. Un offset explícito sí se respeta.
    """
    if valor is None:
        return None
    if not isinstance(valor, str):
        raise ValueError("Las fechas de Compra Ágil deben ser texto ISO-8601.")
    texto = valor.strip()
    if not texto:
        return None
    if texto[-1] in "Zz":
        texto = texto[:-1]
    try:
        fecha = datetime.fromisoformat(texto)
    except ValueError:
        raise ValueError(f"Fecha de Compra Ágil inválida: {valor[:40]!r}.") from None
    if fecha.tzinfo is not None:
        fecha = fecha.astimezone(CHILE).replace(tzinfo=None)
    return fecha


def _objeto(datos, clave):
    valor = datos.get(clave)
    if valor is None:
        return {}
    if not isinstance(valor, dict):
        raise ValueError(f"{clave} debe ser un objeto JSON.")
    return valor


def _lista_de_objetos(datos, clave):
    valor = datos.get(clave)
    if valor is None:
        return []
    if not isinstance(valor, list) or any(not isinstance(v, dict) for v in valor):
        raise ValueError(f"{clave} debe ser una lista de objetos.")
    return valor


def _entero(valor, campo):
    if valor is None or valor == "":
        return None
    if isinstance(valor, bool):
        raise ValueError(f"{campo} debe ser un entero.")
    if isinstance(valor, int):
        return valor
    if isinstance(valor, str) and valor.strip().lstrip("-").isdigit():
        return int(valor.strip())
    raise ValueError(f"{campo} debe ser un entero.")


def _decimal(valor, campo):
    if valor is None or valor == "":
        return None
    if isinstance(valor, bool):
        raise ValueError(f"{campo} debe ser numérico.")
    try:
        numero = Decimal(str(valor))
    except InvalidOperation:
        raise ValueError(f"{campo} debe ser numérico.") from None
    if not numero.is_finite():
        raise ValueError(f"{campo} debe ser numérico.")
    return numero


def estado_de(estado: dict) -> str | None:
    codigo = limpiar_texto(estado.get("codigo"))
    if codigo:
        return codigo.lower()
    id_estado = _entero(estado.get("id_estado"), "estado.id_estado")
    if id_estado == ID_ESTADO_PUBLICADA:
        return "publicada"
    return None


def motivo_no_disponible(estado, id_estado, fecha_cierre, ahora=None):
    """Solo un estado o un cierre conocidos prueban que ya no se reciben cotizaciones."""
    if estado is not None and estado != "publicada":
        return "estado_no_disponible"
    if estado is None and id_estado in IDS_NO_DISPONIBLES:
        return "estado_no_disponible"
    referencia = (ahora or datetime.now(CHILE)).astimezone(CHILE).replace(tzinfo=None)
    if fecha_cierre is not None and fecha_cierre <= referencia:
        return "fecha_cierre"
    return None


def leer_resumen(item) -> dict:
    """Campos del listado que deciden si la compra se encola o se descarta."""
    if not isinstance(item, dict):
        raise ValueError("El resumen debe ser un objeto JSON.")
    codigo = codigo_valido(item.get("codigo"))
    if not codigo:
        raise ValueError("El resumen no contiene un código de Compra Ágil válido.")
    estado = _objeto(item, "estado")
    fechas = _objeto(item, "fechas")
    cambio = convertir_fecha_compra_agil(fechas.get("fecha_ultimo_cambio"))
    if cambio is None:
        raise ValueError("El resumen no informa fecha_ultimo_cambio.")
    return {
        "codigo_externo": codigo,
        "estado": estado_de(estado),
        "id_estado": _entero(estado.get("id_estado"), "estado.id_estado"),
        "cambio": cambio,
        "fecha_publicacion": convertir_fecha_compra_agil(fechas.get("fecha_publicacion")),
        "fecha_cierre": convertir_fecha_compra_agil(fechas.get("fecha_cierre")),
    }


def normalizar_compra_agil(detalle: dict) -> dict:
    if not isinstance(detalle, dict):
        raise ValueError("El detalle debe ser un objeto JSON.")
    codigo = codigo_valido(detalle.get("codigo"))
    if not codigo:
        raise ValueError("El detalle no contiene un código de Compra Ágil válido.")
    estado, convocatoria, fechas, entrega, presupuesto, institucion, resumen, orden_compra = (
        _objeto(detalle, clave) for clave in (
            "estado", "convocatoria", "fechas", "entrega", "presupuesto", "institucion",
            "resumen", "orden_compra",
        )
    )
    productos = _lista_de_objetos(detalle, "productos_solicitados")
    documentos = _lista_de_objetos(detalle, "documentos")
    # La respuesta real trae id_orden_compra en la raíz; la guía lo anida en orden_compra.
    id_orden_compra = detalle["id_orden_compra"] if "id_orden_compra" in detalle else orden_compra.get("id_orden_compra")

    items = [{
        "posicion_fuente": posicion,
        "codigo_producto": limpiar_texto(producto.get("codigo_producto")),
        "nombre_producto": limpiar_texto(producto.get("nombre")),
        "descripcion": limpiar_texto(producto.get("descripcion")),
        "cantidad": _decimal(producto.get("cantidad"), "productos_solicitados.cantidad"),
        "unidad_medida": limpiar_texto(producto.get("unidad_medida")),
    } for posicion, producto in enumerate(productos, 1)]

    return {
        "codigo_externo": codigo,
        "nombre": limpiar_texto(detalle.get("nombre")),
        "descripcion": limpiar_texto(detalle.get("descripcion")),
        "id_estado": _entero(estado.get("id_estado"), "estado.id_estado"),
        "estado": estado_de(estado),
        "estado_glosa": limpiar_texto(estado.get("glosa")),
        "estado_convocatoria": _entero(convocatoria.get("estado_convocatoria"), "convocatoria.estado_convocatoria"),
        "fecha_publicacion": convertir_fecha_compra_agil(fechas.get("fecha_publicacion")),
        "fecha_cierre": convertir_fecha_compra_agil(fechas.get("fecha_cierre")),
        "fecha_ultimo_cambio": convertir_fecha_compra_agil(fechas.get("fecha_ultimo_cambio")),
        "fecha_cancelacion": convertir_fecha_compra_agil(fechas.get("fecha_cancelacion")),
        "moneda": limpiar_texto(presupuesto.get("moneda")),
        "tipo_presupuesto": limpiar_texto(presupuesto.get("tipo_presupuesto")),
        "presupuesto_estimado": _decimal(presupuesto.get("presupuesto_estimado"), "presupuesto.presupuesto_estimado"),
        "monto_disponible": _decimal(presupuesto.get("monto_disponible"), "presupuesto.monto_disponible"),
        "monto_disponible_clp": _decimal(presupuesto.get("monto_disponible_clp"), "presupuesto.monto_disponible_clp"),
        "rut_organismo": limpiar_texto(institucion.get("rut")),
        "nombre_organismo": limpiar_texto(institucion.get("organismo_comprador")),
        "nombre_unidad": limpiar_texto(institucion.get("unidad_compra")),
        "codigo_region": _entero(institucion.get("region"), "institucion.region"),
        "region_comprador": limpiar_texto(institucion.get("nombre_region")),
        "direccion_entrega": limpiar_texto(entrega.get("direccion_entrega")),
        "plazo_entrega_dias": _entero(entrega.get("plazo_entrega_dias"), "entrega.plazo_entrega_dias"),
        "total_ofertas_recibidas": _entero(resumen.get("total_ofertas_recibidas"), "resumen.total_ofertas_recibidas"),
        "id_orden_compra": _entero(id_orden_compra, "id_orden_compra"),
        "documentos": [{"id": d.get("id"), "nombre": limpiar_texto(d.get("nombre"))} for d in documentos],
        # Texto original de las fechas, incluidos los cierres de cada llamado.
        "fechas_fuente": {**deepcopy(fechas), **{
            clave: deepcopy(convocatoria[clave])
            for clave in ("fecha_cierre_primer_llamado", "fecha_cierre_segundo_llamado") if clave in convocatoria
        }},
        "condiciones_fuente": {clave: deepcopy(detalle[clave]) for clave in CONDICIONES_FUENTE if clave in detalle},
        "normalizacion_version": VERSION_NORMALIZACION_COMPRA_AGIL,
        "items": items,
    }
