"""Regresiones de objetos ajenos que compartían palabras con servicios hoteleros."""
from datetime import datetime

import pytest

from app.services.preseleccion import CHILE, evaluar_preseleccion


def evaluar(nombre, descripcion="", items=None):
    return evaluar_preseleccion({"codigo_externo": "100-1-LE26", "estado": "Publicada",
        "codigo_estado": 5, "fecha_cierre": "2026-11-01T15:00:00", "nombre": nombre,
        "descripcion": descripcion, "items": items or []},
        ahora=datetime(2026, 10, 24, 12, tzinfo=CHILE))


CASOS_AJENOS = [
    ("Mantención y reparación de vehículos", "Valor hora mano de obra mecánico fuera de taller, reparaciones en terreno", "78180104"),
    ("Adquisición de mobiliario", "Sillas para salón color verde. Mesa reunión y estaciones de trabajo", "56101500"),
    ("Estudio percepción sobre eje Nueva Alameda", "Investigación basada en el consumidor y focus groups", "80141507"),
    ("Contratación IaaS", "Servicio de alojamiento de infraestructura virtualizada y administración de servidores en datacenter", "80111712"),
    ("Servicio de cursos de capacitación WAFA", "Cursos WAFA, No Deje Rastro y certificación de rescate en aguas blancas", "86101702"),
    ("Campaña comunicacional y plan de medios", "Promoción de destinos turísticos de Ñuble", "80141607"),
]


@pytest.mark.parametrize("especificacion", [
    "Tensión de alimentación: 220V", "Voltaje de alimentación: 12 VDC",
    "Alimentación 220-240 V, 50 Hz", "Alimentación: 12/24V",
    "Fuente de alimentación de 500W", "Cable de alimentación para computador",
    "Conector de alimentación", "Adaptador de alimentación universal",
    "Puerto de alimentación", "Alimentación eléctrica 220 V",
])
def test_especificacion_electrica_no_se_confunde_con_comida(especificacion):
    r = evaluar("Regulador de velocidad para extractor", especificacion,
        items=[{"codigo_producto": "26101766", "descripcion": "Regulador de velocidad para extractor"}])
    assert r["clasificacion"] == "descartada"
    assert r["criterios"]["pertinencia"]["resultado"] == "no_cumple"
    assert not r["criterios"]["pertinencia"]["directa"]


def test_otra_alimentacion_real_se_conserva_en_el_mismo_texto():
    r = evaluar("Servicio de alimentación en Santiago",
        "Equipamiento con tensión de alimentación: 220V. Se requiere alimentación para 40 personas.")
    assert r["clasificacion"] == "preseleccionada"
    menciones = r["criterios"]["pertinencia"]["coincidencias"]
    assert any("40 personas" in m["evidencia"] for m in menciones)
    assert not any(m["fuente"] == "descripcion" and m["inicio"] < 55 for m in menciones)


@pytest.mark.parametrize("servicio", ["Servicio de residencia temporal en Santiago",
    "Se requiere residencia en Santiago", "Residencia para 20 estudiantes en Santiago"])
def test_residencia_contratada_para_personas_sigue_siendo_servicio(servicio):
    r = evaluar(servicio)
    assert r["criterios"]["pertinencia"]["directa"]


@pytest.mark.parametrize("nombre,descripcion,codigo", CASOS_AJENOS,
    ids=["mecanica", "mobiliario", "investigacion", "informatica", "cursos", "publicidad"])
def test_objeto_ajeno_se_descarta_con_motivo_y_evidencia(nombre, descripcion, codigo):
    r = evaluar(nombre, items=[{"codigo_producto": codigo, "descripcion": descripcion}])
    assert r["clasificacion"] == "descartada"
    p = r["criterios"]["pertinencia"]
    assert p["resultado"] == "no_cumple"
    assert p["exclusiones_evidentes"]
    assert all(e["evidencia"] and e["motivo"] for e in p["exclusiones_evidentes"])


@pytest.mark.parametrize("nombre,descripcion,codigo", CASOS_AJENOS,
    ids=["mecanica", "mobiliario", "investigacion", "informatica", "cursos", "publicidad"])
@pytest.mark.parametrize("servicio", ["Arriendo de salón en Santiago", "Alojamiento en Santiago",
    "Coffee break para los asistentes"])
def test_objeto_ajeno_no_descarta_un_paquete_con_servicios_hoteleros(nombre, descripcion, codigo, servicio):
    r = evaluar(nombre, items=[{"codigo_producto": codigo, "descripcion": descripcion},
        {"descripcion": servicio}])
    assert r["clasificacion"] != "descartada"
    assert not r["criterios"]["pertinencia"]["exclusiones_evidentes"]


@pytest.mark.parametrize("ajeno,servicio", [
    ("Alojamiento de servidores", "alojamiento en Santiago para los participantes"),
    ("Sillas para salón", "arriendo de salón en Santiago"),
    ("Mano de obra fuera de taller", "taller para funcionarios con coffee break"),
    ("Alimentación enteral", "alimentación para los asistentes"),
])
def test_primera_mencion_ajena_no_oculta_otra_del_mismo_tipo(ajeno, servicio):
    r = evaluar("Contrato de suministros", descripcion=f"{ajeno}. Se incluye {servicio}.",
        items=[{"codigo_producto": "43211503"}])
    assert r["clasificacion"] != "descartada"
    assert not r["criterios"]["pertinencia"]["exclusiones_evidentes"]


def test_orden_de_compra_no_confunde_una_contratacion_de_alojamiento():
    r = evaluar("Servicios de alojamiento en Santiago para la Universidad de Talca",
        "El servicio comienza desde la aceptación de la orden de compra de Mercado Público.")
    assert r["clasificacion"] == "preseleccionada"


def test_orden_de_compra_no_oculta_una_compra_de_bienes_en_el_mismo_texto():
    r = evaluar("Compra de sábanas para habitaciones de hotel en Santiago",
        "Aceptar la orden de compra. Compra de sábanas para habitaciones de hotel.")
    assert r["clasificacion"] == "revision_manual"
    assert r["criterios"]["pertinencia"]["ambiguedades"]


def test_ubicacion_de_alojamiento_para_pacientes_derivados():
    r = evaluar("Servicio de alojamiento y alimentación transitoria", items=[{
        "descripcion": "Servicio de alojamiento y alimentación transitoria a pacientes del Hospital Hanga Roa derivados a Santiago"}])
    assert r["clasificacion"] == "preseleccionada"
    assert r["criterios"]["ubicacion"]["estado"] == "rm"


def test_derivacion_sin_servicio_hotelero_no_confirma_oportunidad():
    r = evaluar("Transporte de pacientes derivados a Santiago")
    assert r["clasificacion"] != "preseleccionada"


def test_categorias_genericas_repetidas_no_agotan_las_evidencias_del_servicio():
    r = evaluar("Adquisición de mobiliario", items=[{
        "codigo_producto": "56101500", "nombre_producto": "Mobiliario",
        "descripcion": "Sillas para salón y mesa reunión",
        "categoria": "Muebles y mobiliario de alojamiento, salas de reuniones y alimentación",
    } for _ in range(77)])
    assert r["clasificacion"] == "descartada"
    assert not r["entrada_parcial"]


def test_limite_de_menciones_no_oculta_un_servicio_al_final_del_texto():
    r = evaluar("Contrato de suministros", descripcion="Alojamiento de servidores. " * 110
        + "También se requiere alojamiento en Santiago para los asistentes.",
        items=[{"codigo_producto": "43211503"}])
    assert r["entrada_parcial"]
    assert r["clasificacion"] == "revision_manual"
