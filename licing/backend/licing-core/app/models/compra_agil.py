"""Compras Ágiles disponibles, normalizadas desde el detalle de la API v2."""
from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, Numeric, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class CompraAgil(Base):
    __tablename__ = "compra_agil"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    codigo_externo: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    raw_id: Mapped[int] = mapped_column(ForeignKey("raw_mercado_publico.id"), nullable=False, index=True)

    nombre: Mapped[str | None] = mapped_column(Text)
    descripcion: Mapped[str | None] = mapped_column(Text)

    # estado.codigo de la API: publicada, cerrada, desierta, cancelada, proveedor_seleccionado.
    id_estado: Mapped[int | None] = mapped_column(Integer)
    estado: Mapped[str | None] = mapped_column(String(50))
    estado_glosa: Mapped[str | None] = mapped_column(Text)
    estado_convocatoria: Mapped[int | None] = mapped_column(Integer)

    # Hora de Chile sin zona, igual que licitacion.
    fecha_publicacion: Mapped[datetime | None] = mapped_column(DateTime(timezone=False))
    fecha_cierre: Mapped[datetime | None] = mapped_column(DateTime(timezone=False))
    fecha_ultimo_cambio: Mapped[datetime | None] = mapped_column(DateTime(timezone=False))
    fecha_cancelacion: Mapped[datetime | None] = mapped_column(DateTime(timezone=False))

    moneda: Mapped[str | None] = mapped_column(String(20))
    tipo_presupuesto: Mapped[str | None] = mapped_column(String(30))
    presupuesto_estimado: Mapped[Decimal | None] = mapped_column(Numeric())
    monto_disponible: Mapped[Decimal | None] = mapped_column(Numeric())
    monto_disponible_clp: Mapped[Decimal | None] = mapped_column(Numeric())

    rut_organismo: Mapped[str | None] = mapped_column(String(20))
    nombre_organismo: Mapped[str | None] = mapped_column(Text)
    nombre_unidad: Mapped[str | None] = mapped_column(Text)
    codigo_region: Mapped[int | None] = mapped_column(Integer)
    region_comprador: Mapped[str | None] = mapped_column(Text)

    direccion_entrega: Mapped[str | None] = mapped_column(Text)
    plazo_entrega_dias: Mapped[int | None] = mapped_column(Integer)
    total_ofertas_recibidas: Mapped[int | None] = mapped_column(Integer)
    id_orden_compra: Mapped[int | None] = mapped_column(BigInteger)

    documentos: Mapped[list[dict]] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    fechas_fuente: Mapped[dict | None] = mapped_column(JSONB)
    condiciones_fuente: Mapped[dict | None] = mapped_column(JSONB)
    normalizacion_version: Mapped[str | None] = mapped_column(String(30))
    normalizado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # fecha_ultimo_cambio del listado (con milisegundos) ya incorporada; evita volver a encolarla.
    cambio_sincronizado: Mapped[datetime | None] = mapped_column(DateTime(timezone=False))
    # Última evaluación guardada en LicitacionesFiltradas: firma, versión del motor y propuesta.
    # NULL al cambiar el RAW: la compra vuelve a quedar pendiente de preselección.
    preseleccion: Mapped[dict | None] = mapped_column(JSONB(none_as_null=True))
