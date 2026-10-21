// Demostración local; el análisis documental sigue pendiente.
export const EJEMPLOS = [
  { id: "alojamiento", nombre: "Servicio de alojamiento para delegación" },
  { id: "seminario", nombre: "Seminario y coffee break para 80 personas" },
];
const RESULTADOS = {
  alojamiento: { titulo: "Alojamiento de delegación", servicio: "20 habitaciones por 3 noches", participantes: "40 personas" },
  seminario: { titulo: "Seminario y coffee break", servicio: "Salón, proyección y coffee break", participantes: "80 personas" },
};
export const analizarEjemplo = ejemplo => Promise.resolve({
  ...RESULTADOS[ejemplo], presupuesto: "Por confirmar en las bases",
  documentos: "Oferta técnica, económica y antecedentes administrativos",
  pendientes: "disponibilidad, fechas exactas y condiciones de pago.", simulado: true,
});
