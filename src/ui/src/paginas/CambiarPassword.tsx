import { useState, type FormEvent } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { clienteApi } from "../api/cliente";
import { useAuth } from "../auth/ContextoAuth";
import "./CambiarPassword.css";

/** HU-25: pantalla obligatoria en el primer ingreso (contraseña temporal) y
 * también disponible para un cambio voluntario -- siempre pide la
 * contraseña actual. */
export function CambiarPassword() {
  const { usuario, recargarPerfil } = useAuth();
  const ubicacion = useLocation();
  const [passwordActual, setPasswordActual] = useState("");
  const [passwordNueva, setPasswordNueva] = useState("");
  const [confirmacion, setConfirmacion] = useState("");
  const [cargando, setCargando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lista, setLista] = useState(false);

  if (lista && usuario && !usuario.debeCambiarPassword) {
    const destino = (ubicacion.state as { desde?: string } | null)?.desde ?? "/";
    return <Navigate to={destino} replace />;
  }

  async function manejarEnvio(evento: FormEvent) {
    evento.preventDefault();
    setError(null);
    if (passwordNueva !== confirmacion) {
      setError("La confirmación no coincide con la contraseña nueva");
      return;
    }
    setCargando(true);
    try {
      const { error: errorRespuesta } = await clienteApi.POST("/auth/cambiar-password", {
        body: { password_actual: passwordActual, password_nueva: passwordNueva },
      });
      if (errorRespuesta) {
        const detalle = (errorRespuesta as { detail?: unknown }).detail;
        setError(typeof detalle === "string" ? detalle : "No se pudo cambiar la contraseña");
        return;
      }
      await recargarPerfil();
      setLista(true);
    } catch {
      setError("No se pudo conectar con el servidor");
    } finally {
      setCargando(false);
    }
  }

  return (
    <div className="cambiar-password">
      <form className="cambiar-password__tarjeta" onSubmit={manejarEnvio}>
        <h1 className="cambiar-password__titulo">Cambiar contraseña</h1>
        {usuario?.debeCambiarPassword && (
          <p className="cambiar-password__aviso">
            Su contraseña es temporal: debe cambiarla antes de continuar.
          </p>
        )}

        <label className="cambiar-password__campo">
          Contraseña actual
          <input
            type="password"
            value={passwordActual}
            onChange={(e) => setPasswordActual(e.target.value)}
            autoComplete="current-password"
            required
          />
        </label>

        <label className="cambiar-password__campo">
          Contraseña nueva
          <input
            type="password"
            value={passwordNueva}
            onChange={(e) => setPasswordNueva(e.target.value)}
            autoComplete="new-password"
            minLength={10}
            required
          />
        </label>

        <label className="cambiar-password__campo">
          Confirmar contraseña nueva
          <input
            type="password"
            value={confirmacion}
            onChange={(e) => setConfirmacion(e.target.value)}
            autoComplete="new-password"
            minLength={10}
            required
          />
        </label>

        <p className="cambiar-password__ayuda">
          Al menos 10 caracteres, con letras y números.
        </p>

        {error && (
          <p className="cambiar-password__error" role="alert">
            {error}
          </p>
        )}

        <button type="submit" className="cambiar-password__boton" disabled={cargando}>
          {cargando ? "Cambiando…" : "Cambiar contraseña"}
        </button>
      </form>
    </div>
  );
}
