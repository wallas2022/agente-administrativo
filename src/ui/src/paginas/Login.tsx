import { useState, type FormEvent } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "../auth/ContextoAuth";
import "./Login.css";

export function Login() {
  const { usuario, cargando, error, iniciarSesion } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const ubicacion = useLocation();

  if (usuario) {
    const destino = (ubicacion.state as { desde?: string } | null)?.desde ?? "/";
    return <Navigate to={destino} replace />;
  }

  async function manejarEnvio(evento: FormEvent) {
    evento.preventDefault();
    await iniciarSesion(email, password);
  }

  return (
    <div className="login">
      <form className="login__tarjeta" onSubmit={manejarEnvio}>
        <h1 className="login__titulo">Agente Administrativo</h1>
        <p className="login__subtitulo">Iniciar sesión</p>

        <label className="login__campo">
          Correo
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            autoComplete="username"
            required
          />
        </label>

        <label className="login__campo">
          Contraseña
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
            required
          />
        </label>

        {error && (
          <p className="login__error" role="alert">
            {error}
          </p>
        )}

        <button type="submit" className="login__boton" disabled={cargando}>
          {cargando ? "Ingresando…" : "Ingresar"}
        </button>
      </form>
    </div>
  );
}
