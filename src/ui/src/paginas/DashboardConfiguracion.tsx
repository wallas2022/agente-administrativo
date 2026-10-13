import { useEffect, useState } from "react";
import { clienteApi } from "../api/cliente";
import "./Dashboard.css";

type RespuestaConfiguracion = {
  variables: Record<string, string>;
  app_version: string;
  git_commit: string;
};

/** HU-30: variables de configuración vigentes -- solo la lista blanca de
 * comun.dashboard.VARIABLES_CONFIGURACION_VISIBLES (RNF-17); nunca
 * contraseñas, claves ni tokens. */
export function DashboardConfiguracion() {
  const [datos, setDatos] = useState<RespuestaConfiguracion | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      const { data, error: errorRespuesta } = await clienteApi.GET(
        "/admin/dashboard/configuracion",
      );
      if (errorRespuesta || !data) {
        setError("No se pudo cargar la configuración");
        return;
      }
      setDatos(data as RespuestaConfiguracion);
    })();
  }, []);

  return (
    <div className="dashboard__tab">
      {error && (
        <p className="dashboard__error" role="alert">
          {error}
        </p>
      )}

      {datos && (
        <>
          <p className="dashboard__version">
            Versión: <code>{datos.app_version}</code> · Commit: <code>{datos.git_commit}</code>
          </p>
          {Object.keys(datos.variables).length === 0 ? (
            <p className="dashboard__vacio">No hay variables de configuración visibles.</p>
          ) : (
            <table className="dashboard__tabla">
              <thead>
                <tr>
                  <th>Variable</th>
                  <th>Valor</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(datos.variables).map(([clave, valor]) => (
                  <tr key={clave}>
                    <td>
                      <code>{clave}</code>
                    </td>
                    <td>{valor}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      )}
    </div>
  );
}
