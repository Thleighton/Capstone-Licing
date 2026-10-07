"""App FastAPI de LICING. Cada módulo expone un APIRouter y se registra aquí."""
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .modulos import analisis, config_publica, datos, plantilla
from .modulos.sync import router as sync

app = FastAPI(title="LICING API", docs_url="/api/docs", openapi_url="/api/openapi.json")

ROUTERS = [
    config_publica.router,  # core
    datos.router,           # core (lectura de Licing/Datos)
    sync.router,            # E1 obtención de oportunidades
    analisis.router,        # E4/E5 bases y documentos
    plantilla.router,       # ejemplo para módulos nuevos
]
for r in ROUTERS:
    app.include_router(r)


# El frontend espera errores como {"error": "mensaje"}.
@app.exception_handler(HTTPException)
async def _http_error(_: Request, exc: HTTPException):
    return JSONResponse({"error": exc.detail}, status_code=exc.status_code, headers=getattr(exc, "headers", None))


@app.exception_handler(RequestValidationError)
async def _validation_error(_: Request, exc: RequestValidationError):
    return JSONResponse({"error": "Datos inválidos", "detalle": exc.errors()}, status_code=422)


@app.get("/api/salud", tags=["core"])
def salud():
    return {"ok": True}
