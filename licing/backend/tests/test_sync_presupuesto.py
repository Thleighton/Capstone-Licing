import asyncio
from types import SimpleNamespace

from licing.modulos.sync import router

CRIT = {"keywords": ["seminario"], "region": "Metropolitana"}


def _simular(monkeypatch, segundos_por_ficha: float, limite: float) -> tuple[dict, list[str]]:
    """Corre sync_licitaciones con API y Supabase falsos; cada ficha guardada avanza el reloj."""
    reloj = [0.0]
    guardadas: list[str] = []
    lista = [{"CodigoExterno": f"{i}-1-LE26", "Nombre": f"Seminario {i}"} for i in range(5)]

    async def get_licitaciones(_client, qs):
        if qs == "estado=activas":
            return {"Listado": lista}
        codigo = qs.split("=", 1)[1]
        return {"Listado": [{"CodigoExterno": codigo, "Nombre": "Seminario", "Estado": "Publicada",
                             "Comprador": {"RegionUnidad": "Región Metropolitana de Santiago"}}]}

    async def codigos_existentes(_client, _codigos):
        return set()

    async def guardar(_client, n, _ejec_id):
        guardadas.append(n["lic"]["codigo_mp"])
        reloj[0] += segundos_por_ficha

    async def sin_espera(_s):
        pass

    monkeypatch.setattr(router, "get_licitaciones", get_licitaciones)
    monkeypatch.setattr(router, "codigos_existentes", codigos_existentes)
    monkeypatch.setattr(router, "guardar", guardar)
    # Solo en el módulo router: el event loop sigue usando el reloj real.
    monkeypatch.setattr(router, "asyncio", SimpleNamespace(sleep=sin_espera))
    monkeypatch.setattr(router, "time", SimpleNamespace(monotonic=lambda: reloj[0]))

    stats = {"obtenidas": 0, "nuevas": 0, "filtradas": 0, "pendientes": 0, "errores": []}
    asyncio.run(router.sync_licitaciones(None, CRIT, 1, 30, limite, stats))
    return stats, guardadas


def test_sync_licitaciones_procesa_todo_si_hay_tiempo(monkeypatch):
    stats, guardadas = _simular(monkeypatch, segundos_por_ficha=1, limite=40)
    assert len(guardadas) == 5
    assert stats["nuevas"] == 5 and stats["filtradas"] == 5 and stats["pendientes"] == 0


def test_sync_licitaciones_deja_pendientes_al_agotar_el_presupuesto(monkeypatch):
    stats, guardadas = _simular(monkeypatch, segundos_por_ficha=15, limite=40)
    assert guardadas == ["0-1-LE26", "1-1-LE26", "2-1-LE26"]  # t=0, 15, 30; en t=45 ya no pide más
    assert stats["nuevas"] == 3 and stats["pendientes"] == 2 and stats["errores"] == []
