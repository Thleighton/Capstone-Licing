from datetime import datetime, timezone

from sqlalchemy import select ,text
from sqlalchemy.orm import Session
import asyncio
import httpx
from ..config import settings
from ..models.raw import RawMercadoPublico
from ..models.licitacion import Licitacion
from ..models.ejecucion_ingesta import EjecucionIngesta
from .mercado_publico import MercadoPublicoClient
from .procesamiento import procesar_detalle_guardado
from ..database import engine
ID_BLOQUEO_INGESTA = 728401


class EjecucionEnCursoError(RuntimeError):
    pass

def seleccionar_codigos_nuevos(
    listado: list[dict],
    codigos_existentes: set[str],
    limite: int = 5,
) -> list[str]:
    if (
        not isinstance(limite, int)
        or isinstance(limite, bool)
        or limite < 1
        or limite > 20
    ):
        raise ValueError("El límite debe ser un entero entre 1 y 20.")

    seleccionados = []
    vistos = set(codigos_existentes)

    for resumen in listado:
        codigo = resumen.get("CodigoExterno")

        if not isinstance(codigo, str):
            continue

        codigo = codigo.strip()

        if not codigo or codigo in vistos:
            continue

        seleccionados.append(codigo)
        vistos.add(codigo)

        if len(seleccionados) >= limite:
            break

    return seleccionados


async def planificar_ingesta(
    db: Session,
    client: MercadoPublicoClient,
    limite: int = 5,
) -> dict:
    seleccionar_codigos_nuevos([], set(), limite)

    respuesta = await client.licitaciones_activas()

    if not isinstance(respuesta, dict):
        raise ValueError("La API no devolvió un objeto JSON válido.")

    listado = respuesta.get("Listado")

    if not isinstance(listado, list):
        raise ValueError("La respuesta no contiene un Listado válido.")

    if any(not isinstance(item, dict) for item in listado):
        raise ValueError("El listado contiene elementos inválidos.")

    codigos_existentes = set(
        db.scalars(
            select(Licitacion.codigo_externo)
        ).all()
    )

    seleccionados = seleccionar_codigos_nuevos(
        listado=listado,
        codigos_existentes=codigos_existentes,
        limite=limite,
    )

    return {
        "total_informado_api": respuesta.get("Cantidad"),
        "resumenes_recibidos": len(listado),
        "limite_detalles": limite,
        "cantidad_seleccionada": len(seleccionados),
        "codigos_a_descargar": seleccionados,
    }


async def obtener_o_descargar_detalle(
    db: Session,
    client: MercadoPublicoClient,
    codigo: str,
) -> tuple[RawMercadoPublico, bool]:
    existente = (
        db.query(RawMercadoPublico)
        .filter(
            RawMercadoPublico.codigo_externo == codigo,
            RawMercadoPublico.tipo_consulta == "detalle_codigo",
        )
        .order_by(RawMercadoPublico.id.desc())
        .first()
    )

    if existente is not None:
        return existente, False

    await asyncio.sleep(
    settings.mp_pausa_detalles_segundos
)

    respuesta = await client.licitacion_por_codigo(codigo)

    if not isinstance(respuesta, dict):
        raise ValueError(
            f"La consulta de {codigo} no devolvió un objeto JSON."
        )

    listado = respuesta.get("Listado")

    if not isinstance(listado, list) or len(listado) != 1:
        raise ValueError(
            f"Se esperaba exactamente un detalle para {codigo}."
        )

    detalle = listado[0]

    if not isinstance(detalle, dict):
        raise ValueError(
            f"El detalle de {codigo} tiene una estructura inválida."
        )

    if detalle.get("CodigoExterno") != codigo:
        raise ValueError(
            f"La API devolvió un código diferente de {codigo}."
        )

    registro = RawMercadoPublico(
        fuente="licitaciones",
        tipo_consulta="detalle_codigo",
        parametro_consulta=codigo,
        codigo_externo=codigo,
        respuesta=detalle,
        http_status=200,
        cantidad_resultados=respuesta.get("Cantidad"),
    )

    try:
        db.add(registro)
        db.commit()
        db.refresh(registro)

    except Exception:
        db.rollback()
        raise

    return registro, True


async def _ejecutar_lote_interno(
    db: Session,
    client: MercadoPublicoClient,
    limite_detalles: int = 1,
) -> dict:
    plan = await planificar_ingesta(
        db=db,
        client=client,
        limite=limite_detalles,
    )

    codigos = plan["codigos_a_descargar"]

    descargados = 0
    reutilizados = 0
    procesados = 0
    resultados = []
    errores = []
    detenido_por_error_api = False

    for codigo in codigos:
        try:
            registro, fue_descargado = await obtener_o_descargar_detalle(
                db=db,
                client=client,
                codigo=codigo,
            )

            if fue_descargado:
                descargados += 1
            else:
                reutilizados += 1

            # Cada detalle se procesa de forma indivisible. Si un item falla,
            # se conserva el crudo ya guardado y el lote puede continuar.
            with db.begin_nested():
                procesado = procesar_detalle_guardado(
                    db=db,
                    registro=registro,
                )

            procesados += 1

            resultados.append(
                {
                    "licitacion_id": procesado["licitacion_id"],
                    "codigo_externo": procesado["codigo_externo"],
                    "raw_id": procesado["raw_id"],
                    "procesado": procesado["procesado"],
                    "items_procesados": procesado["items_procesados"],
                }
            )

        except httpx.HTTPStatusError as exc:
            errores.append(
                {
                    "codigo_externo": codigo,
                    "tipo": "http_status_error",
                    "status_code": exc.response.status_code,
                    "mensaje": str(exc),
                }
            )

            if exc.response.status_code == 429:
                detenido_por_error_api = True
                break

        except Exception as exc:
            errores.append(
                {
                    "codigo_externo": codigo,
                    "tipo": type(exc).__name__,
                    "mensaje": str(exc),
                }
            )

    return {
        "plan": plan,
        "descargados": descargados,
        "reutilizados": reutilizados,
        "procesados": procesados,
        "detenido_por_error_api": detenido_por_error_api,
        "resultados": resultados,
        "errores": errores,
    }


async def ejecutar_ingesta_lote(
    db: Session,
    client: MercadoPublicoClient,
    limite_detalles: int = 1,
) -> dict:
    seleccionar_codigos_nuevos([], set(), limite_detalles)

    conexion_bloqueo = engine.connect()

    adquirido = conexion_bloqueo.execute(
        text("SELECT pg_try_advisory_lock(:id_bloqueo)"),
        {"id_bloqueo": ID_BLOQUEO_INGESTA},
    ).scalar_one()

    if not adquirido:
        conexion_bloqueo.close()
        raise EjecucionEnCursoError(
            "Ya existe una ejecución de ingesta en curso."
        )

    try:
        return await _ejecutar_ingesta_lote_con_bloqueo(
            db=db,
            client=client,
            limite_detalles=limite_detalles,
        )
    finally:
        conexion_bloqueo.execute(
            text("SELECT pg_advisory_unlock(:id_bloqueo)"),
            {"id_bloqueo": ID_BLOQUEO_INGESTA},
        )
        conexion_bloqueo.commit()
        conexion_bloqueo.close()


async def _ejecutar_ingesta_lote_con_bloqueo(
    db: Session,
    client: MercadoPublicoClient,
    limite_detalles: int = 1,
) -> dict:
    seleccionar_codigos_nuevos([], set(), limite_detalles)

    ejecucion = EjecucionIngesta(
        limite_detalles=limite_detalles,
        estado="en_curso",
    )

    db.add(ejecucion)
    db.commit()
    db.refresh(ejecucion)

    ejecucion_id = ejecucion.id

    try:
        resultado = await _ejecutar_lote_interno(
            db=db,
            client=client,
            limite_detalles=limite_detalles,
        )

        ejecucion.fin = datetime.now(timezone.utc)

        ejecucion.resumenes_recibidos = (
            resultado["plan"]["resumenes_recibidos"]
        )
        ejecucion.seleccionados = (
            resultado["plan"]["cantidad_seleccionada"]
        )
        ejecucion.descargados = resultado["descargados"]
        ejecucion.reutilizados = resultado["reutilizados"]
        ejecucion.procesados = resultado["procesados"]
        ejecucion.detenido_por_error_api = (
            resultado["detenido_por_error_api"]
        )
        ejecucion.errores = resultado["errores"]

        if not resultado["errores"]:
            ejecucion.estado = "completada"
        elif resultado["procesados"] > 0:
            ejecucion.estado = "parcial"
        else:
            ejecucion.estado = "error"

        db.commit()

    except Exception as exc:
        db.rollback()

        ejecucion_error = db.get(
            EjecucionIngesta,
            ejecucion_id,
        )

        if ejecucion_error is not None:
            ejecucion_error.fin = datetime.now(timezone.utc)
            ejecucion_error.estado = "error"
            ejecucion_error.errores = [
                {
                    "tipo": type(exc).__name__,
                    "mensaje": (
                        "La ejecución terminó por una excepción "
                        "fuera del procesamiento individual."
                    ),
                }
            ]
            db.commit()

        raise

    resultado["ejecucion_id"] = ejecucion_id
    return resultado
