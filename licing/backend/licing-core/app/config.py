from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )

    mp_ticket: str

    mp_base_url: str = (
        "https://api.mercadopublico.cl/servicios/v1/publico"
    )

    database_url: str

    max_raw_items: int = 20

    mp_pausa_detalles_segundos: float = Field(
        default=5.0,
        gt=0,
        le=300,
    )


settings = Settings()