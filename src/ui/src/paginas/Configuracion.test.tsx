import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { clienteApi } from "../api/cliente";
import { Configuracion } from "./Configuracion";

vi.mock("../api/cliente", () => ({
  clienteApi: { GET: vi.fn(), POST: vi.fn(), PUT: vi.fn(), PATCH: vi.fn(), DELETE: vi.fn() },
}));

const permisosMock = vi.hoisted(() => ({ actuales: [] as string[] }));

vi.mock("../auth/ContextoAuth", () => ({
  useAuth: () => ({
    tienePermiso: (permiso: string) => permisosMock.actuales.includes(permiso),
  }),
}));

describe("Configuracion", () => {
  beforeEach(() => {
    vi.mocked(clienteApi.GET).mockResolvedValue({
      data: [],
      error: undefined,
      response: new Response(),
    } as never);
  });

  it("solo muestra las pestañas cuyo permiso tiene el usuario", () => {
    permisosMock.actuales = ["usuarios:administrar", "areas:administrar"];
    render(<Configuracion />);

    expect(screen.getByRole("tab", { name: "Usuarios" })).toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: "Roles y permisos" })).not.toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Áreas" })).toBeInTheDocument();
  });

  it("la pestaña Usuarios está activa por defecto cuando el usuario tiene ese permiso", () => {
    permisosMock.actuales = ["usuarios:administrar", "roles:administrar", "areas:administrar"];
    render(<Configuracion />);
    expect(screen.getByRole("tab", { name: "Usuarios" })).toHaveAttribute("aria-selected", "true");
  });

  it("cambiar de pestaña activa la elegida", async () => {
    permisosMock.actuales = ["usuarios:administrar", "roles:administrar"];
    render(<Configuracion />);

    fireEvent.click(screen.getByRole("tab", { name: "Roles y permisos" }));

    await waitFor(() =>
      expect(screen.getByRole("tab", { name: "Roles y permisos" })).toHaveAttribute(
        "aria-selected",
        "true",
      ),
    );
    expect(screen.getByRole("tab", { name: "Usuarios" })).toHaveAttribute(
      "aria-selected",
      "false",
    );
  });
});
