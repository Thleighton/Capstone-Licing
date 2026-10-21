from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.exc import SQLAlchemyError

from .api.config_publica import router as config_router
from .api.consultas import router as consultas_router
from .api.ingesta import router as ingesta_router


app = FastAPI(
    title="LICING Core API",
    version="0.1.0",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
)

app.include_router(config_router)
app.include_router(consultas_router)
app.include_router(ingesta_router, prefix="/api")
# Compatibilidad con los comandos existentes de Core, con los mismos permisos.
app.include_router(ingesta_router, include_in_schema=False)


@app.exception_handler(HTTPException)
async def http_error(_: Request, exc: HTTPException):
    return JSONResponse({"error": exc.detail}, status_code=exc.status_code, headers=exc.headers)


@app.exception_handler(RequestValidationError)
async def validation_error(_: Request, exc: RequestValidationError):
    return JSONResponse({"error": "Datos inválidos"}, status_code=422)


@app.exception_handler(SQLAlchemyError)
async def database_error(_: Request, exc: SQLAlchemyError):
    return JSONResponse({"error": "No se pudo consultar la base de licitaciones"}, status_code=503)


@app.get("/docs", include_in_schema=False)
def docs():
    return RedirectResponse("/api/docs")


@app.get("/health", tags=["Core"])
@app.get("/api/salud", tags=["Core"])
def health():
    return {"status": "ok"}
