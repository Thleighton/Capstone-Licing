from alembic import command
from alembic.config import Config
from sqlalchemy import text
from app.config import CORE_DIR


def test_migracion_preserva_ids_y_admite_escritor_anterior(integration_db):
    c = integration_db.connection()
    config = Config(str(CORE_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(CORE_DIR / "alembic"))
    config.attributes["connection"] = c
    command.downgrade(config, "c4f8a19d620e")
    raw = c.execute(text("""
        INSERT INTO raw_mercado_publico(fuente,tipo_consulta,codigo_externo,respuesta,http_status,consultado_en)
        VALUES ('licitaciones','detalle_codigo','TEST-MIGRACION',
        CAST(:payload AS jsonb),200,now())
        RETURNING id
    """), {"payload": '{"CodigoExterno":"TEST-MIGRACION","Items":{"Cantidad":2,"Listado":[{"Correlativo":9},{"Correlativo":3}]}}'}).scalar_one()
    lic = c.execute(text("INSERT INTO licitacion(codigo_externo,raw_id) VALUES ('TEST-MIGRACION',:raw) RETURNING id"), {"raw": raw}).scalar_one()
    ids = c.execute(text("INSERT INTO licitacion_item(licitacion_id,correlativo) VALUES (:lic,9),(:lic,3) RETURNING id"), {"lic": lic}).scalars().all()
    command.upgrade(config, "968329dc86b0")
    filas = c.execute(text("SELECT id,correlativo,posicion_fuente FROM licitacion_item WHERE licitacion_id=:lic ORDER BY posicion_fuente"), {"lic":lic}).all()
    assert [f.id for f in filas] == ids
    assert [f.correlativo for f in filas] == [9,3]
    assert [f.posicion_fuente for f in filas] == [1,2]
    assert c.execute(text("SELECT verificado_en=consultado_en FROM raw_mercado_publico WHERE id=:raw"), {"raw":raw}).scalar_one()
    # El escritor antiguo sigue utilizando su restricción original entre etapas.
    c.execute(text("""
        INSERT INTO licitacion_item(licitacion_id,correlativo,nombre_producto)
        VALUES (:lic,9,'Actualización del escritor antiguo')
        ON CONFLICT ON CONSTRAINT uq_licitacion_item_correlativo
        DO UPDATE SET nombre_producto=excluded.nombre_producto
    """), {"lic": lic})
    command.upgrade(config, "b9a70e6d4a93")
    assert c.execute(text("SELECT count(*) FROM licitacion_item WHERE licitacion_id=:lic"), {"lic":lic}).scalar_one() == 2
    assert c.execute(text("SELECT count(*) FROM licitacion_item WHERE posicion_fuente IS NULL")).scalar_one() == 0
