"""Preselección explicable y documentos del hotel."""
import asyncio
import hashlib
import json
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..auth import solo_cron, usuario_actual
from ..config import settings
from ..database import get_db
from ..models.licitacion import Licitacion
from ..models.licitacion_item import LicitacionItem
from ..models.raw import RawMercadoPublico
from ..models.licitacion_documento import LicitacionDocumento
from ..services import filtradas, documentos_origen
from ..services.enlaces import ficha_oficial
from ..services.preseleccion import cargar_catalogo, evaluar_preseleccion, evaluar_vigencia, CHILE, VERSION_MOTOR
from ..services.clientes_importantes import identificar_clientes_importantes
from ..services.fechas_consulta import filtrar_cierre

router = APIRouter(prefix="/api/preseleccion", tags=["Preselección"])


def serializable(valor):
    if isinstance(valor, datetime):
        return (valor.replace(tzinfo=CHILE) if valor.tzinfo is None else valor).isoformat()
    if isinstance(valor, Decimal):
        return str(valor)
    raise TypeError(type(valor).__name__)


def cargar_entradas(db, ids):
    if not ids:
        return {}
    filas = db.scalars(select(Licitacion).where(Licitacion.id.in_(ids))).all()
    entradas = {}
    versiones = documentos_origen.versiones(db, ids)
    verificaciones = dict(db.execute(select(RawMercadoPublico.id, RawMercadoPublico.verificado_en)
        .where(RawMercadoPublico.id.in_({f.raw_id for f in filas}))).all())
    for fila in filas:
        datos = {c.name: getattr(fila, c.name) for c in Licitacion.__table__.columns if c.name != "ingesta_documental"}
        datos.update(items=[], documentos_version=versiones[fila.id], url_oficial=ficha_oficial(fila.codigo_externo),
                     fuente_verificada_en=verificaciones.get(fila.raw_id))
        if fila.ingesta_documental.get("incidencia_documental"):
            datos["incidencia_documental"] = fila.ingesta_documental["incidencia_documental"]
        entradas[fila.id] = datos
    for item in db.scalars(select(LicitacionItem).where(LicitacionItem.licitacion_id.in_(ids))
                           .order_by(LicitacionItem.licitacion_id, LicitacionItem.posicion_fuente)):
        entradas[item.licitacion_id]["items"].append({c.name: getattr(item, c.name)
                                                    for c in LicitacionItem.__table__.columns})
    return json.loads(json.dumps(entradas, default=serializable))


def firma_fuente(datos):
    estables = {k: v for k, v in datos.items() if k not in {"fuente_verificada_en", "normalizado_en"}}
    estables.update(version_motor=VERSION_MOTOR, catalogo_version=cargar_catalogo()["version"])
    return hashlib.sha256(json.dumps(estables, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


async def evaluar_lote(db, ids, actor=None, documentos_extra=None):
    ids = list(dict.fromkeys(ids))
    entradas = cargar_entradas(db, ids)
    if len(entradas) != len(set(ids)):
        raise HTTPException(404, "Alguna licitación ya no está disponible. Actualiza la lista.")
    documentos_persistidos = documentos_origen.cargar(db, ids)
    controles = dict(db.execute(select(Licitacion.id, Licitacion.ingesta_documental)
                                .where(Licitacion.id.in_(ids))).all())
    documentos_cache = {i: list((controles.get(i) or {}).get("documentos_analizados", [])) for i in ids}
    documentos_extra = documentos_extra or {}
    lote = []
    documentos_pendientes_auto = []
    ahora_cache = datetime.now(timezone.utc)
    for datos in entradas.values():
        lic_id = datos["id"]
        persistidos = documentos_persistidos.get(lic_id, [])
        control = controles.get(lic_id) or {}
        try:
            expira_cache = datetime.fromisoformat(control["analisis_documental_expira_en"])
            if expira_cache.tzinfo is None:
                expira_cache = expira_cache.replace(tzinfo=timezone.utc)
            cache_valida = (str(control.get("analisis_documental_raw_id")) == str(datos["raw_id"])
                and expira_cache > ahora_cache)
        except (KeyError, TypeError, ValueError):
            cache_valida = False
        cache = documentos_cache.get(lic_id, []) if cache_valida else []
        extra = documentos_extra.get(lic_id, [])
        reemplazos = {str(d.get("id")): d for d in [*cache, *extra]}
        docs = [*persistidos, *[d for d in reemplazos.values()
                               if str(d.get("id")) not in {str(p.get("id")) for p in persistidos}]]
        entrada = {**datos, "documentos": docs}
        resultado = evaluar_preseleccion(entrada)
        necesita_documentos = (resultado.get("clasificacion") == "preseleccionada" or
            (resultado.get("clasificacion") == "revision_manual" and
             (resultado.get("pilar_decisivo") in {"ubicacion", "pertinencia", "documentacion"} or resultado.get("entrada_parcial"))))
        en_cola = control.get("analisis_documental_estado") in {"pendiente", "procesando"}
        if necesita_documentos and not cache_valida and not en_cola:
            documentos_pendientes_auto.append(lic_id)
        # No duplicar RAW ni PDF completos en las evaluaciones: conservar referencias y evidencias.
        firma = firma_fuente(datos)
        lote.append({"datos": datos, "resultado": resultado, "hash_fuente": firma,
                     "documentos_version": [[d["id"], d.get("version", 1), d.get("hash_archivo", "")]
                                             for d in docs]})
    actuales = dict(db.execute(select(Licitacion.id, Licitacion.raw_id).where(Licitacion.id.in_(ids))).all())
    if any(actuales.get(d["id"]) != d["raw_id"] for d in entradas.values()):
        raise HTTPException(409, "La fuente cambió durante la evaluación. Actualiza y vuelve a intentarlo.")
    versiones = documentos_origen.versiones(db, ids)
    if any(versiones[i] != [[d["id"], d["version"], d["hash_archivo"]]
                            for d in documentos_persistidos.get(i, [])] for i in ids):
        raise HTTPException(409, "Los documentos cambiaron durante la evaluación. Vuelve a intentarlo.")
    observado_en = datetime.now(timezone.utc).isoformat()
    codigos_vigentes = list(db.scalars(select(Licitacion.codigo_externo)))
    await filtradas.operar("sincronizar_fuente", {"codigos": codigos_vigentes, "observado_en": observado_en})
    # La persistencia admite 20 entradas. Se carga y comprueba la fuente una sola
    # vez y se mantienen como máximo dos peticiones de guardado en curso.
    semaforo = asyncio.Semaphore(2)
    async def guardar(parte):
        async with semaforo:
            return await filtradas.operar("guardar", {"lote": parte, "perfil": cargar_catalogo(), "actor": actor})
    respuestas = await asyncio.gather(*(guardar(lote[i:i+20]) for i in range(0, len(lote), 20)),
                                     return_exceptions=True)
    for respuesta in respuestas:
        if isinstance(respuesta, BaseException):
            raise respuesta
    return {"evaluadas": [e for r in respuestas for e in r.get("evaluadas", [])],
            "documentos_pendientes_auto": documentos_pendientes_auto}


class Lote(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ids: list[Annotated[int, Field(strict=True, gt=0)]] = Field(min_length=1, max_length=100)


class Revision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    evaluacion_id: Annotated[int, Field(strict=True, gt=0)]
    accion: Literal["confirmar_relevante", "descartar", "mantener_pendiente"]
    categoria_motivo: Literal["servicio", "capacidad", "ubicacion", "plazo", "documentos", "presupuesto", "otro"]
    motivo: str = Field(min_length=5, max_length=1500)


@router.get("/integracion/verificar", dependencies=[Depends(solo_cron)], include_in_schema=False)
def verificar_integracion():
    # La función del segundo proyecto valida aquí la credencial privada existente.
    return {"autorizada": True}


@router.get("", dependencies=[Depends(usuario_actual)])
async def listar(response: Response, background: BackgroundTasks, clasificacion: str = Query(default="", max_length=30),
                 q: str = Query(default="", max_length=150), limite: int = Query(default=25, ge=1, le=100),
                 offset: int = Query(default=0, ge=0), db: Session = Depends(get_db),
                 cierre_desde: date | None = None, cierre_hasta: date | None = None,
                 region: str = Query(default="", max_length=200), solo_abiertas: bool = False,
                 codigo: str = Query(default="", max_length=50)):
    consulta = filtrar_cierre(select(Licitacion.codigo_externo, Licitacion.raw_id),
                             Licitacion.fecha_cierre, cierre_desde, cierre_hasta)
    if q.strip():
        consulta = consulta.where(or_(*[
            func.lower(func.coalesce(campo, "")).contains(q.strip().lower(), autoescape=True)
            for campo in (Licitacion.codigo_externo, Licitacion.nombre,
                          Licitacion.nombre_organismo, Licitacion.nombre_unidad)
        ]))
    if codigo.strip():
        consulta = consulta.where(func.lower(func.coalesce(Licitacion.codigo_externo, "")).contains(
            codigo.strip().lower(), autoescape=True))
    if region.strip():
        consulta = consulta.where(func.lower(func.coalesce(Licitacion.region_comprador, "")).contains(
            region.strip().lower(), autoescape=True))
    if solo_abiertas:
        ahora = datetime.now(CHILE).replace(tzinfo=None)
        consulta = consulta.where(
            func.lower(func.coalesce(Licitacion.estado, "")) == "publicada",
            or_(Licitacion.fecha_cierre.is_(None), Licitacion.fecha_cierre >= ahora),
        )
    fuentes = dict(db.execute(consulta).all())
    codigos = list(fuentes)
    respuesta = await filtradas.operar("listar", {"codigos": codigos, "fuentes": fuentes, "clasificacion": clasificacion,
                                                   "q": "", "limite": limite, "offset": offset})
    actuales = dict(db.execute(select(Licitacion.id, Licitacion.raw_id)).all())
    filas_vistas = respuesta.get("filas", [])
    ids_vistos = [int(f["id"]) for f in filas_vistas]
    entradas_actuales = cargar_entradas(db, ids_vistos)
    controles_vistos = {lic_id: (raw_id, control) for lic_id, raw_id, control in db.execute(
        select(Licitacion.id, Licitacion.raw_id, Licitacion.ingesta_documental)
        .where(Licitacion.id.in_(ids_vistos))).all()} if ids_vistos else {}
    hallazgos_legacy = documentos_origen.hallazgos_persistidos(db, ids_vistos) if ids_vistos else {}
    ahora = datetime.now(timezone.utc)
    from ..services.ingesta_documental import ANALISIS_DOCUMENTAL_VERSION
    documentos_a_encolar = []
    for fila in filas_vistas:
        entrada = entradas_actuales.get(str(fila["id"]), {})
        fila.update({campo: entrada.get(campo) for campo in (
            "nombre_organismo", "nombre_unidad", "descripcion", "monto_estimado", "moneda",
            "estimacion", "visibilidad_monto", "fecha_publicacion", "fecha_cierre", "tipo", "estado",
            "region_comprador", "comuna_comprador",
        )})
        fila["clientes_importantes"] = identificar_clientes_importantes(entrada)
        raw_actual, control = controles_vistos.get(int(fila["id"]), (None, {}))
        control = control or {}
        cache_valida = False
        try:
            vence = datetime.fromisoformat(control["analisis_documental_expira_en"])
            if vence.tzinfo is None:
                vence = vence.replace(tzinfo=timezone.utc)
            cache_valida = (str(raw_actual) == str(control.get("analisis_documental_raw_id")) and
                            control.get("analisis_documental_version") == ANALISIS_DOCUMENTAL_VERSION and
                            vence > ahora)
            if cache_valida:
                fila["hallazgos_documentales"] = control.get("hallazgos_documentales", [])
        except (KeyError, TypeError, ValueError):
            pass
        if not fila.get("hallazgos_documentales"):
            fila["hallazgos_documentales"] = hallazgos_legacy.get(int(fila["id"]), [])
        incidencia = control.get("incidencia_documental") or {}
        incidencia_antigua = (incidencia.get("codigo") == "sin_descarga_publica" or
            (incidencia.get("codigo") == "sin_documentos" and not (
                control.get("documentos_adjuntos_detectados") or control.get("documentos_adjuntos_url"))))
        lista_no_verificada_expirada = (incidencia.get("codigo") == "lista_adjuntos_no_detectada" and
                                        not cache_valida)
        en_cola = control.get("analisis_documental_estado") in {"pendiente", "procesando"}
        motor_antiguo = (control.get("analisis_documental_estado") in
            {"completado", "sin_documentos", "error_temporal", "captcha"} and
            control.get("analisis_documental_version") != ANALISIS_DOCUMENTAL_VERSION)
        estado_candidato = fila.get("estado_seleccion")
        if (settings.documentos_automaticos and not en_cola and
                ((estado_candidato == "preseleccionada" and not cache_valida) or
                 incidencia_antigua or lista_no_verificada_expirada or
                 (estado_candidato == "revision_manual" and motor_antiguo))):
            documentos_a_encolar.append(int(fila["id"]))
        if (actuales.get(fila["id"]) != fila.get("fuente_raw_id") or
                fila.get("hash_fuente") != firma_fuente(entradas_actuales.get(str(fila["id"]), {}))):
            fila.update(estado_seleccion="pendiente_evaluacion", motivo_seleccion="La fuente cambió; actualiza la preselección.")
    if documentos_a_encolar:
        from ..services.ingesta_documental import encolar_analisis_documental, procesar_cola_analisis_documental
        await encolar_analisis_documental(documentos_a_encolar)
        background.add_task(procesar_cola_analisis_documental, 3)
    respuesta["ids_fuente"] = list(db.scalars(select(Licitacion.id).order_by(Licitacion.id)))
    response.headers["Cache-Control"] = "no-store"
    return respuesta


@router.post("/evaluar")
async def evaluar(entrada: Lote, background: BackgroundTasks,
                  usuario=Depends(usuario_actual), db: Session = Depends(get_db)):
    actor = str(UUID(usuario["id"]))
    resultado = await evaluar_lote(db, entrada.ids, actor)
    candidatos = resultado.pop("documentos_pendientes_auto", [])
    if candidatos and settings.documentos_automaticos:
        from ..services.ingesta_documental import encolar_analisis_documental, procesar_cola_analisis_documental
        await encolar_analisis_documental(candidatos)
        background.add_task(procesar_cola_analisis_documental, 3, actor)
    resultado["analisis_documental_programado"] = len(candidatos) if settings.documentos_automaticos else 0
    return resultado


@router.get("/plan", dependencies=[Depends(usuario_actual)])
async def plan(response: Response, db: Session = Depends(get_db)):
    """Evalúa al cambiar la fuente o las reglas; conserva resultados y revisiones vigentes."""
    ids = list(db.scalars(select(Licitacion.id).order_by(Licitacion.id)))
    entradas = cargar_entradas(db, ids)
    fuentes = {d["codigo_externo"]: d["raw_id"] for d in entradas.values()}
    guardadas = {}
    for offset in range(0, len(ids), 100):
        pagina = await filtradas.operar("listar", {"codigos": list(fuentes), "fuentes": fuentes,
            "limite": 100, "offset": offset})
        guardadas.update({str(f["id"]): f for f in pagina.get("filas", [])})
    pendientes = [int(i) for i, d in entradas.items()
        if guardadas.get(i, {}).get("hash_fuente") != firma_fuente(d)
        or guardadas.get(i, {}).get("estado_seleccion") == "pendiente_evaluacion"]
    response.headers["Cache-Control"] = "no-store"
    return {"ids": pendientes, "total": len(ids), "version_motor": VERSION_MOTOR}


@router.post("/documentos/obtener")
async def obtener_documentos(usuario=Depends(usuario_actual), db: Session = Depends(get_db)):
    from ..services.ingesta_documental import procesar_documentos
    return await procesar_documentos(db, str(UUID(usuario["id"])))


@router.get("/pendientes-documentales", dependencies=[Depends(usuario_actual)])
def pendientes_documentales(response: Response, limite: int = Query(default=25, ge=1, le=100),
                            offset: int = Query(default=0, ge=0), db: Session = Depends(get_db)):
    # Lee la fuente original: también funciona si filtradas todavía no se ha evaluado o no responde.
    fuentes = list(db.execute(select(Licitacion.id, Licitacion.codigo_externo, Licitacion.nombre,
        Licitacion.fecha_cierre, Licitacion.codigo_estado, Licitacion.estado)
        .order_by(Licitacion.fecha_cierre.asc().nulls_last(), Licitacion.id)).mappings())
    incidencias = documentos_origen.incidencias(db, [f["id"] for f in fuentes])
    ahora = datetime.now(CHILE)
    filas = []
    for f in fuentes:
        fallos = incidencias[f["id"]]
        if not fallos or evaluar_vigencia(dict(f), ahora)["resultado"] == "no_cumple":
            continue
        filas.append({**dict(f), "fecha_cierre": serializable(f["fecha_cierre"]) if f["fecha_cierre"] else None,
            "estado_seleccion": "revision_manual", "url_oficial": ficha_oficial(f["codigo_externo"]),
            "motivo_seleccion": fallos[0]["motivo"], "incidencias_documentales": fallos})
    response.headers["Cache-Control"] = "no-store"
    return {"filas": filas[offset:offset+limite], "total": len(filas), "ids_fuente": [f["id"] for f in fuentes]}


@router.get("/exportar.xlsx", dependencies=[Depends(usuario_actual)])
async def exportar_excel(db: Session = Depends(get_db)):
    from starlette.concurrency import run_in_threadpool
    from ..services.exportacion_oportunidades import crear_excel, HOJAS

    ids = list(db.scalars(select(Licitacion.id).order_by(Licitacion.id)))
    entradas = await run_in_threadpool(cargar_entradas, db, ids)
    fuentes = {d["codigo_externo"]: d["raw_id"] for d in entradas.values()}
    guardadas = {}
    for offset in range(0, len(ids), 100):
        pagina = await filtradas.operar("listar", {"codigos": list(fuentes), "fuentes": fuentes,
            "limite": 100, "offset": offset})
        guardadas.update({str(f["id"]): f for f in pagina.get("filas", [])})
    filas = []
    for identificador, datos in entradas.items():
        guardada = guardadas.get(identificador, {})
        estado = guardada.get("estado_seleccion")
        if (estado not in HOJAS or guardada.get("fuente_raw_id") != datos["raw_id"]
                or guardada.get("codigo_externo") != datos["codigo_externo"]
                or guardada.get("hash_fuente") != firma_fuente(datos)):
            estado = "revision_manual"
        filas.append({**datos, "estado_seleccion": estado})
    contenido = await run_in_threadpool(crear_excel, filas)
    fecha = datetime.now(CHILE).strftime("%Y-%m-%d")
    return Response(contenido,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="LICING-oportunidades-{fecha}.xlsx"',
                 "Cache-Control": "no-store"})


@router.get("/{licitacion_id}", dependencies=[Depends(usuario_actual)])
async def detalle(licitacion_id: int, response: Response, background: BackgroundTasks,
                  db: Session = Depends(get_db)):
    fila = db.get(Licitacion, licitacion_id)
    if fila is None:
        raise HTTPException(404, "La licitación ya no está disponible.")
    control_actual = fila.ingesta_documental or {}
    incidencia_actual = control_actual.get("incidencia_documental") or {}
    from ..services.ingesta_documental import ANALISIS_DOCUMENTAL_VERSION
    motor_antiguo = (control_actual.get("analisis_documental_estado") in
        {"completado", "sin_documentos", "error_temporal", "captcha"} and
        control_actual.get("analisis_documental_version") != ANALISIS_DOCUMENTAL_VERSION)
    try:
        vence_analisis = datetime.fromisoformat(control_actual.get("analisis_documental_expira_en", ""))
        if vence_analisis.tzinfo is None:
            vence_analisis = vence_analisis.replace(tzinfo=timezone.utc)
        cache_analisis_activa = (str(control_actual.get("analisis_documental_raw_id")) == str(fila.raw_id) and
            control_actual.get("analisis_documental_version") == ANALISIS_DOCUMENTAL_VERSION and
            vence_analisis > datetime.now(timezone.utc))
    except (TypeError, ValueError):
        cache_analisis_activa = False
    documentos_desactualizados = (incidencia_actual.get("codigo") == "sin_descarga_publica" or
        (incidencia_actual.get("codigo") == "sin_documentos" and not (
            control_actual.get("documentos_adjuntos_detectados") or control_actual.get("documentos_adjuntos_url"))) or motor_antiguo or
        (incidencia_actual.get("codigo") == "lista_adjuntos_no_detectada" and not cache_analisis_activa))
    if (settings.documentos_automaticos and documentos_desactualizados and
            control_actual.get("analisis_documental_estado") not in {"pendiente", "procesando"}):
        from ..services.ingesta_documental import encolar_analisis_documental, procesar_cola_analisis_documental
        await encolar_analisis_documental([licitacion_id])
        db.refresh(fila)
        background.add_task(procesar_cola_analisis_documental, 1)
    try:
        resultado = await filtradas.operar("detalle", {"codigo": fila.codigo_externo})
    except filtradas.FiltradasNoDisponible:
        resultado = {"evaluacion": None, "criterios": [], "hash_fuente": None}
    resultado["documentos"] = await documentos_origen.detalle(db, licitacion_id)
    resultado["ingesta_documental"] = {k: v for k, v in fila.ingesta_documental.items() if k != "token"}
    resultado["incidencias_documentales"] = documentos_origen.incidencias(db, [licitacion_id])[licitacion_id]
    resultado["fuente_actualizada"] = resultado.get("hash_fuente") == firma_fuente(cargar_entradas(db, [licitacion_id])[str(licitacion_id)])
    response.headers["Cache-Control"] = "no-store"
    return resultado


@router.post("/{licitacion_id}/documentos/analizar")
async def analizar_documentos_licitacion(licitacion_id: int, usuario=Depends(usuario_actual), db: Session = Depends(get_db)):
    if db.get(Licitacion, licitacion_id) is None:
        raise HTTPException(404, "La licitación ya no está disponible.")
    from ..services.ingesta_documental import analizar_documentos_temporal
    resultado = await analizar_documentos_temporal(db, licitacion_id, str(UUID(usuario["id"])))
    resultado["detalle"] = await documentos_origen.detalle(db, licitacion_id)
    return resultado


@router.post("/{licitacion_id}/revision")
async def revisar(licitacion_id: int, entrada: Revision, usuario=Depends(usuario_actual), db: Session = Depends(get_db)):
    fila = db.get(Licitacion, licitacion_id)
    if fila is None:
        raise HTTPException(404, "La licitación ya no está disponible.")
    return await filtradas.operar("revision", {**entrada.model_dump(), "codigo": fila.codigo_externo,
                                              "raw_id": fila.raw_id, "hash_fuente": firma_fuente(cargar_entradas(db, [licitacion_id])[str(licitacion_id)]), "usuario": str(UUID(usuario["id"]))})


@router.post("/{licitacion_id}/documentos")
async def documento(licitacion_id: int, usuario=Depends(usuario_actual), db: Session = Depends(get_db)):
    fila = db.get(Licitacion, licitacion_id)
    if fila is None:
        raise HTTPException(404, "La licitación ya no está disponible.")
    raise HTTPException(410,
        "LICING ya no recibe documentos para guardarlos. Las bases públicas se analizan temporalmente desde Mercado Público.")


@router.get("/{licitacion_id}/documentos/{documento_id}/texto")
async def texto_documento(licitacion_id: int, documento_id: int, usuario=Depends(usuario_actual), db: Session = Depends(get_db)):
    raise HTTPException(410, "El texto se consulta en la revisión temporal; LICING ya no lo sirve desde su Storage.")


@router.delete("/{licitacion_id}/documentos/{documento_id}")
async def retirar_documento(licitacion_id: int, documento_id: int, usuario=Depends(usuario_actual), db: Session = Depends(get_db)):
    fila = db.get(Licitacion, licitacion_id)
    if fila is None:
        raise HTTPException(404, "La licitación ya no está disponible.")
    doc = db.scalar(select(LicitacionDocumento).where(LicitacionDocumento.id == documento_id,
                                                     LicitacionDocumento.licitacion_id == licitacion_id))
    if not doc:
        raise HTTPException(404, "Documento no encontrado en esta licitación.")
    doc.vigente = False
    db.commit()
    try:
        return await evaluar_lote(db, [licitacion_id], str(UUID(usuario["id"])))
    except filtradas.FiltradasNoDisponible:
        return {"pendiente": True, "retirado": True}
