import { useState } from "react";
import { useAuth } from "../auth/ContextoAuth";
import "./Configuracion.css";
import { ConfiguracionAreas } from "./ConfiguracionAreas";
import { ConfiguracionPermisos } from "./ConfiguracionPermisos";
import { ConfiguracionUsuarios } from "./ConfiguracionUsuarios";

const PESTANAS = [
  { valor: "usuarios", etiqueta: "Usuarios", permiso: "usuarios:administrar" },
  { valor: "permisos", etiqueta: "Roles y permisos", permiso: "roles:administrar" },
  { valor: "areas", etiqueta: "Áreas", permiso: "areas:administrar" },
] as const;

/** HU-22, HU-23, HU-24: pestañas Usuarios / Roles y permisos / Áreas --
 * cada una solo aparece si el usuario tiene el permiso correspondiente
 * (hoy los 3 son exclusivos de Administrador, ver roles-permisos.md v0.3). */
export function Configuracion() {
  const { tienePermiso } = useAuth();
  const disponibles = PESTANAS.filter((p) => tienePermiso(p.permiso));
  const [pestana, setPestana] = useState<string>(disponibles[0]?.valor ?? "usuarios");

  return (
    <div className="configuracion">
      <h1>Configuración</h1>

      <div className="configuracion__pestanas" role="tablist">
        {disponibles.map((p) => (
          <button
            key={p.valor}
            type="button"
            role="tab"
            aria-selected={pestana === p.valor}
            className={
              "configuracion__pestana" +
              (pestana === p.valor ? " configuracion__pestana--activa" : "")
            }
            onClick={() => setPestana(p.valor)}
          >
            {p.etiqueta}
          </button>
        ))}
      </div>

      {pestana === "usuarios" && <ConfiguracionUsuarios />}
      {pestana === "permisos" && <ConfiguracionPermisos />}
      {pestana === "areas" && <ConfiguracionAreas />}
    </div>
  );
}
