from copy import deepcopy
import unicodedata
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.models.licitacion import Licitacion
from app.models.raw import RawMercadoPublico
from app.reprocesar_ubicaciones import reprocesar_ubicaciones
from app.services.procesamiento import procesar_detalle_guardado
from app.services.ubicacion import COMUNAS_RM, MAX_EVIDENCIAS, extraer_ubicacion


def test_sede_del_comprador_no_es_lugar_del_servicio():
    d = {"Comprador": {"RegionUnidad": "Región Metropolitana", "ComunaUnidad": "Santiago"},
         "Descripcion": "Monitoreo del glaciar en la Región de Coquimbo"}
    resultado = extraer_ubicacion(d)
    assert resultado["regiones_candidatas"] == ["04"]
    assert resultado["estado"] == "por_revisar"
    assert extraer_ubicacion({"Comprador": d["Comprador"]})["estado"] == "no_informada"


@pytest.mark.parametrize("nombre", COMUNAS_RM)
def test_detecta_las_52_comunas_sin_exigir_tildes(nombre):
    sin_tildes = "".join(c for c in unicodedata.normalize("NFD", nombre) if not unicodedata.combining(c))
    resultado = extraer_ubicacion({"Descripcion": f"Se requiere un salón en {sin_tildes.upper()}."})
    assert resultado["comunas_candidatas"] == [nombre]
    assert resultado["regiones_candidatas"] == ["13"]


def test_mencion_de_region_no_inventa_comuna():
    resultado = extraer_ubicacion({"Descripcion": "Se necesita alojamiento en la Región Metropolitana de Santiago."})
    assert resultado["regiones_candidatas"] == ["13"]
    assert resultado["comunas_candidatas"] == []


def test_comunas_homonimas_fuera_de_rm_no_confunden_san_pedro():
    assert extraer_ubicacion({"Descripcion": "Salón en San Pedro de Atacama"})["regiones_candidatas"] == ["02"]
    assert extraer_ubicacion({"Descripcion": "Salón en San Pedro de la Paz"})["regiones_candidatas"] == ["08"]


def test_evidencia_tiene_posicion_y_texto_original_con_unicode():
    texto = "Estadía en " + unicodedata.normalize("NFD", "Peñalolén") + " y ÑUÑOA."
    resultado = extraer_ubicacion({"Items": {"Listado": [{"Correlativo": 6}, {"Correlativo": 6, "Descripcion": texto}]}})
    assert len(resultado["evidencias"]) == 2
    for evidencia in resultado["evidencias"]:
        assert evidencia["campo"] == "Items.Listado[1].Descripcion"
        assert texto[evidencia["inicio"]:evidencia["fin"]] == evidencia["texto"]
        assert evidencia["texto"] in evidencia["contexto"]


def test_multirregion_negacion_y_visita_siempre_requieren_revision():
    resultado = extraer_ubicacion({"Descripcion": "No en Santiago. El servicio comprende Atacama, Maule y Los Ríos.",
        "DireccionVisita": "Santiago", "DireccionEntrega": "Providencia"})
    assert resultado["regiones_candidatas"] == ["03", "07", "13", "14"]
    assert resultado["estado"] == "por_revisar"
    assert {e["uso"] for e in resultado["evidencias"]} == {"visita", "entrega", "mencion"}


def test_no_coincide_con_fragmentos_de_palabras():
    assert extraer_ubicacion({"Descripcion": "Maculatura y supermercados"})["estado"] == "no_informada"


def test_limita_evidencia_sin_ocultar_truncamiento_ni_regiones():
    resultado = extraer_ubicacion({"Descripcion": "Santiago. " * (MAX_EVIDENCIAS+1) + "Región de Coquimbo."})
    assert len(resultado["evidencias"]) == MAX_EVIDENCIAS
    assert resultado["truncada"] is True
    assert resultado["regiones_candidatas"] == ["04", "13"]
    assert resultado["estado"] == "por_revisar"


def test_extractor_no_modifica_raw_y_soporta_bloques_invalidos():
    original = {"Nombre": "Salón Santiago", "Comprador": {"RegionUnidad": "Maule"}, "Items": {"Listado": [None]}}
    copia = deepcopy(original)
    assert extraer_ubicacion(original)["regiones_candidatas"] == ["13"]
    assert original == copia


def crear(db, codigo, descripcion):
    raw = RawMercadoPublico(fuente="licitaciones", tipo_consulta="detalle_codigo", codigo_externo=codigo,
        respuesta={"CodigoExterno": codigo, "Descripcion": descripcion, "CodigoEstado": 5,
                   "Fechas": {"FechaCierre": "2099-01-01T12:00:00"}, "Items": {"Cantidad": 0, "Listado": []}}, http_status=200)
    db.add(raw)
    db.flush()
    resultado = procesar_detalle_guardado(db, raw)
    return raw.id, resultado["licitacion_id"]


def test_ingesta_guarda_origen_y_actualizacion_invalida_evidencia_anterior(integration_db):
    db = integration_db
    codigo = "GEO-" + uuid4().hex[:8]
    raw_id, lic_id = crear(db, codigo, "Alojamiento en Santiago")
    db.expire_all()
    assert db.get(Licitacion, lic_id).ubicacion_servicio["raw_id"] == raw_id
    nuevo_raw, mismo_id = crear(db, codigo, "Servicio en la Región de Coquimbo")
    db.expire_all()
    assert mismo_id == lic_id
    geo = db.get(Licitacion, lic_id).ubicacion_servicio
    assert geo["raw_id"] == nuevo_raw and geo["regiones_candidatas"] == ["04"]


def test_reprocesamiento_es_idempotente_y_no_finge_consulta_nueva(integration_db):
    db = integration_db
    codigo = "RE-GEO-" + uuid4().hex[:8]
    raw_id, lic_id = crear(db, codigo, "Salón en Providencia")
    db.expire_all()
    lic = db.get(Licitacion, lic_id)
    lic.ubicacion_servicio = None
    antes = db.get(RawMercadoPublico, raw_id).verificado_en
    normalizado = lic.normalizado_en
    db.commit()
    assert reprocesar_ubicaciones(db) == {"actualizadas": 1, "sin_cambios": 0}
    assert reprocesar_ubicaciones(db) == {"actualizadas": 0, "sin_cambios": 1}
    db.expire_all()
    assert db.get(RawMercadoPublico, raw_id).verificado_en == antes
    assert db.get(Licitacion, lic_id).normalizado_en == normalizado


def test_bd_rechaza_ubicacion_sin_evidencia_estructurada(integration_db):
    db = integration_db
    _, lic_id = crear(db, "INVALID-GEO-"+uuid4().hex[:8], "Sin lugar indicado")
    with pytest.raises(IntegrityError):
        with db.begin_nested():
            db.execute(text("UPDATE licitacion SET ubicacion_servicio='{}'::jsonb WHERE id=:id"), {"id":lic_id})


def test_api_detalle_no_expone_evidencia_de_otro_raw(integration_db, client_usuario):
    db = integration_db
    codigo = "API-GEO-" + uuid4().hex[:8]
    raw_id, lic_id = crear(db, codigo, "Servicio en Santiago")
    db.commit()
    respuesta = client_usuario.get(f"/api/licitaciones/{lic_id}")
    assert respuesta.status_code == 200
    assert respuesta.json()["licitacion"]["ubicacion_servicio"]["raw_id"] == raw_id
    otro = RawMercadoPublico(fuente="licitaciones", tipo_consulta="detalle_codigo", codigo_externo=codigo,
                            respuesta={"CodigoExterno":codigo}, http_status=200)
    db.add(otro)
    db.flush()
    db.get(Licitacion,lic_id).raw_id = otro.id
    db.commit()
    assert client_usuario.get(f"/api/licitaciones/{lic_id}").json()["licitacion"]["ubicacion_servicio"] is None
