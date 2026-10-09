const ESTADOS_EN_PROCESO = new Set(["cargado", "procesando"]);

/** A dónde navegar al hacer clic en un análisis: mientras está en proceso,
 * a la pantalla "Agente trabajando"; ya terminado, directo a Hallazgos.
 * Compartido por PanelAnalisisRecientes e Historial (HU-21). */
export function rutaDeAnalisis(analisis: { id: string; estado: string }): string {
  return ESTADOS_EN_PROCESO.has(analisis.estado)
    ? `/analisis/${analisis.id}`
    : `/analisis/${analisis.id}/hallazgos`;
}
