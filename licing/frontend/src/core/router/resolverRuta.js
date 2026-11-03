export function resolverRuta(modulos, ruta, inicial) {
  if (!ruta) return inicial;
  return modulos.find(modulo => modulo.id === ruta || modulo.aliases?.includes(ruta))?.id || null;
}
