import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { clienteApi } from "../api/cliente";
import { DashboardRecursos } from "./DashboardRecursos";

vi.mock("../api/cliente", () => ({
  clienteApi: { GET: vi.fn() },
}));

describe("DashboardRecursos (HU-29)", () => {
  beforeEach(() => {
    vi.mocked(clienteApi.GET).mockReset();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("muestra un mensaje claro (sin error) cuando Prometheus no está disponible", async () => {
    vi.mocked(clienteApi.GET).mockResolvedValue({
      data: {
        prometheus_disponible: false,
        host: null,
        contenedores: null,
        ollama: null,
        alertas: [],
      },
      error: undefined,
      response: new Response(),
    } as never);

    render(<DashboardRecursos />);

    await waitFor(() =>
      expect(
        screen.getByText(
          "Las métricas de host no están disponibles (Prometheus apagado en este entorno).",
        ),
      ).toBeInTheDocument(),
    );
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("muestra las alertas activas arriba de las demás secciones", async () => {
    vi.mocked(clienteApi.GET).mockResolvedValue({
      data: {
        prometheus_disponible: true,
        host: {
          cpu_ocupado_pct: 10,
          vcpus: 4,
          memoria_usada_bytes: 1000,
          memoria_total_bytes: 2000,
          disco_usado_bytes: 900,
          disco_total_bytes: 1000,
          carga_1m: 0.5,
        },
        contenedores: [],
        ollama: { modelos_en_memoria: [], modelos_instalados: [] },
        alertas: [{ tipo: "disco", mensaje: "Disco al 90.0 % (umbral 70 %)" }],
      },
      error: undefined,
      response: new Response(),
    } as never);

    render(<DashboardRecursos />);

    await waitFor(() =>
      expect(screen.getByText("Disco al 90.0 % (umbral 70 %)")).toBeInTheDocument(),
    );
  });

  it("refresca automáticamente cada 30 segundos", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.mocked(clienteApi.GET).mockResolvedValue({
      data: {
        prometheus_disponible: false,
        host: null,
        contenedores: null,
        ollama: null,
        alertas: [],
      },
      error: undefined,
      response: new Response(),
    } as never);

    render(<DashboardRecursos />);
    await vi.waitFor(() => expect(clienteApi.GET).toHaveBeenCalledTimes(1));

    await vi.advanceTimersByTimeAsync(30_000);
    expect(clienteApi.GET).toHaveBeenCalledTimes(2);
  });
});
