import { useCallback, useEffect, useState, type FormEvent } from "react";
import { clienteApi } from "../api/cliente";
import { descargarArchivo } from "../api/descargas";
import "./Dashboard.css";

type FilaUsuario = {
  usuario_id: string;
  usuario_nombre: string;
  usuario_email: string;
  area_nombre: string;
  numero_analisis: number;
  tokens_entrada: number;
  tokens_salida: number;
  duracion_llm_total_ms: number;
  timeouts: number;
};

/** HU-27: consumo agregado por usuario, con exportación a CSV. El endpoint
 * no tiene `response_model` en la API (puede devolver JSON o un CSV adjunto
 * según `?formato=csv`, ver api/main.py), así que se tipa a mano en vez de
 * usar los tipos generados de OpenAPI para el cuerpo de la respuesta. */
export function DashboardUsuarios() {
  const [desde, setDesde] = useState("");
  const [hasta, setHasta] = useState("");
  const [filas, setFilas] = useState<FilaUsuario[] | null>(null);
  const [cargando, setCargando] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const buscar = useCallback(async () => {
    setCargando(true);
    setError(null);
    const { data, error: errorRespuesta } = await clienteApi.GET("/admin/dashboard/usuarios", {
      params: { query: { desde: desde || undefined, hasta: hasta || undefined } },
    });
    setCargando(false);
    if (errorRespuesta || !data) {
      setError("No se pudo cargar el consumo por usuario");
      return;
    }
    setFilas(data as FilaUsuario[]);
  }, [desde, hasta]);

  useEffect(() => {
    buscar();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function manejarEnvio(evento: FormEvent) {
    evento.preventDefault();
    buscar();
  }

  async function exportarCsv() {
    const parametros = new URLSearchParams();
    if (desde) parametros.set("desde", desde);
    if (hasta) parametros.set("hasta", hasta);
    parametros.set("formato", "csv");
    await descargarArchivo(`/admin/dashboard/usuarios?${parametros.toString()}`);
  }

  return (
    <div className="dashboard__tab">
      <form className="dashboard__filtros" onSubmit={manejarEnvio}>
        <label>
          Desde
          <input type="date" value={desde} onChange={(e) => setDesde(e.target.value)} />
        </label>
        <label>
          Hasta
          <input type="date" value={hasta} onChange={(e) => setHasta(e.target.value)} />
        </label>
        <button type="submit" disabled={cargando}>
          {cargando ? "Buscando…" : "Buscar"}
        </button>
        <button type="button" onClick={exportarCsv} disabled={!filas || filas.length === 0}>
          Exportar CSV
        </button>
      </form>

      {error && (
        <p className="dashboard__error" role="alert">
          {error}
        </p>
      )}

      {filas !== null && filas.length === 0 && !error && (
        <p className="dashboard__vacio">Todavía no hay datos de consumo para estos filtros.</p>
      )}

      {filas !== null && filas.length > 0 && (
        <table className="dashboard__tabla">
          <thead>
            <tr>
              <th>Usuario</th>
              <th>Área</th>
              <th>Análisis</th>
              <th>Tokens entrada</th>
              <th>Tokens salida</th>
              <th>Duración LLM</th>
              <th>Timeouts</th>
            </tr>
          </thead>
          <tbody>
            {filas.map((f) => (
              <tr key={f.usuario_id}>
                <td>
                  {f.usuario_nombre} ({f.usuario_email})
                </td>
                <td>{f.area_nombre}</td>
                <td>{f.numero_analisis}</td>
                <td>{f.tokens_entrada}</td>
                <td>{f.tokens_salida}</td>
                <td>{(f.duracion_llm_total_ms / 1000).toFixed(1)} s</td>
                <td>{f.timeouts}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
