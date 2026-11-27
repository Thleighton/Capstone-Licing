import assert from "node:assert/strict";
import test from "node:test";
import { clientesDestacados } from "../src/core/data/clientes.js";

const osorno = { id: "demo-1", nombre: "Servicio de Salud Osorno" };

test("destaca al cliente agregado por organismo o unidad compradora", () => {
  assert.deepEqual(clientesDestacados({
    nombre_organismo: "SERVICIO  DE SALUD OSORNO",
    nombre_unidad: "Servicio de Salud Osorno",
  }, [osorno]), [osorno]);

  assert.deepEqual(clientesDestacados({
    nombre_organismo: "Ministerio de Salud",
    nombre_unidad: "Servicio de Salud Osórno.",
  }, [osorno]), [osorno]);
});

test("omite coincidencias parciales y menciones en los datos del proceso", () => {
  assert.deepEqual(clientesDestacados({
    nombre_organismo: "Servicio de Salud Osorno Norte",
    nombre_unidad: null,
    nombre: "Servicios para Servicio de Salud Osorno",
    descripcion: "Cotizar para Servicio de Salud Osorno",
  }, [osorno]), []);
});

test("conserva los clientes del catálogo y evita mostrar el mismo nombre dos veces", () => {
  const ministerio = { id: "minsal", nombre: "Ministerio de Salud" };
  const oportunidad = {
    nombre_organismo: "MINISTERIO DE SALUD",
    nombre_unidad: osorno.nombre,
    clientes_importantes: [ministerio],
  };
  assert.deepEqual(clientesDestacados(oportunidad, [
    { id: "demo-2", nombre: "Ministerio de Salud." },
    osorno,
  ]), [ministerio, osorno]);
  assert.deepEqual(clientesDestacados(oportunidad, []), [ministerio]);
});
