def limpiar_texto(valor):
    if valor is None:
        return None

    texto = str(valor).strip()
    return texto or None


def normalizar_licitacion(detalle: dict) -> dict:
    comprador = detalle.get("Comprador") or {}
    fechas = detalle.get("Fechas") or {}
    bloque_items = detalle.get("Items") or {}

    items = []

    for item in bloque_items.get("Listado") or []:
        items.append({
            "correlativo": item.get("Correlativo"),
            "codigo_producto": limpiar_texto(
                item.get("CodigoProducto")
            ),
            "nombre_producto": limpiar_texto(
                item.get("NombreProducto")
            ),
            "descripcion": limpiar_texto(item.get("Descripcion")),
            "cantidad": item.get("Cantidad"),
            "unidad_medida": limpiar_texto(item.get("UnidadMedida")),
        })

    return {
        "codigo_externo": limpiar_texto(detalle.get("CodigoExterno")),
        "nombre": limpiar_texto(detalle.get("Nombre")),
        "descripcion": limpiar_texto(detalle.get("Descripcion")),
        "codigo_estado": detalle.get("CodigoEstado"),
        "estado": limpiar_texto(detalle.get("Estado")),
        "monto_estimado": detalle.get("MontoEstimado"),
        "moneda": limpiar_texto(detalle.get("Moneda")),
        "fecha_publicacion": limpiar_texto(
            fechas.get("FechaPublicacion")
        ),
        "fecha_cierre": limpiar_texto(
            fechas.get("FechaCierre") or detalle.get("FechaCierre")
        ),
        "comprador": {
            "codigo_organismo": limpiar_texto(
                comprador.get("CodigoOrganismo")
            ),
            "nombre_organismo": limpiar_texto(
                comprador.get("NombreOrganismo")
            ),
            "codigo_unidad": limpiar_texto(
                comprador.get("CodigoUnidad")
            ),
            "nombre_unidad": limpiar_texto(
                comprador.get("NombreUnidad")
            ),
            "region": limpiar_texto(comprador.get("RegionUnidad")),
            "comuna": limpiar_texto(comprador.get("ComunaUnidad")),
        },
        "cantidad_items_declarada": bloque_items.get("Cantidad"),
        "cantidad_items_observada": len(items),
        "items": items,
    }