// Indicador circular de confianza del análisis automático (0-100).
export default function Anillo({ valor: v }) {
  if (v == null) return <span className="sub">-</span>;
  const color = v >= 70 ? "var(--ok)" : v >= 40 ? "var(--warn-ring)" : "var(--muted)";
  const C = 2 * Math.PI * 14;
  return (
    <div className="ring">
      <svg viewBox="0 0 34 34">
        <circle cx="17" cy="17" r="14" fill="none" stroke="var(--gray-bg)" strokeWidth="3.5" />
        <circle cx="17" cy="17" r="14" fill="none" stroke={color} strokeWidth="3.5" strokeLinecap="round" strokeDasharray={(C * v / 100).toFixed(1) + " " + C.toFixed(1)} />
      </svg>
      <span>{v}</span>
    </div>
  );
}
