import asyncio
from copy import deepcopy
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from sqlalchemy.orm import Session

from app.database import engine
from app.models.ejecucion_compra_agil import EjecucionCompraAgil
from app.models.compra_agil import CompraAgil
from app.models.compra_agil_item import CompraAgilItem
from app.models.raw import RawMercadoPublico
from app.services.compra_agil import CompraAgilClient
from app.services.lote_compra_agil import (
    EjecucionEnCursoError,
    ejecutar_lote_compra_agil,
)


def construir_listado(codigos, total_paginas=1):
    return {
        "success": "OK",
        "payload": {
            "items": [
                {"codigo": codigo}
                for codigo in codigos
            ],
            "paginacion": {
                "total_resultados": len(codigos),
                "total_paginas": total_paginas,
            },
        },
    }


def construir_detalle(codigo, cantidad=1):
    return {
        "success": "OK",
        "payload": {
            "codigo": codigo,
            "nombre": f"Compra {codigo}",
            "descripcion": "Detalle de prueba",
            "estado": {
                "codigo": "publicada",
                "glosa": "Publicada",
                "id_estado": 2,
            },
            "presupuesto": {
                "tipo_presupuesto": "Estimado",
                "moneda": "CLP",
                "presupuesto_estimado": 1000000,
            },
            "productos_solicitados": [
                {
                    "codigo_producto": 44121506,
                    "nombre": "Producto de prueba",
                    "descripcion": "Producto de prueba",
                    "cantidad": cantidad,
                    "unidad_medida": "EA",
                }
            ],
        },
    }


@pytest.fixture
def entorno_lote(monkeypatch):
    with engine.connect() as conexion:
        transaccion = conexion.begin()

        db = Session(
            bind=conexion,
            join_transaction_mode="create_savepoint",
        )

        client = AsyncMock(spec=CompraAgilClient)
        client.cerrar = AsyncMock()

        pausa_original = asyncio.sleep

        async def pausa_inmediata(segundos):
            return None

        monkeypatch.setattr(
            "app.services.lote_compra_agil.asyncio.sleep",
            pausa_inmediata,
        )

        try:
            yield {
                "db": db,
                "client": client,
            }

        finally:
            db.close()
            transaccion.rollback()


async def ejecutar(entorno, **parametros):
    return await ejecutar_lote_compra_agil(
        db=entorno["db"],
        client=entorno["client"],
        **parametros,
    )


@pytest.mark.anyio
async def test_procesa_solo_pendientes(entorno_lote):
    db = entorno_lote["db"]
    client = entorno_lote["client"]

    codigo_procesado = "1000001-1-COT26"
    codigo_pendiente = "1000002-2-COT26"

    respuesta_procesada = construir_detalle(codigo_procesado)

    registro = RawMercadoPublico(
        fuente="compra_agil",
        tipo_consulta="compra_agil_detalle",
        parametro_consulta=codigo_procesado,
        codigo_externo=codigo_procesado,
        respuesta=respuesta_procesada,
        http_status=200,
        cantidad_resultados=1,
    )

    db.add(registro)
    db.commit()

    from app.services.procesamiento_compra_agil import (
        procesar_compra_agil_guardada,
    )

    procesar_compra_agil_guardada(db, registro)
    db.commit()

    client.comprar_agiles.return_value = construir_listado(
        [codigo_procesado, codigo_pendiente]
    )

    client.detalle_por_codigo.return_value = construir_detalle(
        codigo_pendiente
    )

    resultado = await ejecutar(
    entorno_lote,
    paginas=2,
    maximo_detalles=1,
    pausa_entre_detalles=1,
)

    assert resultado["omitidos_ya_procesados"] == 1
    assert resultado["detalles_intentados"] == 1
    assert resultado["detalles_procesados"] == 1
    assert resultado["compras_nuevas"] == 1
    assert resultado["errores"] == []

    assert (
        db.query(CompraAgil)
        .filter(CompraAgil.codigo_externo == codigo_pendiente)
        .count()
    ) == 1

    client.detalle_por_codigo.assert_awaited_once_with(
        codigo_pendiente
    )


@pytest.mark.anyio
async def test_respeta_limite_de_detalles(entorno_lote):
    db = entorno_lote["db"]
    client = entorno_lote["client"]

    codigos = [
        f"100000{i}-1-COT26"
        for i in range(1, 5)
    ]

    client.comprar_agiles.return_value = construir_listado(codigos)
    client.detalle_por_codigo.side_effect = (
        lambda codigo: construir_detalle(codigo)
    )

    resultado = await ejecutar(
    entorno_lote,
    maximo_detalles=2,
    pausa_entre_detalles=1,
)

    assert resultado["detalles_intentados"] == 2
    assert resultado["detalles_procesados"] == 2
    assert resultado["detenido_por_limite"] is True
    assert client.detalle_por_codigo.await_count == 2


@pytest.mark.anyio
async def test_consulta_siguiente_pagina(entorno_lote):
    db = entorno_lote["db"]
    client = entorno_lote["client"]

    codigo_ya_procesado = "1000002-2-COT26"
    codigo_pendiente = "1000003-3-COT26"

    respuesta_procesada = construir_detalle(codigo_ya_procesado)

    registro = RawMercadoPublico(
        fuente="compra_agil",
        tipo_consulta="compra_agil_detalle",
        parametro_consulta=codigo_ya_procesado,
        codigo_externo=codigo_ya_procesado,
        respuesta=respuesta_procesada,
        http_status=200,
        cantidad_resultados=1,
    )

    db.add(registro)
    db.commit()

    from app.services.procesamiento_compra_agil import (
        procesar_compra_agil_guardada,
    )

    procesar_compra_agil_guardada(db, registro)
    db.commit()

    primera = construir_listado(
    [codigo_ya_procesado],
    total_paginas=2,
)

    segunda = construir_listado(
    [codigo_pendiente],
    total_paginas=2,
)

    client.comprar_agiles.side_effect = [primera, segunda]
    client.detalle_por_codigo.return_value = construir_detalle(
        codigo_pendiente
    )

    resultado = await ejecutar(
    entorno_lote,
        paginas=2,
    maximo_detalles=1,
    pausa_entre_detalles=1,
)

    assert resultado["paginas_consultadas"] == 2
    assert resultado["omitidos_ya_procesados"] == 1
    assert resultado["detalles_intentados"] == 1
    assert resultado["detalles_procesados"] == 1
    assert client.comprar_agiles.await_count == 2
    assert client.detalle_por_codigo.await_count == 1

@pytest.mark.anyio
async def test_se_detiene_ante_429(entorno_lote):
    db = entorno_lote["db"]
    client = entorno_lote["client"]

    codigo = "1000004-4-COT26"

    client.comprar_agiles.return_value = construir_listado([codigo])

    request = httpx.Request(
        "GET",
        "https://api.mercadopublico.cl/v2/compra-agil",
    )
    response = httpx.Response(
        status_code=429,
        request=request,
    )

    client.detalle_por_codigo.side_effect = (
        httpx.HTTPStatusError(
            "Demasiadas solicitudes",
            request=request,
            response=response,
        )
    )

    resultado = await ejecutar(
    entorno_lote,
    maximo_detalles=1,
    pausa_entre_detalles=1,
)

    assert resultado["detalles_intentados"] == 1
    assert resultado["detalles_procesados"] == 0
    assert resultado["detenido_por_error_api"] is True
    assert resultado["detenido_por_429"] is True
    assert len(resultado["errores"]) == 1

    assert (
        db.query(RawMercadoPublico)
        .filter(
            RawMercadoPublico.codigo_externo == codigo,
            RawMercadoPublico.tipo_consulta == "compra_agil_detalle",
        )
        .count()
    ) == 0


@pytest.mark.anyio
async def test_rechaza_ejecucion_simultanea(entorno_lote):
    db = entorno_lote["db"]
    client = entorno_lote["client"]

    from app.services.lote_compra_agil import (
        _bloqueo_lote_compra_agil,
    )

    async with _bloqueo_lote_compra_agil:
        with pytest.raises(EjecucionEnCursoError):
            await ejecutar(
                entorno_lote,
                maximo_detalles=1,
                pausa_entre_detalles=1,
            )

    client.comprar_agiles.assert_not_awaited()
    client.detalle_por_codigo.assert_not_awaited()

@pytest.mark.anyio
async def test_registra_historial_de_ejecucion(entorno_lote):
    db = entorno_lote["db"]
    client = entorno_lote["client"]

    codigo = "1000005-5-COT26"

    client.comprar_agiles.return_value = construir_listado([codigo])
    client.detalle_por_codigo.return_value = construir_detalle(codigo)

    resultado = await ejecutar(
        entorno_lote,
        maximo_detalles=1,
        pausa_entre_detalles=1,
    )

    ejecucion = db.get(
        EjecucionCompraAgil,
        resultado["ejecucion_id"],
    )

    assert ejecucion is not None
    assert ejecucion.estado == "completada"
    assert ejecucion.paginas_consultadas == 1
    assert ejecucion.detalles_intentados == 1
    assert ejecucion.detalles_procesados == 1
    assert ejecucion.compras_nuevas == 1
    assert ejecucion.errores == []
    assert ejecucion.fin is not None