import asyncio
import math
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, Mock
from uuid import uuid4
from zoneinfo import ZoneInfo

import httpx
import pytest
from sqlalchemy import func, select, text

from app.config import settings
from app.models.compra_agil import CompraAgil
from app.models.compra_agil_item import CompraAgilItem
from app.models.compra_agil_sincronizacion import CompraAgilPendiente, CompraAgilSincronizacion
from app.models.ejecucion_ingesta import EjecucionIngesta
from app.models.licitacion import Licitacion
from app.models.raw import RawMercadoPublico
from app.services import compra_agil_ingesta as ingesta
from app.services import ingesta_lote
from app.services.compra_agil_persistencia import FUENTE, TIPO_DETALLE, eliminar_compras_no_disponibles
from app.services.normalizacion import VERSION_NORMALIZACION

CHILE = ZoneInfo("America/Santiago")


def ahora():
    return datetime.now(CHILE).replace(tzinfo=None, microsecond=0)


def texto(fecha, z=False):
    return fecha.isoformat(timespec="milliseconds") + "Z" if z else fecha.strftime("%Y-%m-%d %H:%M")


def codigo_nuevo():
    return f"{uuid4().int % 10**7}-{uuid4().int % 1000}-COT26"


def resumen(codigo, cambio, estado="publicada", cierre=None, publicacion=None):
    cierre = cierre or ahora() + timedelta(days=2)
    return {"codigo": codigo, "nombre": "Servicio", "estado": {"id_estado": 2 if estado == "publicada" else 6,
            "codigo": estado, "glosa": estado.title()},
            "fechas": {"fecha_publicacion": texto(publicacion or cambio), "fecha_cierre": texto(cierre),
                       "fecha_ultimo_cambio": texto(cambio, z=True)}}


def detalle(codigo, cambio=None, estado="publicada", cierre=None, productos=1):
    cambio = cambio or ahora() - timedelta(hours=1)
    cierre = cierre or ahora() + timedelta(days=2)
    return {
        "codigo": codigo, "nombre": "Alojamiento para jornada", "descripcion": "Hotel en Santiago",
        "estado": {"id_estado": 2 if estado == "publicada" else 6, "codigo": estado, "glosa": estado.title()},
        "convocatoria": {"estado_convocatoria": 1, "descripcion": "Primer llamado"},
        "fechas": {"fecha_publicacion": texto(cambio), "fecha_cierre": texto(cierre),
                   "fecha_ultimo_cambio": texto(cambio), "fecha_cancelacion": None},
        "presupuesto": {"moneda": "CLP", "monto_disponible": 1000, "monto_disponible_clp": 1000},
        "institucion": {"organismo_comprador": "Ministerio de Prueba", "rut": "1-9", "unidad_compra": "Unidad",
                        "region": 13, "nombre_region": "Región Metropolitana de Santiago"},
        "productos_solicitados": [{"codigo_producto": 90111501 + n, "nombre": f"Producto {n}", "cantidad": n + 1,
                                   "unidad_medida": "EA"} for n in range(productos)],
        "id_orden_compra": None,
    }


class ApiFalsa:
    """Filtra por estado y ventana, ordena por último cambio descendente y pagina como la API real."""

    def __init__(self, resumenes=(), detalles=None):
        self.resumenes = list(resumenes)
        self.detalles = detalles or {}
        self.consultas, self.pedidos = [], []
        self.al_listar = None

    async def listar(self, params):
        self.consultas.append(params)
        if self.al_listar:
            self.al_listar(self, params)
        estados = set(params["estado"].split(","))
        desde = datetime.fromisoformat(params["cambio_desde"])
        hasta = datetime.fromisoformat(params["cambio_hasta"])

        def cambio(r):
            return datetime.fromisoformat(r["fechas"]["fecha_ultimo_cambio"].rstrip("Z"))
        filas = sorted((r for r in self.resumenes if r["estado"]["codigo"] in estados
                        and desde <= cambio(r) <= hasta), key=cambio, reverse=True)
        tamano, pagina = params["tamano_pagina"], params["numero_pagina"]
        return {"items": filas[(pagina - 1) * tamano:pagina * tamano], "paginacion": {
            "total_paginas": math.ceil(len(filas) / tamano), "numero_pagina": pagina,
            "tamano_pagina": tamano, "total_resultados": len(filas)}}

    async def detalle(self, codigo):
        self.pedidos.append(codigo)
        # Sin respuesta preparada, la compra existe y sigue publicada.
        respuesta = self.detalles[codigo] if codigo in self.detalles else detalle(codigo)
        if isinstance(respuesta, Exception):
            raise respuesta
        return respuesta


@pytest.fixture
def db(integration_db, monkeypatch):
    monkeypatch.setattr(settings, "mp_compra_agil_pausa_segundos", 0)
    monkeypatch.setattr(settings, "mp_compra_agil_lote_timeout_segundos", 30)
    monkeypatch.setattr(settings, "mp_compra_agil_paginas_por_lote", 50)
    monkeypatch.setattr(settings, "mp_compra_agil_regiones", "")
    return integration_db


def lote(db, api, limite=20):
    return asyncio.run(ingesta._ejecutar_con_bloqueo(db, api, limite))


def conocidas(db):
    """Códigos encolados o ya guardados."""
    return (set(db.scalars(select(CompraAgilPendiente.codigo_externo)).all())
            | set(db.scalars(select(CompraAgil.codigo_externo)).all()))


def sincronizacion(db):
    db.expire_all()
    return db.get(CompraAgilSincronizacion, 1)


def http_error(status):
    request = httpx.Request("GET", "https://api2.example.test/v2/compra-agil/x")
    return httpx.HTTPStatusError("error", request=request, response=httpx.Response(status, request=request))


def test_carga_inicial_recorre_paginas_y_guarda_detalles(db):
    base = ahora() - timedelta(hours=3)
    codigos = [codigo_nuevo() for _ in range(120)]
    api = ApiFalsa([resumen(c, base + timedelta(seconds=n), publicacion=base + timedelta(minutes=n))
                    for n, c in enumerate(codigos)], {c: detalle(c, productos=2) for c in codigos})
    r = lote(db, api, limite=5)
    assert r["listado"]["paginas"] == 4  # página 1 para contar, luego 3, 2 y 1.
    assert [c["numero_pagina"] for c in api.consultas] == [1, 3, 2, 1]
    assert {c["estado"] for c in api.consultas} == {"publicada"}
    assert r["listado"]["encolados"] == 120 and r["procesados"] == 5
    estado = sincronizacion(db)
    assert estado.pagina is None and estado.cursor is not None
    # Las más recientes primero.
    assert api.pedidos == sorted(codigos[-5:], key=codigos.index, reverse=True)
    compra = db.scalars(select(CompraAgil).where(CompraAgil.codigo_externo == codigos[-1])).one()
    assert compra.estado == "publicada" and compra.nombre_organismo == "Ministerio de Prueba"
    assert compra.cambio_sincronizado == base + timedelta(seconds=119)
    assert db.scalar(select(func.count()).select_from(CompraAgilItem).where(CompraAgilItem.compra_agil_id == compra.id)) == 2
    assert db.scalar(select(func.count()).select_from(CompraAgilPendiente)) == 115
    ejecucion = db.get(EjecucionIngesta, r["ejecucion_id"])
    assert ejecucion.fuente == "compra_agil" and ejecucion.estado == "completada"
    assert ejecucion.resumenes_recibidos == 170 and ejecucion.descargados == 5
    assert r["sincronizacion"]["pendientes"] == 115


def test_ventana_pendiente_continua_en_el_siguiente_lote(db, monkeypatch):
    monkeypatch.setattr(settings, "mp_compra_agil_paginas_por_lote", 2)
    base = ahora() - timedelta(hours=3)
    codigos = [codigo_nuevo() for _ in range(120)]
    api = ApiFalsa([resumen(c, base + timedelta(seconds=n)) for n, c in enumerate(codigos)])
    lote(db, api, limite=1)
    estado = sincronizacion(db)
    assert estado.cursor is None and estado.pagina == 2 and estado.ventana_estados == "publicada"
    hasta = estado.ventana_hasta
    lote(db, api, limite=1)
    estado = sincronizacion(db)
    assert estado.pagina is None and estado.cursor == hasta
    assert conocidas(db) == set(codigos)


def test_registros_que_salen_de_la_ventana_no_hacen_saltar_otros(db, monkeypatch):
    monkeypatch.setattr(settings, "mp_compra_agil_paginas_por_lote", 2)
    base = ahora() - timedelta(hours=3)
    codigos = [codigo_nuevo() for _ in range(101)]
    api = ApiFalsa([resumen(c, base + timedelta(seconds=n)) for n, c in enumerate(codigos)])
    lote(db, api, limite=1)  # Lee la página 1 (cuenta) y la 3.
    assert sincronizacion(db).pagina == 2
    # Diez compras de la página 1 cambian otra vez y salen de la ventana fija: la página 3 desaparece.
    for r in api.resumenes[-10:]:
        r["fechas"]["fecha_ultimo_cambio"] = texto(ahora() + timedelta(seconds=30), z=True)
    lote(db, api, limite=1)
    assert set(codigos[:91]) <= conocidas(db)


def test_seguimiento_retira_canceladas_y_encola_cambios(db):
    codigo, cancelado = codigo_nuevo(), codigo_nuevo()
    cambio = ahora() - timedelta(hours=2)
    api = ApiFalsa([resumen(codigo, cambio), resumen(cancelado, cambio)],
                   {codigo: detalle(codigo, cambio), cancelado: detalle(cancelado, cambio)})
    lote(db, api)
    assert db.scalar(select(func.count()).select_from(CompraAgil).where(
        CompraAgil.codigo_externo.in_([codigo, cancelado]))) == 2
    # Siguiente ventana: una se cancela y la otra amplía su cierre.
    nuevo = ahora() - timedelta(minutes=1)
    api.resumenes = [resumen(codigo, nuevo, cierre=ahora() + timedelta(days=5)),
                     resumen(cancelado, nuevo, estado="cancelada")]
    api.detalles[codigo] = detalle(codigo, nuevo, cierre=ahora() + timedelta(days=5))
    cursor = ahora() - timedelta(minutes=10)
    sincronizacion(db).cursor = cursor
    db.commit()
    api.consultas.clear()
    r = lote(db, api)
    assert api.consultas[0]["estado"] == "publicada,cancelada,desierta"
    assert api.consultas[0]["cambio_desde"] == (cursor - ingesta.SOLAPE).isoformat()
    assert r["listado"]["descartados"] == 1 and r["listado"]["eliminadas"] == 1
    db.expire_all()
    assert db.scalars(select(CompraAgil).where(CompraAgil.codigo_externo == cancelado)).first() is None
    compra = db.scalars(select(CompraAgil).where(CompraAgil.codigo_externo == codigo)).one()
    assert compra.fecha_cierre.date() == (ahora() + timedelta(days=5)).date()
    assert not db.scalars(select(RawMercadoPublico).where(RawMercadoPublico.codigo_externo == cancelado)).all()


def test_cambio_ya_sincronizado_no_se_vuelve_a_encolar(db):
    codigo = codigo_nuevo()
    cambio = ahora() - timedelta(hours=1)
    api = ApiFalsa([resumen(codigo, cambio)], {codigo: detalle(codigo, cambio)})
    lote(db, api)
    estado = sincronizacion(db)
    estado.cursor = cambio  # El solape vuelve a mostrar el mismo cambio.
    db.commit()
    r = lote(db, api)
    assert r["listado"]["resumenes"] == 1 and r["listado"]["encolados"] == 0
    assert api.pedidos == [codigo]


def test_detalle_identico_no_duplica_raw(db):
    codigo = codigo_nuevo()
    d = detalle(codigo)
    api = ApiFalsa(detalles={codigo: d})
    asyncio.run(ingesta.descargar_y_procesar(db, api, codigo))
    raw = db.scalars(select(RawMercadoPublico).where(RawMercadoPublico.codigo_externo == codigo)).one()
    verificado = raw.verificado_en
    asyncio.run(ingesta.descargar_y_procesar(db, api, codigo))
    db.expire_all()
    filas = db.scalars(select(RawMercadoPublico).where(RawMercadoPublico.codigo_externo == codigo)).all()
    assert len(filas) == 1 and filas[0].verificado_en > verificado
    assert filas[0].fuente == FUENTE and filas[0].tipo_consulta == TIPO_DETALLE


def test_nueva_version_reemplaza_items_ausentes(db):
    codigo = codigo_nuevo()
    api = ApiFalsa(detalles={codigo: detalle(codigo, productos=3)})
    primero = asyncio.run(ingesta.descargar_y_procesar(db, api, codigo))
    api.detalles[codigo] = detalle(codigo, ahora() - timedelta(minutes=5), productos=1)
    segundo = asyncio.run(ingesta.descargar_y_procesar(db, api, codigo))
    assert primero["compra_agil_id"] == segundo["compra_agil_id"] and segundo["raw_id"] != primero["raw_id"]
    items = db.scalars(select(CompraAgilItem).where(CompraAgilItem.compra_agil_id == segundo["compra_agil_id"])).all()
    assert [(i.posicion_fuente, i.codigo_producto) for i in items] == [(1, "90111501")]


def test_inexistente_o_cerrada_se_elimina(db):
    inexistente, cerrada = codigo_nuevo(), codigo_nuevo()
    api = ApiFalsa(detalles={inexistente: detalle(inexistente), cerrada: detalle(cerrada)})
    for codigo in (inexistente, cerrada):
        asyncio.run(ingesta.descargar_y_procesar(db, api, codigo))
    api.detalles[inexistente] = None
    api.detalles[cerrada] = detalle(cerrada, estado="cerrada")
    for codigo in (inexistente, cerrada):
        db.add(CompraAgilPendiente(codigo_externo=codigo, cambio=ahora(), fecha_cierre=ahora() + timedelta(days=1)))
    db.commit()
    r = lote(db, ApiFalsa(detalles=api.detalles))
    assert {d["motivo"] for d in r["descartadas"]} == {"no_encontrada_por_codigo", "estado_no_disponible"}
    assert r["descargados"] == 2 and r["procesados"] == 0
    db.expire_all()
    assert not db.scalars(select(CompraAgil).where(CompraAgil.codigo_externo.in_([inexistente, cerrada]))).all()
    assert not db.scalars(select(CompraAgilPendiente).where(
        CompraAgilPendiente.codigo_externo.in_([inexistente, cerrada]))).all()
    assert not db.scalars(select(RawMercadoPublico).where(
        RawMercadoPublico.codigo_externo.in_([inexistente, cerrada]))).all()


def test_error_pospone_y_429_detiene_el_lote(db):
    falla, limitada, siguiente = codigo_nuevo(), codigo_nuevo(), codigo_nuevo()
    publicada = ahora() - timedelta(hours=1)
    for n, codigo in enumerate((falla, limitada, siguiente)):
        db.add(CompraAgilPendiente(codigo_externo=codigo, cambio=publicada,
                                   fecha_publicacion=publicada - timedelta(minutes=n),
                                   fecha_cierre=ahora() + timedelta(days=1)))
    db.commit()
    api = ApiFalsa(detalles={falla: http_error(500), limitada: http_error(429), siguiente: detalle(siguiente)})
    r = lote(db, api)
    # Las descargas en curso al recibir el 429 no se guardan; quedan pendientes.
    assert api.pedidos[:2] == [falla, limitada]
    assert r["detenido_por_error_api"] is True and r["procesados"] == 0
    assert [e["status_code"] for e in r["errores"]] == [500, 429]
    assert "ticket" not in str(r["errores"])
    db.expire_all()
    pendiente = db.scalars(select(CompraAgilPendiente).where(CompraAgilPendiente.codigo_externo == falla)).one()
    assert pendiente.intentos == 1 and pendiente.reintentar_desde > datetime.now(timezone.utc)
    assert pendiente.ultimo_error["status_code"] == 500
    # El 429 depende del ticket: esa compra no se pospone.
    limitada_fila = db.scalars(select(CompraAgilPendiente).where(CompraAgilPendiente.codigo_externo == limitada)).one()
    assert limitada_fila.intentos == 0 and limitada_fila.reintentar_desde is None
    assert db.get(EjecucionIngesta, r["ejecucion_id"]).estado == "error"
    # Las pospuestas esperan; la siguiente se procesa.
    api.pedidos.clear()
    api.detalles[limitada] = detalle(limitada)
    r = lote(db, api)
    assert api.pedidos == [limitada, siguiente] and r["procesados"] == 2


def test_error_del_listado_no_impide_descargar_pendientes(db):
    codigo = codigo_nuevo()
    db.add(CompraAgilPendiente(codigo_externo=codigo, cambio=ahora(), fecha_cierre=ahora() + timedelta(days=1)))
    db.commit()
    api = ApiFalsa(detalles={codigo: detalle(codigo)})
    api.listar = AsyncMock(side_effect=http_error(503))
    r = lote(db, api)
    assert r["errores"][0]["etapa"] == "listado" and r["procesados"] == 1
    assert db.get(EjecucionIngesta, r["ejecucion_id"]).estado == "parcial"


def test_ventana_con_mas_de_diez_mil_resultados_se_acota(db):
    api = ApiFalsa()
    totales = iter([25_000, 12_000, 40])

    async def listar(params):
        api.consultas.append(params)
        total = next(totales, 0)
        return {"items": [], "paginacion": {"total_resultados": total, "total_paginas": math.ceil(total / 50)}}
    api.listar = listar
    lote(db, api)
    hastas = [datetime.fromisoformat(c["cambio_hasta"]) for c in api.consultas]
    assert hastas[0] > hastas[1] > hastas[2]
    # La ventana acotada se cierra y la siguiente continúa desde su fin hasta ahora.
    assert api.consultas[3]["cambio_desde"] == (hastas[2] - ingesta.SOLAPE).isoformat()
    assert len(api.consultas) == 4 and sincronizacion(db).cursor == hastas[3]


def test_tiempo_agotado_deja_pendientes_para_otro_lote(db, monkeypatch):
    monkeypatch.setattr(settings, "mp_compra_agil_lote_timeout_segundos", 2)
    monkeypatch.setattr(ingesta, "MARGEN_FINAL_SEGUNDOS", 1)
    monkeypatch.setattr(ingesta, "CONCURRENCIA_DETALLES", 1)
    codigos = [codigo_nuevo() for _ in range(3)]
    for codigo in codigos:
        db.add(CompraAgilPendiente(codigo_externo=codigo, cambio=ahora(), fecha_cierre=ahora() + timedelta(days=1)))
    db.commit()
    api = ApiFalsa(detalles={c: detalle(c) for c in codigos})
    lento = api.detalle

    async def detalle_lento(codigo):
        await asyncio.sleep(0.6)
        return await lento(codigo)
    api.detalle = detalle_lento
    r = lote(db, api)
    assert r["procesados"] == 2 and r["pospuestos_por_tiempo"] == 1 and "interrumpido" not in r
    assert db.get(EjecucionIngesta, r["ejecucion_id"]).estado == "completada"


def test_descargas_en_paralelo_se_guardan_en_orden_de_prioridad(db):
    codigos = [codigo_nuevo() for _ in range(6)]
    publicada = ahora() - timedelta(hours=1)
    for n, codigo in enumerate(codigos):
        db.add(CompraAgilPendiente(codigo_externo=codigo, cambio=publicada, fecha_publicacion=publicada - timedelta(minutes=n),
                                   fecha_cierre=ahora() + timedelta(days=1)))
    db.commit()
    api = ApiFalsa()
    original = api.detalle
    en_curso, maximo, guardados = [0], [0], []

    async def detalle_variable(codigo):
        en_curso[0] += 1
        maximo[0] = max(maximo[0], en_curso[0])
        # La primera es la más lenta: las demás terminan antes que ella.
        await asyncio.sleep(0.3 if codigo == codigos[0] else 0.05)
        en_curso[0] -= 1
        return await original(codigo)
    api.detalle = detalle_variable
    r = lote(db, api)
    assert r["procesados"] == 6 and maximo[0] == ingesta.CONCURRENCIA_DETALLES
    assert [x["codigo_externo"] for x in r["resultados"]] == codigos


def test_ritmo_separa_el_inicio_de_las_solicitudes():
    async def escenario():
        ritmo = ingesta.Ritmo(0.05)
        loop = asyncio.get_running_loop()
        inicios = []

        async def solicitar():
            await ritmo.esperar()
            inicios.append(loop.time())
        await asyncio.gather(*(solicitar() for _ in range(4)))
        return inicios
    inicios = asyncio.run(escenario())
    assert all(b - a >= 0.045 for a, b in zip(inicios, inicios[1:]))


def test_limpieza_programada_elimina_vencidas_y_conserva_lo_desconocido(db):
    vigente, vencida, huerfana, desconocida = (codigo_nuevo() for _ in range(4))
    api = ApiFalsa(detalles={vigente: detalle(vigente), vencida: detalle(vencida)})
    for codigo in (vigente, vencida):
        asyncio.run(ingesta.descargar_y_procesar(db, api, codigo))
    db.execute(text("UPDATE compra_agil SET fecha_cierre = now() AT TIME ZONE 'America/Santiago' - interval '1 minute' "
                    "WHERE codigo_externo = :c"), {"c": vencida})
    for codigo, estado in ((huerfana, "cerrada"), (desconocida, None)):
        respuesta = detalle(codigo, estado=estado or "publicada")
        if estado is None:
            respuesta["estado"] = {}
        db.add(RawMercadoPublico(fuente=FUENTE, tipo_consulta=TIPO_DETALLE, codigo_externo=codigo,
                                 respuesta=respuesta, http_status=200))
    db.add(CompraAgilPendiente(codigo_externo=codigo_nuevo(), cambio=ahora(), fecha_cierre=ahora() - timedelta(hours=1)))
    db.commit()
    resultado = eliminar_compras_no_disponibles(db)
    assert resultado["compras"] == 1 and resultado["items"] == 1 and resultado["pendientes"] == 1
    assert resultado["raw"] == 2  # La vencida y la huérfana cerrada.
    restantes = set(db.scalars(select(RawMercadoPublico.codigo_externo).where(
        RawMercadoPublico.codigo_externo.in_([vigente, vencida, huerfana, desconocida]))).all())
    assert restantes == {vigente, desconocida}


def test_eliminacion_confirmada_requiere_codigos(db):
    from sqlalchemy.exc import DBAPIError
    with pytest.raises(DBAPIError):
        with db.begin_nested():
            eliminar_compras_no_disponibles(db, [], confirmada=True)


def test_raw_de_compra_agil_no_afecta_licitaciones(db):
    codigo = codigo_nuevo()
    asyncio.run(ingesta.descargar_y_procesar(db, ApiFalsa(detalles={codigo: detalle(codigo)}), codigo))
    db.execute(text("SELECT public.purgar_licitaciones_no_disponibles(:c, true)"), {"c": codigo})
    assert db.scalars(select(RawMercadoPublico).where(RawMercadoPublico.codigo_externo == codigo)).one()
    assert db.scalars(select(CompraAgil).where(CompraAgil.codigo_externo == codigo)).one()
    assert not db.scalars(select(Licitacion).where(Licitacion.codigo_externo == codigo)).all()


def test_errores_de_compra_agil_no_posponen_licitaciones(db):
    codigo = "TEST-LIC-" + uuid4().hex[:8]
    db.add(EjecucionIngesta(fuente="compra_agil", limite_detalles=1, estado="error", errores=[
        {"codigo_externo": codigo, "tipo": "ValueError", "normalizacion_version": VERSION_NORMALIZACION}]))
    db.commit()
    cliente = AsyncMock()
    cliente.licitaciones_activas.return_value = {"Cantidad": 1, "Listado": [
        {"CodigoExterno": codigo, "CodigoEstado": 5, "Estado": "Publicada"}]}
    plan = asyncio.run(ingesta_lote.planificar_ingesta(db, cliente, 1))
    assert plan["codigos_a_descargar"] == [codigo] and plan["pospuestos_por_error"] == 0


@pytest.mark.parametrize("adquirido", [False, True])
def test_bloqueo_propio_y_liberacion(monkeypatch, adquirido):
    conexion = Mock()
    conexion.execute.return_value.scalar_one.return_value = adquirido
    monkeypatch.setattr(ingesta, "engine", Mock(connect=Mock(return_value=conexion)))
    interno = AsyncMock(side_effect=RuntimeError("fallo del lote"))
    monkeypatch.setattr(ingesta, "_ejecutar_con_bloqueo", interno)
    with pytest.raises(RuntimeError if adquirido else ingesta.EjecucionEnCursoError):
        asyncio.run(ingesta.ejecutar_lote_compras_agiles(Mock(), AsyncMock()))
    assert conexion.execute.call_args_list[0].args[1] == {"id": ingesta.ID_BLOQUEO_COMPRA_AGIL}
    assert ingesta.ID_BLOQUEO_COMPRA_AGIL != ingesta_lote.ID_BLOQUEO_INGESTA
    assert conexion.execute.call_count == (2 if adquirido else 1)
    conexion.close.assert_called_once()
