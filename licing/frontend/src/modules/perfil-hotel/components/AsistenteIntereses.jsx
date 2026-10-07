// Sugerencias de palabras de interés (simulación). Trabaja sobre el <form> no controlado.
import { normalizar } from "../../../core/ui/format";
import { splitInterests, suggestedInterests } from "../sugerencias";

export const STATUS_INICIAL = "No se añaden términos automáticamente ni se consultan licitaciones.";

export default function AsistenteIntereses({ formRef, candidatos, setCandidatos, status, setStatus, onCambio }) {
  const campos = () => formRef.current.elements;
  const yaExiste = s => splitInterests(campos()[s.target]?.value).some(t => normalizar(t) === normalizar(s.text));

  function sugerir() {
    const lista = suggestedInterests(new FormData(formRef.current));
    setCandidatos(lista);
    setStatus(lista.length
      ? "Propuestas simuladas según la ficha. Añada solo las que representen al hotel; las exclusiones se respetan y la capacidad y la agenda se verificarían por separado."
      : "Complete servicios, montaje o tipos de evento (por ejemplo, seminario) para obtener sugerencias. Si ya los completó, revise sus exclusiones. También puede escribir términos manualmente.");
  }

  function agregar(s) {
    const input = campos()[s.target];
    if (!yaExiste(s)) input.value += (input.value.trim() ? "\n" : "") + s.text;
    onCambio();
    setStatus("Se añadió «" + s.text + "». Puede editarlo o eliminarlo en el campo correspondiente. No se guardó en la base de datos.");
  }

  return (
    <div className="interest-assistant">
      <div className="section-title"><h3>Ayuda para encontrar las palabras</h3><span className="badge blue">Futura IA · simulación</span></div>
      <p>En el producto final, el LLM propondría términos según la oferta que complete. Ahora usamos reglas de ejemplo con los servicios, eventos y montaje declarados. Revise cada propuesta antes de añadirla; podrá editarla o borrarla en los campos de arriba.</p>
      <button type="button" className="primary" onClick={sugerir}>Sugerir según mi formulario ✦</button>
      <p role="status">{status}</p>
      <div className="suggestion-list">
        {candidatos.map((s, i) => {
          const existe = formRef.current ? yaExiste(s) : false;
          return (
            <div className="suggestion-item" key={i}>
              <div><strong>{s.text}</strong><small>{s.target === "intereses_palabras" ? "Palabra / sinónimo" : "Frase de interés"} · {s.reason}</small></div>
              <button type="button" disabled={existe} onClick={() => agregar(s)} aria-label={(existe ? "Ya incorporado: " : "Añadir: ") + s.text}>
                {existe ? "Ya incorporado" : "Añadir +"}
              </button>
            </div>
          );
        })}
      </div>
    </div>
  );
}
