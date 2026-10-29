"""Descarga a la capa original; la preselección posterior es independiente."""
import asyncio
import hashlib
import re
from datetime import datetime, timedelta, timezone

from starlette.concurrency import run_in_threadpool

from ..database import SessionLocal
from ..config import settings
from . import bases_mercado_publico as portal
from . import documentos_origen as origen
from .bases_mercado_publico import BasesNoDisponibles
from .lectura_office import extraer_office
from .pdf_bases import extraer_pdf

# No empezar otro archivo con menos tiempo que esto: descarga, lectura y guardado.
MARGEN_DOCUMENTO = 7
# Fallos que afectan a la ficha completa: el turno termina y no se insiste ante límites del portal.
DETIENEN_TURNO = {"acceso_restringido", "error_temporal", "redireccion_no_admitida",
                  "demasiadas_redirecciones", "respuesta_invalida"}
ADVERTENCIAS = {
    "portal_bases": "PDF principal del portal; anexos adicionales no comprobados.",
    "portal_anexos": "Anexo de «Antecedentes para incluir en la oferta»; los archivos adjuntos protegidos no se consultan.",
}
MAX_DOCUMENTOS_ANALISIS = 6
MAX_BYTES_ANALISIS = 12 * 1024 * 1024
ANALISIS_DOCUMENTAL_VERSION = 6
MAX_SNIPPETS_POR_DOCUMENTO = 6
MAX_CARACTERES_POR_DOCUMENTO = 3000
TERMINOS_RELEVANTES = re.compile(
    r"\b(cantidades?|unidades?|personas?|asistentes?|participantes?|comuna|direcci[oó]n|"
    r"lugar|sal[oó]n|sal[oó]nes|evento|banqueter[ií]a|catering|coffee|alimentaci[oó]n|"
    r"alojamiento|traslado|hospedaje|servicio|entrega|fecha|horario|capacidad|"
    r"montaje|desayuno|almuerzo|cena|coffee\s*break)\b", re.I)


def _recortar_paginas(paginas):
    """Retiene pasajes breves para recalcular/evidenciar; nunca el texto completo del anexo."""
    salida, total = [], 0
    for pagina in paginas or []:
        texto = " ".join((pagina.get("texto") or "").split())
        if not texto:
            continue
        matches = list(TERMINOS_RELEVANTES.finditer(texto))
        ventanas = []
        for match in matches:
            inicio, fin = max(0, match.start() - 180), min(len(texto), match.end() + 260)
            if ventanas and inicio <= ventanas[-1][1]:
                ventanas[-1] = (ventanas[-1][0], max(ventanas[-1][1], fin))
            else:
                ventanas.append((inicio, fin))
        if not ventanas and not salida:
            ventanas = [(0, min(len(texto), 320))]
        for inicio, fin in ventanas:
            if len(salida) >= MAX_SNIPPETS_POR_DOCUMENTO or total >= MAX_CARACTERES_POR_DOCUMENTO:
                break
            fragmento = texto[inicio:fin][:MAX_CARACTERES_POR_DOCUMENTO - total]
            salida.append({"pagina": pagina["pagina"], "texto": fragmento})
            total += len(fragmento)
        if len(salida) >= MAX_SNIPPETS_POR_DOCUMENTO or total >= MAX_CARACTERES_POR_DOCUMENTO:
            break
    return salida


def _hallazgos_operativos(paginas):
    """Resume demanda práctica con página y cita; se ejecuta sobre texto transitorio."""
    textos = [(p.get("pagina"), " ".join((p.get("texto") or "").split())) for p in paginas or []]
    completo = " ".join(t for _, t in textos)
    hallazgos = {}

    def evidencia(patron, flags=re.I):
        for pagina, texto in textos:
            m = re.search(patron, texto, flags)
            if m:
                inicio, fin = max(0, m.start() - 110), min(len(texto), m.end() + 180)
                return {"pagina": pagina, "texto": texto[inicio:fin]}
        return None

    patron_asistentes = r"\b(\d{1,5})\s+(?:personas?|asistentes?|participantes?|funcionarios?|profesionales?|cupos?)\b"
    por_dia = re.search(patron_asistentes + r"\s+por\s+d[ií]a\b", completo, re.I)
    asistentes = re.search(patron_asistentes, completo, re.I)
    cantidades = [int(n) for n in re.findall(patron_asistentes, completo, re.I)]
    if por_dia or cantidades:
        dia = int(por_dia.group(1)) if por_dia else None
        total = int(asistentes.group(1)) if asistentes else (cantidades[0] if cantidades else None)
        cita = evidencia(patron_asistentes + r"(?:\s+por\s+d[ií]a)?")
        hallazgos["participantes"] = {"total": total, "por_dia": dia,
            "resumen": (f"{total} en total · {dia} por día" if total and dia else
                        f"{dia} por día" if dia else f"{total} personas"),
            "evidencia": cita}

    region_match = re.search(r"\bRegi[oó]n\s+(?:del?\s+|de la\s+)?([A-ZÁ-Ú][A-Za-zÁ-ú\s]{2,30}?)(?=\s*[-,;.]|\s+Cantidad\b|$)", completo)
    region = " ".join(region_match.group(1).split()).strip() if region_match else None
    lugar = {}
    if region:
        cita_region = evidencia(r"\bRegi[oó]n\s+(?:del?\s+|de la\s+)?[A-ZÁ-Ú][A-Za-zÁ-ú\s]{2,30}")
        lugar.update(region=region, fuera_zona_rm=not bool(re.search(r"metropolitana", region, re.I)), evidencia=cita_region)
    talca = evidencia(r"\bTalca\b")
    if talca:
        lugar.update(comuna="Talca", referencia_talca=True)
        lugar.setdefault("evidencia_referencia", talca)
    direccion = evidencia(r"\b\d+\s+Oriente\b.{0,120}(?:Edificio|Regi[oó]n)")
    if direccion:
        lugar["direccion_referencial"] = direccion["texto"]
        lugar["evidencia_direccion"] = direccion
    if lugar:
        lugar["resumen"] = ", ".join(x for x in (lugar.get("comuna"),
            f"Región del {region}" if region and region.lower() not in {"metropolitana", "de santiago"} else region) if x)
        hallazgos["ubicacion"] = lugar

    fecha_patron = (r"\b(?:los?\s+)?d[ií]as?\s+\d{1,2}(?:\s*(?:y|al|a|-)\s*\d{1,2})?"
                    r"\s+de\s+[A-Za-zÁ-ú]+(?:\s+de\s+20\d{2})?\b")
    fecha = evidencia(fecha_patron)
    fecha_resumen = next((m.group(0) for _, texto in textos
                          if (m := re.search(fecha_patron, texto, re.I))), None)
    if not fecha:
        # Otras bases usan fecha numérica; exigir contexto de la actividad evita
        # confundirla con fechas de publicación o cierre de ofertas.
        fecha_patron = (r"\b(?:actividad|evento|curso|jornada|se realizar[aá])\b.{0,100}"
                        r"\b\d{1,2}[/-]\d{1,2}[/-]20\d{2}\b")
        fecha = evidencia(fecha_patron)
        fecha_resumen = next((m.group(0) for _, texto in textos
                              if (m := re.search(fecha_patron, texto, re.I))), None)
    if fecha:
        hallazgos["fechas"] = {"resumen": fecha_resumen, "evidencia": fecha}

    horario = evidencia(r"\b(?:de|desde las?)\s+\d{1,2}(?::\d{2})?\s*(?:hrs?\.?|h)?\s*(?:a|hasta|y)\s+"
                        r"\d{1,2}(?::\d{2})?\s*(?:hrs?\.?|h)\b")
    if not horario:
        horario = evidencia(r"\b(?:horario|jornada)\b.{0,80}\b\d{1,2}:\d{2}\b")
    if horario:
        hallazgos["horario"] = {"resumen": horario["texto"], "evidencia": horario}

    duracion = evidencia(r"\b(?:duraci[oó]n|durante|por)\s+(\d{1,2})\s+(d[ií]as?|jornadas?)\b")
    if duracion:
        hallazgos["duracion"] = {"resumen": duracion["texto"], "evidencia": duracion}

    servicios = []
    for patron, etiqueta in ((r"arriendo\s+de\s+sal(?:a|o)n(?:es)?", "Arriendo de salón"),
                             (r"coffee\s*break|coffe(?:e)?s?\b", "Coffee break"),
                             (r"almuerzos?", "Almuerzos"),
                             (r"banqueter[ií]a|catering", "Banquetería / catering")):
        if re.search(patron, completo, re.I) and etiqueta not in servicios:
            servicios.append(etiqueta)
    if servicios:
        hallazgos["servicios"] = servicios

    presupuesto = evidencia(r"\b(?:presupuesto|monto|valor|disponible|total)\b.{0,70}(?:\$\s*[\d.]{4,}|[\d.]{4,}\s*(?:pesos|CLP|UTM))|"
                            r"\$\s*[\d.]{4,}.{0,60}\b(?:presupuesto|monto|valor|impuestos? incluidos)\b")
    if presupuesto:
        monto = re.search(r"\$\s*([\d.]{4,})|\b([\d.]{4,})\s*(?:pesos|CLP|UTM)\b", presupuesto["texto"], re.I)
        if monto:
            cantidad = monto.group(1) or monto.group(2)
            hallazgos["presupuesto"] = {"monto": cantidad, "resumen": f"${cantidad}",
                "evidencia": presupuesto}
    return hallazgos


def _doc_temporal(descarga, extraccion):
    huella = extraccion["hash_archivo"]
    identificador = "mp-" + huella[:20]
    compacto = _recortar_paginas(extraccion.get("paginas_texto"))
    hallazgos = _hallazgos_operativos(extraccion.get("paginas_texto"))
    cobertura = {k: v for k, v in extraccion["cobertura"].items() if k != "paginas_indice"}
    doc_eval = {"id": identificador, "version": 1, "hash_archivo": huella,
        "nombre": descarga["nombre"], "estado_extraccion": extraccion["estado_extraccion"],
        "cobertura": cobertura, "vigente": True,
        "paginas_texto": extraccion.get("paginas_texto", []), "hallazgos": hallazgos}
    doc_cache = {**doc_eval, "paginas_texto": compacto, "temporal": True,
        "url_origen": descarga["url_origen"], "formato": descarga["extension"],
        "paginas": extraccion.get("paginas"), "hallazgos": hallazgos}
    return doc_eval, doc_cache


async def analizar_documentos_temporal(db, licitacion_id, actor=None, automatico=False):
    """Analiza pocos anexos en memoria y conserva solo pasajes compactos y trazables."""
    from sqlalchemy import select
    from ..models.licitacion import Licitacion
    fila = db.get(Licitacion, licitacion_id)
    if fila is None:
        return {"pendiente": True, "motivo": "licitacion_no_disponible"}
    capturados, cacheados, vistos, total_bytes = [], [], set(), 0
    documentos_observados = []
    incidencias, captcha = [], False
    try:
        async with asyncio.timeout(50), portal.sesion() as cliente:
            ficha = await portal.abrir_ficha(cliente, fila.codigo_externo)
            adjuntos_ingresados, antecedentes, bases = [], [], []
            if ficha.boton:
                bases.append(("bases", None))
            if not ficha.adjuntos_url:
                # Sin la URL de ViewAttachmentLC no se ha consultado la grilla de
                # «Anexos ingresados»: no afirmar que la ficha carece de documentos.
                incidencias.append({"codigo": "lista_adjuntos_no_detectada",
                    "motivo": "No se pudo identificar la lista de anexos ingresados en la ficha oficial; no se puede confirmar que no haya documentos."})
            # «Anexos ingresados» suele contener las bases administrativas y los
            # formularios que más aportan al análisis. Priorizarlo evita que otras
            # fuentes consuman el límite del turno antes de leerlos.
            for tipo, listar, destino in (("adjunto", portal.listar_adjuntos_ingresados, adjuntos_ingresados),
                                           ("antecedente", portal.listar_anexos, antecedentes)):
                try:
                    destino.extend((tipo, f) for f in await listar(cliente, ficha))
                except BasesNoDisponibles as exc:
                    incidencias.append({"codigo": exc.motivo,
                        "motivo": f"No se pudo consultar la lista de {tipo}s: {exc.motivo}."})
                    if exc.motivo == "captcha_requerido":
                        captcha = True
                        break
            fuentes = [*adjuntos_ingresados, *bases, *antecedentes]
            for indice_fuente, (tipo, fuente) in enumerate(fuentes):
                if fuente is None:
                    nombre = f"Bases_{fila.codigo_externo}.pdf"
                    meta = {"nombre": nombre, "categoria": tipo}
                else:
                    meta = {k: fuente.get(k) for k in ("nombre", "categoria", "descripcion", "tipo", "tamano", "fecha")}
                documentos_observados.append({**meta,
                    "estado": "pendiente" if indice_fuente < MAX_DOCUMENTOS_ANALISIS else "omitido_limite"})
            documentos_a_leer = fuentes[:MAX_DOCUMENTOS_ANALISIS]
            for indice, (tipo, fuente) in enumerate(documentos_a_leer):
                if captcha:
                    break
                try:
                    descarga = (await portal.descargar_bases_ficha(cliente, ficha) if fuente is None
                                else await (portal.descargar_adjunto_ingresado(cliente, fuente)
                                    if tipo == "adjunto" else portal.descargar_anexo(cliente, fuente)))
                    contenido = descarga["contenido"]
                    total_bytes += len(contenido)
                    if total_bytes > MAX_BYTES_ANALISIS:
                        incidencias.append({"motivo": "Se alcanzó el límite de 12 MB por análisis; quedaron anexos pendientes."})
                        break
                    huella = hashlib.sha256(contenido).hexdigest()
                    if huella in vistos:
                        documentos_observados[indice]["estado"] = "duplicado"
                        continue
                    vistos.add(huella)
                    ext = descarga["extension"]
                    extraccion = await run_in_threadpool(extraer_pdf if ext == "pdf" else extraer_office, contenido)
                    # Liberar referencia al binario en cuanto termina la extracción.
                    del contenido
                    captura = "portal_adjuntos" if tipo == "adjunto" else "portal_bases" if tipo == "bases" else "portal_anexos"
                    extraccion["cobertura"].update(origen_captura=captura, anexos_completos=False,
                        bases_completas_confirmadas=False)
                    doc_eval, doc_cache = _doc_temporal(descarga, extraccion)
                    capturados.append(doc_eval)
                    cacheados.append(doc_cache)
                    documentos_observados[indice]["estado"] = "analizado"
                except BasesNoDisponibles as exc:
                    documentos_observados[indice].update(estado="error", error=exc.motivo)
                    if exc.motivo == "captcha_requerido":
                        captcha = True
                        incidencias.append({"codigo": exc.motivo,
                            "motivo": "Mercado Público solicitó CAPTCHA para este anexo. Se detuvo aquí; no se intentó resolverlo."})
                        break
                    incidencias.append({"codigo": exc.motivo,
                        "motivo": f"No se pudo leer {fuente.get('nombre') if fuente else 'las bases'}: {exc.motivo}."})
                    if exc.motivo == "error_temporal":
                        break
    except (TimeoutError, BasesNoDisponibles) as exc:
        motivo = exc.motivo if isinstance(exc, BasesNoDisponibles) else "tiempo_turno_agotado"
        incidencias.append({"codigo": motivo, "motivo": f"La lectura se detuvo: {motivo}."})

    ahora = datetime.now(timezone.utc)
    fila = db.get(Licitacion, licitacion_id)
    if fila:
        control = dict(fila.ingesta_documental or {})
        estado_final = ("captcha" if captcha else "completado" if capturados else
                        "sin_documentos" if not incidencias else "error_temporal")
        control.update(analisis_documental_raw_id=str(fila.raw_id),
            analisis_documental_version=ANALISIS_DOCUMENTAL_VERSION,
            analisis_documental_en=ahora.isoformat(),
            analisis_documental_estado=estado_final,
            analisis_documental_expira_en=(ahora + timedelta(
                minutes=30 if estado_final == "error_temporal" else 24 if captcha or not capturados else 72)).isoformat())
        control["documentos_observados"] = documentos_observados
        if capturados:
            control["documentos_analizados"] = cacheados
            control["hallazgos_documentales"] = [{"documento": d["nombre"], **d["hallazgos"]}
                for d in cacheados if d.get("hallazgos")]
        url_adjuntos = getattr(locals().get("ficha"), "adjuntos_url", None)
        # `enc` is issued by Mercado Público and must not become a long-lived link/cache.
        # Keep only the fact that the list was found; the browser should reopen the stable ficha.
        control["documentos_adjuntos_detectados"] = bool(url_adjuntos)
        control.pop("documentos_adjuntos_url", None)
        if incidencias:
            control["incidencia_documental"] = incidencias[0]
        elif not capturados:
            control["incidencia_documental"] = {"codigo": "sin_documentos", "motivo": "Aún no hay bases ni anexos publicados en la ficha oficial."}
        else:
            control.pop("incidencia_documental", None)
        fila.ingesta_documental = control
        db.commit()
    evaluacion = {"pendiente": True}
    if capturados:
        try:
            from ..api.preseleccion import evaluar_lote
            evaluacion = await evaluar_lote(db, [licitacion_id], actor,
                documentos_extra={licitacion_id: capturados})
        except Exception:
            db.rollback()
            incidencias.append({"codigo": "evaluacion_pendiente", "motivo": "Los documentos se leyeron, pero la evaluación quedó pendiente de actualización."})
    elif incidencias:
        fila = db.get(Licitacion, licitacion_id)
        if fila:
            fila.ingesta_documental = {**fila.ingesta_documental,
                "incidencia_documental": {"codigo": incidencias[0].get("codigo", "lectura_pendiente"),
                                          "motivo": incidencias[0]["motivo"]}}
            db.commit()
        try:
            from ..api.preseleccion import evaluar_lote
            evaluacion = await evaluar_lote(db, [licitacion_id], actor)
        except Exception:
            db.rollback()
            incidencias.append({"codigo": "evaluacion_pendiente",
                "motivo": "La incidencia se guardó; la clasificación quedó pendiente de actualización."})
    return {"procesados": len(capturados), "pendiente": not bool(capturados), "captcha": captcha,
        "documentos": [{"id": d["id"], "nombre": d["nombre"], "estado_extraccion": d["estado_extraccion"],
            "paginas": d.get("paginas"), "caracteres_conservados": sum(len(p["texto"]) for p in c["paginas_texto"])}
            for d, c in zip(capturados, cacheados)], "incidencias": incidencias, "evaluacion": evaluacion}


async def encolar_analisis_documental(ids):
    """Marca candidatos selectivos; no copia documentos ni texto fuente."""
    from sqlalchemy import select
    from ..models.licitacion import Licitacion
    ahora = datetime.now(timezone.utc)
    with SessionLocal() as db:
        filas = db.scalars(select(Licitacion).where(Licitacion.id.in_(ids)).with_for_update()).all()
        for fila in filas:
            control = dict(fila.ingesta_documental or {})
            expira = control.get("analisis_documental_expira_en")
            try:
                vence = datetime.fromisoformat(expira) if expira else None
                if vence and vence.tzinfo is None:
                    vence = vence.replace(tzinfo=timezone.utc)
                cache_vigente = (str(control.get("analisis_documental_raw_id")) == str(fila.raw_id)
                    and vence and vence > ahora)
            except (TypeError, ValueError):
                cache_vigente = False
            incidencia = control.get("incidencia_documental") or {}
            incidencia_antigua = (incidencia.get("codigo") == "sin_descarga_publica" or
                (incidencia.get("codigo") == "sin_documentos" and not (
                    control.get("documentos_adjuntos_detectados") or control.get("documentos_adjuntos_url"))))
            motor_antiguo = control.get("analisis_documental_version") != ANALISIS_DOCUMENTAL_VERSION
            if (cache_vigente and not incidencia_antigua and not motor_antiguo) or control.get("analisis_documental_estado") == "procesando":
                continue
            control.pop("documentos_analizados", None)
            if incidencia_antigua:
                control.pop("incidencia_documental", None)
            control.update(analisis_documental_estado="pendiente",
                analisis_documental_raw_id=str(fila.raw_id), analisis_documental_solicitado_en=ahora.isoformat())
            fila.ingesta_documental = control
        db.commit()


async def procesar_cola_analisis_documental(limite=3, actor=None):
    """Procesa pocos candidatos en segundo plano; cron continúa la cola persistida."""
    from sqlalchemy import select
    from ..models.licitacion import Licitacion
    if not settings.documentos_automaticos:
        return {"procesados": 0, "desactivado": True}
    completados = []
    # El texto breve es solo caché: purgarlo al vencer o cuando cambie la ficha RAW.
    ahora = datetime.now(timezone.utc)
    with SessionLocal() as db:
        filas_cache = db.scalars(select(Licitacion).where(
            Licitacion.ingesta_documental["documentos_analizados"].is_not(None)
        )).all()
        for fila_cache in filas_cache:
            control = dict(fila_cache.ingesta_documental or {})
            expira = control.get("analisis_documental_expira_en")
            try:
                vigente = (str(control.get("analisis_documental_raw_id")) == str(fila_cache.raw_id)
                    and expira and datetime.fromisoformat(expira) > ahora)
                if vigente:
                    vence = datetime.fromisoformat(expira)
                    if vence.tzinfo is None:
                        vence = vence.replace(tzinfo=timezone.utc)
                    vigente = vence > ahora
            except ValueError:
                vigente = False
            if not vigente:
                control.pop("documentos_analizados", None)
                fila_cache.ingesta_documental = control
        db.commit()
    for _ in range(max(1, min(int(limite), 5))):
        with SessionLocal() as db:
            fila = db.scalar(select(Licitacion).where(
                Licitacion.ingesta_documental["analisis_documental_estado"].astext == "pendiente"
            ).order_by(Licitacion.id).with_for_update(skip_locked=True).limit(1))
            if fila is None:
                break
            lic_id = fila.id
            control = dict(fila.ingesta_documental or {})
            control["analisis_documental_estado"] = "procesando"
            fila.ingesta_documental = control
            db.commit()
            try:
                resultado = await analizar_documentos_temporal(db, lic_id, actor, automatico=True)
                completados.append({"id": lic_id, "procesados": resultado.get("procesados", 0), "captcha": resultado.get("captcha", False)})
            except Exception:
                db.rollback()
                recupera = db.get(Licitacion, lic_id)
                if recupera:
                    control = dict(recupera.ingesta_documental or {})
                    control.update(analisis_documental_estado="error_temporal",
                        analisis_documental_expira_en=(datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat())
                    recupera.ingesta_documental = control
                    db.commit()
            except asyncio.CancelledError:
                db.rollback()
                with SessionLocal() as recuperacion:
                    recupera = recuperacion.get(Licitacion, lic_id)
                    if recupera:
                        control = dict(recupera.ingesta_documental or {})
                        control.update(analisis_documental_estado="error_temporal",
                            analisis_documental_expira_en=(datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat())
                        recupera.ingesta_documental = control
                        recuperacion.commit()
                raise
    return {"procesados": len(completados), "resultados": completados}


async def guardar_descarga(db, tarea, descarga, fuente, actor, resumen):
    contenido = descarga.pop("contenido")
    extension = descarga.pop("extension")
    huella = hashlib.sha256(contenido).hexdigest()
    if huella in tarea["hashes"]:
        resumen["reutilizados"] += 1
        return
    if extension == "pdf":
        extraccion = await run_in_threadpool(extraer_pdf, contenido)
    else:
        extraccion = await run_in_threadpool(extraer_office, contenido, extension)
    captura = "portal_anexos" if fuente else "portal_bases"
    extraccion["cobertura"].update(origen_captura=captura, anexos_completos=False,
        bases_completas_confirmadas=False, advertencia=ADVERTENCIAS[captura])
    if fuente:
        extraccion["cobertura"].update(categoria=fuente["categoria"], fecha_portal=fuente.get("fecha"),
                                       descripcion=fuente.get("descripcion"))
    try:
        await origen.guardar(db, tarea["id"], contenido=contenido, extraccion=extraccion, actor=actor,
                             token=tarea["token"], extension=extension, **descarga)
    except origen.LimiteDocumentos:
        raise BasesNoDisponibles("limite_documentos") from None
    tarea["hashes"].append(huella)
    resumen["guardados"] += 1


async def capturar(db, tarea, actor, plazo, manual=False):
    """Bases y anexos de una ficha, uno a uno, mientras quede tiempo en el turno."""
    loop = asyncio.get_running_loop()
    resumen = {"guardados": 0, "reutilizados": 0, "omitidos": [], "pendientes": 0}
    async with portal.sesion() as cliente:
        ficha = await portal.abrir_ficha(cliente, tarea["codigo"])
        fuentes = [None] if ficha.boton else []
        if manual or settings.mp_descarga_anexos_habilitada:
            fuentes += await portal.listar_anexos(cliente, ficha)
        if not fuentes:
            raise BasesNoDisponibles("sin_descarga_publica")
        for fuente in fuentes:
            # Un anexo sin cambios no se vuelve a bajar; las bases se omiten solo al continuar una captura.
            clave = (fuente["url_origen"], fuente.get("fecha")) if fuente else (ficha.origen, None)
            if clave in tarea["fuentes"] and (fuente or tarea["continuacion"]):
                resumen["reutilizados"] += 1
                continue
            if plazo - loop.time() < MARGEN_DOCUMENTO:
                resumen["pendientes"] += 1
                continue
            try:
                descarga = await (portal.descargar_anexo(cliente, fuente) if fuente
                                  else portal.descargar_bases_ficha(cliente, ficha))
                await guardar_descarga(db, tarea, descarga, fuente, actor, resumen)
            except BasesNoDisponibles as exc:
                if exc.motivo in DETIENEN_TURNO:
                    raise
                resumen["omitidos"].append({"nombre": fuente["nombre"] if fuente else "Descarga bases",
                                            "codigo": exc.motivo})
    return resumen


async def procesar_documentos(db, actor=None, plazo=None, licitacion_id=None, manual=False):
    if not settings.mp_descarga_portal_habilitada and not manual:
        return {"pendiente": True, "motivo": "canal_descarga_no_confirmado"}
    plazo = plazo or asyncio.get_running_loop().time() + 40
    tarea = None
    try:
        async with asyncio.timeout(45):
            tarea = origen.reservar(db, licitacion_id=licitacion_id, manual=manual)
            if not tarea:
                return {"procesados": 0}
            resumen = await capturar(db, tarea, actor, plazo, manual=manual)
            if not (resumen["guardados"] or resumen["reutilizados"] or resumen["pendientes"]):
                raise BasesNoDisponibles(resumen["omitidos"][0]["codigo"])
            # Lo guardado ya está confirmado; si faltan archivos, el siguiente turno continúa la ficha.
            origen.finalizar(db, tarea, "pendiente_continuar" if resumen["pendientes"] else "descargada",
                             resumen["omitidos"])
    except asyncio.CancelledError:
        db.rollback()
        if tarea:
            origen.finalizar(db, tarea, "error_temporal")
        raise
    except Exception as exc:
        db.rollback()
        motivo = exc.motivo if isinstance(exc, BasesNoDisponibles) else "error_temporal"
        if tarea:
            origen.finalizar(db, tarea, motivo)
            try:
                from ..api.preseleccion import evaluar_lote
                async with asyncio.timeout(5):
                    await evaluar_lote(db, [tarea["id"]], actor)
            except Exception:
                db.rollback()
        return {"pendiente": True, "motivo": motivo}
    # Los documentos fuente ya quedaron confirmados, incluso si filtradas no responde.
    evaluacion = {"pendiente": True}
    try:
        from ..api.preseleccion import evaluar_lote
        async with asyncio.timeout(5):
            evaluacion = await evaluar_lote(db, [tarea["id"]], actor)
    except Exception:
        db.rollback()
    return {"procesados": 1, "codigo": tarea["codigo"], **resumen, "anexos_completos": False,
            "evaluacion": evaluacion}


async def correr_documentos():
    if not settings.mp_descarga_portal_habilitada:
        return {"pendiente": True, "motivo": "canal_descarga_no_confirmado"}
    with SessionLocal() as db:
        try:
            plazo = asyncio.get_running_loop().time() + settings.documentos_timeout_segundos
            async with asyncio.timeout(settings.documentos_timeout_segundos):
                try:
                    async with asyncio.timeout(1):
                        await origen.storage("limpiar", {})
                except Exception:
                    pass
                return await procesar_documentos(db, plazo=plazo)
        except TimeoutError:
            db.rollback()
            return {"pendiente": True, "motivo": "tiempo_turno_agotado"}
