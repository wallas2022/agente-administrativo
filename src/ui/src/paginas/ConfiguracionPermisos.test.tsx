import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { clienteApi } from "../api/cliente";
import { ConfiguracionPermisos } from "./ConfiguracionPermisos";

vi.mock("../api/cliente", () => ({
  clienteApi: { GET: vi.fn(), PUT: vi.fn(), POST: vi.fn() },
}));

const CELDAS = [
  { rol: "analista", recurso: "analisis", accion: "crear", otorgado: true, protegido: false },
  { rol: "administrador", recurso: "analisis", accion: "crear", otorgado: true, protegido: false },
  {
    rol: "administrador",
    recurso: "usuarios",
    accion: "administrar",
    otorgado: true,
    protegido: true,
  },
  { rol: "analista", recurso: "usuarios", accion: "administrar", otorgado: false, protegido: false },
  { rol: "revisor", recurso: "analisis", accion: "crear", otorgado: false, protegido: false },
  { rol: "curador", recurso: "analisis", accion: "crear", otorgado: false, protegido: false },
  { rol: "auditor", recurso: "analisis", accion: "crear", otorgado: false, protegido: false },
  { rol: "revisor", recurso: "usuarios", accion: "administrar", otorgado: false, protegido: false },
  { rol: "curador", recurso: "usuarios", accion: "administrar", otorgado: false, protegido: false },
  { rol: "auditor", recurso: "usuarios", accion: "administrar", otorgado: false, protegido: false },
];

describe("ConfiguracionPermisos", () => {
  beforeEach(() => {
    vi.mocked(clienteApi.GET).mockReset();
    vi.mocked(clienteApi.PUT).mockReset();
    vi.mocked(clienteApi.POST).mockReset();
  });

  it("dibuja la matriz con una fila por recurso:accion", async () => {
    vi.mocked(clienteApi.GET).mockResolvedValue({
      data: CELDAS,
      error: undefined,
      response: new Response(),
    } as never);

    render(<ConfiguracionPermisos />);
    expect(await screen.findByText("analisis:crear")).toBeInTheDocument();
    expect(screen.getByText("usuarios:administrar")).toBeInTheDocument();
  });

  it("una celda protegida aparece deshabilitada", async () => {
    vi.mocked(clienteApi.GET).mockResolvedValue({
      data: CELDAS,
      error: undefined,
      response: new Response(),
    } as never);

    render(<ConfiguracionPermisos />);
    await screen.findByText("usuarios:administrar");
    const protegida = screen.getByLabelText(
      "administrador usuarios:administrar (protegido)",
    ) as HTMLInputElement;
    expect(protegida.disabled).toBe(true);
  });

  it("marcar una celda no protegida llama a PUT /permisos", async () => {
    vi.mocked(clienteApi.GET).mockResolvedValue({
      data: CELDAS,
      error: undefined,
      response: new Response(),
    } as never);
    vi.mocked(clienteApi.PUT).mockResolvedValue({
      data: { rol: "analista", recurso: "usuarios", accion: "administrar", otorgado: true, protegido: false },
      error: undefined,
      response: new Response(),
    } as never);

    render(<ConfiguracionPermisos />);
    await screen.findByText("usuarios:administrar");
    const casilla = screen.getByLabelText("analista usuarios:administrar");
    casilla.click();

    await waitFor(() =>
      expect(clienteApi.PUT).toHaveBeenCalledWith(
        "/permisos",
        expect.objectContaining({
          body: { rol: "analista", recurso: "usuarios", accion: "administrar", otorgado: true },
        }),
      ),
    );
  });

  it("restaurar matriz pide confirmación y, si se acepta, llama a POST /permisos/restaurar", async () => {
    vi.mocked(clienteApi.GET).mockResolvedValue({
      data: CELDAS,
      error: undefined,
      response: new Response(),
    } as never);
    vi.mocked(clienteApi.POST).mockResolvedValue({
      data: CELDAS,
      error: undefined,
      response: new Response(),
    } as never);
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);

    render(<ConfiguracionPermisos />);
    await screen.findByText("usuarios:administrar");
    screen.getByText("Restaurar matriz por defecto").click();

    await waitFor(() => expect(clienteApi.POST).toHaveBeenCalledWith("/permisos/restaurar"));
    confirmSpy.mockRestore();
  });

  it("restaurar matriz no hace nada si se cancela la confirmación", async () => {
    vi.mocked(clienteApi.GET).mockResolvedValue({
      data: CELDAS,
      error: undefined,
      response: new Response(),
    } as never);
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(false);

    render(<ConfiguracionPermisos />);
    await screen.findByText("usuarios:administrar");
    screen.getByText("Restaurar matriz por defecto").click();

    expect(clienteApi.POST).not.toHaveBeenCalled();
    confirmSpy.mockRestore();
  });
});
