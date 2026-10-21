import httpx

from ..config import settings


class MercadoPublicoClient:
    def __init__(self):
        self.client = httpx.AsyncClient(
            base_url=settings.mp_base_url,
            timeout=httpx.Timeout(30.0, connect=5.0),
        )

    async def licitaciones_por_fecha(self, fecha_ddmmaaaa: str) -> dict:
        response = await self.client.get(
            "/licitaciones.json",
            params={
                "fecha": fecha_ddmmaaaa,
                "ticket": settings.mp_ticket,
            },
        )
        response.raise_for_status()
        return response.json()

    async def licitacion_por_codigo(self, codigo: str) -> dict:
        response = await self.client.get(
            "/licitaciones.json",
            params={
                "codigo": codigo,
                "ticket": settings.mp_ticket,
            },
        )
        response.raise_for_status()
        return response.json()

    async def licitaciones_activas(self) -> dict:
        response = await self.client.get(
            "/licitaciones.json",
            params={
                "estado": "activas",
                "ticket": settings.mp_ticket,
            },
        )
        response.raise_for_status()
        return response.json()

    async def cerrar(self):
        await self.client.aclose()