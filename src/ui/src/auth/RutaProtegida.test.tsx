import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { RutaProtegida } from "./RutaProtegida";

const usuarioMock = vi.hoisted(() => ({ actual: null as { email: string; rol: string } | null }));

vi.mock("./ContextoAuth", () => ({
  useAuth: () => ({ usuario: usuarioMock.actual }),
}));

function renderizarEn(ruta: string, rolesPermitidos?: string[]) {
  return render(
    <MemoryRouter initialEntries={[ruta]}>
      <Routes>
        <Route path="/login" element={<div>pantalla de login</div>} />
        <Route
          path="/"
          element={
            <RutaProtegida rolesPermitidos={rolesPermitidos}>
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

  it("muestra el contenido si hay sesión y no se exige un rol", () => {
    usuarioMock.actual = { email: "analista@local", rol: "analista" };
    renderizarEn("/");
    expect(screen.getByText("contenido protegido")).toBeInTheDocument();
  });

  it("redirige a / si el rol del usuario no está permitido", () => {
    usuarioMock.actual = { email: "analista@local", rol: "analista" };
    renderizarEn("/", ["revisor", "administrador"]);
    // Se redirige a "/" (misma ruta protegida), que vuelve a exigir el rol:
    // termina mostrando el mismo contenido protegido solo si el rol calza,
    // así que con un rol no permitido el contenido nunca aparece.
    expect(screen.queryByText("contenido protegido")).not.toBeInTheDocument();
  });
});
