import { useParams } from "react-router-dom";

/** Pantalla 2 (bloque U3): estado en vivo del análisis. Placeholder por ahora. */
export function AgenteTrabajando() {
  const { analisisId } = useParams();
  return (
    <div>
      <h1>Agente trabajando</h1>
      <p>
        Análisis <code>{analisisId}</code> iniciado correctamente.
      </p>
      <p>Próximamente: seguimiento en vivo del progreso (bloque U3).</p>
    </div>
  );
}
