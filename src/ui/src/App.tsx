import { Navigate, Route, Routes } from "react-router-dom";
import { Layout } from "./componentes/Layout";
import { RutaProtegida } from "./auth/RutaProtegida";
import { AgenteTrabajando } from "./paginas/AgenteTrabajando";
import { BaseConocimiento } from "./paginas/BaseConocimiento";
import { Bitacora } from "./paginas/Bitacora";
import { CambiarPassword } from "./paginas/CambiarPassword";
import { Chat } from "./paginas/Chat";
import { Configuracion } from "./paginas/Configuracion";
import { Dashboard } from "./paginas/Dashboard";
import { Hallazgos } from "./paginas/Hallazgos";
import { Historial } from "./paginas/Historial";
import { Login } from "./paginas/Login";
import { NuevoAnalisis } from "./paginas/NuevoAnalisis";
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
        {/* P-14 (Bloque 3, HU-33): el chat es la pantalla de inicio para
            todos los roles, sin gate de permiso (como Historial) -- "Nuevo
            análisis" se movió a su propia ruta, con el mismo permiso que
            ya tenía. */}
        <Route path="/" element={<Chat />} />
        <Route
          path="/nuevo-analisis"
          element={
            <RutaProtegida permisoRequerido="analisis:crear">
              <NuevoAnalisis />
            </RutaProtegida>
          }
        />
        <Route path="/analisis/:analisisId" element={<AgenteTrabajando />} />
        <Route path="/analisis/:analisisId/hallazgos" element={<Hallazgos />} />
        <Route path="/historial" element={<Historial />} />
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
          path="/dashboard"
          element={
            <RutaProtegida permisoRequerido="dashboard:ver">
              <Dashboard />
            </RutaProtegida>
          }
        />
        <Route
          path="/configuracion"
          element={
            <RutaProtegida
              permisoRequerido={["usuarios:administrar", "roles:administrar", "areas:administrar"]}
            >
              <Configuracion />
            </RutaProtegida>
          }
        />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
