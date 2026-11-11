// Adaptador privado de persistencia. Las reglas y la lectura de PDF viven en Core.
const AUTH_URL = "https://capstone-licing.vercel.app/api/preseleccion/integracion/verificar";
const MAX_BODY = 16_000_000;
const operaciones = new Set(["guardar", "listar", "detalle", "revision", "sincronizar_fuente"]);
class Fallo extends Error {
  constructor(public status: number, mensaje: string, public codigo: string) { super(mensaje); }
}
const respuesta = (dato: unknown, status = 200) => new Response(JSON.stringify(dato), {
  status, headers: { "content-type": "application/json", "cache-control": "no-store" },
});
export function crearHandler(base: string, key: string, fetcher: typeof fetch = fetch) {
  const headers = { "apikey": key, "Authorization": `Bearer ${key}`, "content-type": "application/json" };
  async function interno(path: string, body: unknown, metodo = "POST") {
    let res: Response;
    try {
      res = await fetcher(base + path, { method: metodo, headers,
        body: JSON.stringify(body), signal: AbortSignal.timeout(30_000), redirect: "error" });
    } catch {
      throw new Fallo(503, "Integración temporalmente no disponible", "RPC_NETWORK_OR_TIMEOUT");
    }
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      const sqlstate = typeof data.code === "string" && /^[A-Z0-9]{4,8}$/.test(data.code)
        ? data.code : `HTTP_${res.status}`;
      throw new Fallo(data.code === "40001" || data.code === "P0001" ? 409 : 503,
        data.code === "40001" ? "Los datos cambiaron. Actualiza y vuelve a intentarlo."
          : "No se pudo completar la operación en filtradas.", `RPC_${sqlstate}`);
    }
    return data;
  }
  async function rpc(operacion: string, datos: Record<string, unknown>) {
    return await interno("/rest/v1/rpc/lf_operar", { operacion, datos });
  }
  return async (req: Request) => {
    if (req.method !== "POST") return respuesta({ error: "Método no admitido" }, 405);
    const auth = req.headers.get("authorization") || "";
    if (!/^Bearer [^\s]{16,512}$/.test(auth)) return respuesta({ error: "Sin autorización" }, 401);
    try {
      // La comprobación ocurre antes de leer el cuerpo; nunca acepta JWT del navegador.
      let verificacion: Response;
      try {
        verificacion = await fetcher(AUTH_URL, { headers: { Authorization: auth },
          redirect: "error", signal: AbortSignal.timeout(12_000) });
      } catch {
        throw new Fallo(503, "Integración temporalmente no disponible", "AUTH_NETWORK_OR_TIMEOUT");
      }
      if (!verificacion.ok || (await verificacion.json()).autorizada !== true)
        return respuesta({ error: "No se pudo verificar la integración",
          codigo: verificacion.status === 401 ? "AUTH_UNAUTHORIZED" : `AUTH_HTTP_${verificacion.status}` },
        verificacion.status === 401 ? 401 : 503);
      const reader = req.body?.getReader();
      if (!reader) throw new Fallo(422, "Falta el cuerpo", "BODY_MISSING");
      const partes: Uint8Array[] = []; let size = 0;
      while (true) {
        const { done, value } = await reader.read(); if (done) break;
        size += value.length;
        if (size > MAX_BODY) { await reader.cancel(); throw new Fallo(413, "Entrada demasiado grande", "BODY_TOO_LARGE"); }
        partes.push(value);
      }
      const buffer = new Uint8Array(size); let offset = 0;
      for (const parte of partes) { buffer.set(parte, offset); offset += parte.length; }
      let entrada;
      try { entrada = JSON.parse(new TextDecoder().decode(buffer)); } catch { throw new Fallo(422, "JSON inválido", "BODY_INVALID_JSON"); }
      const { operacion, datos } = entrada || {};
      if (!operaciones.has(operacion) || !datos || Array.isArray(datos) || typeof datos !== "object")
        throw new Fallo(422, "Operación inválida", "OPERATION_INVALID");
      const result = await rpc(operacion, datos);
      return respuesta(result);
    } catch (error) {
      return respuesta({ error: error instanceof Fallo ? error.message : "Integración temporalmente no disponible",
        codigo: error instanceof Fallo ? error.codigo : "EDGE_UNEXPECTED_ERROR" },
      error instanceof Fallo ? error.status : 503);
    }
  };
}
