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
  // Estados de Hallazgo (no de Analisis/Documento) exclusivos de CU-05
  // (RNF-04, Bloque O6): un caso dudoso de LanguageTool que el LLM todavía
  // no confirma o descarta, y su resolución.
  en_validacion: "En validación",
  confirmado: "Confirmado",
  descartado: "Descartado",
};

/** docs/03-diseno/estados/estados-analisis.md */
export function EstadoBadge({ estado }: { estado: string }) {
  return (
    <span className={`estado-badge estado-badge--${estado}`}>
      {ETIQUETAS[estado] ?? estado}
    </span>
  );
}
