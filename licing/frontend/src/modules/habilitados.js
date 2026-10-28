// Módulos pausados temporalmente; se conservan sus pantallas y datos.
const DESACTIVADOS = ["formulario", "disponibilidad", "analisis", "seguimiento", "reportes"];

export const moduloHabilitado = id => !DESACTIVADOS.includes(id);
