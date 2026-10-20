from app.services.normalizacion import normalizar_licitacion


def test_conserva_monto_desconocido_y_fecha_anidada():
    detalle = {
        "CodigoExterno": "1002-89-LP26",
        "Estado": "Adjudicada",
        "MontoEstimado": None,
        "FechaCierre": None,
        "Fechas": {
            "FechaCierre": "2026-10-13T16:00:00",
        },
    }

    resultado = normalizar_licitacion(detalle)

    assert resultado["estado"] == "Adjudicada"
    assert resultado["monto_estimado"] is None
    assert resultado["fecha_cierre"] == "2026-10-13T16:00:00"


def test_limpia_region_y_convierte_codigo_producto_a_texto():
    detalle = {
        "Comprador": {
            "RegionUnidad": "Región de los Lagos ",
        },
        "Items": {
            "Cantidad": 1,
            "Listado": [
                {
                    "CodigoProducto": 30121601,
                    "Cantidad": 850,
                }
            ],
        },
    }

    resultado = normalizar_licitacion(detalle)

    assert resultado["comprador"]["region"] == "Región de los Lagos"
    assert resultado["items"][0]["codigo_producto"] == "30121601"
    assert resultado["items"][0]["cantidad"] == 850
    assert resultado["cantidad_items_declarada"] == 1
    assert resultado["cantidad_items_observada"] == 1


def test_acepta_bloques_nulos_y_conserva_monto_cero():
    detalle = {
        "MontoEstimado": 0,
        "Comprador": None,
        "Fechas": None,
        "Items": None,
    }

    resultado = normalizar_licitacion(detalle)

    assert resultado["monto_estimado"] == 0
    assert resultado["comprador"]["codigo_unidad"] is None
    assert resultado["fecha_cierre"] is None
    assert resultado["items"] == []
    assert resultado["cantidad_items_observada"] == 0


def test_procesa_varios_items():
    detalle = {
        "Items": {
            "Cantidad": 2,
            "Listado": [
                {"Correlativo": 1, "NombreProducto": "Producto A"},
                {"Correlativo": 2, "NombreProducto": "Producto B"},
            ],
        },
    }

    resultado = normalizar_licitacion(detalle)

    assert resultado["cantidad_items_declarada"] == 2
    assert resultado["cantidad_items_observada"] == 2
    assert resultado["items"][1]["nombre_producto"] == "Producto B"