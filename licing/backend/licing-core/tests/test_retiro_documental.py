from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text
from sqlalchemy.exc import DBAPIError

from app.adopcion import REVISION_ACTUAL, registrar_esquema, verificar_esquema
from app.config import CORE_DIR

DOCUMENTALES = {"licitacion_documento", "licitacion_extraccion", "documento_fragmento",
                "licitacion_prestacion", "licitacion_periodo_servicio", "licitacion_requisito"}


def configuracion(connection):
    config = Config(str(CORE_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(CORE_DIR / "alembic"))
    config.attributes["connection"] = connection
    return config


def test_esquema_operativo_sin_tablas_documentales(integration_db):
    c = integration_db.connection()
    tablas = set(inspect(c).get_table_names(schema="public"))
    assert DOCUMENTALES.isdisjoint(tablas)
    assert {"licitacion", "licitacion_item", "raw_mercado_publico", "ejecucion_ingesta", "alembic_version"} <= tablas
    assert verificar_esquema(c) == []
    funcion = c.execute(text("SELECT prosrc FROM pg_proc WHERE oid="
        "'public.purgar_licitaciones_no_disponibles(text,boolean)'::regprocedure")).scalar_one()
    assert all(nombre not in funcion for nombre in DOCUMENTALES)


def test_rutas_documentales_retiradas(client_usuario):
    assert client_usuario.get("/api/licitaciones/1/documentos").status_code == 404
    assert client_usuario.get("/api/licitaciones/1/extracciones/1").status_code == 404
    assert client_usuario.post("/api/licitaciones/1/extracciones", json={}).status_code == 404


def test_migracion_se_niega_a_borrar_datos_y_conserva_licitacion(integration_db):
    c = integration_db.connection()
    config = configuracion(c)
    command.downgrade(config, "c08ccd7a1466")
    assert DOCUMENTALES <= set(inspect(c).get_table_names(schema="public"))
    codigo = "RETIRO-"+uuid4().hex[:8]
    raw_id = c.execute(text("""INSERT INTO raw_mercado_publico
        (fuente,tipo_consulta,codigo_externo,respuesta,http_status,consultado_en)
        VALUES ('licitaciones','detalle_codigo',:codigo,'{}',200,now()) RETURNING id"""), {"codigo":codigo}).scalar_one()
    lic_id = c.execute(text("INSERT INTO licitacion (codigo_externo,raw_id) VALUES (:codigo,:raw) RETURNING id"),
                       {"codigo":codigo,"raw":raw_id}).scalar_one()
    c.execute(text("""INSERT INTO licitacion_documento (licitacion_id,nombre,tipo,url_origen,version)
        VALUES (:lic,'Documento de prueba','bases','https://example.test/bases.pdf','1')"""), {"lic":lic_id})
    with pytest.raises(DBAPIError, match="contiene datos"):
        with c.begin_nested():
            command.upgrade(config, "head")
    assert c.execute(text("SELECT count(*) FROM licitacion_documento")).scalar_one() == 1
    assert c.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == "c08ccd7a1466"
    c.execute(text("DELETE FROM licitacion_documento WHERE licitacion_id=:id"), {"id":lic_id})
    command.upgrade(config, "head")
    assert DOCUMENTALES.isdisjoint(inspect(c).get_table_names(schema="public"))
    assert c.execute(text("SELECT id FROM licitacion WHERE codigo_externo=:codigo"), {"codigo":codigo}).scalar_one() == lic_id
    assert c.execute(text("SELECT raw_id FROM licitacion WHERE id=:id"), {"id":lic_id}).scalar_one() == raw_id


def test_adopcion_legacy_no_reintroduce_documentales(integration_db):
    c = integration_db.connection()
    command.downgrade(configuracion(c), "83c9bcf6857f")
    c.execute(text("DROP TABLE public.alembic_version"))
    registrar_esquema(c)
    assert c.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == REVISION_ACTUAL
    assert DOCUMENTALES.isdisjoint(inspect(c).get_table_names(schema="public"))
    assert verificar_esquema(c) == []
