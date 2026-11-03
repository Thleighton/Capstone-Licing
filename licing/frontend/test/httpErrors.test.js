import test from "node:test";
import assert from "node:assert/strict";
import { detalleRespuesta, mensajeConexion, mensajeHttp } from "../src/core/api/httpErrors.js";
import { resolverRuta } from "../src/core/router/resolverRuta.js";

test("traduce un 404 sin cuerpo JSON a un mensaje claro", () => {
  assert.equal(mensajeHttp(404), "No encontramos la página o el recurso solicitado.");
  assert.equal(mensajeHttp(404, "Not Found"), "No encontramos la página o el recurso solicitado.");
});

test("prioriza el detalle seguro enviado por el backend", () => {
  assert.equal(mensajeHttp(404, "No se encontró la licitación"), "No se encontró la licitación");
  assert.equal(detalleRespuesta({ detail: [{ msg: "Falta el código" }] }), "Falta el código");
});

test("explica errores temporales del servidor y del servicio externo", () => {
  assert.match(mensajeHttp(503), /temporalmente/);
  assert.match(mensajeHttp(503, "Service Unavailable"), /temporalmente/);
  assert.match(mensajeHttp(502), /servicio externo/);
  assert.match(mensajeHttp(500), /problema/);
});

test("no convierte una cancelación del usuario en un error de conexión", () => {
  assert.equal(mensajeConexion({ name: "AbortError" }), "");
  assert.match(mensajeConexion(new TypeError("Failed to fetch")), /conectar con LICING/);
  assert.match(mensajeConexion(new TypeError("Failed to fetch"), "el servicio de autenticación"), /servicio de autenticación/);
});

test("resuelve rutas existentes y deja que la aplicación muestre su pantalla 404", () => {
  const modulos = [{ id: "dashboard" }, { id: "licitaciones", aliases: ["oportunidades"] }];
  assert.equal(resolverRuta(modulos, "", "dashboard"), "dashboard");
  assert.equal(resolverRuta(modulos, "oportunidades", "dashboard"), "licitaciones");
  assert.equal(resolverRuta(modulos, "pagina-que-no-existe", "dashboard"), null);
});
