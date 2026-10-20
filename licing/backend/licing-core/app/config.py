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


settings = Settings()