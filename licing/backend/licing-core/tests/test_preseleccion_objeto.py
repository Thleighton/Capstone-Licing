"""Regresiones de objetos ajenos. Ejecutable sin pytest, base ni red."""
from copy import deepcopy
from datetime import datetime
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.services.preseleccion import CHILE, evaluar_preseleccion


def item(codigo, descripcion, nombre="Producto"):
    return {"codigo_producto": codigo, "descripcion": descripcion, "nombre_producto": nombre}


CASOS = [
    ("hardware_sin_descripcion", {"nombre": "ADQ. INSUMOS Y HARDWARE DEPARTAMENTO TIC", "descripcion": None,
        "items": [item("43201803", "SSD 240 GB", "Discos duros")]}, "descartada"),
    ("sin_nombre_sin_descripcion_con_items", {"nombre": None, "descripcion": None,
        "items": [item("43201803", "SSD 240 GB")]}, "descartada"),
    ("hardware_nombre_generico_salon", {"nombre": "Compra de equipos",
        "items": [item("43201803", "SSD 240 GB", "Salas de reuniones")]}, "descartada"),
    ("ssd_codigo_desconocido", {"nombre": "Compra de equipos",
        "items": [item("99999999", "Disco duro SSD 240 GB")]}, "descartada"),
    ("ssd_entero", {"nombre": "Compra de equipos",
        "items": [item(43201803, "SSD 240 GB")]}, "descartada"),
    ("procedimientos_clinicos", {"nombre": "PROCEDIMIENTOS ENDOVASCULARES DIAGNOSTICOS",
        "items": [item("42142801", "Dispositivos vasculares")]}, "descartada"),
    ("clinica_50_lineas", {"nombre": "Procedimientos endovasculares",
        "items": [item("42142801", "Suministro de insumos clínicos y equipos médicos") for _ in range(50)]}, "descartada"),
    ("abarrotes_50_lineas", {"nombre": "ABARROTES Y OTROS 2027",
        "descripcion": "Suministro de abarrotes para la alimentación de pacientes",
        "items": [item("50101538", "Verduras para alimentación") for _ in range(50)]}, "descartada"),
    ("pintura_codigo_inadecuado", {"nombre": "SUM. PINTURA ACRILICA BLANCA Y MICROESFERAS DVRT",
        "items": [item("86131502", "Sacos (20 kg.)", "Pintura")]}, "descartada"),
    ("pintura_sin_items", {"nombre": "SUM. PINTURA ACRILICA BLANCA Y MICROESFERAS DVRT"}, "descartada"),
    ("curso_wafa", {"nombre": "SERVICIO DE CURSOS DE CAPACITACIÓN WAFA NO DEJE RAS",
        "items": [item("86101702", "CURSOS WAFA-NO DEJE RASTRO Y RESCATE EN AGUAS BLANCAS")]}, "descartada"),
    ("publicidad", {"nombre": "Campaña comunicacional y plan de medios",
        "items": [item("80141607", "Promoción de destinos turísticos de Ñuble")]}, "descartada"),
    ("curso_con_salon", {"nombre": "Cursos de capacitación WAFA",
        "items": [item("86101702", "Curso WAFA"), item("90111603", "Arriendo de salón en Santiago")]}, None),
    ("campana_con_catering", {"nombre": "Campaña comunicacional y plan de medios",
        "items": [item("80141607", "Promoción turística"), item("90101603", "Servicio de catering en Santiago")]}, None),
    ("salon_en_item_sin_descripcion_general", {"nombre": None, "descripcion": None,
        "items": [item("90111603", "Arriendo de salón en Santiago")]}, "preseleccionada"),
    ("alojamiento_codigo_incorrecto", {"nombre": "Contrato de servicios",
        "items": [item("43211503", "Alojamiento en Santiago")]}, None),
    ("coffee_codigo_incorrecto", {"nombre": "Contrato de servicios",
        "items": [item("43211503", "Coffee break para una jornada en Santiago")]}, None),
    ("capacitacion_con_almuerzo", {"nombre": "Contrato de servicios",
        "items": [item("43211503", "Capacitación presencial con almuerzo")]}, None),
    ("equipo_destino_no_es_arriendo", {"nombre": "Compra de hardware para sala de reuniones",
        "items": [item("43201803", "SSD para sala de reuniones")]}, "descartada"),
    ("negacion_no_crea_oportunidad", {"nombre": "Compra de hardware. No incluye alojamiento.",
        "items": [item("43201803", "SSD")]}, "descartada"),
    ("alimentacion_enteral", {"nombre": "Insumos clínicos",
        "items": [item("42231505", "Adaptador", "Equipos de alimentación enteral")]}, "descartada"),
    ("linea_realmente_desconocida", {"nombre": "Suministros",
        "items": [item("43201803", "SSD"), item("99999999", "Por definir")]}, "revision_manual"),
    ("sin_datos_de_objeto", {"nombre": None, "descripcion": None}, "revision_manual"),
    ("alojamiento_sin_lugar", {"nombre": "Servicio de alojamiento"}, "revision_manual"),
    ("junji_sin_lugar", {"nombre": "CAPACITACIÓN ALIMENTACIÓN ALOJAMIENTO Y TRASLADO",
        "nombre_organismo": "JUNJI"}, "revision_manual"),
    ("alimentacion_no_se_ubica_por_comprador", {"nombre": "SERVICIOS DE ALIMENTACIÓN PARA ACCIONES DPTO EDUC",
        "nombre_organismo": "SECRETARIA REGIONAL MINISTERIAL DE EDUCACION VI REGION"}, "revision_manual"),
    ("casa_acogida_sin_lugar", {"nombre": "CASA DE ACOGIDA PROGRAMA MAPUCHE HOSPITAL VICTORIA",
        "items": [item("93141504", "Servicios de alojamiento y traslado de usuarios del programa de salud mapuche")]}, "revision_manual"),
    ("casa_acogida_santiago", {"nombre": "Alojamiento de personas",
        "items": [item("93141504", "Servicio de alojamiento en Santiago para pacientes")]}, "preseleccionada"),
    ("hotel_30222507_no_es_material_construccion", {"nombre": "Contratación",
        "items": [item("30222507", "", "Hotel")]}, "revision_manual"),
    ("salon_fuera_rm", {"nombre": "Arriendo de salón en Valparaíso"}, "descartada"),
    ("lectura_realmente_parcial", {"nombre": "Compra de hardware", "descripcion": "x" * 31000,
        "items": [item("43201803", "SSD")]}, "revision_manual"),
    ("salon_con_equipo", {"nombre": "Contratación",
        "items": [item("43201803", "SSD"), item("90111603", "Arriendo de salón en Santiago")]}, "preseleccionada"),
]


class PruebasObjetoHotel(unittest.TestCase):
    pass


def crear_prueba(cambios, esperado):
    def prueba(self):
        datos = deepcopy({
            "codigo_externo": "PRUEBA-1-LE26", "estado": "Publicada", "codigo_estado": 5,
            "fecha_cierre": "2099-01-01T12:00:00", "items": [], **cambios,
        })
        original = deepcopy(datos)
        r = evaluar_preseleccion(datos, ahora=datetime(2026, 10, 28, 12, tzinfo=CHILE))
        if esperado is None:
            self.assertNotEqual(r["clasificacion"], "descartada", r)
        else:
            self.assertEqual(r["clasificacion"], esperado, r)
        self.assertEqual(datos, original)
    return prueba


for nombre, cambios, esperado in CASOS:
    setattr(PruebasObjetoHotel, "test_" + nombre, crear_prueba(cambios, esperado))

if __name__ == "__main__":
    unittest.main(verbosity=2)
