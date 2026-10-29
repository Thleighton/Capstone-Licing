"""Casos límite y regresiones de la auditoría de Compras Ágiles del 28-10-2026."""
from datetime import datetime

import pytest

from app.services.compra_agil_preseleccion import evaluar
from app.services.preseleccion import evaluar_preseleccion


def compra(**cambios):
    datos = {"codigo_externo": "1-1-COT26", "estado": "publicada", "codigo_estado": None,
             "fecha_cierre": "2099-12-01T12:00:00-03:00", "codigo_region": 13,
             "region_comprador": "Región Metropolitana", "nombre": "Servicio de coffee break",
             "descripcion": "Servicio de coffee break para 40 personas.", "items": []}
    return {**datos, **cambios}


@pytest.mark.parametrize("region", [None, 5, 8, 13])
def test_comprador_no_decide_el_lugar_del_servicio(region):
    resultado = evaluar(compra(codigo_region=region, region_comprador=None))
    assert resultado["clasificacion"] == "revision_manual"
    assert resultado["criterios"]["ubicacion"]["resultado"] == "sin_informacion"
    assert resultado["criterios"]["pertinencia"]["resultado"] == "cumple"


@pytest.mark.parametrize("region", [None, 5, 13])
def test_comprador_de_otra_region_puede_contratar_en_santiago(region):
    resultado = evaluar(compra(codigo_region=region, nombre="Coffee break en Santiago",
        descripcion="Se requiere servicio de coffee break en Santiago para 40 personas."))
    assert resultado["clasificacion"] == "preseleccionada"


@pytest.mark.parametrize("region", [None, 5, 13])
def test_comprador_de_la_rm_no_hace_valido_un_servicio_fuera(region):
    resultado = evaluar(compra(codigo_region=region, nombre="Coffee break en Valparaíso",
        descripcion="Se requiere servicio de coffee break en Valparaíso para 40 personas."))
    assert resultado["clasificacion"] == "descartada"
    assert resultado["pilar_decisivo"] == "ubicacion"


@pytest.mark.parametrize("codigo,nombre", [
    ("80141605", "Regalos publicitarios"),
    ("80141611", "Personalización de regalos o productos promocionales"),
    ("82121505", "Impresión promocional o publicitaria"),
    ("82121511", "Impresión de manuales"),
    ("82121903", "Encuadernación"),
])
def test_bienes_y_grafica_no_son_servicios_del_hotel(codigo, nombre):
    resultado = evaluar(compra(nombre=nombre, descripcion=nombre,
        items=[{"codigo_producto": codigo, "nombre_producto": nombre, "descripcion": nombre}]))
    assert resultado["clasificacion"] == "descartada"
    assert resultado["pilar_decisivo"] == "pertinencia"
    assert resultado["criterios"]["pertinencia"]["exclusiones_evidentes"][0]["evidencia"]


def test_reglas_de_productos_ajenos_se_comparten_con_licitaciones():
    datos = compra(codigo_externo="5251-1194-COT26", nombre="Adquisición de vasos plásticos reutilizables",
        descripcion="Adquisición de vasos plásticos reutilizables, según archivo adjunto.", items=[
            {"codigo_producto": "80141605", "nombre_producto": "Regalos publicitarios",
             "descripcion": "Vaso reutilizable transparente con tapa domo y bombilla."},
            {"codigo_producto": "80141611", "nombre_producto": "Personalización de regalos o productos promocionales",
             "descripcion": "Vaso plástico reutilizable con asa y tapa."}])
    assert evaluar(datos)["clasificacion"] == "descartada"
    assert evaluar_preseleccion({**datos, "documentos": []})["clasificacion"] == "descartada"


@pytest.mark.parametrize("codigo", ["80141605", "82121511", "46171604"])
def test_bienes_en_un_paquete_con_catering_no_descartan_el_servicio(codigo):
    resultado = evaluar(compra(nombre="Paquete para jornada en Santiago", descripcion="Servicios para jornada.", items=[
        {"codigo_producto": codigo, "descripcion": "Suministros complementarios"},
        {"codigo_producto": "90101603", "descripcion": "Servicio de coffee break en Santiago para 40 personas."},
    ]))
    assert resultado["clasificacion"] != "descartada"
    assert resultado["criterios"]["pertinencia"]["directa"]
    assert not resultado["criterios"]["pertinencia"]["exclusiones_evidentes"]


def test_una_linea_desconocida_impide_descartar_todo_el_paquete():
    resultado = evaluar(compra(nombre="Adquisición de suministros", descripcion="Ver adjuntos", items=[
        {"codigo_producto": "80141605", "descripcion": "Vasos promocionales"},
        {"codigo_producto": None, "descripcion": "Otra prestación por especificar"},
    ]))
    assert resultado["clasificacion"] == "revision_manual"


def test_cctv_con_capacitacion_de_uso_no_contrata_un_salon():
    texto = "Suministro e instalación de equipos CCTV y alarma, configuración, puesta en marcha y capacitación."
    resultado = evaluar(compra(codigo_externo="1426100-101-COT26", nombre="Sistema CCTV y alarma",
        descripcion=texto, items=[{"codigo_producto": "46171604", "descripcion": texto}]))
    assert resultado["clasificacion"] == "descartada"
    assert resultado["pilar_decisivo"] == "pertinencia"


def test_capacitacion_con_solo_adjuntos_requiere_revision():
    texto = "Jornada de capacitación y autocuidado según EETT y anexos adjuntos."
    resultado = evaluar(compra(codigo_externo="2408-574-COT26", codigo_region=8, nombre=texto,
        descripcion=texto, items=[{"codigo_producto": "86111604", "descripcion": texto}]))
    assert resultado["clasificacion"] == "revision_manual"


def test_lectura_truncada_no_autoriza_descartar_un_posible_paquete():
    resultado = evaluar(compra(nombre="Especificaciones de servicios", descripcion="x " * 20000,
        items=[{"codigo_producto": "80141605", "descripcion": "Vasos promocionales"}]))
    assert resultado["entrada_parcial"]
    assert resultado["clasificacion"] == "revision_manual"


def test_vigencia_se_compara_con_el_mismo_instante_de_la_auditoria():
    datos = compra(nombre="Coffee break en Santiago", fecha_cierre="2026-10-28T15:00:00-03:00")
    antes = evaluar(datos, ahora=datetime.fromisoformat("2026-10-28T14:59:59-03:00"))
    despues = evaluar(datos, ahora=datetime.fromisoformat("2026-10-28T15:00:00-03:00"))
    assert antes["clasificacion"] == "preseleccionada"
    assert despues["clasificacion"] == "descartada" and despues["pilar_decisivo"] == "vigencia"
