import { Navigate, Route, Routes } from "react-router-dom";
import { Layout } from "./componentes/Layout";
import { RutaProtegida } from "./auth/RutaProtegida";
import { AgenteTrabajando } from "./paginas/AgenteTrabajando";
import { BaseConocimiento } from "./paginas/BaseConocimiento";
import { Bitacora } from "./paginas/Bitacora";
import { CambiarPassword } from "./paginas/CambiarPassword";
import { Hallazgos } from "./paginas/Hallazgos";
import { Login } from "./paginas/Login";
import { NuevoAnalisis } from "./paginas/NuevoAnalisis";
import { Proximamente } from "./paginas/Proximamente";
import { ReporteAjustesAutoaprobados } from "./paginas/ReporteAjustesAutoaprobados";

export function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route
        path="/cambiar-password"
        element={
          <RutaProtegida>
            <CambiarPassword />
          </RutaProtegida>
        }
      />
      <Route
        element={
          <RutaProtegida>
            <Layout />
          </RutaProtegida>
        }
      >
        {/* "/" no se restringe por permiso: hoy también aloja el panel de
            "Análisis recientes", la única forma de llegar a un análisis
            propio/del área para Revisor/Curador/Auditor mientras el
            Historial real (Bloque 3) no existe -- NuevoAnalisis.tsx oculta
            el formulario de carga si el usuario no tiene analisis:crear. */}
        <Route path="/" element={<NuevoAnalisis />} />
        <Route path="/analisis/:analisisId" element={<AgenteTrabajando />} />
        <Route path="/analisis/:analisisId/hallazgos" element={<Hallazgos />} />
        <Route path="/historial" element={<Proximamente titulo="Historial" />} />
        <Route
          path="/base-de-conocimiento"
          element={
            <RutaProtegida permisoRequerido="conocimiento:ver">
              <BaseConocimiento />
            </RutaProtegida>
          }
        />
        <Route
          path="/ajustes-autoaprobados"
          element={
            <RutaProtegida permisoRequerido="reportes:autoaprobados">
              <ReporteAjustesAutoaprobados />
            </RutaProtegida>
          }
        />
        <Route
          path="/bitacora"
          element={
            <RutaProtegida permisoRequerido="bitacora:ver">
              <Bitacora />
            </RutaProtegida>
          }
        />
        <Route
          path="/configuracion"
          element={
            <RutaProtegida
              permisoRequerido={["usuarios:administrar", "roles:administrar", "areas:administrar"]}
            >
              <Proximamente titulo="Configuración" />
            </RutaProtegida>
          }
        />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
