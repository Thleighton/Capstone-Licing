"""Pruebas del perfil de salones. Sin base, red ni pytest."""
from copy import deepcopy
from datetime import datetime
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.services.preseleccion import CHILE, evaluar_preseleccion, cargar_catalogo


def item(codigo, descripcion, nombre="Producto"):
    return {"codigo_producto": codigo, "descripcion": descripcion, "nombre_producto": nombre}


CLINICA = (
    "El Hospital requiere contratar un recinto para realizar procedimientos endovasculares "
    "diagnósticos y terapéuticos guiados por fluoroscopía que incluya la posibilidad de "
    "hospitalizar en camas de cuidados críticos UTI y UCI, para pacientes clasificados "
    "como urgencias y programables, debido al recambio del angiógrafo."
)
ACOGIDA = "La presente licitación tiene como objetivo suscribir convenio para el alojamiento y traslado de usuarios pertenecientes al programa de salud mapuche del Hospital de Victoria."

CASOS = [
    ("clinica_descripcion_real", {"nombre": "PROCEDIMIENTOS ENDOVASCULARES DIAGNOSTICOS", "descripcion": CLINICA}, "descartada"),
    ("clinica_con_items", {"nombre": "PROCEDIMIENTOS ENDOVASCULARES DIAGNOSTICOS", "descripcion": CLINICA,
        "items": [item("42142801", "Procedimientos endovasculares diagnósticos")]}, "descartada"),
    ("clinica_categoria_generica", {"nombre": "Procedimientos endovasculares", "descripcion": CLINICA,
        "items": [item("99999999", "Prestaciones clínicas", "Salas de reuniones")]}, "descartada"),
    ("clinica_en_santiago", {"nombre": "Procedimientos endovasculares", "descripcion": CLINICA + " En Santiago."}, "descartada"),
    ("acogida_descripcion_real", {"nombre": "CASA DE ACOGIDA PROGRAMA MAPUCHE HOSPITAL VICTORIA", "descripcion": ACOGIDA,
        "items": [item("93141504", ACOGIDA, "Servicios de acogida familiar u orfanatos")]}, "descartada"),
    ("acogida_en_rm", {"nombre": "Casa de acogida", "descripcion": ACOGIDA + " El alojamiento se prestará en Santiago."}, "descartada"),
    ("alojamiento_solo", {"nombre": "Servicio de alojamiento en Santiago"}, "descartada"),
    ("habitacion_sola", {"nombre": "Servicio", "items": [item("90111801", "Habitación para dos personas")]}, "descartada"),
    ("hoteles_categoria", {"nombre": "Servicio", "items": [item("90111501", "", "Hoteles")]}, "descartada"),
    ("alojamiento_para_seminario", {"nombre": "Alojamiento para participantes de seminario en Santiago"}, "descartada"),
    ("coffee_solo", {"nombre": "Coffee break en Santiago"}, "revision_manual"),
    ("catering_para_actividades_sin_sede", {"nombre": "Servicio de catering y cóctel para actividades deportivas y ceremonias en Santiago"}, "revision_manual"),
    ("catering_comprador_rm_sin_salon", {"nombre": "Servicio de catering para ceremonias", "region_comprador": "Región Metropolitana de Santiago"}, "revision_manual"),
    ("banqueteria_sola", {"nombre": "Servicio de banquetería en Santiago"}, "revision_manual"),
    ("alimentacion_sola", {"nombre": "Servicios de alimentación para acciones del departamento de Educación"}, "revision_manual"),
    ("almuerzo_solo", {"nombre": "Servicio de almuerzo para 50 personas en Santiago"}, "revision_manual"),
    ("coffee_oficinas", {"nombre": "Coffee break para una reunión", "descripcion": "El servicio debe entregarse en las oficinas del organismo en Santiago."}, "descartada"),
    ("coffee_colegio", {"nombre": "Coffee break para jornada", "descripcion": "El evento se realizará en el colegio de la institución."}, "descartada"),
    ("coffee_salon_municipal", {"nombre": "Coffee break para evento", "descripcion": "La jornada se realizará en el salón municipal de Santiago."}, "descartada"),
    ("salon_municipal_fijo", {"nombre": "Servicios para evento en salón municipal en Santiago"}, "descartada"),
    ("salon_evento", {"nombre": "Arriendo de salón para seminario en Santiago"}, "preseleccionada"),
    ("salon_sin_comida", {"nombre": "Arriendo de salón en Santiago"}, "preseleccionada"),
    ("salon_con_coffee", {"nombre": "Arriendo de salón con coffee break en Santiago"}, "preseleccionada"),
    ("salon_con_banqueteria", {"nombre": "Arriendo de salón con banquetería en Santiago"}, "preseleccionada"),
    ("salon_con_almuerzo", {"nombre": "Arriendo de salón con almuerzo en Santiago"}, "preseleccionada"),
    ("salon_con_alojamiento", {"nombre": "Arriendo de salón para seminario en Santiago con alojamiento para expositores"}, "preseleccionada"),
    ("coffee_en_salon_del_hotel", {"nombre": "Coffee break para reunión en salón del Hotel Plaza San Francisco en Santiago"}, "preseleccionada"),
    ("banqueteria_en_salon_del_hotel", {"nombre": "Servicio de banquetería en el salón del Hotel Plaza San Francisco en Santiago"}, "preseleccionada"),
    ("salon_comprador_rm_sede_por_confirmar", {"nombre": "Contratación de salón para capacitación de funcionarios", "region_comprador": "Región Metropolitana de Santiago"}, "preseleccionada"),
    ("alimentacion_para_provincias_ohiggins", {"nombre": "Servicio de catering para actividades", "descripcion": "El servicio se requiere en las tres provincias de la Región de O’Higgins."}, "descartada"),
    ("adq_material_aseo", {"nombre": "CE ADQUISICIÓN DE MATERIAL DE ASEO", "descripcion": "La licitación consiste en adquisición de material de aseo para jardines infantiles."}, "descartada"),
    ("hardware_cable_alimentacion", {"nombre": "ADQ. INSUMOS Y HARDWARE DEPARTAMENTO TIC", "items": [item("26121609", "Cable de redes", "Cable alimentación IEC C5")]}, "descartada"),
    ("abarrotes_cocktail_fruta", {"nombre": "ABARROTES Y OTROS 2027", "items": [item("50192100", "Frutas procesadas", "Cocktail de fruta o macedonia en galón")]}, "descartada"),
    ("aseo_servilleta_coctel", {"nombre": "Adquisición de material de aseo", "items": [item("47131805", "Limpiadores de uso general", "Servilleta cóctel") ]}, "descartada"),
    ("congreso_medico", {"nombre": "Arriendo de salón para congreso médico en Santiago"}, "preseleccionada"),
    ("congreso_endovascular", {"nombre": "Arriendo de salón para congreso sobre procedimientos endovasculares en Santiago"}, "preseleccionada"),
    ("capacitacion_fluoroscopia", {"nombre": "Arriendo de salón para capacitación sobre fluoroscopía en Santiago"}, "preseleccionada"),
    ("comprador_hospital", {"nombre": "Arriendo de salón para jornada en Santiago", "nombre_organismo": "Hospital de Victoria"}, "preseleccionada"),
    ("otec_pide_salon", {"nombre": "OTEC solicita arriendo de salón en Santiago"}, "preseleccionada"),
    ("recinto_evento", {"nombre": "Arriendo de recinto para seminario en Santiago"}, "preseleccionada"),
    ("espacio_evento", {"nombre": "Arriendo de espacio físico para jornada en Santiago"}, "preseleccionada"),
    ("recinto_ambiguo", {"nombre": "Arriendo de recinto en Santiago"}, "revision_manual"),
    ("actividad_sin_espacio", {"nombre": "Jornada institucional anual"}, "revision_manual"),
    ("sin_info", {"nombre": "Contratación anual 2026"}, "revision_manual"),
    ("salon_sin_ciudad", {"nombre": "Arriendo de salón para seminario"}, "revision_manual"),
    ("recinto_clinico", {"nombre": "Arriendo de recinto para procedimientos clínicos en Santiago"}, "descartada"),
    ("sala_operaciones", {"nombre": "Arriendo de sala de operaciones en Santiago"}, "descartada"),
    ("salon_belleza", {"nombre": "Arriendo de salón de belleza en Santiago"}, "descartada"),
    ("sillas_para_salon", {"nombre": "Compra de sillas para salón en Santiago"}, "descartada"),
    ("mobiliario_para_salon", {"nombre": "Adquisición de mobiliario para un salón en Santiago"}, "descartada"),
    ("ssd_para_sala", {"nombre": "Compra de hardware para sala de reuniones", "items": [item("43201803", "SSD 240 GB")]}, "descartada"),
    ("discos_sin_descripcion", {"nombre": "Compra de equipos", "descripcion": None, "items": [item("43201803", "SSD 240 GB")]}, "descartada"),
    ("sin_nombre_con_salon_item", {"nombre": None, "descripcion": None, "items": [item("90111603", "Arriendo de salón para jornada en Santiago")]}, "preseleccionada"),
    ("salon_mal_codigo", {"nombre": "Servicio", "items": [item("43211503", "Arriendo de salón para seminario en Santiago")]}, "preseleccionada"),
    ("salon_coffee_dos_items", {"nombre": "Salón para seminario en Santiago", "items": [item("90111603", "Arriendo de salón para seminario en Santiago"), item("90101603", "Coffee break para asistentes")]}, "preseleccionada"),
    ("ciudad_de_otro_item", {"nombre": "Servicio para jornada", "items": [item("90111603", "Arriendo de salón para jornada, ciudad por coordinar"), item("90101603", "Coffee break en Santiago")]}, "revision_manual"),
    ("salon_fuera_rm", {"nombre": "Arriendo de salón para evento en Valparaíso"}, "descartada"),
    ("comprador_no_ubica_salon", {"nombre": "Arriendo de salón para evento", "region_comprador": "Metropolitana", "direccion_entrega": "Santiago"}, "preseleccionada"),
    ("direccion_administrativa", {"nombre": "Arriendo de salón para seminario en Santiago", "descripcion": "El domicilio del comprador está en las oficinas de la institución."}, "preseleccionada"),
    ("proveedor_docencia", {"nombre": "Arriendo de salón en Santiago", "descripcion": "El proveedor deberá impartir los cursos y certificar la capacitación."}, "revision_manual"),
    ("clinica_y_evento_separado", {"nombre": "Contratación de servicios", "items": [item("42142801", CLINICA), item("90111603", "Arriendo de salón para congreso médico en Santiago")]}, "preseleccionada"),
    ("negacion_del_salon", {"nombre": "Coffee break en Santiago. No se requiere salón."}, "descartada"),
    ("lectura_incompleta", {"nombre": "Arriendo de salón en Santiago", "descripcion": "x"*31000}, "revision_manual"),
    ("vigencia_prioritaria", {"nombre": "Arriendo de salón para evento en Santiago", "fecha_cierre": "2020-01-01T12:00:00"}, "descartada"),
    ("no_ubicar_por_alojamiento", {"nombre": "Arriendo de salón para evento", "descripcion": "Servicio de alojamiento en Santiago."}, "revision_manual"),
    ("no_ubicar_por_coffee", {"nombre": "Arriendo de salón para evento", "descripcion": "Servicio de coffee break en Santiago."}, "revision_manual"),
    ("ubicacion_del_evento", {"nombre": "Arriendo de salón", "descripcion": "La jornada se realizará en Santiago."}, "preseleccionada"),

    ("salon_otro_hotel_fijado", {"nombre": "Servicios para evento en salón del Hotel Ejemplo en Santiago"}, "descartada"),
    ("otro_hotel_en_descripcion", {"nombre": "Arriendo de salón para evento en Santiago", "descripcion": "El evento se realizará en el Hotel Ejemplo."}, "descartada"),
    ("hotel_propuesto_por_proveedor", {"nombre": "Arriendo de salón en un hotel para seminario en Santiago"}, "preseleccionada"),

    ("compra_agil_coffee_solo", {"codigo_externo": "100-1-COT26", "codigo_estado": None, "estado": "publicada", "nombre": "Coffee break para jornada en Santiago"}, "revision_manual"),
    ("compra_agil_salon_coffee", {"codigo_externo": "100-1-COT26", "codigo_estado": None, "estado": "publicada", "nombre": "Arriendo de salón con coffee break en Santiago"}, "preseleccionada"),

]


class PruebasPerfilSalones(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if (cargar_catalogo().get("perfil_comercial") or {}).get("id") != "salones_eventos_en_hotel":
            raise AssertionError("El perfil de salones no está activado en el catálogo.")


def crear_prueba(cambios, esperado):
    def prueba(self):
        datos = deepcopy({"codigo_externo": "PRUEBA-1-LE26", "estado": "Publicada", "codigo_estado": 5,
                          "fecha_cierre": "2099-01-01T12:00:00", "items": [], **cambios})
        original = deepcopy(datos)
        r = evaluar_preseleccion(datos, ahora=datetime(2026, 10, 28, 12, tzinfo=CHILE))
        self.assertEqual(r["clasificacion"], esperado, r)
        self.assertEqual(datos, original)
        self.assertEqual(list(r["criterios"]), ["vigencia", "ubicacion", "pertinencia"])
    return prueba


for nombre, cambios, esperado in CASOS:
    setattr(PruebasPerfilSalones, "test_"+nombre, crear_prueba(cambios, esperado))


def _probar_motivo_sede_pendiente(self):
    r = evaluar_preseleccion(
        {"codigo_externo": "PRUEBA-1-LE26", "estado": "Publicada", "codigo_estado": 5,
         "fecha_cierre": "2099-01-01T12:00:00", "nombre": "Contratación de salón para capacitación de funcionarios",
         "region_comprador": "Región Metropolitana de Santiago", "items": []},
        ahora=datetime(2026, 10, 28, 12, tzinfo=CHILE),
    )
    self.assertIn("no confirma el lugar de ejecución", r["motivo"])
    self.assertTrue(r["criterios"]["ubicacion"]["comprador_en_rm"])
    self.assertFalse(r["criterios"]["ubicacion"]["sede_confirmada"])


setattr(PruebasPerfilSalones, "test_salon_rm_no_afirma_sede", _probar_motivo_sede_pendiente)

if __name__ == "__main__":
    unittest.main(verbosity=2)
