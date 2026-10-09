import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { clienteApi } from "../api/cliente";
import { ConfiguracionUsuarios } from "./ConfiguracionUsuarios";

vi.mock("../api/cliente", () => ({
  clienteApi: { GET: vi.fn(), POST: vi.fn(), PATCH: vi.fn() },
}));

const AREA = { id: "area-1", nombre: "Contabilidad" };
const USUARIO = {
  id: "u1",
  nombre: "Ana Lista",
  email: "analista@local",
  rol: "analista",
  area_id: "area-1",
  area: "Contabilidad",
  activo: true,
  debe_cambiar_password: false,
  ultimo_acceso: null,
};

function mockListados() {
  vi.mocked(clienteApi.GET).mockImplementation(((ruta: string) => {
    if (ruta === "/usuarios") {
      return Promise.resolve({
        data: [USUARIO],
        error: undefined,
        response: new Response(),
      });
    }
    if (ruta === "/areas") {
      return Promise.resolve({ data: [AREA], error: undefined, response: new Response() });
    }
    return Promise.resolve({ data: undefined, error: { detail: "ruta no mockeada" }, response: new Response() });
  }) as never);
}

describe("ConfiguracionUsuarios", () => {
  beforeEach(() => {
    vi.mocked(clienteApi.GET).mockReset();
    vi.mocked(clienteApi.POST).mockReset();
    vi.mocked(clienteApi.PATCH).mockReset();
  });

  it("lista los usuarios existentes", async () => {
    mockListados();
    render(<ConfiguracionUsuarios />);
    expect(await screen.findByText("analista@local")).toBeInTheDocument();
  });

  it("al crear un usuario muestra la contraseña temporal una sola vez", async () => {
    mockListados();
    vi.mocked(clienteApi.POST).mockResolvedValue({
      data: {
        usuario: { ...USUARIO, id: "u2", email: "nuevo@local" },
        password_temporal: "Abc12345xy",
      },
      error: undefined,
      response: new Response(),
    } as never);

    render(<ConfiguracionUsuarios />);
    await screen.findByText("analista@local");

    fireEvent.change(screen.getByLabelText("Nombre"), { target: { value: "Nuevo" } });
    fireEvent.change(screen.getByLabelText("Correo"), { target: { value: "nuevo@local" } });
    fireEvent.click(screen.getByText("Crear usuario"));

    await waitFor(() => expect(screen.getByText("Abc12345xy")).toBeInTheDocument());
    expect(screen.getByText("nuevo@local", { selector: "strong" })).toBeInTheDocument();
  });

  it("muestra el error del servidor si la creación falla", async () => {
    mockListados();
    vi.mocked(clienteApi.POST).mockResolvedValue({
      data: undefined,
      error: { detail: "Ya existe un usuario con ese correo" },
      response: new Response(),
    } as never);

    render(<ConfiguracionUsuarios />);
    await screen.findByText("analista@local");
    fireEvent.change(screen.getByLabelText("Nombre"), { target: { value: "Dup" } });
    fireEvent.change(screen.getByLabelText("Correo"), { target: { value: "analista@local" } });
    fireEvent.click(screen.getByText("Crear usuario"));

    await waitFor(() =>
      expect(screen.getByText("Ya existe un usuario con ese correo")).toBeInTheDocument(),
    );
  });

  it("cambiar el rol desde la tabla llama a PATCH /usuarios/{id}", async () => {
    mockListados();
    vi.mocked(clienteApi.PATCH).mockResolvedValue({
      data: USUARIO,
      error: undefined,
      response: new Response(),
    } as never);

    render(<ConfiguracionUsuarios />);
    await screen.findByText("analista@local");

    const selectesDeRol = screen.getAllByDisplayValue("analista");
    fireEvent.change(selectesDeRol[selectesDeRol.length - 1], { target: { value: "revisor" } });

    await waitFor(() =>
      expect(clienteApi.PATCH).toHaveBeenCalledWith(
        "/usuarios/{usuario_id}",
        expect.objectContaining({
          params: { path: { usuario_id: "u1" } },
          body: { rol: "revisor" },
        }),
      ),
    );
  });

  it("restablecer contraseña muestra la nueva contraseña temporal", async () => {
    mockListados();
    vi.mocked(clienteApi.POST).mockResolvedValue({
      data: { password_temporal: "Reset1234x" },
      error: undefined,
      response: new Response(),
    } as never);

    render(<ConfiguracionUsuarios />);
    await screen.findByText("analista@local");
    fireEvent.click(screen.getByText("Restablecer contraseña"));

    await waitFor(() => expect(screen.getByText("Reset1234x")).toBeInTheDocument());
  });
});
