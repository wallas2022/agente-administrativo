import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { clienteApi } from "../api/cliente";
import { BaseConocimiento } from "./BaseConocimiento";

vi.mock("../api/cliente", () => ({
  clienteApi: { GET: vi.fn(), POST: vi.fn() },
  obtenerTokenActual: () => "token-falso",
  URL_BASE_API: "http://127.0.0.1:8001",
}));
vi.mock("../auth/ContextoAuth", () => ({
  useAuth: () => ({ usuario: { rol: "curador" } }),
}));

const BASE = {
  tipo: "regla_interna",
  prioridad: 1,
  version: "1",
  vigente_desde: "2026-01-01",
  dueno: "Jefatura",
};

function fuentes(lista: object[]) {
  vi.mocked(clienteApi.GET).mockImplementation(((ruta: string) =>
    Promise.resolve({
      data: ruta === "/curaduria/fuentes" ? lista : [],
      error: undefined,
      response: new Response(),
    })) as never);
}

describe("BaseConocimiento: aprobación asíncrona (P-15, ADR-010)", () => {
  beforeEach(() => {
    vi.mocked(clienteApi.GET).mockReset();
    vi.mocked(clienteApi.POST).mockReset();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("muestra el progreso 'fragmento N de M' mientras indexa", async () => {
    fuentes([
      { ...BASE, id: "f1", fuente_id: "POL-001", titulo: "Política", estado: "indexando",
        fragmentos_total: 40, fragmentos_procesados: 12 },
    ]);

    render(<BaseConocimiento />);

    expect(await screen.findByText("indexando: fragmento 12 de 40")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Aprobar" })).not.toBeInTheDocument();
  });

  it("muestra el motivo del error y permite reintentar", async () => {
    fuentes([
      { ...BASE, id: "f2", fuente_id: "POL-002", titulo: "Otra", estado: "error_indexacion",
        motivo_error: "El servicio de embeddings tardó demasiado en responder" },
    ]);
    vi.mocked(clienteApi.POST).mockResolvedValue({
      data: { fuente_id: "POL-002", version: "1", estado: "indexando" },
      error: undefined,
      response: new Response(),
    } as never);

    render(<BaseConocimiento />);

    expect(await screen.findByRole("alert")).toHaveTextContent("tardó demasiado");
    fireEvent.click(screen.getByRole("button", { name: "Reintentar" }));
    await waitFor(() =>
      expect(clienteApi.POST).toHaveBeenCalledWith("/curaduria/fuentes/{fuente_id}/aprobar", {
        params: { path: { fuente_id: "f2" } },
      }),
    );
  });

  it("muestra el mensaje del servidor si aprobar falla (en vez de quedarse en 'Aprobando…')", async () => {
    fuentes([{ ...BASE, id: "f3", fuente_id: "POL-003", titulo: "Tercera", estado: "borrador" }]);
    vi.mocked(clienteApi.POST).mockResolvedValue({
      data: undefined,
      error: { detalle: "El archivo de la fuente no está en el almacenamiento; súbalo de nuevo" },
      response: new Response(),
    } as never);

    render(<BaseConocimiento />);
    fireEvent.click(await screen.findByRole("button", { name: "Aprobar" }));

    expect(await screen.findByText(/no está en el almacenamiento/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Aprobar" })).toBeEnabled();
  });

  it("consulta de nuevo el listado mientras haya fuentes indexando", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    fuentes([{ ...BASE, id: "f4", fuente_id: "POL-004", titulo: "Cuarta", estado: "indexando" }]);

    render(<BaseConocimiento />);
    await screen.findByText("indexando…");
    const llamadasIniciales = vi
      .mocked(clienteApi.GET)
      .mock.calls.filter(([ruta]) => ruta === "/curaduria/fuentes").length;

    await vi.advanceTimersByTimeAsync(3100);

    const llamadasFinales = vi
      .mocked(clienteApi.GET)
      .mock.calls.filter(([ruta]) => ruta === "/curaduria/fuentes").length;
    expect(llamadasFinales).toBeGreaterThan(llamadasIniciales);
  });

  describe("unicidad de fuentes (bloque 3.5)", () => {
    const DUPLICADA = {
      permitido: false,
      codigo_http: 409,
      mensaje: "Ya existe CONTIT-001 versión 1; use otro ID o suba una nueva versión",
      advertencias: [],
      es_nueva_version: false,
    };

    function escribirIdYVersion(version = "1") {
      fireEvent.change(screen.getByLabelText("fuente_id"), { target: { value: "CONTIT-001" } });
      fireEvent.change(screen.getByLabelText("Versión"), { target: { value: version } });
    }

    it("avisa al escribir un ID y una versión repetidos y bloquea el botón de subir", async () => {
      fuentes([]);
      vi.mocked(clienteApi.POST).mockResolvedValue({
        data: DUPLICADA,
        error: undefined,
        response: new Response(),
      } as never);

      render(<BaseConocimiento />);
      await screen.findByLabelText("fuente_id");
      escribirIdYVersion();

      expect(await screen.findByText(/Ya existe CONTIT-001 versión 1/)).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Subir nueva fuente" })).toBeDisabled();
      expect(clienteApi.POST).toHaveBeenCalledWith("/curaduria/fuentes/validar-alta", {
        body: expect.objectContaining({ fuente_id: "CONTIT-001", version: "1" }),
      });
    });

    it("una nueva versión se permite y muestra la advertencia de título distinto", async () => {
      fuentes([]);
      vi.mocked(clienteApi.POST).mockResolvedValue({
        data: {
          permitido: true,
          codigo_http: 200,
          mensaje: null,
          advertencias: ["El título difiere del de la versión existente («Redes»)"],
          es_nueva_version: true,
        },
        error: undefined,
        response: new Response(),
      } as never);

      render(<BaseConocimiento />);
      await screen.findByLabelText("fuente_id");
      escribirIdYVersion("2");

      expect(await screen.findByRole("status")).toHaveTextContent("El título difiere");
      expect(screen.getByRole("button", { name: "Subir nueva fuente" })).toBeEnabled();
    });

    it("no sube el archivo si, al enviar, el servidor dice que el alta está duplicada", async () => {
      fuentes([]);
      const alta = { ...DUPLICADA, permitido: true, codigo_http: 200, mensaje: null };
      vi.mocked(clienteApi.POST)
        .mockResolvedValueOnce({ data: alta, error: undefined, response: new Response() } as never)
        .mockResolvedValue({ data: DUPLICADA, error: undefined, response: new Response() } as never);
      const fetchFalso = vi.fn();
      vi.stubGlobal("fetch", fetchFalso);

      render(<BaseConocimiento />);
      await screen.findByLabelText("fuente_id");
      escribirIdYVersion();
      await waitFor(() => expect(clienteApi.POST).toHaveBeenCalledTimes(1));
      fireEvent.change(screen.getByLabelText("Archivo"), {
        target: { files: [new File(["x"], "doc.pdf", { type: "application/pdf" })] },
      });
      fireEvent.submit(screen.getByLabelText("fuente_id").closest("form") as HTMLFormElement);

      expect(await screen.findAllByText(/Ya existe CONTIT-001 versión 1/)).not.toHaveLength(0);
      expect(fetchFalso).not.toHaveBeenCalled();
      vi.unstubAllGlobals();
    });
  });
});

