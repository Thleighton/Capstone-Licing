const MENSAJES_HTTP = {
  400: "La solicitud no es válida.",
  404: "No encontramos la página o el recurso solicitado.",
  408: "La solicitud tardó demasiado. Inténtalo nuevamente.",
  429: "Hay demasiadas solicitudes en este momento. Espera un momento e inténtalo nuevamente.",
  500: "LICING tuvo un problema al procesar la solicitud. Inténtalo nuevamente.",
  502: "No se pudo obtener una respuesta válida del servicio externo.",
  503: "LICING no está disponible temporalmente. Inténtalo nuevamente en unos minutos.",
  504: "El servicio tardó demasiado en responder. Inténtalo nuevamente.",
};

export function detalleRespuesta(data) {
  if (typeof data === "string") return data.trim();
  if (!data || typeof data !== "object") return "";

  const detalle = data.error || data.detail || data.message || data.msg;
  if (typeof detalle === "string") return detalle.trim();
  if (Array.isArray(detalle)) {
    return detalle.map(item => typeof item === "string" ? item : item?.msg).filter(Boolean).join(" ");
  }
  return "";
}

export function mensajeHttp(status, detalle = "") {
  const texto = typeof detalle === "string" ? detalle.trim() : "";
  if (status === 404) return !texto || /^(not found|404 not found)$/i.test(texto) ? MENSAJES_HTTP[404] : texto;
  if (status >= 500) {
    const mensajeGenerico = /^(internal server error|bad gateway|service unavailable|gateway timeout|server error)$/i.test(texto);
    return !texto || mensajeGenerico ? MENSAJES_HTTP[status] || MENSAJES_HTTP[500] : texto;
  }
  if (status === 408 || status === 429) return texto || MENSAJES_HTTP[status];
  if (status >= 400) return texto || MENSAJES_HTTP[status] || `La solicitud no se pudo completar (HTTP ${status}).`;
  return texto;
}

export function mensajeConexion(error, servicio = "LICING") {
  if (error?.name === "AbortError") return "";
  return `No se pudo conectar con ${servicio}. Revisa tu conexión e inténtalo nuevamente.`;
}
