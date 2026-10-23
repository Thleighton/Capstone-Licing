// Adaptador privado de persistencia. Las reglas y la lectura de PDF viven en Core.
const AUTH_URL = "https://capstone-licing.vercel.app/api/preseleccion/integracion/verificar";
const BUCKET = "licitacion-bases";
const MAX_BODY = 16_000_000;
const operaciones = new Set(["guardar", "listar", "detalle", "documentos", "revision", "guardar_documento", "retirar_documento", "sincronizar_fuente"]);
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
  async function limpiarArchivos() {
    // Solo huérfanos de más de una hora: no compite con una carga en curso.
    const paths = await interno("/rest/v1/rpc/lf_archivos_huerfanos", {});
    if (paths.length) await interno(`/storage/v1/object/${BUCKET}`, { prefixes: paths }, "DELETE");
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
      if (operacion === "guardar_documento") {
        if (!/^[A-Z0-9-]{1,60}$/.test(datos.codigo) || typeof datos.contenido_base64 !== "string" || datos.contenido_base64.length > 4_194_304)
          throw new Fallo(422, "Documento inválido");
        let binary;
        try { binary = Uint8Array.from(atob(datos.contenido_base64), c => c.charCodeAt(0)); }
        catch { throw new Fallo(422, "Documento inválido"); }
        if (!binary.length || binary.length > 3_145_728 || new TextDecoder().decode(binary.slice(0, 5)) !== "%PDF-")
          throw new Fallo(422, "Documento inválido");
        const digest = new Uint8Array(await crypto.subtle.digest("SHA-256", binary));
        const hash = Array.from(digest, v => v.toString(16).padStart(2, "0")).join("");
        if (hash !== datos.extraccion?.hash_archivo) throw new Fallo(422, "La huella del PDF no coincide");
        const path = `${datos.codigo}/${hash}.pdf`;
        const uploaded = await fetcher(`${base}/storage/v1/object/${BUCKET}/${path}`, {
          method: "POST", headers: { ...headers, "content-type": "application/pdf", "x-upsert": "false" },
          body: binary, redirect: "error", signal: AbortSignal.timeout(12_000),
        });
        if (!uploaded.ok) {
          const err = await uploaded.json().catch(() => ({}));
          if (err.error !== "Duplicate" && err.statusCode !== "409" && uploaded.status !== 409)
            throw new Fallo(503, "No se pudo conservar el PDF original");
        }
        // Reintentar el mismo PDF reutiliza el objeto por su huella; no lo sobrescribe.
        delete datos.contenido_base64;
        datos.storage_path = path;
        datos.url_origen = `${base}/storage/v1/object/${BUCKET}/${path}`;
      }
      const result = await rpc(operacion, datos);
      if (operacion === "detalle") {
        for (const doc of result.documentos || []) {
          const path = doc.cobertura?.storage_path;
          if (path) {
            const signed = await interno(`/storage/v1/object/sign/${BUCKET}/${path}`, { expiresIn: 300 });
            doc.url_descarga = base + "/storage/v1" + signed.signedURL;
          }
        }
      }
      if (operacion === "guardar") await limpiarArchivos().catch(() => { /* Se reintenta en la próxima lectura. */ });
      return respuesta(result);
    } catch (error) {
      return respuesta({ error: error instanceof Fallo ? error.message : "Integración temporalmente no disponible" },
        error instanceof Fallo ? error.status : 503);
    }
  };
}
