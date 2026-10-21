// Estar abierta no implica compatibilidad comercial con el hotel.
export const esAbierta = r => String(r.estado || "").toLowerCase() === "publicada" &&
  (!r.fecha_cierre || new Date(r.fecha_cierre) >= new Date());
