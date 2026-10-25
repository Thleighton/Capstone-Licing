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

    filtradas_url: str = "https://gzhofrcnefoxqvywzgei.supabase.co/functions/v1/licing-filtradas"
    documentos_automaticos: bool = True
    # Habilitar solo tras confirmar con ChileCompra el mecanismo autorizado de descarga del portal.
    mp_descarga_portal_habilitada: bool = False
    # Anexos de «Antecedentes para incluir en la oferta» (VerAntecedentes, sin reCAPTCHA). Requiere la anterior.
    mp_descarga_anexos_habilitada: bool = False
    documentos_storage_url: str = "https://nylzzocvemddikexqzav.supabase.co/functions/v1/documentos-origen"
    # cron-job.org espera hasta 30 s; dejar margen para red y arranque.
    documentos_timeout_segundos: float = Field(default=24, gt=0, le=25)

    max_raw_items: int = 20
    mp_actualizacion_horas: int = Field(default=24, ge=1, le=168)
    mp_reintento_error_minutos: int = Field(default=60, ge=1, le=1440)
    mp_lote_timeout_segundos: float = Field(default=45, gt=0, le=50)

    mp_pausa_detalles_segundos: float = Field(
        default=5.0,
        gt=0,
        le=300,
    )

    # API Compra Ágil v2: mismo ticket, enviado como cabecera.
    mp_compra_agil_url: str = "https://api2.mercadopublico.cl"
    # Ejecuta también un lote de Compra Ágil, en paralelo, en /api/cron/ingesta.
    compras_agiles_automaticas: bool = True
    # Códigos de región 1-16 separados por coma; vacío consulta todo el país.
    mp_compra_agil_regiones: str = Field(default="", pattern=r"^\s*(\d{1,2}\s*(,\s*\d{1,2}\s*)*)?$")
    # Separación entre solicitudes; la API responde 429 sobre 4 por segundo.
    mp_compra_agil_pausa_segundos: float = Field(default=0.35, ge=0.25, le=60)
    mp_compra_agil_paginas_por_lote: int = Field(default=5, ge=1, le=50)
    # /api/cron/ingesta espera este lote y su preselección (8 s); cron-job.org corta a los 30 s.
    mp_compra_agil_lote_timeout_segundos: float = Field(default=16, gt=0, le=50)


settings = Settings()
