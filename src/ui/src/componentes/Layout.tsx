import { NavLink, Outlet, Link } from "react-router-dom";
import logoServiciosCompartidos from "../assets/logo-servicios-compartidos.png";
import { useAuth } from "../auth/ContextoAuth";
import "./Layout.css";

// P-12 (Bloque 2, HU-20): el menú se arma desde los permisos de /auth/me,
// no de una lista fija por rol -- ver roles-permisos.md v0.3, "Menú por
// rol". `permisos: undefined` significa "siempre visible con sesión
// iniciada" (Historial: todos los roles tienen historial:propio).
const OPCIONES_MENU: { a: string; etiqueta: string; permisos?: string[] }[] = [
  { a: "/", etiqueta: "Nuevo análisis", permisos: ["analisis:crear"] },
  { a: "/historial", etiqueta: "Historial" },
  { a: "/base-de-conocimiento", etiqueta: "Base de conocimiento", permisos: ["conocimiento:ver"] },
  {
    a: "/ajustes-autoaprobados",
    etiqueta: "Ajustes autoaprobados",
    permisos: ["reportes:autoaprobados"],
  },
  { a: "/bitacora", etiqueta: "Bitácora", permisos: ["bitacora:ver"] },
  {
    a: "/configuracion",
    etiqueta: "Configuración",
    permisos: ["usuarios:administrar", "roles:administrar", "areas:administrar"],
  },
];

export function Layout() {
  const { usuario, cerrarSesion, tienePermiso } = useAuth();
  const enlaces = OPCIONES_MENU.filter(
    (opcion) => !opcion.permisos || tienePermiso(...opcion.permisos),
  );

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
          {enlaces.map((enlace) => (
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
            <div className="layout__usuario-rol">
              {usuario?.rol} · {usuario?.area}
            </div>
            <Link to="/cambiar-password" className="layout__usuario-cambiar-password">
              Cambiar contraseña
            </Link>
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
