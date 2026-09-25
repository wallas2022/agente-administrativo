import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { clienteApi } from "../api/cliente";
import { EstadoBadge } from "./EstadoBadge";
import "./PanelAnalisisRecientes.css";

const ESTADOS_EN_PROCESO = new Set(["cargado", "procesando"]);

function rutaDe(a: { id: string; estado: string }): string {
  return ESTADOS_EN_PROCESO.has(a.estado) ? `/analisis/${a.id}` : `/analisis/${a.id}/hallazgos`;
}

type Analisis = {
  id: string;
  nombre_documento?: string | null;
  tipo_revision: string;
  estado: string;
  fecha_inicio: string;
};

/** Pantalla 1: panel lateral de análisis recientes del área (o de todas para
 * Administrador/Auditor — mismo criterio de GET /analisis). */
export function PanelAnalisisRecientes({ actualizarEn }: { actualizarEn: number }) {
  const [analisis, setAnalisis] = useState<Analisis[] | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    let cancelado = false;
    setError(false);
    clienteApi
      .GET("/analisis", { params: { query: {} } })
      .then(({ data, error: errorRespuesta }) => {
        if (cancelado) return;
        if (errorRespuesta || !data) {
          setError(true);
          return;
        }
        setAnalisis(data);
      })
      .catch(() => !cancelado && setError(true));
    return () => {
      cancelado = true;
    };
  }, [actualizarEn]);

  return (
    <aside className="panel-recientes">
      <h2 className="panel-recientes__titulo">Análisis recientes</h2>
      {error && <p className="panel-recientes__mensaje">No se pudo cargar el historial.</p>}
      {!error && analisis === null && (
        <p className="panel-recientes__mensaje">Cargando…</p>
      )}
      {!error && analisis?.length === 0 && (
        <p className="panel-recientes__mensaje">Todavía no hay análisis.</p>
      )}
      <ul className="panel-recientes__lista">
        {analisis?.map((a) => (
          <li key={a.id} className="panel-recientes__item">
            <Link to={rutaDe(a)} className="panel-recientes__enlace">
              <span className="panel-recientes__nombre">{a.nombre_documento ?? a.id}</span>
              <EstadoBadge estado={a.estado} />
            </Link>
          </li>
        ))}
      </ul>
    </aside>
  );
}
