// Reglas derivadas sobre las licitaciones (compartidas por Dashboard y Oportunidades).
import { DIA } from "../ui/format";

export const esCandidata = r => !r.descartada_filtro;
export const esNueva = r => Date.now() - new Date(r.creado_en) < DIA;
export const confianza = r => {
  const c = r.requisito_extraido?.[0]?.confianza_nlp;
  return c == null ? null : Math.round(c * 100);
};

export const RUBROS = [
  ["Alojamiento", ["Alojamiento"]],
  ["Banquetes & Eventos", ["Coffee break", "Almuerzo", "Cena", "Cóctel"]],
  ["Salones de Reunión", ["Arriendo de salón"]],
];
export const rubros = rows => RUBROS.map(([nombre, servicios]) => [
  nombre,
  rows.filter(r => (r.requisito_extraido || []).some(q => (q.servicios_req || []).some(s => servicios.includes(s.servicio)))).length,
]);

export const SELECT_LICITACIONES =
  "licitacion?select=id,codigo_mp,tipo,nombre,descripcion,fecha_publicacion,fecha_cierre,monto_estimado,moneda,estado_mp,url," +
  "descartada_filtro,motivo_descarte,n_oferentes,creado_en,organismo(nombre,unidad_compra,region,comuna)," +
  "requisito_extraido(confianza_nlp,n_asistentes,servicios_req)&order=fecha_publicacion.desc.nullslast&limit=500";

export const SELECT_EJECUCIONES =
  "ejecucion_busqueda?select=inicio,fin,estado,disparo,n_obtenidas,n_nuevas,error&order=id.desc&limit=5";
