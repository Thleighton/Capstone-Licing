from copy import deepcopy
from datetime import datetime

import pytest

from app.services.preseleccion import CHILE, cargar_catalogo, evaluar_preseleccion

AHORA = datetime(2026, 10, 23, 12, tzinfo=CHILE)


def licitacion(**cambios):
    datos = {"codigo_externo": "100-1-LE26", "raw_id": 12, "estado": "Publicada", "codigo_estado": 5,
        "fecha_cierre": "2026-11-01T15:00:00", "nombre": "Arriendo de salón en Santiago", "items": []}
    datos.update(cambios)
    return datos


def evaluar(**cambios):
    return evaluar_preseleccion(licitacion(**cambios), ahora=AHORA)


def test_candidata_no_equivale_a_decision_de_postular():
    r = evaluar()
    assert r["clasificacion"] == "preseleccionada"
    assert r["decision_postular"] is False and r["modo"] == "preseleccion"
    assert r["criterios"]["ubicacion"]["evidencias"][0]["fuente"] == "nombre"


@pytest.mark.parametrize("comuna", cargar_catalogo()["comunas_rm"])
def test_cobertura_de_comunas_rm(comuna):
    r = evaluar(nombre=f"Se requiere alojamiento en la comuna de {comuna}, Región Metropolitana.")
    assert r["criterios"]["ubicacion"]["estado"] == "rm"
    assert r["clasificacion"] == "preseleccionada"


def test_comprador_fuera_de_rm_puede_contratar_en_santiago():
    r = evaluar(nombre="Servicio de hotelería", region_comprador="Los Lagos",
        descripcion="La Seremi de la Región de Los Lagos requiere alojamiento en Santiago.")
    assert r["clasificacion"] == "preseleccionada"
    assert {e["region"] for e in r["criterios"]["ubicacion"]["evidencias"]} == {"Metropolitana"}


def test_comprador_en_rm_no_convierte_servicio_fuera_en_candidato():
    r = evaluar(nombre="Servicio de alojamiento", region_comprador="Metropolitana",
        descripcion="Se contrata alojamiento en La Serena para una delegación.")
    assert r["clasificacion"] == "descartada"
    assert r["criterios"]["ubicacion"]["estado"] == "fuera_rm"


@pytest.mark.parametrize("descripcion", [
    "El comprador tiene domicilio en Santiago y requiere un salón.",
    "La Universidad de Santiago solicita un salón, revisar bases.",
    "Arriendo de salón fuera de Santiago.",
    "El evento no se realizará en Santiago, revisar bases.",
    "Servicio de hospedaje en San Pedro.",
    "Servicio de hospedaje en Santiago de Compostela.",
])
def test_menciones_ambiguas_no_se_convierten_en_ubicacion_confirmada(descripcion):
    r = evaluar(nombre="Contratación de servicios", descripcion=descripcion)
    assert r["clasificacion"] == "revision_manual"
    assert r["criterios"]["ubicacion"]["estado"] in {"sin_determinar", "ambigua"}


def test_direcciones_administrativas_y_region_comprador_son_solo_pistas():
    r = evaluar(nombre="Arriendo de salón", region_comprador="Metropolitana",
        direccion_entrega="Santiago", direccion_visita="Providencia")
    assert r["clasificacion"] == "revision_manual"
    assert len(r["criterios"]["ubicacion"]["pistas"]) == 2


def test_ubicacion_en_la_descripcion_del_item():
    r = evaluar(nombre="Jornada institucional", items=[{"correlativo": 1,
        "nombre_producto": "Salas de reuniones", "descripcion": "Arriendo de salón en Providencia."}])
    assert r["clasificacion"] == "preseleccionada"
    assert r["criterios"]["ubicacion"]["evidencias"][0]["fuente"] == "items[0].descripcion"


def test_licitacion_multirregional_se_conserva_para_revisar_ofertas_parciales():
    r = evaluar(nombre="Servicio de alojamiento en Santiago y Valparaíso")
    assert r["criterios"]["ubicacion"]["estado"] == "mixta"
    assert r["clasificacion"] == "revision_manual"


def test_una_linea_fuera_de_rm_no_descarta_otras_lineas_sin_ubicacion():
    r = evaluar(nombre="Alojamiento para delegaciones", items=[
        {"nombre_producto": "Hoteles", "descripcion": "Hospedaje en Valparaíso."},
        {"nombre_producto": "Hoteles", "descripcion": "Alojamiento, lugar por coordinar."},
    ])
    assert r["clasificacion"] == "revision_manual"


def test_san_pedro_de_atacama_no_coincide_con_san_pedro_rm():
    r = evaluar(nombre="Servicio de hospedaje en San Pedro de Atacama")
    assert r["clasificacion"] == "descartada"
    assert r["criterios"]["ubicacion"]["evidencias"][0]["region"] == "Antofagasta"


def test_mencion_fuera_de_rm_en_compra_nacional_no_descarta_todo_el_proceso():
    r = evaluar(nombre="Servicio de alojamiento en diversas regiones",
        descripcion="Incluye hospedaje en Valparaíso y otras ciudades, revisar cada línea.")
    assert r["clasificacion"] == "revision_manual"


@pytest.mark.parametrize("texto", ["OTEC requiere arriendo de salón en Santiago.",
    "Salón para capacitación en Santiago.", "Espacio físico para una jornada institucional en Santiago."])
def test_no_excluye_por_otec_capacitacion_o_ausencia_de_hotel(texto):
    assert evaluar(nombre=texto)["clasificacion"] == "preseleccionada"


@pytest.mark.parametrize("texto", ["Compra de sábanas para habitaciones de hotel en Santiago.",
    "Remodelación de salón en Santiago.", "Servicios de capacitación con docentes en Santiago."])
def test_bienes_obras_y_docencia_requieren_desambiguacion(texto):
    r = evaluar(nombre=texto)
    assert r["clasificacion"] == "revision_manual"
    assert r["criterios"]["pertinencia"]["ambiguedades"]


@pytest.mark.parametrize("texto", ["Coffee break en Santiago", "Coffe-break en Santiago", "COFFEEBREAK en Santiago"])
def test_alimentacion_y_variantes_son_senales_no_oferta_independiente_confirmada(texto):
    r = evaluar(nombre=texto)
    assert "alimentacion_asociada" in r["criterios"]["pertinencia"]["grupos"]
    assert r["clasificacion"] == "revision_manual"


def test_sin_palabras_clave_se_conserva_para_semantica_o_revision():
    r = evaluar(nombre="Contratación 2026", descripcion="Antecedentes disponibles en las bases.")
    assert r["clasificacion"] == "revision_manual"
    assert r["semantica"]["estado"] == "pendiente"


@pytest.mark.parametrize("cambios", [{"fecha_cierre": "2026-10-23T11:59:00"},
    {"estado": "Revocada", "codigo_estado": 18}, {"estado": "Cerrada", "codigo_estado": 6}])
def test_excluye_oportunidades_sin_plazo_o_cerradas(cambios):
    assert evaluar(**cambios)["clasificacion"] == "descartada"


def test_fecha_cierre_con_zona_se_compara_con_hora_chilena():
    assert evaluar(fecha_cierre="2026-10-23T15:00:01Z")["clasificacion"] == "preseleccionada"
    assert evaluar(fecha_cierre="2026-10-23T15:00:00Z")["clasificacion"] == "descartada"


@pytest.mark.parametrize("cambios", [{"fecha_cierre": None}, {"fecha_cierre": "desconocida"},
    {"estado": None, "codigo_estado": None}, {"estado": "Cerrada", "codigo_estado": 5}])
def test_fechas_ausentes_y_estados_contradictorios_se_revisan(cambios):
    assert evaluar(**cambios)["clasificacion"] == "revision_manual"


def test_monto_y_capacidad_ausentes_no_descartan_una_oportunidad_potencial():
    assert evaluar(monto_estimado=None)["clasificacion"] == "preseleccionada"


def test_texto_parcial_no_justifica_descarte_territorial():
    r = evaluar(nombre="Hospedaje en La Serena", descripcion="x" * 31000 + " Hospedaje en Santiago.")
    assert r["entrada_parcial"] and r["clasificacion"] == "revision_manual"


def test_no_muta_el_original_y_la_huella_cambia_con_los_datos():
    datos = licitacion()
    antes = deepcopy(datos)
    a = evaluar_preseleccion(datos, ahora=AHORA)
    assert datos == antes
    datos["nombre"] = "Hospedaje en Valparaíso"
    b = evaluar_preseleccion(datos, ahora=AHORA)
    assert a["huella_entrada"] != b["huella_entrada"]


def test_compra_agil_no_forma_parte_del_piloto():
    with pytest.raises(ValueError, match="licitaciones normales"):
        evaluar(codigo_externo="100-1-COT26")


def test_bases_aportan_lugar_y_servicio_con_pagina():
    datos = {"codigo_externo": "123-1-LE26", "nombre": "Contratación jornada anual", "codigo_estado": 5,
             "fecha_cierre": "2099-01-01", "documentos": [{"id": 7, "estado_extraccion": "extraido",
             "paginas_texto": [{"pagina": 3, "texto": "Se requiere arriendo de salón en Santiago para 50 personas, montaje tipo escuela."}]}]}
    resultado = evaluar_preseleccion(datos)
    assert resultado['clasificacion'] == 'preseleccionada'
    assert resultado['criterios']['ubicacion']['evidencias'][0]['fuente'] == 'documentos[7].paginas[3]'
    assert any(h['texto'] == '50 personas' for h in resultado['requisitos_detectados']['hallazgos'])
    assert resultado['cobertura'] == 'parcial'
    datos['documentos'][0]['estado_extraccion'] = 'parcial'
    assert evaluar_preseleccion(datos)['clasificacion'] == 'revision_manual'


def test_alojamiento_informatico_no_pasa_como_hotel():
    resultado = evaluar_preseleccion({'nombre': 'Alojamiento de infraestructura virtualizada en Santiago',
        'codigo_estado': 5, 'fecha_cierre': '2099-01-01'})
    assert resultado['clasificacion'] != 'preseleccionada'


def test_cliente_prioritario_no_confunde_universidades():
    from app.services.preseleccion import detectar_cliente
    assert detectar_cliente({'nombre_organismo': 'Universidad de Chile, Facultad de Medicina'})
    assert not detectar_cliente({'nombre_organismo': 'Universidad Católica de Chile'})


def test_evidencia_con_acentos_y_unicode_conserva_offsets():
    from app.services.preseleccion import extraer_requisitos
    texto = 'Reunio\u0301n pública: salón para 50 personas en Santiago.'
    hallazgos = extraer_requisitos([('descripcion', texto)])['hallazgos']
    assert hallazgos
    for h in hallazgos:
        assert texto[h['inicio']:h['fin']] == h['texto']
