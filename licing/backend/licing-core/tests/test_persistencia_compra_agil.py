from copy import deepcopy
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.database import engine, get_db
from app.main import app
from app.models.compra_agil import CompraAgil
from app.models.compra_agil_item import CompraAgilItem
from app.models.raw import RawMercadoPublico


@pytest.fixture
def entorno_compra_agil():
    with engine.connect() as conexion:
        transaccion = conexion.begin()

        db = Session(
            bind=conexion,
            join_transaction_mode="create_savepoint",
        )

        codigo = f"{int(uuid4().hex[:12], 16)}-1-COT26"

        detalle = {
            "codigo": codigo,
            "nombre": "Compra de prueba",
            "estado": {
                "codigo": "publicada",
                "glosa": "Publicada",
                "id_estado": 2,
            },
            "presupuesto": {
                "tipo_presupuesto": "Estimado",
                "moneda": "CLP",
                "presupuesto_estimado": 6900000,
            },
            "productos_solicitados": [
                {
                    "codigo_producto": 44121506,
                    "nombre": "Sobres estándar",
                    "descripcion": f"Producto de prueba {posicion}",
                    "cantidad": posicion,
                    "unidad_medida": "EA",
                }
                for posicion in range(1, 7)
            ],
        }

        def guardar_raw(contenido):
            registro = RawMercadoPublico(
                fuente="compra_agil",
                tipo_consulta="compra_agil_detalle",
                parametro_consulta=codigo,
                codigo_externo=codigo,
                respuesta={
                    "success": "OK",
                    "payload": deepcopy(contenido),
                    "errors": None,
                    "trace": None,
                },
                http_status=200,
                cantidad_resultados=1,
            )

            db.add(registro)
            db.commit()

            return registro.id

        def reemplazar_db():
            yield db

        overrides_anteriores = app.dependency_overrides.copy()
        app.dependency_overrides[get_db] = reemplazar_db

        try:
            raw_id = guardar_raw(detalle)

            with TestClient(app) as client:
                url = f"/ingesta/compra-agil/codigo/{codigo}/procesar"

                primera = client.post(url)
                assert primera.status_code == 200, primera.text

                yield {
                    "db": db,
                    "client": client,
                    "url": url,
                    "codigo": codigo,
                    "detalle": detalle,
                    "guardar_raw": guardar_raw,
                    "raw_id": raw_id,
                    "compra_id": primera.json()["compra_agil_id"],
                }

        finally:
            app.dependency_overrides.clear()
            app.dependency_overrides.update(overrides_anteriores)
            db.close()
            transaccion.rollback()


def obtener_compra(entorno):
    db = entorno["db"]
    db.expire_all()

    return (
        db.query(CompraAgil)
        .filter(CompraAgil.codigo_externo == entorno["codigo"])
        .one()
    )


def obtener_items(entorno):
    return (
        entorno["db"].query(CompraAgilItem)
        .filter(
            CompraAgilItem.compra_agil_id == entorno["compra_id"]
        )
        .order_by(CompraAgilItem.posicion)
        .all()
    )


def test_reprocesar_no_duplica(entorno_compra_agil):
    entorno = entorno_compra_agil

    respuesta = entorno["client"].post(entorno["url"])

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["compra_agil_id"] == entorno["compra_id"]
    assert respuesta.json()["items_procesados"] == 6

    assert (
        entorno["db"].query(CompraAgil)
        .filter(CompraAgil.codigo_externo == entorno["codigo"])
        .count()
    ) == 1

    assert len(obtener_items(entorno)) == 6


def test_actualiza_cantidad_sin_duplicar_item(entorno_compra_agil):
    entorno = entorno_compra_agil
    item_id_original = obtener_items(entorno)[0].id

    detalle = deepcopy(entorno["detalle"])
    detalle["productos_solicitados"][0]["cantidad"] = 99

    nuevo_raw_id = entorno["guardar_raw"](detalle)
    respuesta = entorno["client"].post(entorno["url"])

    assert respuesta.status_code == 200, respuesta.text

    compra = obtener_compra(entorno)
    items = obtener_items(entorno)

    assert compra.raw_id == nuevo_raw_id
    assert len(items) == 6
    assert items[0].id == item_id_original
    assert items[0].cantidad == 99


def test_elimina_posiciones_ausentes(entorno_compra_agil):
    entorno = entorno_compra_agil

    detalle = deepcopy(entorno["detalle"])
    detalle["productos_solicitados"] = (
        detalle["productos_solicitados"][:2]
    )

    entorno["guardar_raw"](detalle)
    respuesta = entorno["client"].post(entorno["url"])

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["items_procesados"] == 2

    assert [
        item.posicion for item in obtener_items(entorno)
    ] == [1, 2]


def test_rechaza_cantidad_negativa_sin_cambiar_compra(
    entorno_compra_agil,
):
    entorno = entorno_compra_agil

    detalle = deepcopy(entorno["detalle"])
    detalle["nombre"] = "No debe guardarse"
    detalle["productos_solicitados"][0]["cantidad"] = -1

    entorno["guardar_raw"](detalle)
    respuesta = entorno["client"].post(entorno["url"])

    assert respuesta.status_code == 422, respuesta.text

    compra = obtener_compra(entorno)
    items = obtener_items(entorno)

    assert compra.nombre == "Compra de prueba"
    assert compra.raw_id == entorno["raw_id"]
    assert len(items) == 6
    assert items[0].cantidad == 1


def test_error_intermedio_revierte_compra_e_items(
    entorno_compra_agil,
    monkeypatch,
):
    entorno = entorno_compra_agil
    db = entorno["db"]

    detalle = deepcopy(entorno["detalle"])
    detalle["nombre"] = "Cambio que debe revertirse"
    detalle["productos_solicitados"][0]["cantidad"] = 99

    entorno["guardar_raw"](detalle)

    ejecutar_original = db.execute
    escrituras_items = 0

    def ejecutar_con_fallo(sentencia, *args, **kwargs):
        nonlocal escrituras_items

        tabla = getattr(sentencia, "table", None)

        if (
            getattr(sentencia, "is_insert", False)
            and getattr(tabla, "name", None) == "compra_agil_item"
        ):
            escrituras_items += 1

            if escrituras_items == 2:
                raise RuntimeError("Fallo simulado al guardar ítems")

        return ejecutar_original(sentencia, *args, **kwargs)

    with monkeypatch.context() as parche:
        parche.setattr(db, "execute", ejecutar_con_fallo)

        with pytest.raises(RuntimeError, match="Fallo simulado"):
            entorno["client"].post(entorno["url"])

    compra = obtener_compra(entorno)
    items = obtener_items(entorno)

    assert escrituras_items == 2
    assert compra.nombre == "Compra de prueba"
    assert compra.raw_id == entorno["raw_id"]
    assert len(items) == 6
    assert items[0].cantidad == 1