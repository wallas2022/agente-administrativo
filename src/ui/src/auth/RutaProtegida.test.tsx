import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import type { Usuario } from "./ContextoAuth";
import { RutaProtegida } from "./RutaProtegida";

const usuarioMock = vi.hoisted(() => ({ actual: null as Usuario | null }));

vi.mock("./ContextoAuth", () => ({
  useAuth: () => ({ usuario: usuarioMock.actual }),
}));

function _usuario(sobrescribe: Partial<Usuario> = {}): Usuario {
  return {
    id: "u1",
    nombre: "Ana Lista",
    email: "analista@local",
    rol: "analista",
    area: "Contabilidad",
    permisos: ["analisis:crear"],
    debeCambiarPassword: false,
    ...sobrescribe,
  };
}

function renderizarEn(ruta: string, permisoRequerido?: string | string[]) {
  return render(
    <MemoryRouter initialEntries={[ruta]}>
      <Routes>
        <Route path="/login" element={<div>pantalla de login</div>} />
        <Route path="/cambiar-password" element={<div>pantalla de cambiar contraseña</div>} />
        <Route
          path="/"
          element={
            <RutaProtegida permisoRequerido={permisoRequerido}>
              <div>contenido protegido</div>
            </RutaProtegida>
          }
        />
      </Routes>
    </MemoryRouter>,
  );
}

describe("RutaProtegida", () => {
  it("redirige a /login si no hay sesión", () => {
    usuarioMock.actual = null;
    renderizarEn("/");
    expect(screen.getByText("pantalla de login")).toBeInTheDocument();
  });

  it("muestra el contenido si hay sesión y no se exige un permiso", () => {
    usuarioMock.actual = _usuario();
    renderizarEn("/");
    expect(screen.getByText("contenido protegido")).toBeInTheDocument();
  });

  it("muestra 'Sin acceso' (misma URL) si falta el permiso exigido", () => {
    usuarioMock.actual = _usuario({ permisos: ["historial:propio"] });
    renderizarEn("/", "analisis:crear");
    expect(screen.queryByText("contenido protegido")).not.toBeInTheDocument();
    expect(screen.getByText("Sin acceso")).toBeInTheDocument();
  });

  it("muestra el contenido si tiene al menos uno de varios permisos exigidos", () => {
    usuarioMock.actual = _usuario({ permisos: ["roles:administrar"] });
    renderizarEn("/", ["usuarios:administrar", "roles:administrar", "areas:administrar"]);
    expect(screen.getByText("contenido protegido")).toBeInTheDocument();
  });

  it("redirige a /cambiar-password si debe cambiar la contraseña, sin importar el permiso", () => {
    usuarioMock.actual = _usuario({ debeCambiarPassword: true });
    renderizarEn("/", "analisis:crear");
    expect(screen.getByText("pantalla de cambiar contraseña")).toBeInTheDocument();
  });
});
