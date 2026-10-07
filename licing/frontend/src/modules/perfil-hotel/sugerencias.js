// Sugerencias SIMULADAS de palabras de interés (reglas fijas).
// En el producto final esto lo haría el motor IA/NLP del backend (POST /api/analisis/...).
import { normalizar } from "../../core/ui/format";

export const splitInterests = s => String(s || "").split(/[\n,;]+/).map(s => s.trim()).filter(Boolean);

const OFFER_TERMS = {
  "Alojamiento": [["alojamiento", "hospedaje", "pernoctación"], "Servicio de alojamiento para delegaciones"],
  "Coffee break": [["coffee break", "pausa café"], "Servicio de coffee break para eventos"],
  "Almuerzo o cena": [["almuerzo", "cena"], "Servicio de alimentación para asistentes a eventos"],
  "Banquetería": [["banquetería", "catering"], "Servicio de banquetería para eventos"],
  "Estacionamiento": [["estacionamiento"], "Evento con estacionamiento para asistentes"],
  "Apoyo técnico": [["apoyo técnico"], "Evento con apoyo técnico en sala"],
};
const EVENTS = { seminario: "seminario", seminarios: "seminario", capacitacion: "capacitación", capacitaciones: "capacitación", congreso: "congreso", congresos: "congreso", reunion: "reunión", reuniones: "reunión", taller: "taller", talleres: "taller" };

export function suggestedInterests(data) {
  const suggestions = [];
  const add = (text, target, reason) => suggestions.push({ text, target, reason });
  for (const service of data.getAll("servicios")) {
    const terms = OFFER_TERMS[service]; if (!terms) continue;
    for (const term of terms[0]) add(term, "intereses_palabras", "Servicio declarado: " + service);
    add(terms[1], "intereses_frases", "Servicio declarado: " + service);
  }
  for (const raw of splitInterests(data.get("tipos_evento"))) {
    const event = EVENTS[normalizar(raw)]; if (!event) continue;
    add(event, "intereses_palabras", "Tipo de evento declarado: " + raw);
    add("Espacio para " + event, "intereses_frases", "Tipo de evento declarado: " + raw);
  }
  if (data.get("montaje")) {
    add("salón de eventos", "intereses_palabras", "Montaje declarado: " + data.get("montaje"));
    add("Arriendo de salón con montaje " + data.get("montaje"), "intereses_frases", "Montaje declarado en la ficha del hotel");
  }
  const excluded = splitInterests(data.get("exclusiones_busqueda")).map(normalizar);
  const seen = new Set();
  return suggestions.filter(s => {
    const key = s.target + ":" + normalizar(s.text);
    if (seen.has(key) || excluded.some(x => normalizar(s.text).includes(x))) return false;
    seen.add(key); return true;
  });
}

// Validaciones cruzadas del formulario. Devuelve [campo, mensaje] o null.
export function validarPerfil(d) {
  for (const [min, max, label] of [["minimo", "maximo", "El presupuesto máximo"], ["capacidad_min", "capacidad_max", "La capacidad máxima"]]) {
    if (d.get(min) !== "" && d.get(max) !== "" && Number(d.get(max)) < Number(d.get(min))) return [max, label + " debe ser igual o mayor al mínimo."];
  }
  if (d.get("fecha_evento") && d.get("fecha_fin") && d.get("fecha_fin") < d.get("fecha_evento"))
    return ["fecha_fin", "El término no puede ser anterior al inicio del evento."];
  if (d.get("hora_inicio") && d.get("hora_fin") && d.get("hora_fin") <= d.get("hora_inicio") && (!d.get("fecha_fin") || d.get("fecha_fin") === d.get("fecha_evento")))
    return ["hora_fin", "Indique una hora posterior o una fecha de término posterior si el evento cruza la medianoche."];
  return null;
}
export const CAMPOS_VALIDADOS = ["maximo", "capacidad_max", "fecha_fin", "hora_fin"];
