"""Worker CPU opcional: uvicorn app.semantica_api:app --port 8010."""
import hmac
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from pydantic_settings import BaseSettings, SettingsConfigDict
from starlette.concurrency import run_in_threadpool

from .services.semantica_hotel import MAX_SEGMENTOS, REVISION, TAMANO_TEXTO, VERSION, _modelo


class WorkerSettings(BaseSettings):
    # El worker no necesita credenciales de PostgreSQL ni de Mercado Público.
    model_config = SettingsConfigDict(env_file=(Path(__file__).resolve().parents[3] / ".env",
        Path(__file__).resolve().parents[1] / ".env"), env_file_encoding="utf-8", extra="ignore")
    semantica_token: str = ""
    semantica_modelo_dir: str = ""


settings = WorkerSettings()


@asynccontextmanager
async def lifespan(app):
    if settings.semantica_token and settings.semantica_modelo_dir:
        await run_in_threadpool(_modelo, settings.semantica_modelo_dir)
    yield


app = FastAPI(title="Clasificador semántico de servicios hoteleros", docs_url=None, openapi_url=None,
              lifespan=lifespan)


def autorizar(authorization: str = Header(default="")):
    if not settings.semantica_token:
        raise HTTPException(503, "Falta configurar la credencial del worker")
    if not hmac.compare_digest(authorization, "Bearer " + settings.semantica_token):
        raise HTTPException(401, "Sin acceso")


class Consulta(BaseModel):
    model_config = ConfigDict(extra="forbid")
    textos: list[Annotated[str, StringConstraints(min_length=1, max_length=TAMANO_TEXTO)]] = Field(min_length=1, max_length=MAX_SEGMENTOS)


@app.post("/clasificar", dependencies=[Depends(autorizar)])
def clasificar(consulta: Consulta):
    if not settings.semantica_modelo_dir:
        raise HTTPException(503, "Falta configurar el directorio del modelo")
    try:
        modelo = _modelo(settings.semantica_modelo_dir)
        valores = [modelo.puntuar(t) for t in consulta.textos]
    except Exception:
        raise HTTPException(503, "No se pudo completar la inferencia") from None
    return {"version": VERSION, "revision": REVISION, "puntuaciones": [v[0] for v in valores],
            "parcial": any(v[1] for v in valores)}
