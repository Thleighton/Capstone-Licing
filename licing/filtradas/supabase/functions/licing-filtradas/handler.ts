// Adaptador privado de persistencia. Las reglas y la lectura de PDF viven en Core.
const AUTH_URL = "https://capstone-licing.vercel.app/api/preseleccion/integracion/verificar";
const MAX_BODY = 16_000_000;
const operaciones = new Set(["guardar", "listar", "detalle", "revision", "sincronizar_fuente"]);
class Fallo extends Error { constructor(public status: number, mensaje: string) { super(mensaje); } }
const respuesta = (dato: unknown, status = 200) => new Response(JSON.stringify(dato), {
  status, headers: { "content-type": "application/json", "cache-control": "no-store" },
});
export function crearHandler(base: string, key: string, fetcher: typeof fetch = fetch) {
  const headers = { "apikey": key, "Authorization": `Bearer ${key}`, "content-type": "application/json" };
  async function interno(path: string, body: unknown, metodo = "POST") {
    const res = await fetcher(base + path, { method: metodo, headers,
      body: JSON.stringify(body), signal: AbortSignal.timeout(12_000), redirect: "error" });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Fallo(data.code === "40001" || data.code === "P0001" ? 409 : 503,
      data.code === "40001" ? "Los datos cambiaron. Actualiza y vuelve a intentarlo." : "No se pudo completar la operación en filtradas.");
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
      const verificacion = await fetcher(AUTH_URL, { headers: { Authorization: auth },
        redirect: "error", signal: AbortSignal.timeout(8_000) });
      if (!verificacion.ok || (await verificacion.json()).autorizada !== true)
        return respuesta({ error: "No se pudo verificar la integración" }, verificacion.status === 401 ? 401 : 503);
      const reader = req.body?.getReader();
      if (!reader) throw new Fallo(422, "Falta el cuerpo");
      const partes: Uint8Array[] = []; let size = 0;
      while (true) {
        const { done, value } = await reader.read(); if (done) break;
        size += value.length;
        if (size > MAX_BODY) { await reader.cancel(); throw new Fallo(413, "Entrada demasiado grande"); }
        partes.push(value);
      }
      const buffer = new Uint8Array(size); let offset = 0;
      for (const parte of partes) { buffer.set(parte, offset); offset += parte.length; }
      let entrada;
      try { entrada = JSON.parse(new TextDecoder().decode(buffer)); } catch { throw new Fallo(422, "JSON inválido"); }
      const { operacion, datos } = entrada || {};
      if (!operaciones.has(operacion) || !datos || Array.isArray(datos) || typeof datos !== "object")
        throw new Fallo(422, "Operación inválida");
      const result = await rpc(operacion, datos);
      return respuesta(result);
    } catch (error) {
      return respuesta({ error: error instanceof Fallo ? error.message : "Integración temporalmente no disponible" },
        error instanceof Fallo ? error.status : 503);
    }
  };
}
