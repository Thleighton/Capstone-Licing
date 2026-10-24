"""Persistencia documental en la base original; no depende de filtradas."""
import base64
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import HTTPException
from sqlalchemy import func, select, text, update

from ..config import settings
from ..models.licitacion import Licitacion
from ..models.licitacion_documento import LicitacionDocumento as Documento
from .revision_documental import incidencia_descarga, incidencia_documento


class StorageNoDisponible(RuntimeError):
    pass


async def storage(operacion, datos):
    if not settings.documentos_storage_url or not settings.cron_secret:
        raise StorageNoDisponible("Almacenamiento documental de origen pendiente de configurar.")
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=False) as cliente:
            r = await cliente.post(settings.documentos_storage_url,
                headers={"Authorization": "Bearer " + settings.cron_secret},
                json={"operacion": operacion, "datos": datos})
            r.raise_for_status()
            return r.json()
    except (httpx.HTTPError, ValueError):
        raise StorageNoDisponible("No se pudo acceder al Storage privado de Usuarios/Licitaciones.") from None


def versiones(db, ids):
    salida = {i: [] for i in ids}
    for lic_id, doc_id, version, huella in db.execute(select(Documento.licitacion_id,
            Documento.id, Documento.version, Documento.hash_archivo)
            .where(Documento.licitacion_id.in_(ids), Documento.vigente).order_by(Documento.id)):
        salida[lic_id].append([doc_id, version, huella])
    return salida


def cargar(db, ids):
    salida = {i: [] for i in ids}
    for doc in db.scalars(select(Documento).where(Documento.licitacion_id.in_(ids), Documento.vigente)
                          .order_by(Documento.id).execution_options(populate_existing=True)):
        texto = doc.texto_extraido or ""
        paginas = [{"pagina": p["pagina"], "texto": texto[p["inicio"]:p["fin"]]}
                   for p in doc.cobertura.get("paginas_indice", [])]
        salida[doc.licitacion_id].append({"id": doc.id, "version": doc.version,
            "hash_archivo": doc.hash_archivo, "estado_extraccion": doc.estado_extraccion,
            "nombre": doc.nombre, "cobertura": {k: v for k, v in doc.cobertura.items() if k != "paginas_indice"},
            "vigente": True, "paginas_texto": paginas})
    return salida


async def guardar(db, licitacion_id, nombre, tipo, url_origen, contenido, extraccion, actor=None, token=None):
    huella = extraccion["hash_archivo"]
    # El mismo objeto para la misma licitación y huella; la carga es idempotente.
    codigo = db.scalar(select(Licitacion.codigo_externo).where(Licitacion.id == licitacion_id))
    if codigo is None:
        raise HTTPException(404, "La licitación ya no está disponible.")
    path = f"{codigo}/{huella}.pdf"
    await storage("subir", {"path": path, "contenido_base64": base64.b64encode(contenido).decode("ascii")})
    # Serializa versiones, retiros y la baja física de la licitación.
    fila = db.scalar(select(Licitacion).where(Licitacion.id == licitacion_id)
                     .with_for_update().execution_options(populate_existing=True))
    if fila is None:
        raise HTTPException(404, "La licitación ya no está disponible.")
    if token and (fila.ingesta_documental.get("token") != token or
            datetime.fromisoformat(fila.ingesta_documental["reservada_hasta"]) <= datetime.now(timezone.utc)):
        raise HTTPException(409, "La reserva documental venció.")
    anterior = db.scalar(select(Documento).where(Documento.licitacion_id == licitacion_id,
                                               Documento.hash_archivo == huella))
    if anterior:
        if token is None:
            anterior.vigente = True
            fila.ingesta_documental = {k: v for k, v in fila.ingesta_documental.items() if k != "incidencia_documental"}
        db.commit()
        return {"id": anterior.id, "reutilizado": True}
    if token:
        db.execute(update(Documento).where(Documento.licitacion_id == licitacion_id,
            Documento.cobertura["origen_captura"].astext == "portal_bases").values(vigente=False))
    activos = db.scalar(select(func.count()).select_from(Documento).where(
        Documento.licitacion_id == licitacion_id, Documento.vigente))
    if activos >= 10:
        db.rollback()
        raise HTTPException(409, "Máximo 10 documentos activos por licitación.")
    version = db.scalar(select(func.coalesce(func.max(Documento.version), 0)).where(
        Documento.licitacion_id == licitacion_id, Documento.url_origen == url_origen)) + 1
    partes, indice, posicion = [], [], 0
    for pagina in extraccion.get("paginas_texto", []):
        texto = pagina["texto"]
        indice.append({"pagina": pagina["pagina"], "inicio": posicion, "fin": posicion + len(texto)})
        partes.append(texto)
        posicion += len(texto) + 1
    doc = Documento(licitacion_id=licitacion_id, nombre=nombre, tipo=tipo, url_origen=url_origen,
        version=version, hash_archivo=huella, storage_path=path,
        estado_extraccion=extraccion["estado_extraccion"], texto_extraido="\n".join(partes) or None,
        paginas=extraccion.get("paginas"), cobertura={**extraccion["cobertura"],
            "paginas_indice": indice, "version_extractor": extraccion["version_extractor"], "subido_por": actor},
        vigente=True)
    if token is None and "incidencia_documental" in fila.ingesta_documental:
        fila.ingesta_documental = {k: v for k, v in fila.ingesta_documental.items() if k != "incidencia_documental"}
    db.add(doc)
    db.commit()
    return {"id": doc.id, "estado_extraccion": doc.estado_extraccion}


async def detalle(db, licitacion_id):
    docs = list(db.scalars(select(Documento).where(Documento.licitacion_id == licitacion_id,
                                                  Documento.vigente).order_by(Documento.id)))
    try:
        enlaces = await storage("firmar", {"paths": [d.storage_path for d in docs]}) if docs else {}
    except StorageNoDisponible:
        enlaces = {}
    return [{"id": d.id, "nombre": d.nombre, "tipo": d.tipo, "paginas": d.paginas,
             "version": d.version, "url_origen": d.url_origen, "estado_extraccion": d.estado_extraccion,
             "incidencia": incidencia_documento({"id": d.id, "nombre": d.nombre,
                 "estado_extraccion": d.estado_extraccion, "cobertura": d.cobertura}),
             "url_descarga": enlaces.get(d.storage_path)} for d in docs]


def incidencias(db, ids):
    salida = {i: [] for i in ids}
    for lic_id, doc_id, nombre, estado, cobertura in db.execute(select(Documento.licitacion_id, Documento.id,
            Documento.nombre, Documento.estado_extraccion, Documento.cobertura)
            .where(Documento.licitacion_id.in_(ids), Documento.vigente,
                   Documento.estado_extraccion != "extraido").order_by(Documento.id)):
        salida[lic_id].append(incidencia_documento({"id": doc_id, "nombre": nombre,
            "estado_extraccion": estado, "cobertura": cobertura}))
    for lic_id, control in db.execute(select(Licitacion.id, Licitacion.ingesta_documental).where(Licitacion.id.in_(ids))):
        if control.get("incidencia_documental"):
            salida[lic_id].append(control["incidencia_documental"])
    return salida


def registrar_incidencia(db, licitacion_id, codigo, nombre=None):
    fila = db.scalar(select(Licitacion).where(Licitacion.id == licitacion_id)
                     .with_for_update().execution_options(populate_existing=True))
    if fila is None:
        raise HTTPException(404, "La licitación ya no está disponible.")
    incidencia = incidencia_descarga(codigo)
    if nombre:
        incidencia["nombre"] = nombre
    fila.ingesta_documental = {**fila.ingesta_documental, "incidencia_documental": incidencia}
    db.commit()
    return incidencia


def reservar(db):
    fila = db.execute(text("""
      SELECT id,codigo_externo,raw_id,ingesta_documental FROM public.licitacion
      WHERE coalesce(codigo_estado,5)=5 AND (fecha_cierre IS NULL OR
         fecha_cierre>clock_timestamp() AT TIME ZONE 'America/Santiago')
       AND coalesce((ingesta_documental->>'reservada_hasta')::timestamptz,'-infinity')<=clock_timestamp()
       AND (coalesce((ingesta_documental->>'proximo_intento')::timestamptz,'-infinity')<=clock_timestamp()
            OR ingesta_documental->>'raw_id' IS DISTINCT FROM raw_id::text)
      ORDER BY (ingesta_documental='{}') DESC,
       coalesce((ingesta_documental->>'ultimo_intento')::timestamptz,'-infinity'),id
      LIMIT 1 FOR UPDATE SKIP LOCKED
    """)).mappings().first()
    if not fila:
        db.rollback()
        return None
    from uuid import uuid4
    ahora = datetime.now(timezone.utc)
    control = {**fila["ingesta_documental"], "token": str(uuid4()), "estado": "procesando",
        "reservada_hasta": (ahora + timedelta(minutes=2)).isoformat(), "ultimo_intento": ahora.isoformat(),
        "intentos": fila["ingesta_documental"].get("intentos", 0) + 1, "raw_id": fila["raw_id"]}
    db.execute(update(Licitacion).where(Licitacion.id == fila["id"]).values(ingesta_documental=control))
    hashes = list(db.scalars(select(Documento.hash_archivo).where(Documento.licitacion_id == fila["id"])))
    db.commit()
    return {"id": fila["id"], "codigo": fila["codigo_externo"], "token": control["token"], "hashes": hashes}


def finalizar(db, tarea, estado):
    fila = db.scalar(select(Licitacion).where(Licitacion.id == tarea["id"])
                     .with_for_update().execution_options(populate_existing=True))
    if not fila or fila.ingesta_documental.get("token") != tarea["token"]:
        db.rollback()
        return
    control = {k: v for k, v in fila.ingesta_documental.items() if k not in {"token", "reservada_hasta"}}
    if estado == "descargada":
        control.pop("incidencia_documental", None)
    else:
        control["incidencia_documental"] = incidencia_descarga(estado)
    horas = 168 if estado == "descargada" else 24 if estado != "error_temporal" or control["intentos"] >= 3 else 1
    ahora = datetime.now(timezone.utc)
    fila.ingesta_documental = {**control, "estado": estado, "anexos_completos": False,
        "finalizado_en": ahora.isoformat(), "proximo_intento": (ahora + timedelta(hours=horas)).isoformat()}
    db.commit()
