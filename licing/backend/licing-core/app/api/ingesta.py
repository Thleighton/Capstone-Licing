import httpx
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException,Path, Query
from sqlalchemy.orm import Session
from ..config import settings
from ..database import get_db
from ..models.raw import RawMercadoPublico
from ..services.mercado_publico import MercadoPublicoClient
from ..services.compra_agil import CompraAgilClient
from ..services.normalizacion import normalizar_licitacion
from ..services.ingesta_lote import (
    planificar_ingesta,
    ejecutar_ingesta_lote,
    EjecucionEnCursoError,
)
from ..services.procesamiento import procesar_detalle_guardado
from ..services.normalizacion_compra_agil import (
    normalizar_compra_agil,
)
from ..services.procesamiento_compra_agil import (
    procesar_compra_agil_guardada,
)

router = APIRouter(prefix="/ingesta")


@router.post(
    "/licitaciones/fecha/{fecha}",
    tags=["Licitaciones"],
    summary="Guardar resúmenes por fecha",
)
async def ingestar_por_fecha(
    fecha: str,
    limite: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    if len(fecha) != 8 or not fecha.isdigit():
        raise HTTPException(
            status_code=400,
            detail="La fecha debe tener formato ddmmaaaa, por ejemplo 19102026.",
        )

    client = MercadoPublicoClient()

    try:
        respuesta = await client.licitaciones_por_fecha(fecha)
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Mercado Público respondió {exc.response.status_code}.",
        )
    finally:
        await client.cerrar()

    listado = respuesta.get("Listado") or []
    seleccion = listado[:limite]

    guardados = []

    for item in seleccion:
        registro = RawMercadoPublico(
            fuente="licitaciones",
            tipo_consulta="listado_fecha",
            parametro_consulta=fecha,
            codigo_externo=item.get("CodigoExterno"),
            respuesta=item,
            http_status=200,
            cantidad_resultados=respuesta.get("Cantidad"),
        )
        db.add(registro)
        guardados.append(registro.codigo_externo)

    db.commit()

    return {
        "fecha": fecha,
        "total_en_respuesta": respuesta.get("Cantidad"),
        "solicitados": limite,
        "guardados": len(guardados),
        "codigos": guardados,
    }


@router.post(
    "/licitaciones/codigo/{codigo}",
    tags=["Licitaciones"],
    summary="Descargar y guardar un detalle",
)
async def ingestar_por_codigo(
    codigo: str,
    db: Session = Depends(get_db),
):
    client = MercadoPublicoClient()

    try:
        respuesta = await client.licitacion_por_codigo(codigo)
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Mercado Público respondió {exc.response.status_code}.",
        )
    finally:
        await client.cerrar()

    listado = respuesta.get("Listado") or []

    if not listado:
        raise HTTPException(status_code=404, detail="No se encontró la licitación.")

    detalle = listado[0]

    registro = RawMercadoPublico(
        fuente="licitaciones",
        tipo_consulta="detalle_codigo",
        parametro_consulta=codigo,
        codigo_externo=detalle.get("CodigoExterno"),
        respuesta=detalle,
        http_status=200,
        cantidad_resultados=respuesta.get("Cantidad"),
    )

    db.add(registro)
    db.commit()

    return {
        "codigo": codigo,
        "guardado": True,
        "raw_id": registro.id,
    }


@router.post(
    "/licitaciones/activas",
    tags=["Licitaciones"],
    summary="Guardar resúmenes de licitaciones activas",
)
async def ingestar_activas(
    limite: int = Query(default=5, ge=1, le=20),
    db: Session = Depends(get_db),
):
    client = MercadoPublicoClient()

    try:
        respuesta = await client.licitaciones_activas()

    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=502,
            detail=(
                "Mercado Público respondió con estado HTTP "
                f"{exc.response.status_code}."
            ),
        ) from exc

    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=502,
            detail="No se pudo conectar con Mercado Público.",
        ) from exc

    except ValueError as exc:
        raise HTTPException(
            status_code=502,
            detail="Mercado Público no devolvió un JSON válido.",
        ) from exc

    finally:
        await client.cerrar()

    # No confundir una respuesta de error con un listado vacío.
    if not isinstance(respuesta, dict) or not isinstance(
        respuesta.get("Listado"), list
    ):
        raise HTTPException(
            status_code=502,
            detail="La respuesta no contiene un Listado válido.",
        )

    listado = respuesta["Listado"]
    seleccion = listado[:limite]

    codigos = []

    for item in seleccion:
        registro = RawMercadoPublico(
            fuente="licitaciones",
            tipo_consulta="listado_activas",
            parametro_consulta="estado=activas",
            codigo_externo=item.get("CodigoExterno"),
            respuesta=item,
            http_status=200,
            cantidad_resultados=respuesta.get("Cantidad"),
        )

        db.add(registro)
        codigos.append(registro.codigo_externo)

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise

    return {
        "consulta": "activas",
        "total_en_respuesta": respuesta.get("Cantidad"),
        "solicitados": limite,
        "guardados": len(codigos),
        "codigos": codigos,
    }

@router.get(
    "/licitaciones/codigo/{codigo}/normalizada",
    tags=["Licitaciones"],
    summary="Consultar la normalización de un detalle guardado",
)
def ver_licitacion_normalizada(
    codigo: str,
    db: Session = Depends(get_db),
):
    registro = (
        db.query(RawMercadoPublico)
        .filter(
            RawMercadoPublico.codigo_externo == codigo,
            RawMercadoPublico.tipo_consulta == "detalle_codigo",
        )
        .order_by(RawMercadoPublico.id.desc())
        .first()
    )

    if registro is None:
        raise HTTPException(
            status_code=404,
            detail="No hay un detalle guardado para ese código.",
        )

    return {
        "raw_id": registro.id,
        "datos": normalizar_licitacion(registro.respuesta),
    }

@router.post(
    "/licitaciones/codigo/{codigo}/procesar",
    tags=["Licitaciones"],
    summary="Guardar una licitación y sus ítems normalizados",
)
def procesar_licitacion_guardada(
    codigo: str,
    db: Session = Depends(get_db),
):
    registro = (
        db.query(RawMercadoPublico)
        .filter(
            RawMercadoPublico.codigo_externo == codigo,
            RawMercadoPublico.tipo_consulta == "detalle_codigo",
        )
        .order_by(RawMercadoPublico.id.desc())
        .first()
    )

    if registro is None:
        raise HTTPException(
            status_code=404,
            detail="No hay un detalle guardado para ese código.",
        )

    try:
        resultado = procesar_detalle_guardado(
            db=db,
            registro=registro,
        )

        db.commit()

    except ValueError as exc:
        db.rollback()
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc

    except Exception:
        db.rollback()
        raise

    return resultado

@router.get(
    "/licitaciones/lote/plan",
    tags=["Licitaciones"],
    summary="Consultar el plan de ingesta",
)
async def ver_plan_ingesta(
    limite: int = Query(default=5, ge=1, le=20),
    db: Session = Depends(get_db),
):
    client = MercadoPublicoClient()

    try:
        return await planificar_ingesta(
            db=db,
            client=client,
            limite=limite,
        )

    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=502,
            detail=(
                "Mercado Público respondió con estado HTTP "
                f"{exc.response.status_code}."
            ),
        ) from exc

    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=502,
            detail="No se pudo conectar con Mercado Público.",
        ) from exc

    except ValueError as exc:
        raise HTTPException(
            status_code=502,
            detail=str(exc),
        ) from exc

    finally:
        await client.cerrar()

@router.post(
    "/licitaciones/lote/ejecutar",
    tags=["Licitaciones"],
    summary="Ejecutar una ingesta por lote",
)
async def ejecutar_lote(
    limite: int = Query(default=1, ge=1, le=5),
    db: Session = Depends(get_db),
):
    client = MercadoPublicoClient()

    try:
        return await ejecutar_ingesta_lote(
            db=db,
            client=client,
            limite_detalles=limite,
        )
    except EjecucionEnCursoError as exc:
        db.rollback()
        raise HTTPException(
           status_code=409,
           detail=str(exc),
        ) from exc

    except httpx.HTTPStatusError as exc:
        db.rollback()

        raise HTTPException(
            status_code=502,
            detail=(
                "No se pudo obtener el listado de activas. "
                "Mercado Público respondió con estado HTTP "
                f"{exc.response.status_code}."
            ),
        ) from exc

    except httpx.RequestError as exc:
        db.rollback()

        raise HTTPException(
            status_code=502,
            detail="Falló la conexión al consultar Mercado Público.",
        ) from exc

    except ValueError as exc:
        db.rollback()

        raise HTTPException(
            status_code=502,
            detail=str(exc),
        ) from exc

    except Exception:
        db.rollback()
        raise

    finally:
        await client.cerrar()


#COMPRA AGIL
@router.post(
    "/compra-agil/explorar",
    tags=["Compras Ágiles"],
    summary="Consultar y guardar una página de resúmenes",
)
async def explorar_compra_agil(
    region: int | None = Query(default=None, ge=1, le=16),
    pagina: int = Query(default=1, ge=1),
    tamano_pagina: int = Query(default=10, ge=10, le=50),
    db: Session = Depends(get_db),
) -> dict:
    client = CompraAgilClient()

    try:
        respuesta = await client.comprar_agiles(
            region=region,
            pagina=pagina,
            tamano_pagina=tamano_pagina,
        )

    except httpx.HTTPStatusError as exc:
        mensaje_origen = exc.response.text

        if settings.mp_ticket:
            mensaje_origen = mensaje_origen.replace(
                settings.mp_ticket,
                "[TICKET_OCULTO]",
            )

        raise HTTPException(
            status_code=502,
            detail={
                "origen": "api_compra_agil",
                "http_status_origen": exc.response.status_code,
                "retry_after": exc.response.headers.get("Retry-After"),
                "respuesta_origen": mensaje_origen[:2000],
            },
        ) from exc

    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=502,
            detail="No se pudo conectar con la API de Compra Ágil.",
        ) from exc

    except ValueError as exc:
        raise HTTPException(
            status_code=502,
            detail="La API de Compra Ágil no devolvió un JSON válido.",
        ) from exc

    finally:
        await client.cerrar()

    if not isinstance(respuesta, dict):
        raise HTTPException(
            status_code=502,
            detail="La respuesta de Compra Ágil no es un objeto JSON.",
        )

    if respuesta.get("success") != "OK":
        raise HTTPException(
            status_code=502,
            detail=(
                "La API de Compra Ágil devolvió success distinto de OK."
            ),
        )

    payload = respuesta.get("payload")

    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=502,
            detail="La respuesta no contiene un payload válido.",
        )

    items = payload.get("items")
    paginacion = payload.get("paginacion")

    if (
        not isinstance(items, list)
        or any(not isinstance(item, dict) for item in items)
    ):
        raise HTTPException(
            status_code=502,
            detail="payload.items no contiene una lista válida.",
        )

    if not isinstance(paginacion, dict):
        raise HTTPException(
            status_code=502,
            detail="payload.paginacion no es un objeto válido.",
        )

    total_resultados = paginacion.get("total_resultados")

    if (
        not isinstance(total_resultados, int)
        or isinstance(total_resultados, bool)
        or total_resultados < 0
    ):
        raise HTTPException(
            status_code=502,
            detail="La paginación no contiene un total_resultados válido.",
        )

    registro = RawMercadoPublico(
        fuente="compra_agil",
        tipo_consulta="compra_agil_listado",
        parametro_consulta=(
            f"estado=publicada;region={region};"
            f"pagina={pagina};tamano_pagina={tamano_pagina}"
        ),
        codigo_externo=None,
        respuesta=respuesta,
        http_status=200,
        cantidad_resultados=total_resultados,
    )

    try:
        db.add(registro)
        db.commit()
        db.refresh(registro)

    except Exception:
        db.rollback()
        raise

    return {
        "raw_id": registro.id,
        "fuente": "compra_agil",
        "estado_consultado": "publicada",
        "region": region,
        "pagina": pagina,
        "tamano_pagina": tamano_pagina,
        "total_resultados": total_resultados,
        "total_paginas": paginacion.get("total_paginas"),
        "items_recibidos": len(items),
        "codigos": [item.get("codigo") for item in items],
    }


@router.post(
    "/compra-agil/codigo/{codigo}",
    tags=["Compras Ágiles"],
    summary="Descargar o reutilizar un detalle",
)
async def guardar_detalle_compra_agil(
    codigo: str = Path(
        ...,
        pattern=r"^[0-9]+-[0-9]+-COT[0-9]{2}$",
    ),
    db: Session = Depends(get_db),
) -> dict:
    existente = (
        db.query(RawMercadoPublico)
        .filter(
            RawMercadoPublico.fuente == "compra_agil",
            RawMercadoPublico.tipo_consulta == "compra_agil_detalle",
            RawMercadoPublico.codigo_externo == codigo,
        )
        .order_by(RawMercadoPublico.id.desc())
        .first()
    )

    if existente is not None:
        return {
            "codigo": codigo,
            "raw_id": existente.id,
            "descargado": False,
            "reutilizado": True,
        }

    client = CompraAgilClient()

    try:
        respuesta = await client.detalle_por_codigo(codigo)

    except httpx.HTTPStatusError as exc:
        mensaje = exc.response.text.replace(
            settings.mp_ticket,
            "[TICKET_OCULTO]",
        )

        raise HTTPException(
            status_code=502,
            detail={
                "origen": "api_compra_agil",
                "http_status_origen": exc.response.status_code,
                "retry_after": exc.response.headers.get("Retry-After"),
                "respuesta_origen": mensaje[:2000],
            },
        ) from exc

    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=502,
            detail="No se pudo conectar con Compra Ágil.",
        ) from exc

    except ValueError as exc:
        raise HTTPException(
            status_code=502,
            detail="Compra Ágil no devolvió un JSON válido.",
        ) from exc

    finally:
        await client.cerrar()

    if (
        not isinstance(respuesta, dict)
        or respuesta.get("success") != "OK"
    ):
        raise HTTPException(
            status_code=502,
            detail="Compra Ágil no devolvió una respuesta exitosa.",
        )

    detalle = respuesta.get("payload")

    if (
        not isinstance(detalle, dict)
        or detalle.get("codigo") != codigo
    ):
        raise HTTPException(
            status_code=502,
            detail="El detalle no es válido o corresponde a otro código.",
        )

    productos = detalle.get("productos_solicitados")

    if (
        not isinstance(productos, list)
        or any(not isinstance(item, dict) for item in productos)
    ):
        raise HTTPException(
            status_code=502,
            detail="El detalle no contiene productos_solicitados válidos.",
        )

    registro = RawMercadoPublico(
        fuente="compra_agil",
        tipo_consulta="compra_agil_detalle",
        parametro_consulta=codigo,
        codigo_externo=codigo,
        respuesta=respuesta,
        http_status=200,
        cantidad_resultados=1,
    )

    try:
        db.add(registro)
        db.commit()
        db.refresh(registro)

    except Exception:
        db.rollback()
        raise

    return {
        "codigo": codigo,
        "raw_id": registro.id,
        "descargado": True,
        "reutilizado": False,
        "productos_recibidos": len(productos),
    }

@router.get(
    "/compra-agil/codigo/{codigo}/normalizada",
    tags=["Compras Ágiles"],
    summary="Consultar la normalización de un detalle guardado",
)
def ver_compra_agil_normalizada(
    codigo: str = Path(
        ...,
        pattern=r"^[0-9]+-[0-9]+-COT[0-9]{2}$",
    ),
    db: Session = Depends(get_db),
) -> dict:
    registro = (
        db.query(RawMercadoPublico)
        .filter(
            RawMercadoPublico.fuente == "compra_agil",
            RawMercadoPublico.tipo_consulta == "compra_agil_detalle",
            RawMercadoPublico.codigo_externo == codigo,
        )
        .order_by(RawMercadoPublico.id.desc())
        .first()
    )

    if registro is None:
        raise HTTPException(
            status_code=404,
            detail="No hay un detalle guardado para esta Compra Ágil.",
        )

    respuesta = registro.respuesta

    if (
        not isinstance(respuesta, dict)
        or respuesta.get("success") != "OK"
        or not isinstance(respuesta.get("payload"), dict)
    ):
        raise HTTPException(
            status_code=422,
            detail="El registro crudo no contiene un detalle válido.",
        )

    detalle = respuesta["payload"]

    if detalle.get("codigo") != codigo:
        raise HTTPException(
            status_code=422,
            detail="El código del detalle no coincide con el solicitado.",
        )

    try:
        datos = normalizar_compra_agil(detalle)

    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc

    return {
        "raw_id": registro.id,
        "datos": datos,
    }

@router.post(
    "/compra-agil/codigo/{codigo}/procesar",
    tags=["Compras Ágiles"],
    summary="Guardar una Compra Ágil y sus ítems normalizados",
)
def procesar_compra_agil(
    codigo: str = Path(
        ...,
        pattern=r"^[0-9]+-[0-9]+-COT[0-9]{2}$",
    ),
    db: Session = Depends(get_db),
) -> dict:
    registro = (
        db.query(RawMercadoPublico)
        .filter(
            RawMercadoPublico.fuente == "compra_agil",
            RawMercadoPublico.tipo_consulta == "compra_agil_detalle",
            RawMercadoPublico.codigo_externo == codigo,
        )
        .order_by(RawMercadoPublico.id.desc())
        .first()
    )

    if registro is None:
        raise HTTPException(
            status_code=404,
            detail="No hay un detalle guardado para esta Compra Ágil.",
        )

    try:
        resultado = procesar_compra_agil_guardada(
            db=db,
            registro=registro,
        )

        db.commit()

    except ValueError as exc:
        db.rollback()
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc

    except Exception:
        db.rollback()
        raise

    return resultado
