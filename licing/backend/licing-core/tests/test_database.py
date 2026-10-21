from sqlalchemy.pool import NullPool, QueuePool

from app.database import crear_engine

URL_PRUEBA = "postgresql+psycopg://test:test@localhost/licing_test"


def test_vercel_delega_pool_a_supabase(monkeypatch):
    monkeypatch.setenv("VERCEL", "1")
    engine = crear_engine(URL_PRUEBA)
    try:
        assert isinstance(engine.pool, NullPool)
    finally:
        engine.dispose()


def test_desarrollo_conserva_pool_local(monkeypatch):
    monkeypatch.delenv("VERCEL", raising=False)
    engine = crear_engine(URL_PRUEBA)
    try:
        assert isinstance(engine.pool, QueuePool)
    finally:
        engine.dispose()
