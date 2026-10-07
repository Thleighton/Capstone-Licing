// <dialog> nativo controlado por React (abre con showModal para mantener foco y backdrop).
import { useEffect, useRef } from "react";

export default function Dialog({ open, onClose, children, ...props }) {
  const ref = useRef(null);
  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (open && !d.open) d.showModal();
    if (!open && d.open) d.close();
  }, [open]);
  return <dialog ref={ref} onClose={onClose} {...props}>{children}</dialog>;
}
