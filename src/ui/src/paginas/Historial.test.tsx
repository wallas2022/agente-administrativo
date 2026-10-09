import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { clienteApi } from "../api/cliente";
import { Historial } from "./Historial";

vi.mock("../api/cliente", () => ({
  clienteApi: { GET: vi.fn() },
}));

const permisosMock = vi.hoisted(() => ({ actuales: [] as string[] }));

vi.mock("../auth/ContextoAuth", () => ({
  useAuth: () => ({
    tienePermiso: (permiso: string) => permisosMock.actuales.includes(permiso),
  }),
}));

const ITEM = {
  id: "a1",
  nombre_documento: "cierre.xlsx",
  tipo_revision: "contable",
  estado: "con_hallazgos",
  fecha_inicio: "2026-10-09T10:00:00Z",
  duracion_segundos: 125,
  usuario_nombre: "Ana Lista",
  usuario_email: "analista@local",
  area_nombre: "Contabilidad",
  numero_hallazgos: 2,
};

function renderizar() {
  return render(
    <MemoryRouter>
      <Historial />
    </MemoryRouter>,
  );
}

describe("Historial", () => {
  beforeEach(() => {
    vi.mocked(clienteApi.GET).mockReset();
    permisosMock.actuales = ["historial:propio"];
  });

  it("busca con el alcance 'propio' al montar (HU-21: alcance por defecto)", async () => {
    vi.mocked(clienteApi.GET).mockResolvedValue({
      data: { total: 1, pagina: 1, tamano_pagina: 20, resultados: [ITEM] },
      error: undefined,
      response: new Response(),
    } as never);

    renderizar();

    await waitFor(() => expect(clienteApi.GET).toHaveBeenCalled());
    const [, opciones] = vi.mocked(clienteApi.GET).mock.calls[0];
    expect((opciones as { params: { query: { alcance: string } } }).params.query.alcance).toBe(
      "propio",
    );
    expect(screen.getByText("cierre.xlsx")).toBeInTheDocument();
    expect(screen.getByText("2 min 5 s")).toBeInTheDocument();
  });

  it("no muestra selector de alcance si solo tiene un permiso de historial", async () => {
    vi.mocked(clienteApi.GET).mockResolvedValue({
      data: { total: 0, pagina: 1, tamano_pagina: 20, resultados: [] },
      error: undefined,
      response: new Response(),
    } as never);

    renderizar();
    await waitFor(() => expect(clienteApi.GET).toHaveBeenCalled());
    expect(screen.queryByRole("group", { name: "Alcance" })).not.toBeInTheDocument();
  });

  it("muestra el selector y cambia de alcance al hacer clic (HU-21)", async () => {
    permisosMock.actuales = ["historial:propio", "historial:area"];
    vi.mocked(clienteApi.GET).mockResolvedValue({
      data: { total: 0, pagina: 1, tamano_pagina: 20, resultados: [] },
      error: undefined,
      response: new Response(),
    } as never);

    renderizar();
    await waitFor(() => expect(clienteApi.GET).toHaveBeenCalledTimes(1));

    screen.getByText("Mi área").click();

    await waitFor(() => expect(clienteApi.GET).toHaveBeenCalledTimes(2));
    const [, opciones] = vi.mocked(clienteApi.GET).mock.calls[1];
    expect((opciones as { params: { query: { alcance: string } } }).params.query.alcance).toBe(
      "area",
    );
  });

  it("muestra un mensaje si no hay resultados", async () => {
    vi.mocked(clienteApi.GET).mockResolvedValue({
      data: { total: 0, pagina: 1, tamano_pagina: 20, resultados: [] },
      error: undefined,
      response: new Response(),
    } as never);

    renderizar();
    await waitFor(() =>
      expect(screen.getByText("No hay análisis con esos filtros.")).toBeInTheDocument(),
    );
  });

  it("muestra un error si la búsqueda falla", async () => {
    vi.mocked(clienteApi.GET).mockResolvedValue({
      data: undefined,
      error: { detail: "no autorizado" },
      response: new Response(),
    } as never);

    renderizar();
    await waitFor(() =>
      expect(screen.getByText("No se pudo cargar el historial")).toBeInTheDocument(),
    );
  });

  it("deshabilita 'Anterior' en la primera página y 'Siguiente' en la última", async () => {
    vi.mocked(clienteApi.GET).mockResolvedValue({
      data: { total: 1, pagina: 1, tamano_pagina: 20, resultados: [ITEM] },
      error: undefined,
      response: new Response(),
    } as never);

    renderizar();
    await waitFor(() => expect(screen.getByText("cierre.xlsx")).toBeInTheDocument());

    expect(screen.getByRole("button", { name: "Anterior" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Siguiente" })).toBeDisabled();
  });

  it("el documento enlaza al resultado del análisis", async () => {
    vi.mocked(clienteApi.GET).mockResolvedValue({
      data: { total: 1, pagina: 1, tamano_pagina: 20, resultados: [ITEM] },
      error: undefined,
      response: new Response(),
    } as never);

    renderizar();
    const enlace = await screen.findByRole("link", { name: "cierre.xlsx" });
    expect(enlace).toHaveAttribute("href", "/analisis/a1/hallazgos");
  });
});
