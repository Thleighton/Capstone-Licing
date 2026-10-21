from fastapi import FastAPI

from .api.ingesta import router as ingesta_router


tags_metadata = [
    {
        "name": "Core",
        "description": "Comprobación básica del servicio.",
    },
    {
        "name": "Licitaciones",
        "description": (
            "Consulta, almacenamiento crudo, normalización "
            "y procesamiento de licitaciones de Mercado Público. "
            "Incluye ejecución por lotes."
        ),
    },
    {
        "name": "Compras Ágiles",
        "description": (
            "Exploración paginada, almacenamiento crudo, "
            "normalización y procesamiento individual de Compras Ágiles. "
            "El procesamiento por lotes todavía está pendiente."
        ),
    },
]


app = FastAPI(
    title="LICING Core API",
    version="0.2.0",
    docs_url="/docs",
    openapi_tags=tags_metadata,
    swagger_ui_parameters={
        "docExpansion": "none",
    },
)

app.include_router(ingesta_router)


@app.get("/health", tags=["Core"], summary="Comprobar el servicio")
def health():
    return {"status": "ok"}