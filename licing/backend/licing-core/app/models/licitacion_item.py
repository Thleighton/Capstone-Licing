from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import JSONB

from ..database import Base


class LicitacionItem(Base):
    __tablename__ = "licitacion_item"

    __table_args__ = (
        UniqueConstraint(
            "licitacion_id",
            "posicion_fuente",
            name="uq_licitacion_item_posicion",
        ),
        CheckConstraint("posicion_fuente > 0", name="ck_item_posicion_positiva"),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    licitacion_id: Mapped[int] = mapped_column(
        ForeignKey("licitacion.id"),
        nullable=False,
        index=True,
    )

    correlativo: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    posicion_fuente: Mapped[int] = mapped_column(Integer, nullable=False)
    codigo_producto: Mapped[str | None] = mapped_column(String(50))
    nombre_producto: Mapped[str | None] = mapped_column(Text)
    descripcion: Mapped[str | None] = mapped_column(Text)

    cantidad: Mapped[Decimal | None] = mapped_column(Numeric())
    unidad_medida: Mapped[str | None] = mapped_column(Text)
    codigo_categoria: Mapped[str | None] = mapped_column(String(100), index=True)
    categoria: Mapped[str | None] = mapped_column(Text)
    estado_fuente: Mapped[int | None] = mapped_column(Integer)
    adjudicacion_fuente: Mapped[dict | None] = mapped_column(JSONB)
