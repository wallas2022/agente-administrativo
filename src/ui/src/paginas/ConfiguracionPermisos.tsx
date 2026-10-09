import { useCallback, useEffect, useState } from "react";
import { clienteApi } from "../api/cliente";
import "./Configuracion.css";

const ROLES = ["analista", "revisor", "curador", "administrador", "auditor"] as const;

type Celda = {
  rol: string;
  recurso: string;
  accion: string;
  otorgado: boolean;
  protegido: boolean;
};

/** HU-23: matriz recurso:acción × rol -- marcar/desmarcar aplica desde el
 * siguiente request de ese rol; las filas protegidas no se pueden tocar. */
export function ConfiguracionPermisos() {
  const [celdas, setCeldas] = useState<Celda[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const cargar = useCallback(async () => {
    setError(null);
    const { data, error: errorRespuesta } = await clienteApi.GET("/permisos");
    if (errorRespuesta || !data) {
      setError("No se pudo cargar la matriz de permisos");
      return;
    }
    setCeldas(data);
  }, []);

  useEffect(() => {
    cargar();
  }, [cargar]);

  async function alternar(celda: Celda) {
    if (celda.protegido) return;
    setError(null);
    const { error: errorRespuesta } = await clienteApi.PUT("/permisos", {
      body: {
        rol: celda.rol,
        recurso: celda.recurso,
        accion: celda.accion,
        otorgado: !celda.otorgado,
      },
    });
    if (errorRespuesta) {
      setError("No se pudo actualizar el permiso");
      return;
    }
    await cargar();
  }

  async function restaurar() {
    if (!window.confirm("¿Restaurar la matriz de permisos a los valores por defecto (v0.3)?")) {
      return;
    }
    setError(null);
    const { error: errorRespuesta } = await clienteApi.POST("/permisos/restaurar");
    if (errorRespuesta) {
      setError("No se pudo restaurar la matriz");
      return;
    }
    await cargar();
  }

  if (!celdas) {
    return error ? (
      <p className="configuracion__error" role="alert">
        {error}
      </p>
    ) : null;
  }

  const recursosAcciones = Array.from(
    new Map(celdas.map((c) => [`${c.recurso}:${c.accion}`, { recurso: c.recurso, accion: c.accion }])).values(),
  );

  function celdaDe(recurso: string, accion: string, rol: string): Celda {
    return celdas!.find((c) => c.recurso === recurso && c.accion === accion && c.rol === rol)!;
  }

  return (
    <div className="configuracion__tab">
      <button type="button" onClick={restaurar} className="configuracion__restaurar">
        Restaurar matriz por defecto
      </button>

      {error && (
        <p className="configuracion__error" role="alert">
          {error}
        </p>
      )}

      <table className="configuracion__tabla">
        <thead>
          <tr>
            <th>Recurso:acción</th>
            {ROLES.map((rol) => (
              <th key={rol}>{rol}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {recursosAcciones.map(({ recurso, accion }) => (
            <tr key={`${recurso}:${accion}`}>
              <td>
                {recurso}:{accion}
              </td>
              {ROLES.map((rol) => {
                const celda = celdaDe(recurso, accion, rol);
                return (
                  <td key={rol}>
                    <input
                      type="checkbox"
                      checked={celda.otorgado}
                      disabled={celda.protegido}
                      onChange={() => alternar(celda)}
                      aria-label={`${rol} ${recurso}:${accion}${celda.protegido ? " (protegido)" : ""}`}
                      title={celda.protegido ? "Permiso protegido: no editable" : undefined}
                    />
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
