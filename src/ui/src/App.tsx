import { Navigate, Route, Routes } from "react-router-dom";
import { Layout } from "./componentes/Layout";
import { RutaProtegida } from "./auth/RutaProtegida";
import { Login } from "./paginas/Login";
import { NuevoAnalisis } from "./paginas/NuevoAnalisis";
import { Proximamente } from "./paginas/Proximamente";

export function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route
        element={
          <RutaProtegida>
            <Layout />
          </RutaProtegida>
        }
      >
        <Route path="/" element={<NuevoAnalisis />} />
        <Route path="/historial" element={<Proximamente titulo="Historial" />} />
        <Route
          path="/base-de-conocimiento"
          element={<Proximamente titulo="Base de conocimiento" />}
        />
        <Route path="/configuracion" element={<Proximamente titulo="Configuración" />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
