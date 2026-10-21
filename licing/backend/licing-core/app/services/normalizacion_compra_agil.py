from .normalizacion import limpiar_texto


def _leer_bloque(detalle: dict, nombre: str) -> dict:
    bloque = detalle.get(nombre)

    if bloque is None:
        return {}

    if not isinstance(bloque, dict):
        raise ValueError(f"El bloque {nombre} debe ser un objeto.")

    return bloque


def normalizar_compra_agil(detalle: dict) -> dict:
    if not isinstance(detalle, dict):
        raise ValueError("El detalle debe ser un objeto JSON.")

    codigo = detalle.get("codigo")

    if not isinstance(codigo, str) or not codigo.strip():
        raise ValueError("El detalle no contiene un código válido.")

    estado = _leer_bloque(detalle, "estado")
    fechas = _leer_bloque(detalle, "fechas")
    presupuesto = _leer_bloque(detalle, "presupuesto")
    institucion = _leer_bloque(detalle, "institucion")
    entrega = _leer_bloque(detalle, "entrega")
    convocatoria = _leer_bloque(detalle, "convocatoria")
    orden_compra = _leer_bloque(detalle, "orden_compra")

    productos = detalle.get("productos_solicitados")

    if (
        not isinstance(productos, list)
        or any(not isinstance(item, dict) for item in productos)
    ):
        raise ValueError("productos_solicitados debe ser una lista válida.")

    items = []

    for posicion, producto in enumerate(productos, start=1):
        items.append(
            {
                "posicion": posicion,
                "codigo_producto": limpiar_texto(
                    producto.get("codigo_producto")
                ),
                "nombre_producto": limpiar_texto(
                    producto.get("nombre")
                ),
                "descripcion": limpiar_texto(
                    producto.get("descripcion")
                ),
                "cantidad": producto.get("cantidad"),
                "unidad_medida": limpiar_texto(
                    producto.get("unidad_medida")
                ),
            }
        )

    id_orden_compra = detalle.get("id_orden_compra")

    if id_orden_compra is None:
        id_orden_compra = orden_compra.get("id_orden_compra")

    return {
        "codigo_externo": codigo.strip(),
        "nombre": limpiar_texto(detalle.get("nombre")),
        "descripcion": limpiar_texto(detalle.get("descripcion")),
        "estado": limpiar_texto(estado.get("codigo")),
        "estado_glosa": limpiar_texto(estado.get("glosa")),
        "codigo_estado": estado.get("id_estado"),
        "fechas": {
            nombre: limpiar_texto(fechas.get(nombre))
            for nombre in (
                "fecha_publicacion",
                "fecha_cierre",
                "fecha_ultimo_cambio",
                "fecha_cancelacion",
            )
        },
        "presupuesto": {
            "tipo": limpiar_texto(
                presupuesto.get("tipo_presupuesto")
            ),
            "moneda": limpiar_texto(presupuesto.get("moneda")),
            "estimado": presupuesto.get("presupuesto_estimado"),
            "disponible": presupuesto.get("monto_disponible"),
            "disponible_clp": presupuesto.get("monto_disponible_clp"),
        },
        "comprador": {
            "rut": limpiar_texto(institucion.get("rut")),
            "nombre_organismo": limpiar_texto(
                institucion.get("organismo_comprador")
            ),
            "nombre_unidad": limpiar_texto(
                institucion.get("unidad_compra")
            ),
            "codigo_region": institucion.get("region"),
            "region": limpiar_texto(
                institucion.get("nombre_region")
            ),
        },
        "entrega": {
            "direccion": limpiar_texto(
                entrega.get("direccion_entrega")
            ),
            "plazo_dias": entrega.get("plazo_entrega_dias"),
        },
        "convocatoria": {
            "numero": convocatoria.get("estado_convocatoria"),
            "fecha_cierre_primer_llamado": limpiar_texto(
                convocatoria.get("fecha_cierre_primer_llamado")
            ),
            "fecha_cierre_segundo_llamado": limpiar_texto(
                convocatoria.get("fecha_cierre_segundo_llamado")
            ),
        },
        "id_orden_compra": id_orden_compra,
        "cantidad_items_observada": len(items),
        "items": items,
    }