import asyncio
import pytest
import httpx
from app.models.licitacion import Licitacion
from unittest.mock import AsyncMock
from uuid import uuid4
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.database import engine
from app.models.ejecucion_ingesta import EjecucionIngesta
from app.models.raw import RawMercadoPublico
from app.services.ingesta_lote import (
    obtener_o_descargar_detalle,
    ID_BLOQUEO_INGESTA,
    EjecucionEnCursoError,
    ejecutar_ingesta_lote,
)
from app.services.mercado_publico import MercadoPublicoClient


@pytest.fixture
def entorno_descarga():
    with engine.connect() as conexion:
        transaccion = conexion.begin()

        db = Session(
            bind=conexion,
            join_transaction_mode="create_savepoint",
        )

        codigo = f"TEST-{uuid4().hex[:12]}"

        cliente = AsyncMock(spec=MercadoPublicoClient)

        try:
            yield {
                "db": db,
                "codigo": codigo,
                "cliente": cliente,
            }
        finally:
            db.close()
            transaccion.rollback()


def contar_detalles(db, codigo):
    return (
        db.query(RawMercadoPublico)
        .filter(
            RawMercadoPublico.codigo_externo == codigo,
            RawMercadoPublico.tipo_consulta == "detalle_codigo",
        )
        .count()
    )


def test_reutiliza_detalle_sin_consultar_api(entorno_descarga):
    db = entorno_descarga["db"]
    codigo = entorno_descarga["codigo"]
    cliente = entorno_descarga["cliente"]

    existente = RawMercadoPublico(
        fuente="licitaciones",
        tipo_consulta="detalle_codigo",
        parametro_consulta=codigo,
        codigo_externo=codigo,
        respuesta={"CodigoExterno": codigo},
        http_status=200,
        cantidad_resultados=1,
    )

    db.add(existente)
    db.commit()
    id_original = existente.id

    registro, descargado = asyncio.run(
        obtener_o_descargar_detalle(
            db=db,
            client=cliente,
            codigo=codigo,
        )
    )

    assert descargado is False
    assert registro.id == id_original
    assert contar_detalles(db, codigo) == 1

    cliente.licitacion_por_codigo.assert_not_awaited()


def test_descarga_guarda_y_despues_reutiliza(entorno_descarga):
    db = entorno_descarga["db"]
    codigo = entorno_descarga["codigo"]
    cliente = entorno_descarga["cliente"]

    detalle = {
        "CodigoExterno": codigo,
        "Nombre": "Detalle de prueba",
        "Estado": "Publicada",
        "Items": {
            "Cantidad": 0,
            "Listado": [],
        },
    }

    cliente.licitacion_por_codigo.return_value = {
        "Cantidad": 1,
        "Listado": [detalle],
    }

    primero, primera_descarga = asyncio.run(
        obtener_o_descargar_detalle(
            db=db,
            client=cliente,
            codigo=codigo,
        )
    )

    id_guardado = primero.id

    assert primera_descarga is True
    assert primero.respuesta == detalle
    assert contar_detalles(db, codigo) == 1

    segundo, segunda_descarga = asyncio.run(
        obtener_o_descargar_detalle(
            db=db,
            client=cliente,
            codigo=codigo,
        )
    )

    assert segunda_descarga is False
    assert segundo.id == id_guardado
    assert contar_detalles(db, codigo) == 1

    cliente.licitacion_por_codigo.assert_awaited_once_with(codigo)


def test_rechaza_codigo_distinto_sin_guardar(entorno_descarga):
    db = entorno_descarga["db"]
    codigo = entorno_descarga["codigo"]
    cliente = entorno_descarga["cliente"]

    cliente.licitacion_por_codigo.return_value = {
        "Cantidad": 1,
        "Listado": [
            {"CodigoExterno": "OTRO-CODIGO"}
        ],
    }

    with pytest.raises(ValueError, match="código diferente"):
        asyncio.run(
            obtener_o_descargar_detalle(
                db=db,
                client=cliente,
                codigo=codigo,
            )
        )

    assert contar_detalles(db, codigo) == 0
    cliente.licitacion_por_codigo.assert_awaited_once_with(codigo)

def test_lote_procesa_un_detalle(entorno_descarga):
    db = entorno_descarga["db"]
    codigo = entorno_descarga["codigo"]
    cliente = entorno_descarga["cliente"]

    cliente.licitaciones_activas.return_value = {
        "Cantidad": 1,
        "Listado": [{"CodigoExterno": codigo}],
    }

    cliente.licitacion_por_codigo.return_value = {
        "Cantidad": 1,
        "Listado": [{
            "CodigoExterno": codigo,
            "Nombre": "Licitación del lote",
            "Estado": "Publicada",
            "Items": {
                "Cantidad": 1,
                "Listado": [{
                    "Correlativo": 1,
                    "NombreProducto": "Servicio de prueba",
                    "Cantidad": 1,
                }],
            },
        }],
    }

    resultado = asyncio.run(
        ejecutar_ingesta_lote(db, cliente, limite_detalles=1)
    )

    assert resultado["descargados"] == 1
    assert resultado["procesados"] == 1
    assert resultado["errores"] == []

    assert (
        db.query(Licitacion)
        .filter(Licitacion.codigo_externo == codigo)
        .count()
    ) == 1

    cliente.licitaciones_activas.assert_awaited_once()
    cliente.licitacion_por_codigo.assert_awaited_once_with(codigo)


def test_lote_conserva_crudo_invalido_y_continua(entorno_descarga):
    db = entorno_descarga["db"]
    codigo_malo = entorno_descarga["codigo"]
    codigo_bueno = f"{codigo_malo}-B"
    cliente = entorno_descarga["cliente"]

    cliente.licitaciones_activas.return_value = {
        "Cantidad": 2,
        "Listado": [
            {"CodigoExterno": codigo_malo},
            {"CodigoExterno": codigo_bueno},
        ],
    }

    def responder_detalle(codigo):
        return {
            "Cantidad": 1,
            "Listado": [{
                "CodigoExterno": codigo,
                "Nombre": "Licitación de prueba",
                "Items": {
                    # El primero declara 2 pero entrega 0.
                    "Cantidad": 2 if codigo == codigo_malo else 0,
                    "Listado": [],
                },
            }],
        }

    cliente.licitacion_por_codigo.side_effect = responder_detalle

    resultado = asyncio.run(
        ejecutar_ingesta_lote(db, cliente, limite_detalles=2)
    )

    assert resultado["descargados"] == 2
    assert resultado["procesados"] == 1
    assert resultado["detenido_por_error_api"] is False
    assert len(resultado["errores"]) == 1
    assert resultado["errores"][0]["codigo_externo"] == codigo_malo

    # Conservamos ambos crudos para diagnóstico o reprocesamiento.
    assert contar_detalles(db, codigo_malo) == 1
    assert contar_detalles(db, codigo_bueno) == 1

    codigos_guardados = {
        fila.codigo_externo
        for fila in db.query(Licitacion).filter(
            Licitacion.codigo_externo.in_([
                codigo_malo,
                codigo_bueno,
            ])
        ).all()
    }

    assert codigos_guardados == {codigo_bueno}

@pytest.mark.parametrize("error_item", ["correlativo_repetido", "codigo_producto_largo"])
def test_lote_revierte_detalle_invalido_y_guarda_el_siguiente(entorno_descarga, monkeypatch, error_item):
    from app.config import settings

    monkeypatch.setattr(settings, "mp_pausa_detalles_segundos", 0.001)
    db = entorno_descarga["db"]
    cliente = entorno_descarga["cliente"]
    codigo_malo = entorno_descarga["codigo"]
    codigo_bueno = f"{codigo_malo}-B"
    cliente.licitaciones_activas.return_value = {
        "Cantidad": 2,
        "Listado": [{"CodigoExterno": codigo_malo}, {"CodigoExterno": codigo_bueno}],
    }

    def responder_detalle(codigo):
        items = [{"Correlativo": 1, "NombreProducto": "Servicio valido", "Cantidad": 1}]
        if codigo == codigo_malo:
            items.append({
                "Correlativo": 1 if error_item == "correlativo_repetido" else 2,
                "CodigoProducto": "X" * 51 if error_item == "codigo_producto_largo" else "123",
                "NombreProducto": "Item invalido",
                "Cantidad": 1,
            })
        return {"Cantidad": 1, "Listado": [{
            "CodigoExterno": codigo,
            "Nombre": "Licitacion de prueba",
            "Items": {"Cantidad": len(items), "Listado": items},
        }]}

    cliente.licitacion_por_codigo.side_effect = responder_detalle
    resultado = asyncio.run(ejecutar_ingesta_lote(db, cliente, limite_detalles=2))

    assert resultado["procesados"] == 1
    assert len(resultado["errores"]) == 1
    assert resultado["errores"][0]["codigo_externo"] == codigo_malo
    assert db.query(Licitacion).filter_by(codigo_externo=codigo_malo).count() == 0
    assert db.query(Licitacion).filter_by(codigo_externo=codigo_bueno).count() == 1
    assert contar_detalles(db, codigo_malo) == 1
    assert contar_detalles(db, codigo_bueno) == 1
    ejecucion = db.get(EjecucionIngesta, resultado["ejecucion_id"])
    assert ejecucion.estado == "parcial"
    assert ejecucion.descargados == 2 and ejecucion.procesados == 1


def test_lote_se_detiene_ante_error_429(entorno_descarga):
    db = entorno_descarga["db"]
    codigo_primero = entorno_descarga["codigo"]
    codigo_segundo = f"{codigo_primero}-B"
    cliente = entorno_descarga["cliente"]

    cliente.licitaciones_activas.return_value = {
        "Cantidad": 2,
        "Listado": [
            {"CodigoExterno": codigo_primero},
            {"CodigoExterno": codigo_segundo},
        ],
    }

    request = httpx.Request(
        "GET",
        "https://example.test/licitaciones.json",
    )

    response = httpx.Response(
        status_code=429,
        request=request,
    )

    cliente.licitacion_por_codigo.side_effect = (
        httpx.HTTPStatusError(
            "Demasiadas solicitudes",
            request=request,
            response=response,
        )
    )

    resultado = asyncio.run(
        ejecutar_ingesta_lote(
            db=db,
            client=cliente,
            limite_detalles=2,
        )
    )

    assert resultado["detenido_por_error_api"] is True
    assert resultado["procesados"] == 0
    assert resultado["descargados"] == 0
    assert len(resultado["errores"]) == 1

    error = resultado["errores"][0]
    assert error["codigo_externo"] == codigo_primero
    assert error["status_code"] == 429

    # Se intentó únicamente el primer detalle.
    cliente.licitacion_por_codigo.assert_awaited_once_with(
        codigo_primero
    )

    assert contar_detalles(db, codigo_primero) == 0
    assert contar_detalles(db, codigo_segundo) == 0

    
def test_lote_rechaza_ejecucion_simultanea(entorno_descarga):
    db = entorno_descarga["db"]
    cliente = entorno_descarga["cliente"]

    conexion_bloqueo = engine.connect()
    adquirido = conexion_bloqueo.execute(
        text("SELECT pg_try_advisory_lock(:id_bloqueo)"),
        {"id_bloqueo": ID_BLOQUEO_INGESTA},
    ).scalar_one()

    assert adquirido is True

    try:
        with pytest.raises(EjecucionEnCursoError):
            asyncio.run(
                ejecutar_ingesta_lote(
                    db,
                    cliente,
                    limite_detalles=1,
                )
            )

        cliente.licitaciones_activas.assert_not_awaited()
        cliente.licitacion_por_codigo.assert_not_awaited()

    finally:
        conexion_bloqueo.execute(
            text("SELECT pg_advisory_unlock(:id_bloqueo)"),
            {"id_bloqueo": ID_BLOQUEO_INGESTA},
        )
        conexion_bloqueo.commit()
        conexion_bloqueo.close()
