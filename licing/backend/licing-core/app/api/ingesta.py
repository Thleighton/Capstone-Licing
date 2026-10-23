import httpx
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from ..config import settings
from ..auth import solo_rol
from ..database import get_db
from ..models.raw import RawMercadoPublico
from ..services.mercado_publico import MercadoPublicoClient
from ..services.normalizacion import normalizar_licitacion
from ..services.ingesta_lote import (
    planificar_ingesta,
    ejecutar_ingesta_lote,
    EjecucionEnCursoError,
)
from ..services.procesamiento import procesar_detalle_guardado
from ..services.limpieza import ausencia_confirmada, eliminar_no_disponibles, motivo_no_disponible

router = APIRouter(prefix="/ingesta", tags=["Ingesta"], dependencies=[Depends(solo_rol("administrador"))])


@router.post("/licitaciones/fecha/{fecha}")
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
        if motivo_no_disponible(item):
            codigo = item.get("CodigoExterno")
            if codigo:
                eliminar_no_disponibles(db, codigo, confirmada=True)
            continue
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


@router.post("/licitaciones/codigo/{codigo}")
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

    if ausencia_confirmada(respuesta):
        eliminar_no_disponibles(db, codigo, confirmada=True)
        db.commit()
        return {"codigo": codigo, "guardado": False, "motivo": "no_encontrada_por_codigo"}
    if not listado:
        raise HTTPException(status_code=404, detail="No se encontró la licitación.")

    detalle = listado[0]
    if not isinstance(detalle, dict) or detalle.get("CodigoExterno") != codigo:
        raise HTTPException(status_code=502, detail="La API devolvió un detalle de otro código.")
    motivo = motivo_no_disponible(detalle)
    if motivo:
        eliminar_no_disponibles(db, codigo, confirmada=True)
        db.commit()
        return {"codigo": codigo, "guardado": False, "motivo": motivo}

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


@router.post("/licitaciones/activas")
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
        if motivo_no_disponible(item):
            codigo = item.get("CodigoExterno")
            if codigo:
                eliminar_no_disponibles(db, codigo, confirmada=True)
            continue
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

@router.get("/licitaciones/codigo/{codigo}/normalizada")
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

@router.post("/licitaciones/codigo/{codigo}/procesar")
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

@router.get("/licitaciones/lote/plan")
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

@router.post("/licitaciones/lote/ejecutar")
async def ejecutar_lote(
    limite: int = Query(default=1, ge=1, le=5),
    db: Session = Depends(get_db),
):
    try:
        return await correr_lote(db=db, limite=limite)
    except EjecucionEnCursoError as exc:
        raise HTTPException(
           status_code=409,
           detail=str(exc),
        ) from exc


async def correr_lote(db: Session, limite: int) -> dict:
    """Lote compartido por el botón y el cron. Deja pasar EjecucionEnCursoError."""
    client = MercadoPublicoClient()

    try:
        resultado = await ejecutar_ingesta_lote(
            db=db,
            client=client,
            limite_detalles=limite,
        )
        ids = [r["licitacion_id"] for r in resultado.get("resultados", []) if r.get("procesado")]
        if ids and settings.cron_secret and settings.filtradas_url:
            import asyncio
            from .preseleccion import evaluar_lote
            try:
                async with asyncio.timeout(8):
                    resultado["preseleccion"] = await evaluar_lote(db, ids)
            except Exception:
                resultado["preseleccion"] = {"pendiente": True, "motivo": "Ingesta guardada; reintentar la preselección desde el dashboard."}
        return resultado
    except EjecucionEnCursoError:
        db.rollback()
        raise

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
