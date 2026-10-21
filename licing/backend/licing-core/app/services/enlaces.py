"""Enlaces públicos; nunca se expone el endpoint de API con su ticket."""
import re
from urllib.parse import quote


def ficha_oficial(codigo: str) -> str | None:
    codigo = codigo.strip()
    if not re.fullmatch(r"\d+-\d+-[A-Za-z]+\d+", codigo):
        return None
    return "https://www.mercadopublico.cl/fichaLicitacion.html?idLicitacion=" + quote(codigo, safe="")
