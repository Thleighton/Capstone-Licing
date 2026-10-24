import asyncio
import math
import re
from asyncio import Lock
import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session
from datetime import datetime, timezone
from ..models.compra_agil import CompraAgil
from ..models.raw import RawMercadoPublico
from .compra_agil import CompraAgilClient
from .procesamiento_compra_agil import (
    procesar_compra_agil_guardada,
)
from ..models.ejecucion_compra_agil import EjecucionCompraAgil


PATRON_CODIGO = re.compile(r"[0-9]+-[0-9]+-COT[0-9]{2}")
class EjecucionEnCursoError(RuntimeError):
    pass


_bloqueo_lote_compra_agil = Lock()


def validar_respuesta(respuesta: dict) -> dict:
    if (
        not isinstance(respuesta, dict)
        or respuesta.get("success") != "OK"
        or not isinstance(respuesta.get("payload"), dict)
    ):
        raise ValueError(
            "Compra Ágil no devolvió un payload exitoso válido."
        )

    return respuesta["payload"]


def guardar_crudo(
    db: Session,
    *,
    tipo_consulta: str,
    parametro_consulta: str,
    codigo: str | None,
    respuesta: dict,
    cantidad: int,
) -> RawMercadoPublico:
    registro = RawMercadoPublico(
        fuente="compra_agil",
        tipo_consulta=tipo_consulta,
        parametro_consulta=parametro_consulta,
        codigo_externo=codigo,
        respuesta=respuesta,
        http_status=200,
        cantidad_resultados=cantidad,
    )

    try:
        db.add(registro)
        db.commit()
        db.refresh(registro)
    except Exception:
        db.rollback()
        raise

    return registro


async def obtener_o_descargar_detalle(
    db: Session,
    client: CompraAgilClient,
    codigo: str,
    pausa: float,
) -> tuple[RawMercadoPublico, bool]:
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
        return existente, False

    await asyncio.sleep(pausa)
    respuesta = await client.detalle_por_codigo(codigo)
    detalle = validar_respuesta(respuesta)

    if detalle.get("codigo") != codigo:
        raise ValueError(
            "El detalle no corresponde al código solicitado."
        )

    productos = detalle.get("productos_solicitados")

    if (
        not isinstance(productos, list)
        or any(not isinstance(item, dict) for item in productos)
    ):
        raise ValueError(
            "El detalle no contiene productos_solicitados válidos."
        )

    registro = guardar_crudo(
        db,
        tipo_consulta="compra_agil_detalle",
        parametro_consulta=codigo,
        codigo=codigo,
        respuesta=respuesta,
        cantidad=1,
    )

    return registro, True


async def _ejecutar_lote_interno(
    db: Session,
    client: CompraAgilClient,
    *,
    paginas: int = 1,
    maximo_detalles: int = 3,
    pausa_entre_detalles: float = 5.0,
    region: int | None = None,
    tamano_pagina: int = 10,
) -> dict:
    if _bloqueo_lote_compra_agil.locked():
        raise EjecucionEnCursoError(
            "Ya existe una ingesta de Compras Ágiles en curso."
        )

    async with _bloqueo_lote_compra_agil:
        for nombre, valor, minimo, maximo in (
            ("paginas", paginas, 1, 10),
            ("maximo_detalles", maximo_detalles, 1, 5),
            ("tamano_pagina", tamano_pagina, 10, 50),
        ):
            if (
                not isinstance(valor, int)
                or isinstance(valor, bool)
                or not minimo <= valor <= maximo
            ):
                raise ValueError(
                    f"{nombre} debe ser un entero entre "
                    f"{minimo} y {maximo}."
                )

        if region is not None and (
            not isinstance(region, int)
            or isinstance(region, bool)
            or not 1 <= region <= 16
        ):
            raise ValueError(
                "region debe ser un entero entre 1 y 16."
            )

        if (
            isinstance(pausa_entre_detalles, bool)
            or not isinstance(pausa_entre_detalles, (int, float))
            or not math.isfinite(pausa_entre_detalles)
            or not 1 <= pausa_entre_detalles <= 300
        ):
            raise ValueError(
                "La pausa debe estar entre 1 y 300 segundos."
            )

        resultado = {
            "paginas_consultadas": 0,
            "codigos_encontrados": 0,
            "omitidos_ya_procesados": 0,
            "codigos_invalidos": 0,
            "detalles_intentados": 0,
            "descargados": 0,
            "reutilizados": 0,
            "detalles_procesados": 0,
            "compras_nuevas": 0,
            "detenido_por_limite": False,
            "detenido_por_error_api": False,
            "detenido_por_429": False,
            "listados_raw_ids": [],
            "resultados": [],
            "errores": [],
        }

        vistos = set()
        etapa = "listado"
        codigo_actual = None

        try:
            for pagina in range(1, paginas + 1):
                etapa = "listado"
                codigo_actual = None

                if pagina > 1:
                    await asyncio.sleep(pausa_entre_detalles)

                respuesta = await client.comprar_agiles(
                    region=region,
                    pagina=pagina,
                    tamano_pagina=tamano_pagina,
                )

                payload = validar_respuesta(respuesta)
                items = payload.get("items")
                paginacion = payload.get("paginacion")

                if (
                    not isinstance(items, list)
                    or any(
                        not isinstance(item, dict)
                        for item in items
                    )
                    or not isinstance(paginacion, dict)
                ):
                    raise ValueError(
                        "El listado no contiene items y paginación válidos."
                    )

                total = paginacion.get("total_resultados")

                if (
                    not isinstance(total, int)
                    or isinstance(total, bool)
                    or total < 0
                ):
                    raise ValueError(
                        "total_resultados no es un entero válido."
                    )

                listado_raw = guardar_crudo(
                    db,
                    tipo_consulta="compra_agil_listado",
                    parametro_consulta=(
                        f"estado=publicada;region={region};"
                        f"pagina={pagina};tamano_pagina={tamano_pagina}"
                    ),
                    codigo=None,
                    respuesta=respuesta,
                    cantidad=total,
                )

                resultado["paginas_consultadas"] += 1
                resultado["listados_raw_ids"].append(listado_raw.id)

                for item in items:
                    codigo = item.get("codigo")

                    if (
                        not isinstance(codigo, str)
                        or PATRON_CODIGO.fullmatch(codigo.strip()) is None
                    ):
                        resultado["codigos_invalidos"] += 1
                        continue

                    codigo = codigo.strip()

                    if codigo in vistos:
                        continue

                    vistos.add(codigo)
                    resultado["codigos_encontrados"] += 1

                    existente_id = db.scalar(
                        select(CompraAgil.id).where(
                            CompraAgil.codigo_externo == codigo
                        )
                    )

                    if existente_id is not None:
                        resultado["omitidos_ya_procesados"] += 1
                        continue

                    codigo_actual = codigo
                    etapa = "detalle"
                    resultado["detalles_intentados"] += 1

                    try:
                        registro, descargado = (
                            await obtener_o_descargar_detalle(
                                db=db,
                                client=client,
                                codigo=codigo,
                                pausa=pausa_entre_detalles,
                            )
                        )

                        if descargado:
                            resultado["descargados"] += 1
                        else:
                            resultado["reutilizados"] += 1

                        etapa = "procesamiento"

                        procesado = procesar_compra_agil_guardada(
                            db=db,
                            registro=registro,
                        )

                        db.commit()

                        resultado["detalles_procesados"] += 1
                        resultado["compras_nuevas"] += 1
                        resultado["resultados"].append(procesado)

                    except ValueError:
                        db.rollback()
                        resultado["errores"].append({
                            "etapa": etapa,
                            "codigo_externo": codigo,
                            "tipo": "datos_invalidos",
                            "mensaje": (
                                "El detalle no superó la validación. "
                                "Si se guardó el crudo, se conserva "
                                "para diagnóstico."
                            ),
                        })

                    if (
                        resultado["detalles_intentados"]
                        >= maximo_detalles
                    ):
                        resultado["detenido_por_limite"] = True
                        break

                if (
                    resultado["detenido_por_limite"]
                    or not items
                ):
                    break

                total_paginas = paginacion.get("total_paginas")

                if (
                    isinstance(total_paginas, int)
                    and not isinstance(total_paginas, bool)
                    and pagina >= total_paginas
                ):
                    break

        except httpx.HTTPStatusError as exc:
            db.rollback()
            status = exc.response.status_code

            resultado["detenido_por_error_api"] = True
            resultado["detenido_por_429"] = status == 429
            resultado["errores"].append({
                "etapa": etapa,
                "codigo_externo": codigo_actual,
                "tipo": "http_status",
                "http_status": status,
                "retry_after": exc.response.headers.get("Retry-After"),
                "mensaje": (
                    "La API rechazó una solicitud; lote detenido."
                ),
            })

        except httpx.RequestError:
            db.rollback()
            resultado["detenido_por_error_api"] = True
            resultado["errores"].append({
                "etapa": etapa,
                "codigo_externo": codigo_actual,
                "tipo": "conexion",
                "mensaje": "Falló la conexión con Compra Ágil.",
            })

        except ValueError:
            db.rollback()
            resultado["detenido_por_error_api"] = True
            resultado["errores"].append({
                "etapa": etapa,
                "codigo_externo": codigo_actual,
                "tipo": "respuesta_invalida",
                "mensaje": (
                    "La API devolvió un listado o JSON inválido."
                ),
            })

        except Exception:
            db.rollback()
            raise

        return resultado

async def ejecutar_lote_compra_agil(
    db: Session,
    client: CompraAgilClient,
    *,
    paginas: int = 1,
    maximo_detalles: int = 3,
    pausa_entre_detalles: float = 5.0,
    region: int | None = None,
    tamano_pagina: int = 10,
) -> dict:
    ejecucion = EjecucionCompraAgil(
        paginas_solicitadas=paginas,
        maximo_detalles=maximo_detalles,
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
            paginas=paginas,
            maximo_detalles=maximo_detalles,
            pausa_entre_detalles=pausa_entre_detalles,
            region=region,
            tamano_pagina=tamano_pagina,
        )

        ejecucion = db.get(EjecucionCompraAgil, ejecucion_id)

        ejecucion.fin = datetime.now(timezone.utc)
        ejecucion.paginas_consultadas = resultado["paginas_consultadas"]
        ejecucion.codigos_encontrados = resultado["codigos_encontrados"]
        ejecucion.omitidos_ya_procesados = resultado["omitidos_ya_procesados"]
        ejecucion.codigos_invalidos = resultado["codigos_invalidos"]
        ejecucion.detalles_intentados = resultado["detalles_intentados"]
        ejecucion.descargados = resultado["descargados"]
        ejecucion.reutilizados = resultado["reutilizados"]
        ejecucion.detalles_procesados = resultado["detalles_procesados"]
        ejecucion.compras_nuevas = resultado["compras_nuevas"]
        ejecucion.detenido_por_limite = resultado["detenido_por_limite"]
        ejecucion.detenido_por_error_api = resultado["detenido_por_error_api"]
        ejecucion.detenido_por_429 = resultado["detenido_por_429"]
        ejecucion.listados_raw_ids = resultado["listados_raw_ids"]
        ejecucion.resultados = resultado["resultados"]
        ejecucion.errores = resultado["errores"]

        if not resultado["errores"]:
            ejecucion.estado = "completada"
        elif resultado["detalles_procesados"] > 0:
            ejecucion.estado = "parcial"
        else:
            ejecucion.estado = "error"

        db.commit()

        resultado["ejecucion_id"] = ejecucion_id
        return resultado

    except Exception as exc:
        db.rollback()

        ejecucion = db.get(EjecucionCompraAgil, ejecucion_id)

        if ejecucion is not None:
            ejecucion.fin = datetime.now(timezone.utc)
            ejecucion.estado = "error"
            ejecucion.errores = [
                {
                    "tipo": type(exc).__name__,
                    "mensaje": "La ejecución terminó por una excepción fuera del procesamiento individual.",
                }
            ]
            db.commit()

        raise