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

from ..database import Base


class CompraAgilItem(Base):
    __tablename__ = "compra_agil_item"

    __table_args__ = (
        UniqueConstraint(
            "compra_agil_id",
            "posicion",
            name="uq_compra_agil_item_posicion",
        ),
        CheckConstraint(
            "posicion > 0",
            name="ck_compra_agil_item_posicion",
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    compra_agil_id: Mapped[int] = mapped_column(
        ForeignKey("compra_agil.id"),
        nullable=False,
        index=True,
    )

    posicion: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    codigo_producto: Mapped[str | None] = mapped_column(String(50))
    nombre_producto: Mapped[str | None] = mapped_column(Text)
    descripcion: Mapped[str | None] = mapped_column(Text)
    cantidad: Mapped[Decimal | None] = mapped_column(Numeric)
    unidad_medida: Mapped[str | None] = mapped_column(Text)