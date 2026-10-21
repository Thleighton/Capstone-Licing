import httpx

from ..config import settings


class CompraAgilClient:
    def __init__(self) -> None:
        self.client = httpx.AsyncClient(
            base_url=settings.mp_ca_base_url,
            timeout=httpx.Timeout(30.0, connect=5.0),
            headers={
                "ticket": settings.mp_ticket,
            },
        )

    async def comprar_agiles(
        self,
        region: int | None = None,
        pagina: int = 1,
        tamano_pagina: int = 10,
    ) -> dict:
        params = {
            "estado": "publicada",
            "ordenar_por": "FechaPublicacion",
            "tamano_pagina": tamano_pagina,
            "numero_pagina": pagina,
        }

        if region is not None:
            params["region"] = region

        response = await self.client.get(
            "/v2/compra-agil",
            params=params,
        )

        response.raise_for_status()
        return response.json()

    async def detalle_por_codigo(self, codigo: str) -> dict:
        response = await self.client.get(
            f"/v2/compra-agil/{codigo}",
        )

        response.raise_for_status()
        return response.json()    

    async def cerrar(self) -> None:
        await self.client.aclose()