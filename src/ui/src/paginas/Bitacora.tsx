import { useState, type FormEvent } from "react";
import { clienteApi } from "../api/cliente";
import "./Bitacora.css";

type EntradaBitacora = {
  id: string;
  fecha_hora: string;
  usuario_email: string;
  usuario_nombre: string;
  rol?: string | null;
  accion: string;
  entidad_tipo: string;
  detalle?: string | null;
};

/** HU-20 (Bloque 2): auditoría global de solo lectura para
 * Administrador/Auditor (permiso bitacora:ver) -- GET /bitacora, distinto
 * del detalle de pasos de un análisis puntual. */
export function Bitacora() {
  const [fechaDesde, setFechaDesde] = useState("");
  const [fechaHasta, setFechaHasta] = useState("");
  const [usuarioEmail, setUsuarioEmail] = useState("");
  const [accion, setAccion] = useState("");
  const [entradas, setEntradas] = useState<EntradaBitacora[] | null>(null);
  const [cargando, setCargando] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function buscar(evento?: FormEvent) {
    evento?.preventDefault();
    setCargando(true);
    setError(null);
    const { data, error: errorRespuesta } = await clienteApi.GET("/bitacora", {
      params: {
        query: {
          fecha_desde: fechaDesde || undefined,
          fecha_hasta: fechaHasta || undefined,
          usuario_email: usuarioEmail || undefined,
          accion: accion || undefined,
        },
      },
    });
    setCargando(false);
    if (errorRespuesta || !data) {
      setError("No se pudo cargar la bitácora");
      return;
    }
    setEntradas(data);
  }

  return (
    <div className="bitacora">
      <h1>Bitácora</h1>
      <p className="bitacora__ayuda">
        Registro de auditoría de solo lectura (RF-19): altas, cambios y decisiones quedan acá,
        nunca la contraseña ni su hash.
      </p>

      <form className="bitacora__filtros" onSubmit={buscar}>
        <label>
          Desde
          <input type="date" value={fechaDesde} onChange={(e) => setFechaDesde(e.target.value)} />
        </label>
        <label>
          Hasta
          <input type="date" value={fechaHasta} onChange={(e) => setFechaHasta(e.target.value)} />
        </label>
        <label>
          Usuario (correo)
          <input
            type="text"
            placeholder="p. ej. analista@local"
            value={usuarioEmail}
            onChange={(e) => setUsuarioEmail(e.target.value)}
          />
        </label>
        <label>
          Acción
          <input
            type="text"
            placeholder="p. ej. cambio_password"
            value={accion}
            onChange={(e) => setAccion(e.target.value)}
          />
        </label>
        <button type="submit" disabled={cargando}>
          {cargando ? "Buscando…" : "Buscar"}
        </button>
      </form>

      {error && (
        <p className="bitacora__error" role="alert">
          {error}
        </p>
      )}

      {entradas === null ? (
        <p className="bitacora__vacio">Elige un rango o busca sin filtros.</p>
      ) : entradas.length === 0 ? (
        <p className="bitacora__vacio">No hay registros con esos filtros.</p>
      ) : (
        <table className="bitacora__tabla">
          <thead>
            <tr>
              <th>Fecha</th>
              <th>Usuario</th>
              <th>Rol</th>
              <th>Acción</th>
              <th>Entidad</th>
              <th>Detalle</th>
            </tr>
          </thead>
          <tbody>
            {entradas.map((e) => (
              <tr key={e.id}>
                <td>{new Date(e.fecha_hora).toLocaleString("es-GT")}</td>
                <td>
                  {e.usuario_nombre} ({e.usuario_email})
                </td>
                <td>{e.rol ?? "—"}</td>
                <td>{e.accion}</td>
                <td>{e.entidad_tipo}</td>
                <td>{e.detalle ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
