import { useEffect, useState } from "react";

/** Tiempo transcurrido entre `fechaInicioIso` y `fechaFinIso` (si ya terminó)
 * o "ahora" (mientras sigue en curso), actualizado cada segundo. */
export function useTiempoTranscurrido(
  fechaInicioIso: string | undefined,
  fechaFinIso: string | null | undefined,
): string {
  const [ahora, setAhora] = useState(() => Date.now());

  useEffect(() => {
    if (fechaFinIso || !fechaInicioIso) return;
    const intervalo = setInterval(() => setAhora(Date.now()), 1000);
    return () => clearInterval(intervalo);
  }, [fechaInicioIso, fechaFinIso]);

  if (!fechaInicioIso) return "—";

  const inicio = new Date(fechaInicioIso).getTime();
  const fin = fechaFinIso ? new Date(fechaFinIso).getTime() : ahora;
  const segundosTotales = Math.max(0, Math.floor((fin - inicio) / 1000));
  const minutos = Math.floor(segundosTotales / 60);
  const segundos = segundosTotales % 60;

  return `${minutos}m ${segundos.toString().padStart(2, "0")}s`;
}
