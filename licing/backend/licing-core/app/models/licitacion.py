from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class Licitacion(Base):
    __tablename__ = "licitacion"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    codigo_externo: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        unique=True,
    )

    raw_id: Mapped[int] = mapped_column(
        ForeignKey("raw_mercado_publico.id"),
        nullable=False,
        index=True,
    )

    nombre: Mapped[str | None] = mapped_column(Text)
    descripcion: Mapped[str | None] = mapped_column(Text)

    codigo_estado: Mapped[int | None] = mapped_column(Integer)
    estado: Mapped[str | None] = mapped_column(String(50))

    monto_estimado: Mapped[Decimal | None] = mapped_column(Numeric())
    moneda: Mapped[str | None] = mapped_column(String(20))

    fecha_publicacion: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=False)
    )
    fecha_cierre: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=False)
    )

    codigo_organismo: Mapped[str | None] = mapped_column(String(50))
    nombre_organismo: Mapped[str | None] = mapped_column(Text)

    codigo_unidad: Mapped[str | None] = mapped_column(String(50))
    nombre_unidad: Mapped[str | None] = mapped_column(Text)

    region_comprador: Mapped[str | None] = mapped_column(Text)
    comuna_comprador: Mapped[str | None] = mapped_column(Text)

    tipo: Mapped[str | None] = mapped_column(String(30))
    codigo_tipo: Mapped[int | None] = mapped_column(Integer)
    estimacion: Mapped[int | None] = mapped_column(Integer)
    visibilidad_monto: Mapped[int | None] = mapped_column(Integer)
    justificacion_monto: Mapped[str | None] = mapped_column(Text)
    direccion_comprador: Mapped[str | None] = mapped_column(Text)
    direccion_entrega: Mapped[str | None] = mapped_column(Text)
    direccion_visita: Mapped[str | None] = mapped_column(Text)
    # Contexto de la API, sin interpretarlo como fechas/lugar del evento.
    fechas_fuente: Mapped[dict | None] = mapped_column(JSONB)
    condiciones_fuente: Mapped[dict | None] = mapped_column(JSONB)
    normalizacion_version: Mapped[str | None] = mapped_column(String(30))
    normalizado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
