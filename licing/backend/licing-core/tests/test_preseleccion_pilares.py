"""Solo vigencia, lugar y servicio deciden la etapa anterior al filtro semántico."""
from datetime import datetime
from itertools import product

import pytest

from app.services.preseleccion import CHILE, PILARES, clasificar_pilares, evaluar_preseleccion


def evaluar(**cambios):
    datos = {"codigo_externo": "100-1-LE26", "estado": "Publicada", "codigo_estado": 5,
        "fecha_cierre": "2026-12-01T15:00:00", "nombre": "Alojamiento en Santiago"}
    return evaluar_preseleccion({**datos, **cambios}, ahora=datetime(2026, 10, 24, 12, tzinfo=CHILE))


@pytest.mark.parametrize("resultados", product(("cumple", "no_cumple", "sin_informacion"), repeat=3))
def test_todas_las_combinaciones_de_los_tres_pilares(resultados):
    criterios = {codigo: {"resultado": r, "motivo": f"Motivo {codigo}"}
        for codigo, r in zip(PILARES, resultados)}
    clasificacion, motivo, decisivo = clasificar_pilares(criterios)
    if "no_cumple" in resultados:
        esperado = PILARES[resultados.index("no_cumple")]
        assert clasificacion == "descartada"
    elif "sin_informacion" in resultados:
        esperado = PILARES[resultados.index("sin_informacion")]
        assert clasificacion == "revision_manual"
    else:
        esperado = None
        assert clasificacion == "preseleccionada"
    assert decisivo == esperado
    if esperado:
        assert motivo == criterios[esperado]["motivo"]


@pytest.mark.parametrize("servicio", ["Coffee break", "Coffe-break", "Catering", "Banquetería",
    "Servicio de alimentación", "Servicio de desayuno", "Cóctel", "Alojamiento y alimentación",
    "Arriendo de salón y coffee break"])
def test_servicios_simples_o_combinados_cumplen_los_tres_pilares(servicio):
    r = evaluar(nombre=f"{servicio} en Santiago")
    assert r["clasificacion"] == "preseleccionada"
    assert tuple(r["criterios"]) == PILARES
    assert r["orden_pilares"] == list(PILARES)
    assert all(c["resultado"] == "cumple" and c["motivo"] for c in r["criterios"].values())


def test_lugar_pendiente_es_el_primer_motivo_antes_del_servicio_pendiente():
    r = evaluar(nombre="Antecedentes disponibles en las bases")
    assert r["clasificacion"] == "revision_manual"
    assert r["pilar_decisivo"] == "ubicacion"
    assert r["motivo"] == r["criterios"]["ubicacion"]["motivo"]


def test_alimentacion_fuera_de_cobertura_se_descarta_por_ubicacion():
    r = evaluar(nombre="Coffee break en Valparaíso")
    assert r["clasificacion"] == "descartada"
    assert r["pilar_decisivo"] == "ubicacion"
    assert r["criterios"]["pertinencia"]["resultado"] == "cumple"


def test_alimentacion_sin_lugar_se_conserva_para_confirmar_ubicacion():
    r = evaluar(nombre="Servicio de banquetería", region_comprador="Metropolitana")
    assert r["clasificacion"] == "revision_manual"
    assert r["pilar_decisivo"] == "ubicacion"
    assert r["criterios"]["pertinencia"]["resultado"] == "cumple"


def test_suministro_de_un_servicio_de_coffee_break_no_es_compra_de_bienes():
    r = evaluar(nombre="Contratar el servicio de suministro de coffee break y cóctel en La Florida")
    assert r["clasificacion"] == "preseleccionada"


def test_lugar_de_alimentacion_no_se_toma_de_otra_linea():
    r = evaluar(nombre="Servicios para actividades", items=[
        {"descripcion": "Coffee break, lugar por coordinar"},
        {"descripcion": "Servicio de impresión en Santiago"},
    ])
    assert r["clasificacion"] == "revision_manual"
    assert r["pilar_decisivo"] == "ubicacion"


def test_documentos_capacidad_presupuesto_y_comprador_no_crean_otros_pilares():
    r = evaluar(nombre="Coffee break en Santiago", monto_estimado=None, nombre_organismo="Comprador nuevo",
        documentos=[{"id": 1, "estado_extraccion": "error"}])
    assert r["clasificacion"] == "preseleccionada"
    assert tuple(r["criterios"]) == PILARES
    assert "documentacion" in r
    assert r["documentacion"]["bloquea_preseleccion"] is False


def test_informacion_incompleta_se_refleja_dentro_de_los_pilares():
    r = evaluar(items=[None])
    assert r["clasificacion"] == "revision_manual"
    assert any(c["resultado"] == "sin_informacion" for c in r["criterios"].values())


@pytest.mark.parametrize("nombre", ["No se requiere alimentación en Santiago",
    "No incluye servicio de coffee break en Santiago", "Alimentación eléctrica en Santiago"])
def test_alimentacion_negada_o_no_humana_no_prueba_servicio_del_hotel(nombre):
    r = evaluar(nombre=nombre)
    assert r["clasificacion"] != "preseleccionada"
    assert r["criterios"]["pertinencia"]["resultado"] != "cumple"


def test_alojamiento_sin_alimentacion_sigue_siendo_oportunidad():
    assert evaluar(nombre="Alojamiento en Santiago sin alimentación")["clasificacion"] == "preseleccionada"
