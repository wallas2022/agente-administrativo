import { Link, useParams } from "react-router-dom";
import { EstadoBadge } from "../componentes/EstadoBadge";
import { EtapasAnalisis } from "../componentes/EtapasAnalisis";
import { useAnalisisEnVivo } from "../hooks/useAnalisisEnVivo";
import { useTiempoTranscurrido } from "../hooks/useTiempoTranscurrido";
import "./AgenteTrabajando.css";

const ETIQUETAS_ACCION: Record<string, string> = {
  analisis_iniciado: "Análisis iniciado",
  analisis_completado: "Análisis completado",
};

/** Pantalla 2 (bloque U3): estado en vivo del análisis, con polling cada 3 s
 * (useAnalisisEnVivo) hasta llegar a un estado terminal. */
export function AgenteTrabajando() {
  const { analisisId } = useParams<{ analisisId: string }>();
  const { analisis, bitacora, error } = useAnalisisEnVivo(analisisId ?? "");
  const tiempoTranscurrido = useTiempoTranscurrido(analisis?.fecha_inicio, analisis?.fecha_fin);

  if (error) {
    return (
      <div>
        <h1>Agente trabajando</h1>
        <p className="agente-trabajando__error" role="alert">
          {error}
        </p>
      </div>
    );
  }

  if (!analisis) {
    return (
      <div>
        <h1>Agente trabajando</h1>
        <p>Cargando…</p>
      </div>
    );
  }

  const terminado = analisis.estado !== "cargado" && analisis.estado !== "procesando";

  return (
    <div className="agente-trabajando">
      <h1>Agente trabajando</h1>
      <p className="agente-trabajando__documento">
        {analisis.nombre_documento} <EstadoBadge estado={analisis.estado} />
      </p>

      <div className="agente-trabajando__tarjeta">
        <EtapasAnalisis estado={analisis.estado} />
        <p className="agente-trabajando__tiempo">Tiempo transcurrido: {tiempoTranscurrido}</p>

        <h2 className="agente-trabajando__subtitulo">Registro de pasos</h2>
        {bitacora.length === 0 ? (
          <p className="agente-trabajando__mensaje">Todavía no hay pasos registrados.</p>
        ) : (
          <ul className="agente-trabajando__bitacora">
            {bitacora.map((entrada) => (
              <li key={entrada.id}>
                <span className="agente-trabajando__hora">
                  {new Date(entrada.fecha_hora).toLocaleTimeString("es-GT")}
                </span>
                <span>{ETIQUETAS_ACCION[entrada.accion] ?? entrada.accion}</span>
              </li>
            ))}
          </ul>
        )}
      </div>

      {terminado && analisis.estado !== "fallido" && (
        <Link className="agente-trabajando__boton" to={`/analisis/${analisis.id}/hallazgos`}>
          Ver hallazgos
        </Link>
      )}
      {analisis.estado === "fallido" && (
        <Link className="agente-trabajando__boton" to="/">
          Volver a intentar
        </Link>
      )}
    </div>
  );
}
