# Backend FastAPI para desarrollo local. Se construye desde la raíz del repo
# (ver docker-compose.yml) porque necesita api/ y requirements.txt.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY requirements.txt ./
COPY backend/requirements-dev.txt backend/
RUN pip install -r backend/requirements-dev.txt

COPY api/ api/
COPY backend/ backend/

EXPOSE 8000
CMD ["uvicorn", "api.index:app", "--host", "0.0.0.0", "--port", "8000", "--reload", "--reload-dir", "api", "--reload-dir", "backend"]
