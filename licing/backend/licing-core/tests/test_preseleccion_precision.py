"""Regresiones de falsos positivos observados el 15 de noviembre de 2026."""
from datetime import datetime
import json

import pytest

from app.services.preseleccion import CHILE, evaluar_preseleccion
from app.services.compra_agil_preseleccion import evaluar as evaluar_compra_agil

CASOS_AJENOS = json.loads(r'''[
  {
    "codigo_externo": "1075956-182-COT26",
    "modalidad": "compra_agil",
    "nombre": "ADQUISICIÓN DE LETRERO SALA DE REUNIONES- SEGÚN REQUERIMIENTOS TECNICOS ADJUNTOS - PRESUPUESTO DISPONIBLE $ 200.000-",
    "descripcion": "ADQUISICIÓN DE LETRERO SALA DE REUNIONES- SEGÚN REQUERIMIENTOS TECNICOS ADJUNTOS - PRESUPUESTO DISPONIBLE $ 200.000-SERÁ ADJUDICADO EL PROVEEDOR QUE CUMPLA CON LA TOTALIDAD DE REQUISITOS Y SU OFERTA SE ENMARQUE DENTRO DEL PRESUPUESTO DISPONIBLE.",
    "items": [
      {
        "codigo_producto": "82101501",
        "nombre_producto": "Letreros publicitarios",
        "descripcion": "ADQUISICIÓN DE LETRERO SALA DE REUNIONES- SEGÚN REQUERIMIENTOS TECNICOS ADJUNTOS - PRESUPUESTO DISPONIBLE $ 200.000-SERÁ ADJUDICADO EL PROVEEDOR QUE CUMPLA CON LA TOTALIDAD DE REQUISITOS Y SU OFERTA SE ENMARQUE DENTRO DEL PRESUPUESTO DISPONIBLE."
      }
    ]
  },
  {
    "codigo_externo": "1221019-105-COT26",
    "modalidad": "compra_agil",
    "nombre": "Adquisición Insumos Médicos para las Distintas Dependencias de la Corporación Municipal del Deporte de Vitacura.",
    "descripcion": "La Corporación Municipal del Deporte de Vitacura es una entidad encargada de promover la actividad física, el deporte y la vida sana en la comuna, administrando recintos de alta afluencia de público (como centros deportivos, piscinas municipales y espacios al aire libre) y ejecutando diversos programas y eventos deportivos de carácter recreativo y competitivo (tales como talleres formativos y las Olimpiadas Escolares).",
    "items": [
      {
        "codigo_producto": "85121902",
        "nombre_producto": "Farmacias",
        "descripcion": "Adquisición Insumos Médicos para las Distintas Dependencias de la Corporación, de acuerdo a Términos de Referencia adjuntos a la presenta propuesta."
      }
    ]
  },
  {
    "codigo_externo": "1238119-26-COT26",
    "modalidad": "compra_agil",
    "nombre": "GUIRNALDA DE LUCES PARA EL “PASEO DE LAS ARTES” ALDEA DEL ENCUENTRO",
    "descripcion": "La Corporación Aldea del Encuentro requiere comprar 21  guirnaldas de luces led, de  20 metros, con sus ampolletas incluidas, luz fría y de material resistentes, ya  que se instalaran  en el exterior del pasillo principal del Paseo de las Artes y en los pasillos de las Huertas Urbanas, permitiendo mejorar la luminosidad de los espacios, dándole mayor visibilidad.",
    "items": [
      {
        "codigo_producto": "39111809",
        "nombre_producto": "Filtros acondicionadores de luz",
        "descripcion": "La Corporación Aldea del Encuentro requiere comprar 21  guirnaldas de luces led, de  20 metros, con sus ampolletas incluidas, luz fría y de material resistentes, ya  que se instalaran  en el exterior del pasillo principal del Paseo de las Artes y en los pasillos de las Huertas Urbanas, permitiendo mejorar la luminosidad de los espacios, dándole mayor visibilidad. SE REQUIERE GUIARSE POR LOS TÉRMINOS DE REFERENCIAS QUE VAN EN EL ADJUNTO. DEBE INCLUIR DESPACHO."
      }
    ]
  },
  {
    "codigo_externo": "165-70-COT26",
    "modalidad": "compra_agil",
    "nombre": "Adquisición de escaño para jardín institucional",
    "descripcion": "El Consejo Nacional de Educación requiere adquirir un escaño para habilitar espacios de descanso y encuentro en las áreas exteriores de sus dependencias, procurando contar con mobiliario resistente, funcional y adecuado para su uso en jardines y espacios al aire libre.",
    "items": [
      {
        "codigo_producto": "23231901",
        "nombre_producto": "Bancada base",
        "descripcion": "Escaño o banca para jardín, terraza o espacios exteriores."
      }
    ]
  },
  {
    "codigo_externo": "2407-665-COT26",
    "modalidad": "compra_agil",
    "nombre": "ACTIVIDAD COMUNITARIA RECUPERACIÓN DE ESPACIOS PUBLICOS - SP 618 - IDDOC 279630",
    "descripcion": "Con el propósito de dar a conocer a la comunidad las mejoras realizadas, promover el uso y cuidado del espacio recuperado y fortalecer el encuentro entre vecinas, vecinos y comerciantes del sector, se requiere contratar servicios de encarpado, pantallas y una presentación artística para la realización de una jornada comunitaria, en el espacio Ofelia Moreno. Proveedores interesados deben adjuntar cotización con detalle de servicio ofertado.",
    "items": [
      {
        "codigo_producto": "30221001",
        "nombre_producto": "Carpas",
        "descripcion": "Encarpado, según especificaciones adjuntas."
      },
      {
        "codigo_producto": "43211903",
        "nombre_producto": "Monitores de pantalla táctil",
        "descripcion": "Totems led, según especificaciones adjuntas."
      },
      {
        "codigo_producto": "82151704",
        "nombre_producto": "Servicios de músicos, banda u orquestas",
        "descripcion": "Show artístico, según especificaciones adjuntas."
      }
    ]
  },
  {
    "codigo_externo": "2735-1433-COT26",
    "modalidad": "compra_agil",
    "nombre": "SERVICIO DE IMPLEMENTACIÓN DE \"JORNADA DE ACERCAMIENTO A CULTURAS JUVENILES\".",
    "descripcion": "EL SERVICIO DE BIENESTAR DE LA MUNICIPALIDAD DE LO BARNECHEA REQUIERE LA “ADQUISICIÓN DE SERVICIO DE IMPLEMENTACIÓN DE \"JORNADA DE ACERCAMIENTO A CULTURAS JUVENILES\". ESTA JORNADA LÚDICA Y EXPERIENCIAL DE CULTURA POP JAPONESA Y GAMER DIRIGIDA A LAS USUARIOS, JÓVENES Y FAMILIAS DE LA COMUNA, BUSCA PROMOVER ESPACIOS DE PARTICIPACIÓN JUVENIL Y EXPRESIÓN A TRAVÉS DE PRESENTACIONES DE BAILE/CANTO, DINÁMICAS LÚDICAS, JUEGOS DE MESA, VIDEOJUEGOS, CULTURA POP Y COSPLAY. DETALLE ADJUNTO",
    "items": [
      {
        "codigo_producto": "93141702",
        "nombre_producto": "Servicios de promoción cultural",
        "descripcion": "SERVICIO DE IMPLEMENTACIÓN DE \"JORNADA DE ACERCAMIENTO A CULTURAS JUVENILES\". OFERTAS DEBEN CUMPLIR CON ESPECIFICACIONES Y CONDICIONES EN ARCHIVO ADJUNTO."
      }
    ]
  },
  {
    "codigo_externo": "2462-47-LE26",
    "modalidad": "licitacion",
    "nombre": "BUS PARA ACTIVIDAD “VIAJE MÁGICO NAVIDAD 2026”",
    "descripcion": "Se requiere contratar un servicio de producción y transporte para la realización de la actividad “Viaje Mágico Navidad 2026”, en el marco del Programa Navidad Comunal del Departamento de Desarrollo Social. Esta iniciativa tiene por objetivo celebrar la Navidad mediante un recorrido por distintos sectores de la comuna de Providencia, ofreciendo un espectáculo callejero lleno de música, alegría y entretención, que permita a niños, niñas y sus familias disfrutar de una experiencia navideña, promoviendo la participación comunitaria, la integración familiar y el fortalecimiento de los espacios de encuentro y convivencia entre los vecinos.",
    "items": [
      {
        "codigo_producto": "78111803",
        "nombre_producto": "Servicios de autobuses contratados",
        "descripcion": "Servicio de producción y transporte para la realización de la actividad “Viaje Mágico Navidad 2026”, en el marco del Programa Navidad Comunal, según Bases."
      }
    ]
  },
  {
    "codigo_externo": "2673-60-LE26",
    "modalidad": "licitacion",
    "nombre": "Servicio de Arriendo Navidad 2026",
    "descripcion": "La Ilustre Municipalidad de Melipilla, requiere la contratación del servicio de arriendo de árbol de navidad, ornamentación y carro alegórico, año 2026, en el marco de las actividades que se desarrollarán en dicho espacio en el periodo de diciembre de 2026. Además, de un carro alegórico que recorrerá la comuna, en zona céntrica y localidades entre el 11 y 22 de diciembre de 2026; se detalla la solicitud según las indicaciones de las especificaciones técnicas.",
    "items": [
      {
        "codigo_producto": "80141607",
        "nombre_producto": "Producción de eventos",
        "descripcion": "La Ilustre Municipalidad de Melipilla, requiere la contratación del servicio de arriendo de árbol de navidad, ornamentación y carro alegórico, año 2026, en el marco de las actividades que se desarrollarán en dicho espacio en el periodo de diciembre de 202"
      }
    ]
  },
  {
    "codigo_externo": "2735-166-LE26",
    "modalidad": "licitacion",
    "nombre": "ADQUISICIÓN DE TOLDOS MESAS Y SILLAS",
    "descripcion": "Destinados al fortalecimiento y habilitación de espacios de comercialización para emprendedores, feriantes y quioscos de la comuna de Lo Barnechea, contribuyendo directamente al desarrollo económico local y al mejoramiento de las condiciones de funcionamiento de las ferias libres comunales, en beneficio de los vecinos y vecinas de la comuna.",
    "items": [
      {
        "codigo_producto": "30151901",
        "nombre_producto": "Toldos",
        "descripcion": "Adquisición de toldos, mesas y sillas."
      }
    ]
  },
  {
    "codigo_externo": "2982-62-LE26",
    "modalidad": "licitacion",
    "nombre": "SERVICIO DE CONVENIO SUMINISTRO DE COLCHONES",
    "descripcion": "Los Agentes Policiales Estudiantes se encuentran en régimen de internado en el Centro de Capacitación Profesional, por lo tanto existe la necesidad de brindar a dichos alumnos el espacio para que puedan pernoctar y descansar.",
    "items": [
      {
        "codigo_producto": "56101508",
        "nombre_producto": "Colchones o sets de cama",
        "descripcion": "COLCHONES ERGONOMICOS SEGUN ESPECIFICACIONES TECNICAS ADJUNTAS EN BASES DE LICITACION \r\n250 AÑO 2026\r\n250 AÑO 2027"
      }
    ]
  },
  {
    "codigo_externo": "3310-41-LP26",
    "modalidad": "licitacion",
    "nombre": "Pantallas LED indoor outdoor",
    "descripcion": "La Feria Internacional del Aire y del Espacio FIDAE requiere la adquisición, instalación, configuración, capacitación, puesta en marcha y garantía de una pantalla LED Full Color para uso interior y exterior de 15 x 8 metros, destinada a la difusión de contenidos institucionales, audiovisuales, promocionales y operacionales durante el desarrollo de la Feria Internacional del Aire y del Espacio y demás actividades organizadas por la Institución.",
    "items": [
      {
        "codigo_producto": "43211902",
        "nombre_producto": "Monitores o pantallas de visualización en cristal líquido (LCD)",
        "descripcion": "Pantalla led indoor outdoor 15x8 m"
      },
      {
        "codigo_producto": "43211902",
        "nombre_producto": "Monitores o pantallas de visualización en cristal líquido (LCD)",
        "descripcion": "Estructura de soporte"
      },
      {
        "codigo_producto": "43211902",
        "nombre_producto": "Monitores o pantallas de visualización en cristal líquido (LCD)",
        "descripcion": "Instalación implementación y capacitación"
      }
    ]
  },
  {
    "codigo_externo": "4650-22-L126",
    "modalidad": "licitacion",
    "nombre": "SERVICIOS DE PRODUCCIÓN PARA ACTIVIDAD “RUTA POR ESCUELAS PATRIMONIALES DE LA REGIÓN DE COQUIMBO”.",
    "descripcion": "La Secretaría Técnica del Consejo de Monumentos Nacionales en el marco del cumplimiento del programa de mejoramiento de gestión, realiza diferentes actividades enfocadas a niñas y niños, el cual busca difundir, educar y concientizar sobre el cuidado de los Monumentos Nacionales.\n\nPor lo anterior esta licitación busca realizar actividades de difusión sobre los monumentos nacionales a través de visitas a escuelas y a espacios patrimoniales por medio de un mapa grande que se puede desplegar en un e",
    "items": [
      {
        "codigo_producto": "80141607",
        "nombre_producto": "Producción de eventos",
        "descripcion": "SERVICIOS DE PRODUCCIÓN PARA ACTIVIDAD RUTA POR ESCUELAS PATRIMONIALES DE LA REGIÓN DE COQUIMBO."
      }
    ]
  },
  {
    "codigo_externo": "5251-106-LE26",
    "modalidad": "licitacion",
    "nombre": "DOTACIÓN INSTALACIÓN DE GABINETE DE BIOSEGURIDAD",
    "descripcion": "El objetivo de la presente licitación es adquirir un gabinete de bioseguridad ya que se tiene la necesidad de disponer de un espacio de trabajo controlado y seguro para la manipulación de muestras y materiales biológicos en actividades de investigación y docencia.",
    "items": [
      {
        "codigo_producto": "41103504",
        "nombre_producto": "Armarios o depósitos de flujo laminar",
        "descripcion": "Gabinete de bioseguridad Clase II Tipo A2 (o equivalente técnico justificado)"
      }
    ]
  }
]''')


def evaluar(datos):
    entrada = {
        "estado": "Publicada", "codigo_estado": 5,
        "fecha_cierre": "2099-01-01T12:00:00-03:00",
        "region_comprador": "Región Metropolitana de Santiago", **datos,
    }
    motor = evaluar_preseleccion
    if entrada.get("modalidad") == "compra_agil":
        entrada.update(codigo_estado=None, codigo_region=13)
        motor = evaluar_compra_agil
    return motor(entrada, ahora=datetime(2026, 11, 15, 3, tzinfo=CHILE))


@pytest.mark.parametrize("datos", CASOS_AJENOS, ids=lambda d: d["codigo_externo"])
def test_objetos_reales_ajenos_no_se_convierten_en_salones(datos):
    resultado = evaluar(datos)
    assert resultado["clasificacion"] == "descartada", resultado
    assert resultado["criterios"]["pertinencia"]["resultado"] == "no_cumple"
    assert not resultado["criterios"]["pertinencia"]["coincidencias"]


@pytest.mark.parametrize("descripcion", [
    "Arriendo de espacio físico para jornada institucional en Santiago.",
    "Se requiere contar con un lugar que disponga de un espacio habilitado, "
    "con capacidad para 35 personas, para la realización de un taller y servicio de almuerzo.",
    "Se solicita un espacio para realizar un seminario para 80 participantes en Santiago.",
    "El proveedor deberá proporcionar un espacio para la jornada en Santiago.",
    "Contratación de sala para capacitación en Santiago.",
    "Arriendo de salón para seminario en Santiago.",
    "Servicio de coffee break para una jornada en Santiago.",
])
@pytest.mark.parametrize("modalidad", ["licitacion", "compra_agil"])
def test_solicitudes_concretas_se_conservan(descripcion, modalidad):
    resultado = evaluar({"codigo_externo": "100-1-COT26" if modalidad == "compra_agil" else "100-1-LE26",
                         "modalidad": modalidad, "descripcion": descripcion})
    assert resultado["clasificacion"] == "preseleccionada", resultado


def test_codigo_ajeno_no_oculta_arriendo_explicito_en_otra_linea():
    resultado = evaluar({
        "nombre": "Servicios para jornada",
        "descripcion": "Se fortalecen los espacios de encuentro de la comunidad.",
        "items": [
            {"codigo_producto": "78111803", "descripcion": "Bus para traslado de asistentes"},
            {"codigo_producto": "43211503", "descripcion": "Arriendo de salón para seminario en Santiago"},
        ],
    })
    assert resultado["clasificacion"] == "preseleccionada", resultado
    assert any(e["fuente"] == "items[1].descripcion"
               for e in resultado["criterios"]["pertinencia"]["coincidencias"])
