import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { clienteApi } from "../api/cliente";
import { Bitacora } from "./Bitacora";

vi.mock("../api/cliente", () => ({
  clienteApi: { GET: vi.fn() },
}));

const ENTRADA = {
  id: "b1",
  fecha_hora: "2026-10-09T10:00:00Z",
  usuario_email: "analista@local",
  usuario_nombre: "Analista",
  rol: "analista",
  accion: "usuario_cambio_password",
  entidad_tipo: "usuario",
  detalle: null,
};

describe("Bitacora", () => {
  beforeEach(() => {
    vi.mocked(clienteApi.GET).mockReset();
  });

  it("busca y muestra las entradas al enviar el formulario", async () => {
    vi.mocked(clienteApi.GET).mockResolvedValue({
      data: [ENTRADA],
      error: undefined,
      response: new Response(),
    } as never);

    render(<Bitacora />);
    screen.getByText("Buscar").click();

    await waitFor(() => expect(screen.getByText("usuario_cambio_password")).toBeInTheDocument());
    expect(screen.getByText(/Analista \(analista@local\)/)).toBeInTheDocument();
  });

  it("muestra un mensaje si no hay registros", async () => {
    vi.mocked(clienteApi.GET).mockResolvedValue({
      data: [],
      error: undefined,
      response: new Response(),
    } as never);

    render(<Bitacora />);
    screen.getByText("Buscar").click();

    await waitFor(() =>
      expect(screen.getByText("No hay registros con esos filtros.")).toBeInTheDocument(),
    );
  });

  it("muestra un error si la búsqueda falla", async () => {
    vi.mocked(clienteApi.GET).mockResolvedValue({
      data: undefined,
      error: { detail: "no autorizado" },
      response: new Response(),
    } as never);

    render(<Bitacora />);
    screen.getByText("Buscar").click();

    await waitFor(() =>
      expect(screen.getByText("No se pudo cargar la bitácora")).toBeInTheDocument(),
    );
  });
});
