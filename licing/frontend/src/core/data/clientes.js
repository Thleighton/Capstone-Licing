export function normalizarNombreCliente(nombre) {
  if (typeof nombre !== "string") return "";
  return nombre.normalize("NFD")
    .replace(/\p{M}/gu, "")
    .toLowerCase()
    .replace(/[^\p{L}\p{N}]+/gu, " ")
    .trim();
}

export function clientesDestacados(oportunidad, clientesDemo, clientes) {
  const catalogo = clientes ?? oportunidad?.clientes_importantes ?? [];
  if (!oportunidad || !clientesDemo.length) return catalogo;

  const compradores = [oportunidad.nombre_organismo, oportunidad.nombre_unidad]
    .map(normalizarNombreCliente).filter(Boolean);
  const nombresCatalogo = new Set(catalogo.map(c => normalizarNombreCliente(c.nombre)));

  return [...catalogo, ...clientesDemo.filter(cliente => {
    const nombre = normalizarNombreCliente(cliente.nombre);
    return compradores.includes(nombre) && !nombresCatalogo.has(nombre);
  })];
}
