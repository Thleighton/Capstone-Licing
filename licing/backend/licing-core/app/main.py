from fastapi import FastAPI

from .api.ingesta import router as ingesta_router
from .database import Base, engine
from .models import raw, licitacion, licitacion_item  # noqa: F401

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="LICING Core API",
    version="0.1.0",
    docs_url="/docs",
)

app.include_router(ingesta_router)


@app.get("/health", tags=["Core"])
def health():
    return {"status": "ok"}