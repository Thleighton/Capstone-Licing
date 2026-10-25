from decimal import Decimal

from sqlalchemy import CheckConstraint, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class CompraAgilItem(Base):
    """Línea de productos_solicitados; la posición identifica la línea dentro del RAW."""
    __tablename__ = "compra_agil_item"
    __table_args__ = (
        UniqueConstraint("compra_agil_id", "posicion_fuente", name="uq_compra_agil_item_posicion"),
        CheckConstraint("posicion_fuente > 0", name="ck_compra_agil_item_posicion_positiva"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    compra_agil_id: Mapped[int] = mapped_column(
        ForeignKey("compra_agil.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    posicion_fuente: Mapped[int] = mapped_column(Integer, nullable=False)
    codigo_producto: Mapped[str | None] = mapped_column(String(50), index=True)
    nombre_producto: Mapped[str | None] = mapped_column(Text)
    descripcion: Mapped[str | None] = mapped_column(Text)
    cantidad: Mapped[Decimal | None] = mapped_column(Numeric())
    unidad_medida: Mapped[str | None] = mapped_column(Text)
