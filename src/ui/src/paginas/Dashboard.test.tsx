import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { clienteApi } from "../api/cliente";
import { Dashboard } from "./Dashboard";

vi.mock("../api/cliente", () => ({
  clienteApi: { GET: vi.fn() },
}));

const RESPUESTA_VACIA_POR_RUTA: Record<string, unknown> = {
  "/admin/dashboard/consumo": {
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
  "/admin/dashboard/usuarios": [],
  "/admin/dashboard/recursos": {
    prometheus_disponible: false,
    host: null,
    contenedores: null,
    ollama: null,
    alertas: [],
  },
  "/admin/dashboard/configuracion": {
    variables: {},
    app_version: "sin-confirmar",
    git_commit: "sin-confirmar",
  },
};

describe("Dashboard (P-13 Bloque 4)", () => {
  beforeEach(() => {
    vi.mocked(clienteApi.GET).mockReset();
    vi.mocked(clienteApi.GET).mockImplementation(
      ((ruta: string) =>
        Promise.resolve({
          data: RESPUESTA_VACIA_POR_RUTA[ruta],
          error: undefined,
          response: new Response(),
        })) as never,
    );
  });

  it("muestra las 4 pestañas", () => {
    render(<Dashboard />);
    expect(screen.getByRole("tab", { name: "Consumo" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Usuarios" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Recursos" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Configuración" })).toBeInTheDocument();
  });

  it("la pestaña Consumo está activa por defecto", async () => {
    render(<Dashboard />);
    expect(screen.getByRole("tab", { name: "Consumo" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    await waitFor(() =>
      expect(clienteApi.GET).toHaveBeenCalledWith(
        "/admin/dashboard/consumo",
        expect.anything(),
      ),
    );
  });

  it("cambiar de pestaña activa la elegida y consulta su endpoint", async () => {
    render(<Dashboard />);
    await waitFor(() => expect(clienteApi.GET).toHaveBeenCalled());

    screen.getByRole("tab", { name: "Configuración" }).click();

    await waitFor(() =>
      expect(screen.getByRole("tab", { name: "Configuración" })).toHaveAttribute(
        "aria-selected",
        "true",
      ),
    );
    expect(screen.getByRole("tab", { name: "Consumo" })).toHaveAttribute(
      "aria-selected",
      "false",
    );
    await waitFor(() =>
      expect(clienteApi.GET).toHaveBeenCalledWith("/admin/dashboard/configuracion"),
    );
  });
});
