// Llamadas del módulo al backend Python (api/licing/modulos/analisis.py).
import { apiFetch } from "../../core/api/client";

export const EJEMPLOS = [
  { id: "alojamiento", nombre: "Servicio de alojamiento para delegación" },
  { id: "seminario", nombre: "Seminario y coffee break para 80 personas" },
];

/** Hoy devuelve un resultado simulado. Cuando exista el motor IA/NLP, la firma se mantiene. */
export const analizarEjemplo = ejemplo =>
  apiFetch("/api/analisis/simular", { method: "POST", body: { ejemplo } }).then(r => r.json());
