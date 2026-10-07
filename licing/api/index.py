# Punto de entrada del backend en Vercel. Todas las rutas /api/* llegan aquí
# (ver "rewrites" en vercel.json) y las atiende la app FastAPI de backend/licing.
# En local: `uvicorn api.index:app --reload --port 8000` desde la raíz del repo.
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend"))

from licing.main import app  # noqa: E402,F401
