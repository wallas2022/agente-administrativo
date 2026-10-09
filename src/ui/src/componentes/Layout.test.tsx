import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import type { Usuario } from "../auth/ContextoAuth";
import { Layout } from "./Layout";

const usuarioMock = vi.hoisted(() => ({ actual: null as Usuario | null }));

vi.mock("../auth/ContextoAuth", () => ({
  useAuth: () => ({
    usuario: usuarioMock.actual,
    cerrarSesion: vi.fn(),
    tienePermiso: (...permisos: string[]) =>
      permisos.some((p) => usuarioMock.actual?.permisos.includes(p)),
  }),
}));

function _usuario(sobrescribe: Partial<Usuario> = {}): Usuario {
  return {
    id: "u1",
    nombre: "Prueba",
    email: "prueba@local",
    rol: "prueba",
    area: "Contabilidad",
    permisos: [],
    debeCambiarPassword: false,
    ...sobrescribe,
  };
}

function renderizar() {
  return render(
    <MemoryRouter initialEntries={["/"]}>
      <Routes>
        <Route path="/" element={<Layout />}>
          <Route index element={<div>contenido</div>} />
        </Route>
      </Routes>
    </MemoryRouter>,
  );
}

describe("Layout", () => {
  it("Analista ve Nuevo análisis e Historial, nada más (HU-20)", () => {
    usuarioMock.actual = _usuario({
      rol: "analista",
      permisos: ["analisis:crear", "historial:propio", "historial:area"],
    });
    renderizar();

    expect(screen.getByText("Nuevo análisis")).toBeInTheDocument();
    expect(screen.getByText("Historial")).toBeInTheDocument();
    expect(screen.queryByText("Base de conocimiento")).not.toBeInTheDocument();
    expect(screen.queryByText("Ajustes autoaprobados")).not.toBeInTheDocument();
    expect(screen.queryByText("Bitácora")).not.toBeInTheDocument();
    expect(screen.queryByText("Configuración")).not.toBeInTheDocument();
  });

  it("Revisor solo ve Historial", () => {
    usuarioMock.actual = _usuario({
      rol: "revisor",
      permisos: ["historial:propio", "historial:area", "hallazgos:decidir"],
    });
    renderizar();

    expect(screen.queryByText("Nuevo análisis")).not.toBeInTheDocument();
    expect(screen.getByText("Historial")).toBeInTheDocument();
    expect(screen.queryByText("Base de conocimiento")).not.toBeInTheDocument();
  });

  it("Auditor ve Historial, Base de conocimiento, Ajustes autoaprobados y Bitácora, sin Configuración", () => {
    usuarioMock.actual = _usuario({
      rol: "auditor",
      permisos: [
        "historial:propio",
        "historial:area",
        "historial:todas",
        "conocimiento:ver",
        "bitacora:ver",
        "reportes:autoaprobados",
      ],
    });
    renderizar();

    expect(screen.getByText("Historial")).toBeInTheDocument();
    expect(screen.getByText("Base de conocimiento")).toBeInTheDocument();
    expect(screen.getByText("Ajustes autoaprobados")).toBeInTheDocument();
    expect(screen.getByText("Bitácora")).toBeInTheDocument();
    expect(screen.queryByText("Configuración")).not.toBeInTheDocument();
    expect(screen.queryByText("Nuevo análisis")).not.toBeInTheDocument();
  });

  it("Administrador ve Configuración (OR entre usuarios/roles/areas:administrar)", () => {
    usuarioMock.actual = _usuario({ rol: "administrador", permisos: ["roles:administrar"] });
    renderizar();

    expect(screen.getByText("Configuración")).toBeInTheDocument();
  });

  it("muestra el rol y el área junto al usuario", () => {
    usuarioMock.actual = _usuario({ rol: "analista", area: "Tesorería", permisos: [] });
    const { container } = renderizar();

    const rolYArea = container.querySelector(".layout__usuario-rol");
    expect(rolYArea?.textContent).toBe("analista · Tesorería");
  });
});
