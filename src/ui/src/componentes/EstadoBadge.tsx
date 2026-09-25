import "./EstadoBadge.css";

const ETIQUETAS: Record<string, string> = {
  cargado: "Cargado",
  procesando: "Procesando",
  con_hallazgos: "Con hallazgos",
  en_revision: "En revisión",
  fallido: "Fallido",
  aprobado: "Aprobado",
  rechazado: "Rechazado",
  cerrado: "Cerrado",
};

/** docs/03-diseno/estados/estados-analisis.md */
export function EstadoBadge({ estado }: { estado: string }) {
  return (
    <span className={`estado-badge estado-badge--${estado}`}>
      {ETIQUETAS[estado] ?? estado}
    </span>
  );
}
