import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { clienteApi } from "../api/cliente";
import { descargarArchivo } from "../api/descargas";
import { DashboardUsuarios } from "./DashboardUsuarios";

vi.mock("../api/cliente", () => ({
  clienteApi: { GET: vi.fn() },
}));

vi.mock("../api/descargas", () => ({
  descargarArchivo: vi.fn(),
}));

const FILA = {
  usuario_id: "u1",
  usuario_nombre: "Ana Lista",
  usuario_email: "analista@local",
  area_nombre: "Contabilidad",
  numero_analisis: 2,
  tokens_entrada: 100,
  tokens_salida: 50,
  duracion_llm_total_ms: 2000,
  timeouts: 0,
};

describe("DashboardUsuarios (HU-27)", () => {
  beforeEach(() => {
    vi.mocked(clienteApi.GET).mockReset();
    vi.mocked(descargarArchivo).mockReset();
  });

  it("muestra el mensaje de 'sin datos' cuando no hay filas", async () => {
    vi.mocked(clienteApi.GET).mockResolvedValue({
      data: [],
      error: undefined,
      response: new Response(),
    } as never);

    render(<DashboardUsuarios />);

    await waitFor(() =>
      expect(
        screen.getByText("Todavía no hay datos de consumo para estos filtros."),
      ).toBeInTheDocument(),
    );
    expect(screen.getByRole("button", { name: "Exportar CSV" })).toBeDisabled();
  });

  it("muestra la fila de un usuario y habilita 'Exportar CSV'", async () => {
    vi.mocked(clienteApi.GET).mockResolvedValue({
      data: [FILA],
      error: undefined,
      response: new Response(),
    } as never);

    render(<DashboardUsuarios />);

    await waitFor(() =>
      expect(screen.getByText("Ana Lista (analista@local)")).toBeInTheDocument(),
    );
    expect(screen.getByRole("button", { name: "Exportar CSV" })).toBeEnabled();
  });

  it("al exportar, descarga con formato=csv y los filtros vigentes", async () => {
    vi.mocked(clienteApi.GET).mockResolvedValue({
      data: [FILA],
      error: undefined,
      response: new Response(),
    } as never);

    render(<DashboardUsuarios />);
    await waitFor(() => expect(screen.getByText("Ana Lista (analista@local)")).toBeInTheDocument());

    screen.getByRole("button", { name: "Exportar CSV" }).click();

    await waitFor(() => expect(descargarArchivo).toHaveBeenCalledWith(
      "/admin/dashboard/usuarios?formato=csv",
    ));
  });

  it("muestra un error si la búsqueda falla", async () => {
    vi.mocked(clienteApi.GET).mockResolvedValue({
      data: undefined,
      error: { detail: "no autorizado" },
      response: new Response(),
    } as never);

    render(<DashboardUsuarios />);

    await waitFor(() =>
      expect(screen.getByText("No se pudo cargar el consumo por usuario")).toBeInTheDocument(),
    );
  });
});
