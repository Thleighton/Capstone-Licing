"""Contratos de preselección: pertinencia y territorio deben tener evidencia compatible."""
from copy import deepcopy
from datetime import datetime

import pytest

from app.services.preseleccion import (
    CHILE, cargar_catalogo, evaluar_preseleccion, normalizar_texto,
)


AHORA = datetime(2026, 10, 24, 12, tzinfo=CHILE)


def entrada(**cambios):
    datos = {"codigo_externo": "100-1-LE26", "codigo_estado": 5, "estado": "Publicada",
             "fecha_cierre": "2026-12-01T12:00:00", "nombre": "Arriendo de salón en Santiago"}
    datos.update(cambios)
    return datos


def evaluar(**cambios):
    return evaluar_preseleccion(entrada(**cambios), ahora=AHORA)


@pytest.mark.parametrize("nombre", [
    "Alojamiento Santiago", "ALOJAMIENTO: SANTIAGO", "Hospedaje - Santiago",
    "Arriendo de salón Santiago", "Alquiler de salas Santiago",
    "Se requiere hotel en Santiago", "Contratación de hoteles en Providencia",
    "Servicio de hotelería en R.M.", "Arriendo de sala en Ñuñoa",
    "Arriendo de sala multiuso en Santiago", "Sala de reuniones en Santiago",
    "Espacio físico para un seminario en Santiago", "Salón para capacitación en Santiago",
    "Hospedaje para la comuna de Las Condes", "Alojamiento en la RM",
    "En Santiago se requiere alojamiento para una delegación",
    "SERVICIO\tDE\tALOJAMIENTO\tEN\tSANTIAGO",
    "Arriendo\u00a0de\u00a0salón en Santiago", "Arriendo   de   salón en Santiago",
    "Arriendo de salo\u0301n en Santiago", "Arriendo de salón en la Región Metropolitana",
])
def test_servicios_del_hotel_con_ubicacion_explicita(nombre):
    r = evaluar(nombre=nombre)
    assert r["clasificacion"] == "preseleccionada"
    assert r["criterios"]["ubicacion"]["vinculo_servicio"]["completo"]
    assert r["decision_postular"] is False


@pytest.mark.parametrize("nombre", [
    "Fumigación de habitaciones de hotel en Santiago",
    "Lavandería para hoteles en Santiago", "Limpieza de habitaciones en Santiago",
    "Traslado desde hoteles en Santiago", "Servicios de vigilancia para hoteles en Santiago",
    "Arriendo de salón de belleza en Santiago", "Remodelación de habitaciones en Santiago",
    "Construcción de hotel en Santiago", "Adquisición de mobiliario para un salón en Santiago",
    "Alojamiento web en servidores de Santiago", "Alojamiento cloud en Santiago",
    "Compra de proyectores para salón en Santiago", "Reparación de salón en Santiago",
    "Capacitación con docentes en un hotel en Santiago",
    "Servicios de producción integral con salón en Santiago",
    "Arriendo de equipos audiovisuales en Santiago", "Compra de desayunos en Santiago",
    "Servicio para residencia sanitaria en Santiago", "Habitaciones hospitalarias en Santiago",
    "El Hotel Ejemplo informa sus novedades. Evento en Santiago.",
])
def test_menciones_relacionadas_no_prueban_contratacion_hotelera(nombre):
    assert evaluar(nombre=nombre)["clasificacion"] == "revision_manual"


@pytest.mark.parametrize("separador", [" y ", " o ", ", ", " / ", " - ", " – "])
def test_listas_de_ciudades_no_ocultan_otras_regiones(separador):
    r = evaluar(nombre=f"Alojamiento en Santiago{separador}Valparaíso")
    assert r["clasificacion"] == "revision_manual"
    assert r["criterios"]["ubicacion"]["estado"] == "mixta"


@pytest.mark.parametrize("ciudad", ["Santiago", "La Serena", "Valparaíso"])
def test_no_mezcla_ciudad_de_otro_item_con_alojamiento_sin_localizar(ciudad):
    r = evaluar(nombre="Contratación de servicios", items=[
        {"descripcion": "Alojamiento para una delegación; lugar por coordinar."},
        {"descripcion": f"Servicio de impresión de folletos en {ciudad}."},
    ])
    assert r["clasificacion"] == "revision_manual"
    assert r["criterios"]["ubicacion"]["estado"] == "ambigua"


def test_no_mezcla_servicios_de_parrafos_distintos_de_la_descripcion():
    r = evaluar(nombre="Contratación de servicios", descripcion=(
        "Se requiere alojamiento; la ciudad se informará después.\n"
        "Servicio de impresión de folletos en Santiago."))
    assert r["clasificacion"] == "revision_manual"


def test_lugar_explicitamente_identificado_se_puede_vincular_al_titulo():
    r = evaluar(nombre="Contratación de alojamiento", descripcion="Lugar de ejecución: Providencia.")
    assert r["clasificacion"] == "preseleccionada"


def test_evento_en_rm_se_vincula_al_salon_del_titulo():
    r = evaluar(nombre="Arriendo de salón", descripcion="La jornada se realizará en Santiago.")
    assert r["clasificacion"] == "preseleccionada"


@pytest.mark.parametrize("descripcion", [
    "El comprador tiene domicilio en Santiago.",
    "La sede de la universidad está en Santiago.",
    "Las ofertas se entregan en las oficinas de Santiago.",
    "La facturación del servicio se realiza en Santiago.",
    "El evento no se realizará en Santiago.",
    "El servicio se prestará fuera de Santiago.",
    "Alojamiento en Santiago de Compostela.",
    "Alojamiento en Santiago del Estero.",
    "Alojamiento en San Pedro.",
    "Alojamiento en San Miguel de Tucumán.",
    "Alojamiento en La Florida, Estados Unidos.",
    "Alojamiento en Santiago, España.",
])
def test_no_infiere_ubicacion_desde_comprador_negacion_o_toponimo_ambiguo(descripcion):
    assert evaluar(nombre="Alojamiento para delegación", descripcion=descripcion)["clasificacion"] == "revision_manual"


@pytest.mark.parametrize("ciudad", ["Santiago", "Valparaíso"])
def test_cobertura_nacional_se_conserva_aunque_nombre_una_ciudad(ciudad):
    r = evaluar(nombre=f"Alojamiento en {ciudad}", descripcion="Servicio con cobertura nacional.")
    assert r["clasificacion"] == "revision_manual"


@pytest.mark.parametrize("cambios", [
    {"nombre": {}}, {"descripcion": 123}, {"items": {}}, {"items": "alojamiento"},
    {"items": [None]}, {"items": [{"descripcion": []}]},
    {"codigo_estado": "5"}, {"codigo_estado": True}, {"nombre_organismo": []},
])
def test_datos_mal_formados_no_detienen_el_lote_ni_se_certifican(cambios):
    r = evaluar(**cambios)
    assert r["clasificacion"] == "revision_manual"
    assert r["entrada_parcial"]
    assert r["calidad_datos"]["incidencias"]


@pytest.mark.parametrize("cambios", [
    {"documentos": {}},
    {"documentos": [True]}, {"documentos": [{"id": 1, "paginas_texto": "Santiago"}]},
    {"documentos": [{"id": 1, "paginas_texto": [None]}]},
    {"documentos": [{"id": 1, "paginas_texto": [{"texto": 123}]}]},
    {"documentos": [{"id": 1, "estado_extraccion": []}]},
    {"documentos": [{"id": 1, "cobertura": "parcial"}]},
    {"documentos": [{"id": 1, "cobertura": {"motivo_codigo": []}}]},
    {"documentos": [{"id": 1, "vigente": "false"}]},
    {"incidencia_documental": []}, {"incidencia_documental": {}},
])
def test_datos_documentales_invalidos_no_bloquean_una_ficha_suficiente(cambios):
    r = evaluar(**cambios)
    assert r["clasificacion"] == "preseleccionada"
    assert r["calidad_datos"]["incidencias"]
    assert r["decision_postular"] is False


@pytest.mark.parametrize("datos", [None, [], "alojamiento en Santiago", 1, False])
def test_entrada_invalida_se_devuelve_como_revision(datos):
    r = evaluar_preseleccion(datos, ahora=AHORA)
    assert r["clasificacion"] == "revision_manual"
    assert r["calidad_datos"]["incidencias"]


def test_documentos_retirados_no_producen_dudas_nuevas():
    r = evaluar(documentos=[{"vigente": False, "paginas_texto": "dato histórico inválido"}])
    assert r["clasificacion"] == "preseleccionada"


def test_datos_incompletos_no_justifican_descartar_por_ubicacion():
    r = evaluar(nombre="Alojamiento en La Serena", items=[None])
    assert r["clasificacion"] == "revision_manual"


def test_los_indices_de_evidencia_no_cambian_al_encontrar_un_item_invalido():
    r = evaluar(nombre="Contratación", items=[None, {"descripcion": "Alojamiento en Santiago"}])
    assert any(e["fuente"] == "items[1].descripcion" for e in r["criterios"]["ubicacion"]["evidencias"])


def test_offsets_se_conservan_con_espacios_unicode_y_acentos_descompuestos():
    texto = "Se requiere   salo\u0301n\u00a0para  50 personas en Santiago."
    r = evaluar(nombre=texto)
    for h in r["requisitos_detectados"]["hallazgos"]:
        assert texto[h["inicio"]:h["fin"]] == h["texto"]
    for e in r["criterios"]["ubicacion"]["evidencias"]:
        assert texto[e["inicio"]:e["fin"]] == "Santiago"
    for e in r["criterios"]["pertinencia"]["coincidencias"]:
        assert normalizar_texto(texto[e["inicio"]:e["fin"]]) == e["termino"]


def test_calidad_y_version_de_reglas_invalidan_la_huella(monkeypatch):
    a = evaluar()
    b = evaluar(items=[None])
    assert a["huella_entrada"] != b["huella_entrada"]
    monkeypatch.setattr("app.services.preseleccion.VERSION_MOTOR", "reglas-siguiente")
    assert a["huella_entrada"] != evaluar()["huella_entrada"]
    catalogo = deepcopy(cargar_catalogo())
    catalogo["version"] = "catalogo-siguiente"
    monkeypatch.setattr("app.services.preseleccion.cargar_catalogo", lambda: catalogo)
    assert a["huella_entrada"] != evaluar()["huella_entrada"]


def test_no_muta_documentos_ni_items_del_llamador():
    datos = entrada(items=[None, {"descripcion": "Alojamiento en Santiago"}],
                    documentos=[{"id": 1, "cobertura": {"motivo_codigo": []}}])
    copia = deepcopy(datos)
    evaluar_preseleccion(datos, ahora=AHORA)
    assert datos == copia


def test_falta_de_pdf_se_expone_sin_afirmar_cumplimiento_de_las_bases():
    r = evaluar()
    assert r["clasificacion"] == "preseleccionada"
    assert r["cobertura"] == "sin_bases"
    assert r["documentacion"]["resultado"] == "sin_informacion"
    assert r["decision_postular"] is False


def test_no_certifica_una_entrada_si_no_caben_todas_las_evidencias():
    r = evaluar(items=[{"descripcion": "Arriendo de salón en Santiago"} for _ in range(110)])
    assert r["entrada_parcial"]
    assert r["clasificacion"] == "revision_manual"


def test_lectura_acotada_conserva_el_limite_total_y_no_descarta():
    from app.services.preseleccion import MAX_TEXTO_TOTAL, _campos
    datos = entrada(items=[{"descripcion": "a" * 30000} for _ in range(20)])
    campos, parcial = _campos(datos)
    assert parcial and sum(len(t) for _, t in campos) <= MAX_TEXTO_TOTAL


def test_lista_de_paginas_invalida_no_impide_usar_la_ficha_suficiente():
    r = evaluar(documentos=[{"id": 1, "estado_extraccion": "extraido", "paginas_texto": [
        {"pagina": n, "texto": "Alojamiento en Santiago"} for n in range(1, 122)]}])
    assert r["calidad_datos"]["incidencias"]
    assert r["clasificacion"] == "preseleccionada"
    assert r["decision_postular"] is False


@pytest.mark.parametrize("nombre", [
    "Adquisición de catéteres", "Compra de medicamentos", "SUMINSTRO DE ANTISÉPTICOS",
    "KITS PARA PROCEDIMIENTOS ENDOVASCULARES", "SUMINISTRO ALCOHOL GEL 70%",
    "Servicio de prestaciones médicas ambulatorias", "Procedimientos quirúrgicos",
    "SERVICIOS PROFESIONALES PERSONAL TI", "Compra de computadores",
    "Adquisición de notebooks", "Construcción de puentes", "Conservación de caminos",
])
def test_objeto_ajeno_explicito_sin_senales_hoteleras_se_descarta_con_evidencia(nombre):
    r = evaluar(nombre=nombre)
    assert r["clasificacion"] == "descartada"
    assert r["criterios"]["pertinencia"]["resultado"] == "no_cumple"
    assert r["criterios"]["pertinencia"]["exclusiones_evidentes"][0]["fuente"] == "nombre"


@pytest.mark.parametrize("servicio", [
    "Arriendo de salón en Santiago", "Alojamiento en Santiago",
    "Coffee break para una jornada en Santiago", "Seminario para funcionarios",
])
def test_una_linea_ajena_no_oculta_servicios_hoteleros_en_otras_lineas(servicio):
    r = evaluar(nombre="Compra de computadores", items=[{"descripcion": servicio}])
    assert r["clasificacion"] != "descartada"
    assert not r["criterios"]["pertinencia"]["exclusiones_evidentes"]


def test_entrada_parcial_se_conserva_pero_fallo_documental_no_oculta_objeto_ajeno():
    assert evaluar(nombre="Compra de medicamentos", items=[None])["clasificacion"] == "revision_manual"
    assert evaluar(nombre="Compra de medicamentos", incidencia_documental={
        "codigo": "pdf_corrupto", "motivo": "PDF ilegible"})["clasificacion"] == "descartada"


@pytest.mark.parametrize("codigo,nombre_producto", [
    ("42142502", "Agujas para anestesia"), ("51111716", "Medicamento oncológico"),
    ("56101532", "Mobiliario"), ("43211503", "Computadores"),
    ("72101506", "Mantenimiento de ascensores"), ("80111713", "Administradores de bases de datos"),
    ("101101001", "Licitación Pública de Obra"), ("102101001", "Licitación Pública de Consultoria"),
])
def test_codigos_ajenos_descartan_sin_exigir_pdf_ni_lugar(codigo, nombre_producto):
    r = evaluar(nombre="Contratación de suministros o servicios", items=[{
        "codigo_producto": codigo, "nombre_producto": nombre_producto,
        "categoria": "Servicios de Viajes, alimentación, alojamiento y entretenimiento"}],
        incidencia_documental={"codigo": "sin_descarga_publica", "motivo": "No fue posible obtener bases."})
    assert r["clasificacion"] == "descartada"
    e = r["criterios"]["pertinencia"]["exclusiones_evidentes"][0]
    assert e["fuente"] == "items[0].codigo_producto"
    assert codigo in e["evidencia"]


@pytest.mark.parametrize("codigo", [None, "99999999", "42", 42142502])
def test_codigo_desconocido_en_una_linea_impide_descartar_el_conjunto(codigo):
    r = evaluar(nombre="Contrato de servicios", items=[
        {"codigo_producto": "42142502", "nombre_producto": "Agujas"},
        {"codigo_producto": codigo, "descripcion": "Servicio por especificar"},
    ])
    assert r["clasificacion"] == "revision_manual"


@pytest.mark.parametrize("servicio", ["Alojamiento en Santiago", "Arriendo de salón en Santiago",
    "Coffee break para una jornada en Santiago", "Capacitación presencial con almuerzo"])
def test_codigo_ajeno_no_sobrepasa_una_necesidad_hoteleria_en_otra_linea(servicio):
    r = evaluar(nombre="Contrato de servicios", items=[
        {"codigo_producto": "42142502", "descripcion": "Suministro de agujas"},
        {"codigo_producto": "43211503", "descripcion": servicio},
    ])
    assert r["clasificacion"] != "descartada"


@pytest.mark.parametrize("texto,codigo", [
    ("Adaptadores de equipos de alimentación enteral", "42231500"),
    ("Reparación de vehículos en taller particular, jornada normal", "78180101"),
])
def test_alimentacion_clinica_y_jornada_laboral_no_son_servicios_del_hotel(texto, codigo):
    r = evaluar(nombre="Contrato de suministros", items=[{"codigo_producto": codigo, "descripcion": texto}])
    assert r["clasificacion"] == "descartada"


def test_bases_legibles_que_contradicen_la_ficha_si_se_consideran():
    r = evaluar(documentos=[{"id": 7, "estado_extraccion": "extraido", "paginas_texto": [
        {"pagina": 1, "texto": "El alojamiento se prestará en Valparaíso."}]}])
    assert r["clasificacion"] == "revision_manual"
    assert r["criterios"]["ubicacion"]["estado"] == "mixta"


def test_pdf_ilegible_no_inventa_servicio_o_ubicacion_que_no_estan_en_la_ficha():
    r = evaluar(nombre="Contrato 2026", documentos=[{"id": 1, "estado_extraccion": "parcial",
        "paginas_texto": [{"pagina": 1, "texto": "Alojamiento en Santiago"}]}])
    assert r["clasificacion"] == "revision_manual"
    assert not r["criterios"]["pertinencia"]["directa"]
