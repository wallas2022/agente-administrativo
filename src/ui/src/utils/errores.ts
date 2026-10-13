/** Extrae el mensaje legible de un cuerpo de error de la API: `detalle` (manejador
 * global), `detail` como texto (HTTPException) o lista de validación (422). */
export function mensajeDeError(cuerpo: unknown, porDefecto: string): string {
  if (!cuerpo || typeof cuerpo !== "object") return porDefecto;
  const { detalle, detail } = cuerpo as { detalle?: unknown; detail?: unknown };
  if (typeof detalle === "string" && detalle) return detalle;
  if (typeof detail === "string" && detail) return detail;
  if (Array.isArray(detail)) {
    const mensajes = detail
      .map((item) => (item && typeof item === "object" ? (item as { msg?: unknown }).msg : null))
      .filter((m): m is string => typeof m === "string" && m.length > 0);
    if (mensajes.length > 0) return mensajes.join("; ");
  }
  return porDefecto;
}

export const MENSAJE_SIN_CONEXION =
  "No se pudo conectar con el servidor. Verifique su conexión e intente de nuevo";
