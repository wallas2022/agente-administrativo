import { useState } from "react";
import "./Dashboard.css";
import { DashboardConfiguracion } from "./DashboardConfiguracion";
import { DashboardConsumo } from "./DashboardConsumo";
import { DashboardRecursos } from "./DashboardRecursos";
import { DashboardUsuarios } from "./DashboardUsuarios";

const PESTANAS = [
  { valor: "consumo", etiqueta: "Consumo" },
  { valor: "usuarios", etiqueta: "Usuarios" },
  { valor: "recursos", etiqueta: "Recursos" },
  { valor: "configuracion", etiqueta: "Configuración" },
] as const;

/** P-13 (Bloque 4, HU-26..30): pantalla de solo-Administrador (dashboard:ver)
 * con 4 pestañas -- misma estructura que Configuracion.tsx, pero sin
 * filtrar pestañas por permiso individual porque las 4 comparten el mismo
 * permiso de ruta (RutaProtegida ya exige dashboard:ver en App.tsx). */
export function Dashboard() {
  const [pestana, setPestana] = useState<string>("consumo");

  return (
    <div className="dashboard">
      <h1>Dashboard</h1>
      <div className="dashboard__pestanas" role="tablist">
        {PESTANAS.map((p) => (
          <button
            key={p.valor}
            type="button"
            role="tab"
            aria-selected={pestana === p.valor}
            className={
              "dashboard__pestana" + (pestana === p.valor ? " dashboard__pestana--activa" : "")
            }
            onClick={() => setPestana(p.valor)}
          >
            {p.etiqueta}
          </button>
        ))}
      </div>
      {pestana === "consumo" && <DashboardConsumo />}
      {pestana === "usuarios" && <DashboardUsuarios />}
      {pestana === "recursos" && <DashboardRecursos />}
      {pestana === "configuracion" && <DashboardConfiguracion />}
    </div>
  );
}
