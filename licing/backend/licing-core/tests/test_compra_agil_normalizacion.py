import asyncio
from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import httpx
import pytest

from app.config import settings
from app.services import compra_agil_ingesta as ingesta
from app.services.compra_agil_normalizacion import (
    codigo_valido, convertir_fecha_compra_agil, leer_resumen, motivo_no_disponible, normalizar_compra_agil,
)
from app.services.enlaces import ficha_compra_agil
from app.services.mercado_publico import CompraAgilClient

CHILE = ZoneInfo("America/Santiago")


def detalle_api(codigo="1195-539-COT26", **cambios):
    """Forma real del payload de /v2/compra-agil/{codigo} observada en octubre de 2026."""
    detalle = {
        "codigo": codigo,
        "nombre": " Servicio de coffee break ",
        "descripcion": "\nCOFFEE BREAK PARA 40 PERSONAS",
        "estado": {"id_estado": 2, "codigo": "publicada", "glosa": "Publicada"},
        "convocatoria": {"estado_convocatoria": 1, "descripcion": "Primer llamado",
                         "fecha_cierre_primer_llamado": "2030-10-26 08:00",
                         "fecha_cierre_segundo_llamado": "2030-10-27 16:03"},
        "fechas": {"fecha_publicacion": "2030-10-24 23:56", "fecha_cierre": "2030-10-26 08:00",
                   "fecha_ultimo_cambio": "2030-10-25 00:00", "fecha_cancelacion": None},
        "entrega": {"direccion_entrega": "Club de huasos", "plazo_entrega_dias": 2},
        "documentos": [{"id": 2034059, "nombre": "TDR.pdf"}],
        "presupuesto": {"tipo_presupuesto": "Disponible", "moneda": "CLP", "presupuesto_estimado": 4100000,
                        "monto_disponible": 4100000, "monto_disponible_clp": 4100000,
                        "valor_cambio_moneda": None, "fecha_cambio_moneda": None},
        "id_orden_compra": None,
        "institucion": {"organismo_comprador": "I MUNICIPALIDAD DE PRUEBA", "rut": "69.240.300-2",
                        "unidad_compra": "Unidad de prueba", "region": 13,
                        "nombre_region": "Región Metropolitana de Santiago "},
        "productos_solicitados": [{"codigo_producto": 90101603, "nombre": "Servicios de coffee break",
                                   "descripcion": "Para 40 personas", "cantidad": 1, "unidad_medida": "EA"}],
        "proveedores_cotizando": [],
        "resumen": {"multa_sancion": 0, "total_ofertas_recibidas": 0, "total_demandas": 0},
        "motivos": {"motivo_cancelacion": None, "motivo_desierta": None},
        "flags": {"considera_requisitos_medioambientales": False},
    }
    detalle.update(cambios)
    return detalle


@pytest.mark.parametrize("valor,esperado", [
    # La Z de la API no indica UTC: el mismo cierre llega como «08:00:00Z» y como «08:00».
    ("2026-10-26T08:00:00Z", "2026-10-26T08:00:00"),
    ("2026-10-26 08:00", "2026-10-26T08:00:00"),
    ("2026-10-25T00:00:00.990Z", "2026-10-25T00:00:00.990000"),
    ("2026-10-26T11:00:00+00:00", "2026-10-26T08:00:00"),
])
def test_fechas_quedan_en_hora_de_chile(valor, esperado):
    assert convertir_fecha_compra_agil(valor).isoformat() == esperado


@pytest.mark.parametrize("valor", [None, "", "  "])
def test_fecha_ausente(valor):
    assert convertir_fecha_compra_agil(valor) is None


@pytest.mark.parametrize("valor", ["mañana", 20261026, "2026-13-40 10:00"])
def test_fecha_invalida_es_error_controlado(valor):
    with pytest.raises(ValueError):
        convertir_fecha_compra_agil(valor)


def test_normaliza_detalle_real():
    datos = normalizar_compra_agil(detalle_api())
    assert datos["codigo_externo"] == "1195-539-COT26"
    assert datos["nombre"] == "Servicio de coffee break"
    assert datos["estado"] == "publicada" and datos["id_estado"] == 2 and datos["estado_convocatoria"] == 1
    assert datos["fecha_cierre"] == datetime(2030, 10, 26, 8, 0)
    assert datos["monto_disponible_clp"] == Decimal("4100000")
    assert datos["codigo_region"] == 13 and datos["region_comprador"] == "Región Metropolitana de Santiago"
    assert datos["documentos"] == [{"id": 2034059, "nombre": "TDR.pdf"}]
    assert datos["fechas_fuente"]["fecha_cierre_primer_llamado"] == "2030-10-26 08:00"
    assert "proveedores_cotizando" not in datos["condiciones_fuente"]
    assert datos["condiciones_fuente"]["flags"] == {"considera_requisitos_medioambientales": False}
    assert datos["items"] == [{
        "posicion_fuente": 1, "codigo_producto": "90101603", "nombre_producto": "Servicios de coffee break",
        "descripcion": "Para 40 personas", "cantidad": Decimal("1"), "unidad_medida": "EA",
    }]


def test_orden_de_compra_en_raiz_o_anidada():
    assert normalizar_compra_agil(detalle_api(id_orden_compra=987))["id_orden_compra"] == 987
    anidada = detalle_api(orden_compra={"id_orden_compra": 654})
    del anidada["id_orden_compra"]
    assert normalizar_compra_agil(anidada)["id_orden_compra"] == 654


@pytest.mark.parametrize("cambios", [
    {"codigo": "../../licitaciones"}, {"codigo": None}, {"estado": "publicada"},
    {"productos_solicitados": {"a": 1}}, {"productos_solicitados": [1]},
    {"productos_solicitados": [{"cantidad": "muchas"}]}, {"presupuesto": {"monto_disponible": True}},
    {"institucion": {"region": "Metropolitana"}}, {"fechas": {"fecha_cierre": "pronto"}},
])
def test_detalle_malformado_es_error_controlado(cambios):
    with pytest.raises(ValueError):
        normalizar_compra_agil(detalle_api(**cambios))


def test_disponibilidad_solo_con_estado_o_cierre_conocidos():
    ahora = datetime(2026, 10, 25, 12, tzinfo=CHILE)
    futuro, pasado = datetime(2026, 10, 26), datetime(2026, 10, 25, 11)
    assert motivo_no_disponible("publicada", 2, futuro, ahora) is None
    assert motivo_no_disponible("publicada", 2, pasado, ahora) == "fecha_cierre"
    assert motivo_no_disponible("cancelada", 6, futuro, ahora) == "estado_no_disponible"
    assert motivo_no_disponible(None, 3, futuro, ahora) == "estado_no_disponible"
    assert motivo_no_disponible(None, None, None, ahora) is None


def test_resumen_del_listado():
    item = {"codigo": "1-2-COT26", "estado": {"id_estado": 2, "codigo": "publicada"},
            "fechas": {"fecha_publicacion": "2026-10-24 23:51", "fecha_cierre": "2026-10-28 12:00",
                       "fecha_ultimo_cambio": "2026-10-24T23:55:00.630Z"}}
    resumen = leer_resumen(item)
    assert resumen["cambio"] == datetime(2026, 10, 24, 23, 55, 0, 630000)
    assert resumen["fecha_cierre"] == datetime(2026, 10, 28, 12)
    with pytest.raises(ValueError):
        leer_resumen({**item, "fechas": {}})


def test_codigos_y_ficha_publica():
    assert codigo_valido(" 1057539-228-cot26 ") == "1057539-228-COT26"
    assert codigo_valido("1057539-228-LE26") is None
    assert ficha_compra_agil("1057539-228-COT26") == "https://buscador.mercadopublico.cl/ficha?code=1057539-228-COT26"
    assert ficha_compra_agil("x/../y") is None


def cliente_con(respuesta, solicitudes):
    def manejar(request):
        solicitudes.append(request)
        return respuesta(request)
    cliente = CompraAgilClient()
    cliente.client = httpx.AsyncClient(base_url="https://api2.example.test", headers=cliente.client.headers,
                                       transport=httpx.MockTransport(manejar))
    return cliente


def test_cliente_envia_ticket_en_cabecera_y_no_en_url(monkeypatch):
    solicitudes = []
    cliente = cliente_con(lambda r: httpx.Response(200, json={"success": "OK", "payload": {"items": []}}), solicitudes)
    payload = asyncio.run(cliente.listar({"estado": "publicada"}))
    assert payload == {"items": []}
    assert solicitudes[0].headers["ticket"] == settings.mp_ticket
    assert settings.mp_ticket not in str(solicitudes[0].url)


def test_cliente_distingue_inexistente_de_otros_errores():
    no_encontrada = {"success": "NOK", "payload": None,
                     "errors": [{"codigo": "NO_ENCONTRADO", "mensaje": "No existe", "detalle": None}]}
    cliente = cliente_con(lambda r: httpx.Response(404, json=no_encontrada), [])
    assert asyncio.run(cliente.detalle("1-2-COT26")) is None
    cliente = cliente_con(lambda r: httpx.Response(404, text="ruta inexistente"), [])
    with pytest.raises(httpx.HTTPStatusError):
        asyncio.run(cliente.detalle("1-2-COT26"))
    cliente = cliente_con(lambda r: httpx.Response(200, json={"success": "NOK", "payload": None}), [])
    with pytest.raises(ValueError):
        asyncio.run(cliente.detalle("1-2-COT26"))


def test_parametros_sin_zona_y_regiones(monkeypatch):
    desde, hasta = datetime(2026, 10, 25, 10), datetime(2026, 10, 25, 10, 5)
    params = ingesta.parametros_listado(desde, hasta, "publicada", 3)
    assert params["cambio_desde"] == "2026-10-25T10:00:00" and params["cambio_hasta"] == "2026-10-25T10:05:00"
    assert params["numero_pagina"] == 3 and params["tamano_pagina"] == 50 and "region" not in params
    monkeypatch.setattr(settings, "mp_compra_agil_regiones", " 13, 5")
    assert ingesta.parametros_listado(desde, hasta, "publicada", 1)["region"] == "13,5"
    monkeypatch.setattr(settings, "mp_compra_agil_regiones", "17")
    with pytest.raises(ValueError):
        ingesta.parametros_listado(desde, hasta, "publicada", 1)


@pytest.mark.parametrize("payload", [{}, {"items": [], "paginacion": {"total_resultados": -1, "total_paginas": 0}},
                                     {"items": {}, "paginacion": {"total_resultados": 0, "total_paginas": 0}}])
def test_paginacion_invalida(payload):
    with pytest.raises(ValueError):
        ingesta.leer_pagina(payload)


def test_limite_del_lote():
    for limite in (0, 21, True, "5"):
        with pytest.raises(ValueError):
            ingesta.validar_limite(limite)
    ingesta.validar_limite(20)


def test_ventana_inicial_no_usa_hora_utc():
    # La API compara contra hora de Chile; ahora_chile no debe adelantarse 3 o 4 horas.
    diferencia = datetime.now(CHILE).replace(tzinfo=None) - ingesta.ahora_chile()
    assert timedelta(0) <= diferencia < timedelta(seconds=5)
