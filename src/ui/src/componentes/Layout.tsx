import { NavLink, Outlet } from "react-router-dom";
import logoServiciosCompartidos from "../assets/logo-servicios-compartidos.png";
import { useAuth } from "../auth/ContextoAuth";
import "./Layout.css";

const ENLACES = [
  { a: "/", etiqueta: "Nuevo análisis" },
  { a: "/historial", etiqueta: "Historial" },
  { a: "/base-de-conocimiento", etiqueta: "Base de conocimiento" },
  { a: "/ajustes-autoaprobados", etiqueta: "Ajustes autoaprobados" },
  { a: "/configuracion", etiqueta: "Configuración" },
];

export function Layout() {
  const { usuario, cerrarSesion } = useAuth();

  return (
    <div className="layout">
      <aside className="layout__sidebar">
        <div className="layout__marca">
          <img
            className="layout__logo"
            src={logoServiciosCompartidos}
            alt="Servicios Compartidos"
          />
          <span className="layout__nombre-app">Agente Administrativo</span>
        </div>
        <nav className="layout__nav">
          {ENLACES.map((enlace) => (
            <NavLink
              key={enlace.a}
              to={enlace.a}
              end={enlace.a === "/"}
              className={({ isActive }) =>
                "layout__enlace" + (isActive ? " layout__enlace--activo" : "")
              }
            >
              {enlace.etiqueta}
            </NavLink>
          ))}
        </nav>
        <div className="layout__usuario">
          <div>
            <div className="layout__usuario-email">{usuario?.email}</div>
            <div className="layout__usuario-rol">{usuario?.rol}</div>
          </div>
          <button type="button" className="layout__salir" onClick={cerrarSesion}>
            Salir
          </button>
        </div>
      </aside>
      <main className="layout__contenido">
        <Outlet />
      </main>
    </div>
  );
}
