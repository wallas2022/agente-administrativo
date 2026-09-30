import { useState, type FormEvent } from "react";
import { clienteApi } from "../api/cliente";
import { useAuth } from "../auth/ContextoAuth";
import "./ReporteAjustesAutoaprobados.css";

type Ajuste = {
  fecha_hora: string;
  usuario_email: string;
  usuario_nombre: string;
  rol?: string | null;
  documento_nombre: string;
  hallazgo_descripcion: string;
  resultado: string;
  comentario?: string | null;
};

// SRS v0.9 (RG-06, PP-09): visible para Administrador/Auditor -- "Jefatura"
// no es un rol propio del sistema hoy, se cubre con Administrador (mismo
// criterio que usa el backend, ver GET /reportes/ajustes-autoaprobados).
const ROLES_CON_ACCESO = new Set(["administrador", "auditor"]);

export function ReporteAjustesAutoaprobados() {
  const { usuario } = useAuth();
  const tieneAcceso = usuario != null && ROLES_CON_ACCESO.has(usuario.rol);

  const [fechaDesde, setFechaDesde] = useState("");
  const [fechaHasta, setFechaHasta] = useState("");
  const [usuarioEmail, setUsuarioEmail] = useState("");
  const [ajustes, setAjustes] = useState<Ajuste[] | null>(null);
  const [cargando, setCargando] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function buscar(evento?: FormEvent) {
    evento?.preventDefault();
    setCargando(true);
    setError(null);
    const { data, error: errorRespuesta } = await clienteApi.GET("/reportes/ajustes-autoaprobados", {
      params: {
        query: {
          fecha_desde: fechaDesde || undefined,
          fecha_hasta: fechaHasta || undefined,
          usuario_email: usuarioEmail || undefined,
        },
      },
    });
    setCargando(false);
    if (errorRespuesta || !data) {
      setError("No se pudo cargar el reporte");
      return;
    }
    setAjustes(data);
  }

  if (!tieneAcceso) {
    return (
      <div className="reporte-autoaprobados">
        <h1>Ajustes autoaprobados</h1>
        <p>Su rol no tiene acceso a este reporte.</p>
      </div>
    );
  }

  return (
    <div className="reporte-autoaprobados">
      <h1>Ajustes autoaprobados</h1>
      <p className="reporte-autoaprobados__ayuda">
        Hallazgos de CU-01 (contable) donde quien decidió es el mismo usuario que cargó el
        documento -- permitido desde SRS v0.9 (SEGREGACION_APROBACION=false), siempre registrado
        en la bitácora (RG-06, PP-09: "0 aprobaciones sin registro").
      </p>

      <form className="reporte-autoaprobados__filtros" onSubmit={buscar}>
        <label>
          Desde
          <input
            type="date"
            value={fechaDesde}
            onChange={(e) => setFechaDesde(e.target.value)}
          />
        </label>
        <label>
          Hasta
          <input
            type="date"
            value={fechaHasta}
            onChange={(e) => setFechaHasta(e.target.value)}
          />
        </label>
        <label>
          Usuario (correo)
          <input
            type="text"
            placeholder="p. ej. administrador@local"
            value={usuarioEmail}
            onChange={(e) => setUsuarioEmail(e.target.value)}
          />
        </label>
        <button type="submit" disabled={cargando}>
          {cargando ? "Buscando…" : "Buscar"}
        </button>
      </form>

      {error && (
        <p className="reporte-autoaprobados__error" role="alert">
          {error}
        </p>
      )}

      {ajustes === null ? (
        <p className="reporte-autoaprobados__vacio">Elige un rango o busca sin filtros.</p>
      ) : ajustes.length === 0 ? (
        <p className="reporte-autoaprobados__vacio">No hay ajustes autoaprobados en ese rango.</p>
      ) : (
        <table className="reporte-autoaprobados__tabla">
          <thead>
            <tr>
              <th>Fecha</th>
              <th>Usuario</th>
              <th>Rol</th>
              <th>Documento</th>
              <th>Hallazgo</th>
              <th>Resultado</th>
            </tr>
          </thead>
          <tbody>
            {ajustes.map((a, indice) => (
              <tr key={indice}>
                <td>{new Date(a.fecha_hora).toLocaleString("es-GT")}</td>
                <td>
                  {a.usuario_nombre} ({a.usuario_email})
                </td>
                <td>{a.rol ?? "—"}</td>
                <td>{a.documento_nombre}</td>
                <td>{a.hallazgo_descripcion}</td>
                <td>{a.resultado}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
