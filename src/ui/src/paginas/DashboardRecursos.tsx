import { useCallback, useEffect, useState } from "react";
import { clienteApi } from "../api/cliente";
import "./Dashboard.css";

type Host = {
  cpu_ocupado_pct?: number | null;
  vcpus?: number | null;
  memoria_usada_bytes: number;
  memoria_total_bytes: number;
  disco_usado_bytes?: number | null;
  disco_total_bytes?: number | null;
  carga_1m?: number | null;
};

type Contenedor = {
  nombre: string;
  cpu_pct: number;
  memoria_usada_bytes?: number | null;
  memoria_limite_bytes?: number | null;
  memoria_pct_del_limite?: number | null;
};

type Ollama = {
  modelos_en_memoria: Record<string, unknown>[];
  modelos_instalados: Record<string, unknown>[];
};

type Alerta = { tipo: string; mensaje: string };

type RespuestaRecursos = {
  prometheus_disponible: boolean;
  host?: Host | null;
  contenedores?: Contenedor[] | null;
  ollama?: Ollama | null;
  alertas: Alerta[];
};

const INTERVALO_REFRESCO_MS = 30_000;

function formatearBytes(bytes: number | null | undefined): string {
  if (bytes == null) return "—";
  const gb = bytes / 1024 ** 3;
  return gb >= 1 ? `${gb.toFixed(1)} GB` : `${(bytes / 1024 ** 2).toFixed(0)} MB`;
}

/** HU-29: recursos de host y contenedores (vía Prometheus, P-13 Bloque 2) y
 * de Ollama, con refresco automático cada 30 s. Las alertas (disco, memoria
 * de Ollama, timeouts -- umbrales de comun/dashboard.py) se muestran
 * siempre arriba, antes de cualquier sección. */
export function DashboardRecursos() {
  const [datos, setDatos] = useState<RespuestaRecursos | null>(null);
  const [error, setError] = useState<string | null>(null);

  const consultar = useCallback(async () => {
    const { data, error: errorRespuesta } = await clienteApi.GET("/admin/dashboard/recursos");
    if (errorRespuesta || !data) {
      setError("No se pudieron cargar los recursos");
      return;
    }
    setError(null);
    setDatos(data as RespuestaRecursos);
  }, []);

  useEffect(() => {
    consultar();
    const id = setInterval(consultar, INTERVALO_REFRESCO_MS);
    return () => clearInterval(id);
  }, [consultar]);

  return (
    <div className="dashboard__tab">
      {error && (
        <p className="dashboard__error" role="alert">
          {error}
        </p>
      )}

      {datos && datos.alertas.length > 0 && (
        <ul className="dashboard__alertas" role="alert">
          {datos.alertas.map((a) => (
            <li key={a.tipo} className="dashboard__alerta">
              {a.mensaje}
            </li>
          ))}
        </ul>
      )}

      {datos && (
        <>
          <section>
            <h2 className="dashboard__subtitulo">Host</h2>
            {!datos.prometheus_disponible || !datos.host ? (
              <p className="dashboard__vacio">
                Las métricas de host no están disponibles (Prometheus apagado en este entorno).
              </p>
            ) : (
              <table className="dashboard__tabla">
                <tbody>
                  <tr>
                    <th>CPU ocupado</th>
                    <td>{datos.host.cpu_ocupado_pct?.toFixed(1) ?? "—"}%</td>
                  </tr>
                  <tr>
                    <th>vCPUs</th>
                    <td>{datos.host.vcpus ?? "—"}</td>
                  </tr>
                  <tr>
                    <th>Memoria</th>
                    <td>
                      {formatearBytes(datos.host.memoria_usada_bytes)} de{" "}
                      {formatearBytes(datos.host.memoria_total_bytes)}
                    </td>
                  </tr>
                  <tr>
                    <th>Disco</th>
                    <td>
                      {formatearBytes(datos.host.disco_usado_bytes)} de{" "}
                      {formatearBytes(datos.host.disco_total_bytes)}
                    </td>
                  </tr>
                  <tr>
                    <th>Carga (1 min)</th>
                    <td>{datos.host.carga_1m?.toFixed(2) ?? "—"}</td>
                  </tr>
                </tbody>
              </table>
            )}
          </section>

          <section>
            <h2 className="dashboard__subtitulo">Contenedores</h2>
            {!datos.contenedores || datos.contenedores.length === 0 ? (
              <p className="dashboard__vacio">
                Las métricas por contenedor no están disponibles (Prometheus apagado en este
                entorno).
              </p>
            ) : (
              <table className="dashboard__tabla">
                <thead>
                  <tr>
                    <th>Contenedor</th>
                    <th>CPU</th>
                    <th>Memoria</th>
                    <th>% del límite</th>
                  </tr>
                </thead>
                <tbody>
                  {datos.contenedores.map((c) => (
                    <tr key={c.nombre}>
                      <td>{c.nombre}</td>
                      <td>{c.cpu_pct.toFixed(1)}%</td>
                      <td>
                        {formatearBytes(c.memoria_usada_bytes)}
                        {c.memoria_limite_bytes
                          ? ` de ${formatearBytes(c.memoria_limite_bytes)}`
                          : ""}
                      </td>
                      <td>
                        {c.memoria_pct_del_limite != null
                          ? `${c.memoria_pct_del_limite.toFixed(1)}%`
                          : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </section>

          <section>
            <h2 className="dashboard__subtitulo">Ollama</h2>
            {!datos.ollama ? (
              <p className="dashboard__vacio">No se pudo conectar con Ollama.</p>
            ) : (
              <p>
                {datos.ollama.modelos_en_memoria.length} modelo(s) en memoria de{" "}
                {datos.ollama.modelos_instalados.length} instalado(s).
              </p>
            )}
          </section>
        </>
      )}
    </div>
  );
}
