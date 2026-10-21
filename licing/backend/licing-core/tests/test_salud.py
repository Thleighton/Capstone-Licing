def test_salud_y_documentacion(client):
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/api/salud").status_code == 200
    assert client.get("/docs").status_code == 200
    rutas = client.get("/api/openapi.json").json()["paths"]
    assert "/api/licitaciones" in rutas
    assert "/api/ingesta/licitaciones/lote/ejecutar" in rutas
    assert "/api/datos" not in rutas and "/api/sync" not in rutas
