from urllib.parse import quote

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


class CompraAgilClient:
    """API Compra Ágil v2. El ticket viaja en la cabecera, nunca en la URL."""

    def __init__(self):
        self.client = httpx.AsyncClient(
            base_url=settings.mp_compra_agil_url,
            headers={"ticket": settings.mp_ticket},
            timeout=httpx.Timeout(30.0, connect=5.0),
        )

    @staticmethod
    def _payload(response: httpx.Response) -> dict:
        response.raise_for_status()
        cuerpo = response.json()
        if not isinstance(cuerpo, dict) or cuerpo.get("success") != "OK" or not isinstance(cuerpo.get("payload"), dict):
            raise ValueError("La API de Compra Ágil no devolvió un payload válido.")
        return cuerpo["payload"]

    async def listar(self, params: dict) -> dict:
        return self._payload(await self.client.get("/v2/compra-agil", params=params))

    async def detalle(self, codigo: str) -> dict | None:
        """None solo cuando la API confirma que el código no existe o no es público."""
        response = await self.client.get("/v2/compra-agil/" + quote(codigo, safe=""))
        if response.status_code == 404:
            try:
                errores = response.json().get("errors") or []
            except (ValueError, AttributeError):
                errores = []
            if any(isinstance(e, dict) and e.get("codigo") == "NO_ENCONTRADO" for e in errores):
                return None
        return self._payload(response)

    async def cerrar(self):
        await self.client.aclose()
