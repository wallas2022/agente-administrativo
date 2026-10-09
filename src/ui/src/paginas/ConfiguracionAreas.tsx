import { useCallback, useEffect, useState, type FormEvent } from "react";
import { clienteApi } from "../api/cliente";
import "./Configuracion.css";

type Area = { id: string; nombre: string };

/** HU-24: crear y renombrar áreas; eliminar solo si no tiene usuarios ni
 * documentos asociados (el backend lo rechaza con 409 en ese caso). */
export function ConfiguracionAreas() {
  const [areas, setAreas] = useState<Area[] | null>(null);
  const [nombreNueva, setNombreNueva] = useState("");
  const [edicion, setEdicion] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);

  const cargar = useCallback(async () => {
    setError(null);
    const { data, error: errorRespuesta } = await clienteApi.GET("/areas");
    if (errorRespuesta || !data) {
      setError("No se pudo cargar la lista de áreas");
      return;
    }
    setAreas(data);
  }, []);

  useEffect(() => {
    cargar();
  }, [cargar]);

  async function crear(evento: FormEvent) {
    evento.preventDefault();
    setError(null);
    const { error: errorRespuesta } = await clienteApi.POST("/areas", {
      body: { nombre: nombreNueva },
    });
    if (errorRespuesta) {
      const detalle = (errorRespuesta as { detail?: unknown })?.detail;
      setError(typeof detalle === "string" ? detalle : "No se pudo crear el área");
      return;
    }
    setNombreNueva("");
    await cargar();
  }

  async function renombrar(area: Area) {
    const nuevoNombre = (edicion[area.id] ?? area.nombre).trim();
    if (!nuevoNombre || nuevoNombre === area.nombre) return;
    setError(null);
    const { error: errorRespuesta } = await clienteApi.PATCH("/areas/{area_id}", {
      params: { path: { area_id: area.id } },
      body: { nombre: nuevoNombre },
    });
    if (errorRespuesta) {
      const detalle = (errorRespuesta as { detail?: unknown })?.detail;
      setError(typeof detalle === "string" ? detalle : "No se pudo renombrar el área");
      return;
    }
    await cargar();
  }

  async function eliminar(area: Area) {
    setError(null);
    const { error: errorRespuesta, response } = await clienteApi.DELETE("/areas/{area_id}", {
      params: { path: { area_id: area.id } },
    });
    if (errorRespuesta || !response.ok) {
      setError(
        response.status === 409
          ? "El área tiene usuarios o documentos asociados -- no se puede eliminar"
          : "No se pudo eliminar el área",
      );
      return;
    }
    await cargar();
  }

  return (
    <div className="configuracion__tab">
      <form className="configuracion__formulario" onSubmit={crear}>
        <label>
          Nueva área
          <input
            type="text"
            value={nombreNueva}
            onChange={(e) => setNombreNueva(e.target.value)}
            required
          />
        </label>
        <button type="submit">Crear área</button>
      </form>

      {error && (
        <p className="configuracion__error" role="alert">
          {error}
        </p>
      )}

      {areas && (
        <table className="configuracion__tabla">
          <thead>
            <tr>
              <th>Nombre</th>
              <th>Acciones</th>
            </tr>
          </thead>
          <tbody>
            {areas.map((a) => (
              <tr key={a.id}>
                <td>
                  <input
                    type="text"
                    value={edicion[a.id] ?? a.nombre}
                    onChange={(e) => setEdicion((actual) => ({ ...actual, [a.id]: e.target.value }))}
                  />
                </td>
                <td>
                  <button type="button" onClick={() => renombrar(a)}>
                    Guardar
                  </button>
                  <button type="button" onClick={() => eliminar(a)}>
                    Eliminar
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
