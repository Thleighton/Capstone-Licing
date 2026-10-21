import pytest

from app.services.normalizacion_compra_agil import (
    normalizar_compra_agil,
)


def test_conserva_productos_con_codigo_repetido():
    detalle = {
        "codigo": "2258-935-COT26",
        "productos_solicitados": [
            {
                "codigo_producto": 44121506,
                "nombre": "Sobres estándar",
                "descripcion": "SOBRES DE PAPEL COLOR BLANCO",
                "cantidad": 10000,
                "unidad_medida": "EA",
            },
            {
                "codigo_producto": 44121506,
                "nombre": "Sobres estándar",
                "descripcion": "SOBRES OFICIO",
                "cantidad": 500,
                "unidad_medida": "EA",
            },
        ],
    }

    resultado = normalizar_compra_agil(detalle)

    assert resultado["cantidad_items_observada"] == 2
    assert [item["posicion"] for item in resultado["items"]] == [1, 2]
    assert resultado["items"][0]["codigo_producto"] == "44121506"
    assert resultado["items"][1]["cantidad"] == 500


def test_conserva_presupuesto_cero_y_fecha_sin_zona():
    detalle = {
        "codigo": "2258-935-COT26",
        "fechas": {
            "fecha_cierre": "2026-10-23 11:59",
        },
        "presupuesto": {
            "tipo_presupuesto": "Estimado",
            "presupuesto_estimado": 0,
            "monto_disponible_clp": 0,
        },
        "productos_solicitados": [],
    }

    resultado = normalizar_compra_agil(detalle)

    assert resultado["presupuesto"]["tipo"] == "Estimado"
    assert resultado["presupuesto"]["estimado"] == 0
    assert resultado["presupuesto"]["disponible_clp"] == 0
    assert resultado["fechas"]["fecha_cierre"] == "2026-10-23 11:59"


@pytest.mark.parametrize(
    "detalle",
    [
        {"codigo": "2258-935-COT26"},
        {
            "codigo": "2258-935-COT26",
            "productos_solicitados": None,
        },
        {
            "codigo": "2258-935-COT26",
            "productos_solicitados": [None],
        },
    ],
)
def test_rechaza_productos_ausentes_o_invalidos(detalle):
    with pytest.raises(ValueError, match="productos_solicitados"):
        normalizar_compra_agil(detalle)


@pytest.mark.parametrize(
    "ubicacion",
    [
        {"id_orden_compra": 123},
        {"orden_compra": {"id_orden_compra": 123}},
    ],
)
def test_lee_id_orden_compra_en_ambas_ubicaciones(ubicacion):
    detalle = {
        "codigo": "2258-935-COT26",
        "productos_solicitados": [],
        **ubicacion,
    }

    resultado = normalizar_compra_agil(detalle)

    assert resultado["id_orden_compra"] == 123