// Datos de DEMOSTRACIÓN aislados de las consultas reales a Supabase.
// Los usan Dashboard (recomendaciones), Disponibilidad y Clientes.
// Cuando existan las tablas reales (salon, disponibilidad_salon, cliente_conocido),
// cada módulo debe reemplazar estas constantes por llamadas a la API.
import { createStore } from "../../core/store/createStore";

export const DEMO_CLIENTS = [
  { id: "c1", name: "Instituto Horizonte · ficticio", relation: "Cliente recurrente", known: true, contact: "Contacto A · coordinación de eventos", visits: 6, history: ["6 eventos anteriores (ejemplo)", "Último servicio: seminario y coffee break"], note: "Organización y contacto vinculados en esta simulación." },
  { id: "c2", name: "Fundación Encuentro · ficticia", relation: "Contacto conocido", known: true, contact: "Contacto B · administración", visits: 2, history: ["2 reuniones anteriores (ejemplo)", "Contacto con relación comercial previa"], note: "La vinculación del contacto se validaría con la cartera del hotel." },
  { id: "c3", name: "Centro Formación Sur · ficticio", relation: "Cliente nuevo", known: false, contact: "Por identificar", visits: 0, history: ["Sin historial en esta demostración"], note: "Se evalúa por los requisitos de la solicitud; no tiene prioridad por recurrencia." },
];

// Un solo edificio, según el alcance confirmado. Inventario tentativo.
export const DEMO_HOTEL = { name: "Hotel Plaza San Francisco", rooms: [
  { id: "r1", name: "Salón A · ejemplo", features: "Luz natural, climatización y acceso universal", capacity: 120, layout: "Auditorio", equipment: ["Proyector", "Audio", "Wi-Fi"], bookings: [{ date: "2026-10-05", start: "09:00", end: "13:00", label: "Evento reservado" }] },
  { id: "r2", name: "Salón B · ejemplo", features: "Espacio divisible, climatización y acceso universal", capacity: 80, layout: "Escuela", equipment: ["Proyector", "Audio", "Wi-Fi"], bookings: [{ date: "2026-10-05", start: "14:00", end: "18:00", label: "Evento reservado" }, { date: "2026-10-06", start: "09:00", end: "13:00", label: "Evento reservado" }] },
  { id: "r3", name: "Salón C · ejemplo", features: "Mesa central, climatización y aislamiento acústico", capacity: 20, layout: "Directorio", equipment: ["Pantalla", "Wi-Fi", "Videoconferencia"], bookings: [] },
] };
export const DEMO_ROOMS = DEMO_HOTEL.rooms;

export const DEMO_REQUESTS = [
  { id: "demo1", name: "Seminario y coffee break", client: "c1", date: "2026-10-05", start: "09:30", end: "12:30", module: "Mañana", people: 60, layout: "Escuela", equipment: ["Proyector", "Audio"], setup: 30, teardown: 30 },
  { id: "demo2", name: "Capacitación de equipo", client: "c3", date: "2026-10-05", start: "14:30", end: "17:30", module: "Tarde", people: 90, layout: "Auditorio", equipment: ["Proyector", "Wi-Fi"], setup: 30, teardown: 30 },
  { id: "demo3", name: "Congreso de jornada completa", client: "c1", date: "2026-10-05", start: "09:00", end: "18:00", module: "Jornada completa", people: 100, layout: "Auditorio", equipment: ["Proyector", "Audio"], setup: 30, teardown: 30 },
  { id: "demo4", name: "Reunión de coordinación", client: "c2", date: "2026-10-06", start: "09:30", end: "12:30", module: "Mañana", people: 12, layout: "Directorio", equipment: ["Videoconferencia"], setup: 30, teardown: 30 },
];

export const DEMO_MODULES = [["Mañana", "09:00", "13:00"], ["Tarde", "14:00", "18:00"], ["Jornada completa", "09:00", "18:00"]];

export const clockMinutes = t => Number(t.split(":")[0]) * 60 + Number(t.split(":")[1]);
export const overlapping = (start, end, b) => start < clockMinutes(b.end) && end > clockMinutes(b.start);
export const demoDate = d => d.split("-").reverse().join("/");

export function roomMatch(room, request) {
  const reasons = [];
  if (request.people > room.capacity) reasons.push("Capacidad insuficiente: " + room.capacity + " personas para " + request.people + " solicitadas.");
  if (request.layout !== room.layout) reasons.push("Montaje solicitado: " + request.layout + "; disponible en el ejemplo: " + room.layout + ".");
  const missing = request.equipment.filter(e => !room.equipment.includes(e));
  if (missing.length) reasons.push("Falta equipamiento: " + missing.join(", ") + ".");
  if (room.bookings.some(b => b.date === request.date && overlapping(clockMinutes(request.start) - request.setup, clockMinutes(request.end) + request.teardown, b)))
    reasons.push("Conflicto de horario, incluyendo montaje y desmontaje.");
  return { room, reasons, compatible: reasons.length === 0 };
}

export function demoRecommendation(request) {
  const client = DEMO_CLIENTS.find(c => c.id === request.client);
  const matches = DEMO_ROOMS.map(r => roomMatch(r, request));
  const available = matches.filter(m => m.compatible);
  const priority = !available.length ? "low" : client.known ? "high" : "medium";
  return { request, client, matches, available, priority };
}

// Selección compartida: el Dashboard puede abrir una solicitud en Disponibilidad.
export const seleccionDemo = createStore({ requestId: DEMO_REQUESTS[0].id, date: DEMO_REQUESTS[0].date });
