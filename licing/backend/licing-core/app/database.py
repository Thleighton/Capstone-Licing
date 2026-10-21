import os

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import NullPool

from .config import settings

def crear_engine(url):
    opciones = {"pool_pre_ping": True}
    if os.environ.get("VERCEL") == "1":
        # Supabase mantiene su pool. No retenemos sesiones PostgreSQL entre
        # invocaciones de una función que Vercel puede suspender.
        opciones["poolclass"] = NullPool
    return create_engine(url, **opciones)


engine = crear_engine(settings.database_url)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
