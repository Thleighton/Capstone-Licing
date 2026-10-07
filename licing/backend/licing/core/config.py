"""Variables de entorno. En local se leen del archivo .env en la raíz del repo;
en Vercel, desde Settings > Environment Variables."""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[3] / ".env")


def env(nombre: str, defecto: str = "") -> str:
    return os.environ.get(nombre, defecto) or defecto


def faltantes(*nombres: str) -> list[str]:
    return [n for n in nombres if not env(n)]
