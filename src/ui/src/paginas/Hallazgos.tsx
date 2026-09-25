import { useParams } from "react-router-dom";

/** Pantalla 3 (bloque U4): lista de hallazgos, aceptar/rechazar. Placeholder. */
export function Hallazgos() {
  const { analisisId } = useParams();
  return (
    <div>
      <h1>Hallazgos</h1>
      <p>
        Análisis <code>{analisisId}</code>.
      </p>
      <p>Próximamente: hallazgos, totales y decisión del Revisor (bloque U4).</p>
    </div>
  );
}
