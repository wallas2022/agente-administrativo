import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { clienteApi } from "../api/cliente";
import { ConfiguracionAreas } from "./ConfiguracionAreas";

vi.mock("../api/cliente", () => ({
  clienteApi: { GET: vi.fn(), POST: vi.fn(), PATCH: vi.fn(), DELETE: vi.fn() },
}));

const AREA = { id: "a1", nombre: "Contabilidad" };

describe("ConfiguracionAreas", () => {
  beforeEach(() => {
    vi.mocked(clienteApi.GET).mockReset();
    vi.mocked(clienteApi.POST).mockReset();
    vi.mocked(clienteApi.PATCH).mockReset();
    vi.mocked(clienteApi.DELETE).mockReset();
    vi.mocked(clienteApi.GET).mockResolvedValue({
      data: [AREA],
      error: undefined,
      response: new Response(),
    } as never);
  });

  it("lista las áreas existentes", async () => {
    render(<ConfiguracionAreas />);
    expect(await screen.findByDisplayValue("Contabilidad")).toBeInTheDocument();
  });

  it("crea un área nueva", async () => {
    vi.mocked(clienteApi.POST).mockResolvedValue({
      data: { id: "a2", nombre: "Tesorería" },
      error: undefined,
      response: new Response(),
    } as never);

    render(<ConfiguracionAreas />);
    await screen.findByDisplayValue("Contabilidad");
    fireEvent.change(screen.getByLabelText("Nueva área"), { target: { value: "Tesorería" } });
    fireEvent.click(screen.getByText("Crear área"));

    await waitFor(() =>
      expect(clienteApi.POST).toHaveBeenCalledWith("/areas", { body: { nombre: "Tesorería" } }),
    );
  });

  it("muestra el error del servidor si el nombre está duplicado", async () => {
    vi.mocked(clienteApi.POST).mockResolvedValue({
      data: undefined,
      error: { detail: "Ya existe un área con ese nombre" },
      response: new Response(),
    } as never);

    render(<ConfiguracionAreas />);
    await screen.findByDisplayValue("Contabilidad");
    fireEvent.change(screen.getByLabelText("Nueva área"), { target: { value: "Contabilidad" } });
    fireEvent.click(screen.getByText("Crear área"));

    await waitFor(() =>
      expect(screen.getByText("Ya existe un área con ese nombre")).toBeInTheDocument(),
    );
  });

  it("renombrar llama a PATCH con el nuevo nombre", async () => {
    vi.mocked(clienteApi.PATCH).mockResolvedValue({
      data: { id: "a1", nombre: "Contabilidad General" },
      error: undefined,
      response: new Response(),
    } as never);

    render(<ConfiguracionAreas />);
    const campo = await screen.findByDisplayValue("Contabilidad");
    fireEvent.change(campo, { target: { value: "Contabilidad General" } });
    fireEvent.click(screen.getByText("Guardar"));

    await waitFor(() =>
      expect(clienteApi.PATCH).toHaveBeenCalledWith("/areas/{area_id}", {
        params: { path: { area_id: "a1" } },
        body: { nombre: "Contabilidad General" },
      }),
    );
  });

  it("eliminar un área en uso muestra el mensaje de conflicto (409)", async () => {
    vi.mocked(clienteApi.DELETE).mockResolvedValue({
      data: undefined,
      error: { detail: "conflicto" },
      response: new Response(null, { status: 409 }),
    } as never);

    render(<ConfiguracionAreas />);
    await screen.findByDisplayValue("Contabilidad");
    fireEvent.click(screen.getByText("Eliminar"));

    await waitFor(() =>
      expect(
        screen.getByText("El área tiene usuarios o documentos asociados -- no se puede eliminar"),
      ).toBeInTheDocument(),
    );
  });

  it("eliminar un área sin usar recarga la lista", async () => {
    vi.mocked(clienteApi.DELETE).mockResolvedValue({
      data: null,
      error: undefined,
      response: new Response(null, { status: 204 }),
    } as never);

    render(<ConfiguracionAreas />);
    await screen.findByDisplayValue("Contabilidad");
    fireEvent.click(screen.getByText("Eliminar"));

    await waitFor(() => expect(clienteApi.GET).toHaveBeenCalledTimes(2));
  });
});
