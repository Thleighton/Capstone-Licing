"""Convierte las respuestas de la API de Mercado Público a las filas de licing_datos."""
import unicodedata
from datetime import datetime, timezone
from urllib.parse import quote
from zoneinfo import ZoneInfo

CHILE = ZoneInfo("America/Santiago")

REGIONES = {
    "tarapaca": 1, "antofagasta": 2, "atacama": 3, "coquimbo": 4, "valparaiso": 5, "o'higgins": 6, "ohiggins": 6,
    "maule": 7, "biobio": 8, "araucania": 9, "los lagos": 10, "aysen": 11, "magallanes": 12,
    "metropolitana": 13, "los rios": 14, "arica": 15, "nuble": 16,
}


def norm(s) -> str:
    s = unicodedata.normalize("NFD", "" if s is None else str(s))
    return "".join(c for c in s if not unicodedata.combining(c)).lower()


def region_codigo(nombre) -> int | None:
    n = norm(nombre)
    return next((v for k, v in REGIONES.items() if k in n), None)


def chile_iso(s) -> str | None:
    """La API entrega fechas sin zona horaria (hora de Chile). Se convierten a UTC."""
    if not s:
        return None
    s = str(s).strip()
    try:
        d = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    if d.tzinfo is None:
        if d.year < 2000:
            return None
        d = d.replace(tzinfo=CHILE)
    return d.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def num(v):
    if v is None or v == "" or isinstance(v, bool):
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return int(f) if f.is_integer() else f


def _texto(v) -> str | None:
    s = "" if v is None else str(v)
    return s or None


def motivos_descarte(estado, region_txt, region_objetivo) -> list[str]:
    m = []
    if norm(estado) != "publicada":
        m.append(f"Estado '{estado}' (no abierta)")
    if region_objetivo and norm(region_objetivo) not in norm(region_txt):
        m.append(f"Fuera de región objetivo ({region_txt})")
    return m


def _tipo_mp(tipo: str) -> str:
    if tipo.startswith("L") or tipo == "E2":
        return "licitacion"
    return {"CO": "compra_agil", "TD": "trato_directo"}.get(tipo, "otro")


def norm_licitacion(l: dict, region_objetivo: str | None) -> dict:
    c, f, a = l.get("Comprador") or {}, l.get("Fechas") or {}, l.get("Adjudicacion") or {}
    items = []
    for i in (l.get("Items") or {}).get("Listado") or []:
        adj = i.get("Adjudicacion") or {}
        items.append({
            "correlativo": num(i.get("Correlativo")), "codigo_producto": _texto(i.get("CodigoProducto")),
            "codigo_categoria": _texto(i.get("CodigoCategoria")), "categoria": i.get("Categoria") or None,
            "nombre_producto": i.get("NombreProducto") or None, "descripcion": (i.get("Descripcion") or "").strip() or None,
            "unidad_medida": i.get("UnidadMedida") or None, "cantidad": num(i.get("Cantidad")),
            "adj_rut_proveedor": adj.get("RutProveedor") or None, "adj_nombre_proveedor": adj.get("NombreProveedor") or None,
            "adj_cantidad": num(adj.get("Cantidad")), "adj_monto_unitario": num(adj.get("MontoUnitario")),
        })
    estado = l.get("Estado") or "Publicada"
    motivos = motivos_descarte(estado, c.get("RegionUnidad"), region_objetivo)
    codigo = l["CodigoExterno"].strip()
    return {
        "org": {
            "rut": c["RutUnidad"], "nombre": c.get("NombreOrganismo") or c.get("NombreUnidad") or "(sin nombre)",
            "unidad_compra": c.get("NombreUnidad") or None, "region": c.get("RegionUnidad") or None,
            "comuna": c.get("ComunaUnidad") or None,
        } if c.get("RutUnidad") else None,
        "lic": {
            "codigo_mp": codigo, "tipo": _tipo_mp(str(l.get("Tipo") or "")),
            "nombre": (l.get("Nombre") or "").strip(), "descripcion": (l.get("Descripcion") or "").strip() or None,
            "fecha_publicacion": chile_iso(f.get("FechaPublicacion")),
            "fecha_cierre": chile_iso(f.get("FechaCierre") or l.get("FechaCierre")),
            "monto_estimado": num(l.get("MontoEstimado")), "moneda": l.get("Moneda") or "CLP", "estado_mp": estado,
            "url": "https://www.mercadopublico.cl/Procurement/Modules/RFB/DetailsAcquisition.aspx?idlicitacion=" + codigo,
            "json_raw": l, "descartada_filtro": bool(motivos), "motivo_descarte": "; ".join(motivos) or None,
            "fecha_adjudicacion": chile_iso(a.get("Fecha")), "n_oferentes": num(a.get("NumeroOferentes")),
            "url_acta": a.get("UrlActa") or None,
        },
        "items": items,
    }


def norm_compra_agil(d: dict, region_objetivo: str | None) -> dict:
    inst, f, p = d.get("institucion") or {}, d.get("fechas") or {}, d.get("presupuesto") or {}
    items = [{
        "correlativo": idx + 1, "codigo_producto": _texto(i.get("codigo_producto")), "codigo_categoria": None,
        "categoria": None, "nombre_producto": i.get("nombre") or None, "descripcion": i.get("descripcion") or None,
        "unidad_medida": i.get("unidad_medida") or None, "cantidad": num(i.get("cantidad")),
        "adj_rut_proveedor": None, "adj_nombre_proveedor": None, "adj_cantidad": None, "adj_monto_unitario": None,
    } for idx, i in enumerate(d.get("productos_solicitados") or [])]
    estado = (d.get("estado") or {}).get("codigo") or "publicada"
    motivos = motivos_descarte(estado, inst.get("nombre_region"), region_objetivo)
    monto = p.get("monto_disponible_clp")
    return {
        "org": {
            "rut": inst["rut"], "nombre": inst.get("organismo_comprador") or "(sin nombre)",
            "unidad_compra": inst.get("unidad_compra") or None, "region": inst.get("nombre_region") or None, "comuna": None,
        } if inst.get("rut") else None,
        "lic": {
            "codigo_mp": d["codigo"], "tipo": "compra_agil", "nombre": (d.get("nombre") or "").strip(),
            "descripcion": (d.get("descripcion") or "").strip() or None,
            "fecha_publicacion": f.get("fecha_publicacion") or None, "fecha_cierre": f.get("fecha_cierre") or None,
            "monto_estimado": num(monto if monto is not None else p.get("presupuesto_estimado")), "moneda": "CLP",
            "estado_mp": estado, "url": "https://buscador.mercadopublico.cl/ficha?code=" + quote(d["codigo"], safe=""),
            "json_raw": d, "descartada_filtro": bool(motivos), "motivo_descarte": "; ".join(motivos) or None,
            "fecha_adjudicacion": None, "n_oferentes": num((d.get("resumen") or {}).get("total_ofertas_recibidas")),
            "url_acta": None,
        },
        "items": items,
    }
