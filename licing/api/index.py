# Entrada única: en local y en Vercel se sirve el mismo backend Core.
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend", "licing-core"))

from app.main import app  # noqa: E402,F401
