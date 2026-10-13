import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { clienteApi } from "../api/cliente";
import { DashboardConsumo } from "./DashboardConsumo";

vi.mock("../api/cliente", () => ({
  clienteApi: { GET: vi.fn() },
}));

describe("DashboardConsumo (HU-26, HU-28)", () => {
  beforeEach(() => {
    vi.mocked(clienteApi.GET).mockReset();
  });

  it("muestra el mensaje de 'sin datos' cuando no hay llamadas", async () => {
    vi.mocked(clienteApi.GET).mockResolvedValue({
      data: {
        tarjetas: {
          tokens_entrada: 0,
          tokens_salida: 0,
          tokens_totales: 0,
          llamadas: 0,
          tokens_por_segundo_promedio: null,
          pct_timeouts: 0,
        },
        serie_diaria: [],
        ranking_caso_uso: [],
        ranking_modelo: [],
      },
      error: undefined,
      response: new Response(),
    } as never);

    render(<DashboardConsumo />);

    await waitFor(() =>
      expect(
        screen.getByText("Todavía no hay datos de consumo para estos filtros."),
      ).toBeInTheDocument(),
    );
  });

  it("muestra las tarjetas y los rankings cuando hay datos", async () => {
    vi.mocked(clienteApi.GET).mockResolvedValue({
      data: {
        tarjetas: {
          tokens_entrada: 100,
          tokens_salida: 50,
          tokens_totales: 150,
          llamadas: 3,
          tokens_por_segundo_promedio: 12.5,
          pct_timeouts: 0,
        },
        serie_diaria: [{ fecha: "2026-10-12", tokens_entrada: 100, tokens_salida: 50, llamadas: 3 }],
        ranking_caso_uso: [
          {
            caso_uso: "contable",
            tokens_totales: 150,
            duracion_llm_total_ms: 2000,
            llamadas: 3,
            duracion_media_analisis_ms: 1500,
          },
        ],
        ranking_modelo: [
          {
            modelo: "gpt-oss:20b",
            tokens_totales: 150,
            duracion_llm_total_ms: 2000,
            llamadas: 3,
            duracion_media_analisis_ms: 1500,
          },
        ],
      },
      error: undefined,
      response: new Response(),
    } as never);

    render(<DashboardConsumo />);

    await waitFor(() => expect(screen.getAllByText("150").length).toBeGreaterThan(0));
    expect(screen.getAllByText("contable").length).toBeGreaterThan(0);
    expect(screen.getAllByText("gpt-oss:20b").length).toBeGreaterThan(0);
  });

  it("muestra un error si la búsqueda falla", async () => {
    vi.mocked(clienteApi.GET).mockResolvedValue({
      data: undefined,
      error: { detail: "no autorizado" },
      response: new Response(),
    } as never);

    render(<DashboardConsumo />);

    await waitFor(() =>
      expect(screen.getByText("No se pudo cargar el consumo")).toBeInTheDocument(),
    );
  });

  it("envía los filtros de fecha y caso de uso al buscar", async () => {
    vi.mocked(clienteApi.GET).mockResolvedValue({
      data: {
        tarjetas: {
          tokens_entrada: 0,
          tokens_salida: 0,
          tokens_totales: 0,
          llamadas: 0,
          tokens_por_segundo_promedio: null,
          pct_timeouts: 0,
        },
        serie_diaria: [],
        ranking_caso_uso: [],
        ranking_modelo: [],
      },
      error: undefined,
      response: new Response(),
    } as never);

    render(<DashboardConsumo />);
    await waitFor(() => expect(clienteApi.GET).toHaveBeenCalledTimes(1));

    fireEvent.change(screen.getByPlaceholderText("p. ej. contable"), {
      target: { value: "contable" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Buscar" }));

    await waitFor(() => expect(clienteApi.GET).toHaveBeenCalledTimes(2));
    const [, opciones] = vi.mocked(clienteApi.GET).mock.calls[1];
    expect(
      (opciones as { params: { query: { caso_uso?: string } } }).params.query.caso_uso,
    ).toBe("contable");
  });
});
