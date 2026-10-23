from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

CORE_DIR = Path(__file__).resolve().parent.parent
ENV_FILES = (CORE_DIR / ".env",)
if CORE_DIR.name == "licing-core" and CORE_DIR.parent.name == "backend":
    ENV_FILES = (CORE_DIR.parent.parent / ".env", *ENV_FILES)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # Conserva el .env de Core; el de LICING puede aportar el login.
        env_file=ENV_FILES,
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
    )

    mp_ticket: str

    mp_base_url: str = (
        "https://api.mercadopublico.cl/servicios/v1/publico"
    )

    database_url: str

    usuarios_url: str = ""
    usuarios_anon_key: str = ""

    # Secreto del planificador externo. Vacío desactiva /api/cron/ingesta.
    cron_secret: str = ""

    max_raw_items: int = 20
    mp_actualizacion_horas: int = Field(default=24, ge=1, le=168)
    mp_reintento_error_minutos: int = Field(default=60, ge=1, le=1440)
    mp_lote_timeout_segundos: float = Field(default=45, gt=0, le=50)

    mp_pausa_detalles_segundos: float = Field(
        default=5.0,
        gt=0,
        le=300,
    )


settings = Settings()
