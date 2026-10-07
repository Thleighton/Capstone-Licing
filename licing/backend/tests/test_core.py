from licing.modulos.datos import embebidas


def test_config_publica_es_json(client, monkeypatch):
    monkeypatch.setenv("USUARIOS_URL", "https://usr.supabase.co")
    monkeypatch.setenv("USUARIOS_ANON_KEY", "anon")
    monkeypatch.setenv("SUPABASE_URL", "https://datos.supabase.co")
    r = client.get("/api/config")
    assert r.status_code == 200
    assert r.json() == {"USUARIOS_URL": "https://usr.supabase.co", "USUARIOS_KEY": "anon", "DATOS_HOST": "datos.supabase.co"}
    assert "SERVICE" not in r.text.upper()


def test_datos_exige_sesion(client):
    r = client.get("/api/datos", params={"t": "licitacion"})
    assert r.status_code == 401
    assert r.json() == {"error": "Debes iniciar sesión"}


def test_datos_rechaza_tabla_fuera_de_lista(client_autenticado):
    r = client_autenticado.get("/api/datos", params={"t": "usuario"})
    assert r.status_code == 400
    assert "Tabla no permitida" in r.json()["error"]


def test_datos_rechaza_relacion_embebida_no_permitida(client_autenticado):
    r = client_autenticado.get("/api/datos", params={"t": "licitacion", "q": "select=id,secreto(x)"})
    assert r.status_code == 400
    assert "secreto" in r.json()["error"]


def test_embebidas():
    assert embebidas("id,organismo(nombre),alias:requisito_extraido!fk(x)") == ["organismo", "requisito_extraido"]
    assert embebidas(None) == []


def test_sync_exige_secreto(client, monkeypatch):
    monkeypatch.setenv("CRON_SECRET", "abc")
    assert client.get("/api/sync").status_code == 401
    assert client.get("/api/sync", headers={"Authorization": "Bearer otro"}).status_code == 401


def test_analisis_simulado(client_autenticado):
    r = client_autenticado.post("/api/analisis/simular", json={"ejemplo": "seminario"})
    assert r.status_code == 200
    assert r.json()["participantes"] == "80 personas"
    assert client_autenticado.post("/api/analisis/simular", json={"ejemplo": "otro"}).status_code == 422


def test_plantilla_saluda(client_autenticado):
    assert client_autenticado.get("/api/plantilla/hola").json()["mensaje"] == "Hola Usuario Prueba"
