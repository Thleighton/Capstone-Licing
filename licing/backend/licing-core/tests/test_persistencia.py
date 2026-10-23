from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.database import engine, get_db
from app.main import app
from app.models.raw import RawMercadoPublico
from app.models.licitacion import Licitacion
from app.models.licitacion_item import LicitacionItem


@pytest.fixture
def entorno():
    with engine.connect() as conexion:
        transaccion = conexion.begin()

        db = Session(
            bind=conexion,
            join_transaction_mode="create_savepoint",
        )

        def reemplazar_db():
            yield db

        overrides_anteriores = app.dependency_overrides.copy()
        app.dependency_overrides[get_db] = reemplazar_db

        codigo = f"TEST-{uuid4().hex[:12]}"

        detalle = {
            "CodigoExterno": codigo,
            "Nombre": "Nombre inicial",
            "Estado": "Publicada",
            "CodigoEstado": 5,
            "MontoEstimado": None,
            "Moneda": "CLP",
            "Fechas": {
                "FechaCierre": "2026-12-01T15:00:00",
            },
            "Items": {
                "Cantidad": 1,
                "Listado": [
                    {
                        "Correlativo": 1,
                        "CodigoProducto": 80111715,
                        "NombreProducto": "Producto de prueba",
                        "Cantidad": 1,
                    }
                ],
            },
        }

        def guardar_raw(contenido):
            registro = RawMercadoPublico(
                fuente="licitaciones",
                tipo_consulta="detalle_codigo",
                parametro_consulta=codigo,
                codigo_externo=codigo,
                respuesta=contenido,
                http_status=200,
                cantidad_resultados=1,
            )
            db.add(registro)
            db.commit()
            return registro.id

        try:
            guardar_raw(detalle)

            with TestClient(app) as client:
                yield {
                    "client": client,
                    "db": db,
                    "codigo": codigo,
                    "detalle": detalle,
                    "guardar_raw": guardar_raw,
                }
        finally:
            app.dependency_overrides.clear()
            app.dependency_overrides.update(overrides_anteriores)
            db.close()
            transaccion.rollback()


def procesar(entorno):
    return entorno["client"].post(
        "/ingesta/licitaciones/codigo/"
        f"{entorno['codigo']}/procesar"
    )


def obtener_licitacion(entorno):
    db = entorno["db"]
    db.expire_all()

    return (
        db.query(Licitacion)
        .filter(Licitacion.codigo_externo == entorno["codigo"])
        .one()
    )


def test_reprocesar_no_duplica(entorno):
    primera = procesar(entorno)
    segunda = procesar(entorno)

    assert primera.status_code == 200, primera.text
    assert segunda.status_code == 200, segunda.text
    assert (
        primera.json()["licitacion_id"]
        == segunda.json()["licitacion_id"]
    )

    db = entorno["db"]
    licitacion = obtener_licitacion(entorno)

    assert (
        db.query(Licitacion)
        .filter(Licitacion.codigo_externo == entorno["codigo"])
        .count()
    ) == 1

    assert (
        db.query(LicitacionItem)
        .filter(LicitacionItem.licitacion_id == licitacion.id)
        .count()
    ) == 1


def test_actualiza_item_existente(entorno):
    primera = procesar(entorno)
    assert primera.status_code == 200, primera.text

    db = entorno["db"]
    licitacion = obtener_licitacion(entorno)

    item = (
        db.query(LicitacionItem)
        .filter(LicitacionItem.licitacion_id == licitacion.id)
        .one()
    )
    item_id_original = item.id

    # Simula un nuevo detalle con una cantidad diferente.
    detalle = entorno["detalle"]
    detalle["Items"]["Listado"][0]["Cantidad"] = 10
    nuevo_raw_id = entorno["guardar_raw"](detalle)

    segunda = procesar(entorno)
    assert segunda.status_code == 200, segunda.text

    licitacion = obtener_licitacion(entorno)
    item = (
        db.query(LicitacionItem)
        .filter(LicitacionItem.licitacion_id == licitacion.id)
        .one()
    )

    assert licitacion.raw_id == nuevo_raw_id
    assert item.id == item_id_original
    assert item.cantidad == 10


def test_recupera_el_caso_real_con_correlativos_6_y_7_repetidos(entorno):
    detalle = entorno["detalle"]
    correlativos = [3, 4, 5, 6, 6, 7, 7]
    detalle["Items"] = {"Cantidad": 7, "Listado": [
        {"Correlativo": c, "NombreProducto": f"Producto distinto {n}", "Cantidad": 1}
        for n, c in enumerate(correlativos, 1)
    ]}
    raw_id = entorno["guardar_raw"](detalle)
    primera = procesar(entorno)
    assert primera.status_code == 200, primera.text
    lic = obtener_licitacion(entorno)
    db = entorno["db"]
    items = db.query(LicitacionItem).filter_by(licitacion_id=lic.id).order_by(LicitacionItem.posicion_fuente).all()
    assert [i.correlativo for i in items] == correlativos
    assert [i.posicion_fuente for i in items] == list(range(1, 8))
    ids = [i.id for i in items]
    assert procesar(entorno).status_code == 200
    assert [i.id for i in db.query(LicitacionItem).filter_by(licitacion_id=lic.id).order_by(LicitacionItem.posicion_fuente)] == ids
    assert db.get(RawMercadoPublico, raw_id).respuesta["Items"] == detalle["Items"]


def test_error_revierte_licitacion_e_items(entorno):
    primera = procesar(entorno)
    assert primera.status_code == 200, primera.text

    licitacion = obtener_licitacion(entorno)
    raw_id_original = licitacion.raw_id

    detalle = entorno["detalle"]
    detalle["Nombre"] = "Este cambio debe revertirse"
    detalle["Items"]["Listado"][0]["Cantidad"] = 99

    # El primer ítem se actualizaría, pero el segundo es inválido.
    detalle["Items"]["Cantidad"] = 2
    detalle["Items"]["Listado"].append({
        "Correlativo": None,
        "NombreProducto": "Ítem inválido",
    })

    entorno["guardar_raw"](detalle)

    respuesta = procesar(entorno)
    assert respuesta.status_code == 422, respuesta.text

    db = entorno["db"]
    licitacion = obtener_licitacion(entorno)

    items = (
        db.query(LicitacionItem)
        .filter(LicitacionItem.licitacion_id == licitacion.id)
        .all()
    )

    assert licitacion.nombre == "Nombre inicial"
    assert licitacion.raw_id == raw_id_original
    assert len(items) == 1
    assert items[0].cantidad == 1

def test_elimina_item_ausente_en_nuevo_detalle(entorno):
    detalle = entorno["detalle"]

    detalle["Items"]["Cantidad"] = 2
    detalle["Items"]["Listado"].append({
        "Correlativo": 2,
        "NombreProducto": "Segundo producto",
        "Cantidad": 3,
    })
    entorno["guardar_raw"](detalle)

    primera = procesar(entorno)
    assert primera.status_code == 200, primera.text

    db = entorno["db"]
    licitacion = obtener_licitacion(entorno)

    assert (
        db.query(LicitacionItem)
        .filter(LicitacionItem.licitacion_id == licitacion.id)
        .count()
    ) == 2

    # Nueva versión: el correlativo 2 ya no está.
    detalle["Items"]["Cantidad"] = 1
    detalle["Items"]["Listado"] = detalle["Items"]["Listado"][:1]
    entorno["guardar_raw"](detalle)

    segunda = procesar(entorno)
    assert segunda.status_code == 200, segunda.text

    licitacion = obtener_licitacion(entorno)
    items = (
        db.query(LicitacionItem)
        .filter(LicitacionItem.licitacion_id == licitacion.id)
        .all()
    )

    assert len(items) == 1
    assert items[0].correlativo == 1


def test_rechaza_lista_incompleta_sin_cambiar_datos(entorno):
    primera = procesar(entorno)
    assert primera.status_code == 200, primera.text

    licitacion = obtener_licitacion(entorno)
    raw_id_original = licitacion.raw_id

    detalle = entorno["detalle"]
    detalle["Nombre"] = "No debe guardarse"
    detalle["Items"]["Cantidad"] = 2
    # La lista sigue teniendo solamente un ítem.
    entorno["guardar_raw"](detalle)

    respuesta = procesar(entorno)
    assert respuesta.status_code == 422, respuesta.text

    licitacion = obtener_licitacion(entorno)

    assert licitacion.nombre == "Nombre inicial"
    assert licitacion.raw_id == raw_id_original

    assert (
        entorno["db"].query(LicitacionItem)
        .filter(LicitacionItem.licitacion_id == licitacion.id)
        .count()
    ) == 1
