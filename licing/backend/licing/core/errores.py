from fastapi import HTTPException


class ErrorApi(HTTPException):
    """Error con mensaje en español que el frontend muestra tal cual ({"error": "..."})."""

    def __init__(self, status: int, mensaje: str):
        super().__init__(status_code=status, detail=mensaje)
