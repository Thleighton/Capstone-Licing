export default function PaginacionResultados({ total, offset, limite, cargando, onCambiar, etiqueta = "Páginas de resultados" }) {
  const paginas = Math.max(1, Math.ceil(total / limite));
  const actual = Math.floor(offset / limite) + 1;
  return <nav className="ca-paginas" aria-label={etiqueta}>
    <span className="ca-paginas__rango" aria-live="polite">
      Mostrando <strong>{total ? `${offset + 1}–${Math.min(offset + limite, total)}` : "0"}</strong> de {total}
    </span>
    <div className="ca-paginas__acciones">
      <button type="button" disabled={cargando || offset === 0}
        onClick={() => onCambiar(Math.max(0, offset - limite))}>
        ← Anterior
      </button>
      <span className="ca-paginas__actual" aria-live="polite">{actual} de {paginas}</span>
      <button type="button" disabled={cargando || offset + limite >= total}
        onClick={() => onCambiar(offset + limite)}>
        Siguiente →
      </button>
    </div>
  </nav>;
}
