from decimal import Decimal

from sqlalchemy import BigInteger, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class CompraAgil(Base):
    __tablename__ = "compra_agil"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

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

    estado: Mapped[str | None] = mapped_column(String(50))
    estado_glosa: Mapped[str | None] = mapped_column(Text)
    codigo_estado: Mapped[int | None] = mapped_column(Integer)

    fecha_publicacion_original: Mapped[str | None] = mapped_column(Text)
    fecha_cierre_original: Mapped[str | None] = mapped_column(Text)
    fecha_ultimo_cambio_original: Mapped[str | None] = mapped_column(Text)
    fecha_cancelacion_original: Mapped[str | None] = mapped_column(Text)

    tipo_presupuesto: Mapped[str | None] = mapped_column(String(50))
    moneda: Mapped[str | None] = mapped_column(String(20))

    presupuesto_estimado: Mapped[Decimal | None] = mapped_column(Numeric)
    monto_disponible: Mapped[Decimal | None] = mapped_column(Numeric)
    monto_disponible_clp: Mapped[Decimal | None] = mapped_column(Numeric)

    rut_comprador: Mapped[str | None] = mapped_column(String(30))
    nombre_organismo: Mapped[str | None] = mapped_column(Text)
    nombre_unidad: Mapped[str | None] = mapped_column(Text)

    codigo_region: Mapped[int | None] = mapped_column(Integer)
    region_comprador: Mapped[str | None] = mapped_column(Text)

    direccion_entrega: Mapped[str | None] = mapped_column(Text)
    plazo_entrega_dias: Mapped[int | None] = mapped_column(Integer)

    numero_convocatoria: Mapped[int | None] = mapped_column(Integer)

    fecha_cierre_primer_llamado_original: Mapped[str | None] = mapped_column(
        Text
    )
    fecha_cierre_segundo_llamado_original: Mapped[str | None] = mapped_column(
        Text
    )

    id_orden_compra: Mapped[int | None] = mapped_column(BigInteger)