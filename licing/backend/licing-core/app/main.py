from fastapi import FastAPI

from .api.ingesta import router as ingesta_router


app = FastAPI(
    title="LICING Core API",
    version="0.1.0",
    docs_url="/docs",
)

app.include_router(ingesta_router)


@app.get("/health", tags=["Core"])
def health():
    return {"status": "ok"}