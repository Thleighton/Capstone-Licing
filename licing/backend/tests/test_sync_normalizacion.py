from licing.modulos.sync.normalizacion import chile_iso, norm_compra_agil, norm_licitacion, num, region_codigo
from licing.modulos.sync.requisitos import extraer_requisitos

LIC = {
    "CodigoExterno": " 1234-56-LE26 ", "Tipo": "LE", "Nombre": "Seminario regional", "Descripcion": "Para 80 personas",
    "Estado": "Publicada", "MontoEstimado": "1500000", "Moneda": "CLP",
    "Comprador": {"RutUnidad": "61.000.000-1", "NombreOrganismo": "Servicio X", "NombreUnidad": "Unidad Y",
                  "RegionUnidad": "Región Metropolitana de Santiago", "ComunaUnidad": "Santiago"},
    "Fechas": {"FechaPublicacion": "2026-10-01T10:00:00", "FechaCierre": "2026-10-10T15:00:00"},
    "Items": {"Listado": [{"Correlativo": 1, "CodigoProducto": 90101501, "NombreProducto": "Coffee break",
                           "Descripcion": " Coffee break para 80 personas ", "Cantidad": "1"}]},
}


def test_chile_iso_convierte_hora_chile_a_utc():
    assert chile_iso("2026-10-10T15:00:00") == "2026-10-10T18:00:00Z"  # horario de verano (UTC-3)
    assert chile_iso("2026-07-10T15:00:00") == "2026-07-10T19:00:00Z"  # invierno (UTC-4)
    assert chile_iso("2026-10-10T15:00:00Z") == "2026-10-10T15:00:00Z"
    assert chile_iso("1900-01-01T00:00:00") is None
    assert chile_iso("") is None and chile_iso("basura") is None


def test_num():
    assert num("10") == 10 and num("1.5") == 1.5 and num("") is None and num(None) is None and num("x") is None


def test_region_codigo():
    assert region_codigo("Región Metropolitana de Santiago") == 13
    assert region_codigo("Ñuble") == 16
    assert region_codigo("Desconocida") is None


def test_norm_licitacion():
    n = norm_licitacion(LIC, "Metropolitana")
    assert n["lic"]["codigo_mp"] == "1234-56-LE26"
    assert n["lic"]["tipo"] == "licitacion"
    assert n["lic"]["descartada_filtro"] is False
    assert n["lic"]["monto_estimado"] == 1500000
    assert n["org"]["rut"] == "61.000.000-1"
    assert n["items"][0]["codigo_producto"] == "90101501"
    assert n["items"][0]["descripcion"] == "Coffee break para 80 personas"


def test_norm_licitacion_fuera_de_region():
    n = norm_licitacion(LIC, "Valparaíso")
    assert n["lic"]["descartada_filtro"] is True
    assert "Fuera de región objetivo" in n["lic"]["motivo_descarte"]


def test_norm_compra_agil():
    d = {"codigo": "1234-5-COT26", "nombre": "Almuerzo", "estado": {"codigo": "publicada"},
         "institucion": {"rut": "1-9", "organismo_comprador": "Org", "nombre_region": "Metropolitana"},
         "presupuesto": {"monto_disponible_clp": 0, "presupuesto_estimado": 999},
         "productos_solicitados": [{"nombre": "Almuerzo", "cantidad": 30}]}
    n = norm_compra_agil(d, None)
    assert n["lic"]["monto_estimado"] == 0  # ?? de JS: 0 no se reemplaza
    assert n["items"][0]["correlativo"] == 1
    assert n["lic"]["url"].endswith("code=1234-5-COT26")


def test_extraer_requisitos():
    n = norm_licitacion(LIC, None)
    r = extraer_requisitos(n["lic"]["nombre"], n["lic"]["descripcion"], n["items"])
    assert r["tipo_evento"] == "seminario"
    assert r["n_asistentes"] == 80
    assert r["servicios_req"][0]["servicio"] == "Coffee break"
    assert r["servicios_req"][0]["personas"] == 80
    assert r["confianza_nlp"] == 0.5
