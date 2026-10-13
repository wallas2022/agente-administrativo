import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { clienteApi } from "../api/cliente";
import { DashboardConfiguracion } from "./DashboardConfiguracion";

vi.mock("../api/cliente", () => ({
  clienteApi: { GET: vi.fn() },
}));

describe("DashboardConfiguracion (HU-30)", () => {
  beforeEach(() => {
    vi.mocked(clienteApi.GET).mockReset();
  });

  it("muestra las variables de la lista blanca y la versión", async () => {
    vi.mocked(clienteApi.GET).mockResolvedValue({
      data: {
        variables: { LLM_PROVIDER: "ollama", APP_ENV: "local" },
        app_version: "0.2.0",
        git_commit: "a7fcbf1",
      },
      error: undefined,
      response: new Response(),
    } as never);

    render(<DashboardConfiguracion />);

    await waitFor(() => expect(screen.getByText("ollama")).toBeInTheDocument());
    expect(screen.getByText("LLM_PROVIDER")).toBeInTheDocument();
    expect(screen.getByText("0.2.0")).toBeInTheDocument();
    expect(screen.getByText("a7fcbf1")).toBeInTheDocument();
  });

  it("nunca muestra una variable cuyo nombre sugiera un secreto", async () => {
    vi.mocked(clienteApi.GET).mockResolvedValue({
      data: {
        variables: { LLM_PROVIDER: "ollama" },
        app_version: "sin-confirmar",
        git_commit: "sin-confirmar",
      },
      error: undefined,
      response: new Response(),
    } as never);

    render(<DashboardConfiguracion />);

    await waitFor(() => expect(screen.getByText("LLM_PROVIDER")).toBeInTheDocument());
    expect(screen.queryByText(/PASSWORD|SECRET|KEY|TOKEN/i)).not.toBeInTheDocument();
  });

  it("muestra un error si la carga falla", async () => {
    vi.mocked(clienteApi.GET).mockResolvedValue({
      data: undefined,
      error: { detail: "no autorizado" },
      response: new Response(),
    } as never);

    render(<DashboardConfiguracion />);

    await waitFor(() =>
      expect(screen.getByText("No se pudo cargar la configuración")).toBeInTheDocument(),
    );
  });
});
