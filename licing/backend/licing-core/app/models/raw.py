from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class RawMercadoPublico(Base):
    __tablename__ = "raw_mercado_publico"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    fuente: Mapped[str] = mapped_column(String(50), nullable=False)
    tipo_consulta: Mapped[str] = mapped_column(String(30), nullable=False)
    parametro_consulta: Mapped[str | None] = mapped_column(String(200))

    codigo_externo: Mapped[str | None] = mapped_column(String(50), index=True)
    respuesta: Mapped[dict] = mapped_column(JSONB, nullable=False)

    http_status: Mapped[int] = mapped_column(Integer, nullable=False)
    cantidad_resultados: Mapped[int | None] = mapped_column(Integer)

    consultado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )