import { useCallback, useEffect, useState, type FormEvent } from "react";
import { clienteApi } from "../api/cliente";
import "./Configuracion.css";

const ROLES = ["analista", "revisor", "curador", "administrador", "auditor"] as const;

type Usuario = {
  id: string;
  nombre: string;
  email: string;
  rol: string;
  area_id: string;
  area: string;
  activo: boolean;
  debe_cambiar_password: boolean;
  ultimo_acceso?: string | null;
};

type Area = { id: string; nombre: string };

/** HU-22: crear, editar (nombre/área/rol/activo) y restablecer contraseña
 * -- nunca se borra un usuario (no hay botón de eliminar). */
export function ConfiguracionUsuarios() {
  const [usuarios, setUsuarios] = useState<Usuario[] | null>(null);
  const [areas, setAreas] = useState<Area[]>([]);
  const [cargando, setCargando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [passwordTemporal, setPasswordTemporal] = useState<{ email: string; password: string } | null>(
    null,
  );

  const [nombre, setNombre] = useState("");
  const [email, setEmail] = useState("");
  const [areaId, setAreaId] = useState("");
  const [rol, setRol] = useState<string>(ROLES[0]);

  const cargar = useCallback(async () => {
    setCargando(true);
    setError(null);
    const [respuestaUsuarios, respuestaAreas] = await Promise.all([
      clienteApi.GET("/usuarios"),
      clienteApi.GET("/areas"),
    ]);
    setCargando(false);
    if (respuestaUsuarios.error || !respuestaUsuarios.data) {
      setError("No se pudo cargar la lista de usuarios");
      return;
    }
    setUsuarios(respuestaUsuarios.data);
    if (respuestaAreas.data) {
      setAreas(respuestaAreas.data);
      setAreaId((actual) => actual || respuestaAreas.data[0]?.id || "");
    }
  }, []);

  useEffect(() => {
    cargar();
  }, [cargar]);

  async function crearUsuario(evento: FormEvent) {
    evento.preventDefault();
    setError(null);
    const { data, error: errorRespuesta } = await clienteApi.POST("/usuarios", {
      body: { nombre, email, area_id: areaId, rol },
    });
    if (errorRespuesta || !data) {
      const detalle = (errorRespuesta as { detail?: unknown })?.detail;
      setError(typeof detalle === "string" ? detalle : "No se pudo crear el usuario");
      return;
    }
    setPasswordTemporal({ email: data.usuario.email, password: data.password_temporal });
    setNombre("");
    setEmail("");
    await cargar();
  }

  async function editar(id: string, cambios: Record<string, unknown>) {
    setError(null);
    const { error: errorRespuesta } = await clienteApi.PATCH("/usuarios/{usuario_id}", {
      params: { path: { usuario_id: id } },
      body: cambios,
    });
    if (errorRespuesta) {
      const detalle = (errorRespuesta as { detail?: unknown })?.detail;
      setError(typeof detalle === "string" ? detalle : "No se pudo editar el usuario");
      return;
    }
    await cargar();
  }

  async function restablecerPassword(usuario: Usuario) {
    setError(null);
    const { data, error: errorRespuesta } = await clienteApi.POST(
      "/usuarios/{usuario_id}/restablecer-password",
      { params: { path: { usuario_id: usuario.id } } },
    );
    if (errorRespuesta || !data) {
      setError("No se pudo restablecer la contraseña");
      return;
    }
    setPasswordTemporal({ email: usuario.email, password: data.password_temporal });
    await cargar();
  }

  return (
    <div className="configuracion__tab">
      {passwordTemporal && (
        <div className="configuracion__password-temporal" role="status">
          Contraseña temporal para <strong>{passwordTemporal.email}</strong>:{" "}
          <code>{passwordTemporal.password}</code> -- cópiela, no se volverá a mostrar.
          <button type="button" onClick={() => setPasswordTemporal(null)}>
            Cerrar
          </button>
        </div>
      )}

      <form className="configuracion__formulario" onSubmit={crearUsuario}>
        <label>
          Nombre
          <input type="text" value={nombre} onChange={(e) => setNombre(e.target.value)} required />
        </label>
        <label>
          Correo
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
        </label>
        <label>
          Área
          <select value={areaId} onChange={(e) => setAreaId(e.target.value)} required>
            {areas.map((a) => (
              <option key={a.id} value={a.id}>
                {a.nombre}
              </option>
            ))}
          </select>
        </label>
        <label>
          Rol
          <select value={rol} onChange={(e) => setRol(e.target.value)}>
            {ROLES.map((r) => (
              <option key={r} value={r}>
                {r}
              </option>
            ))}
          </select>
        </label>
        <button type="submit" disabled={cargando}>
          Crear usuario
        </button>
      </form>

      {error && (
        <p className="configuracion__error" role="alert">
          {error}
        </p>
      )}

      {usuarios && (
        <table className="configuracion__tabla">
          <thead>
            <tr>
              <th>Nombre</th>
              <th>Correo</th>
              <th>Rol</th>
              <th>Área</th>
              <th>Activo</th>
              <th>Debe cambiar contraseña</th>
              <th>Acciones</th>
            </tr>
          </thead>
          <tbody>
            {usuarios.map((u) => (
              <tr key={u.id}>
                <td>{u.nombre}</td>
                <td>{u.email}</td>
                <td>
                  <select value={u.rol} onChange={(e) => editar(u.id, { rol: e.target.value })}>
                    {ROLES.map((r) => (
                      <option key={r} value={r}>
                        {r}
                      </option>
                    ))}
                  </select>
                </td>
                <td>
                  <select
                    value={u.area_id}
                    onChange={(e) => editar(u.id, { area_id: e.target.value })}
                  >
                    {areas.map((a) => (
                      <option key={a.id} value={a.id}>
                        {a.nombre}
                      </option>
                    ))}
                  </select>
                </td>
                <td>
                  <input
                    type="checkbox"
                    checked={u.activo}
                    onChange={(e) => editar(u.id, { activo: e.target.checked })}
                    aria-label={`Activo: ${u.nombre}`}
                  />
                </td>
                <td>{u.debe_cambiar_password ? "Sí" : "No"}</td>
                <td>
                  <button type="button" onClick={() => restablecerPassword(u)}>
                    Restablecer contraseña
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
