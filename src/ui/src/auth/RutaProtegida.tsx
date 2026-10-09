import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { SinAcceso } from "../paginas/SinAcceso";
import { useAuth } from "./ContextoAuth";

interface Props {
  children: ReactNode;
  /** Un permiso, o varios cuando cualquiera de ellos habilita la pantalla
   * (p. ej. Configuración: usuarios:administrar O roles:administrar O
   * areas:administrar -- ver roles-permisos.md v0.3, "Menú por rol"). */
  permisoRequerido?: string | string[];
}

/** Exige sesión iniciada y, si se indica, al menos uno de los permisos
 * dados (RF-01/RNF-02). Sin el permiso, muestra "Sin acceso" en la misma
 * URL -- no un redirect silencioso -- porque el backend es la barrera real
 * (requiere_permiso) y esto es solo para no ofrecer algo que de todas
 * formas sería rechazado (HU-20). */
export function RutaProtegida({ children, permisoRequerido }: Props) {
  const { usuario } = useAuth();
  const ubicacion = useLocation();

  if (!usuario) {
    return <Navigate to="/login" replace state={{ desde: ubicacion.pathname }} />;
  }
  if (usuario.debeCambiarPassword && ubicacion.pathname !== "/cambiar-password") {
    return (
      <Navigate to="/cambiar-password" replace state={{ desde: ubicacion.pathname }} />
    );
  }
  if (permisoRequerido) {
    const requeridos = Array.isArray(permisoRequerido) ? permisoRequerido : [permisoRequerido];
    const tieneAcceso = requeridos.some((permiso) => usuario.permisos.includes(permiso));
    if (!tieneAcceso) {
      return <SinAcceso />;
    }
  }
  return <>{children}</>;
}
