import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "./ContextoAuth";

interface Props {
  children: ReactNode;
  rolesPermitidos?: string[];
}

/** Exige sesión iniciada y, si se indica, uno de los roles permitidos
 * (RF-01, segregación de funciones por rol). */
export function RutaProtegida({ children, rolesPermitidos }: Props) {
  const { usuario } = useAuth();
  const ubicacion = useLocation();

  if (!usuario) {
    return <Navigate to="/login" replace state={{ desde: ubicacion.pathname }} />;
  }
  if (rolesPermitidos && !rolesPermitidos.includes(usuario.rol)) {
    return <Navigate to="/" replace />;
  }
  return <>{children}</>;
}
