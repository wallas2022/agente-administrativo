import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { clienteApi } from "../api/cliente";
import { Chat } from "./Chat";

vi.mock("../api/cliente", () => ({
  clienteApi: { GET: vi.fn(), POST: vi.fn() },
  obtenerTokenActual: () => "token-falso",
  URL_BASE_API: "http://127.0.0.1:8001",
}));

const CONVERSACION = { id: "c1", titulo: null, fecha_creacion: "2026-10-13T10:00:00Z" };

function _respuestaFetchFalsa(cuerpo: unknown, ok = true) {
  return { ok, json: () => Promise.resolve(cuerpo) };
}

describe("Chat (P-14 Bloque 3, HU-31..34)", () => {
  beforeEach(() => {
    vi.mocked(clienteApi.GET).mockReset();
    vi.mocked(clienteApi.POST).mockReset();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("muestra 'todavía no tienes conversaciones' cuando la lista está vacía", async () => {
    vi.mocked(clienteApi.GET).mockResolvedValue({
      data: [],
      error: undefined,
      response: new Response(),
    } as never);

    render(<Chat />);

    await waitFor(() =>
      expect(screen.getByText("Todavía no tienes conversaciones.")).toBeInTheDocument(),
    );
    expect(
      screen.getByText("Escribe una pregunta sobre la base de conocimiento para empezar."),
    ).toBeInTheDocument();
  });

  it("muestra la lista de conversaciones existentes", async () => {
    vi.mocked(clienteApi.GET).mockResolvedValue({
      data: [{ id: "c1", titulo: "Política de viáticos", fecha_creacion: "2026-10-13T10:00:00Z" }],
      error: undefined,
      response: new Response(),
    } as never);

    render(<Chat />);

    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Política de viáticos" })).toBeInTheDocument(),
    );
  });

  it("al enviar la primera pregunta crea una conversación y envía el mensaje", async () => {
    vi.mocked(clienteApi.GET).mockImplementation(((ruta: string) => {
      if (ruta === "/chat/conversaciones") {
        return Promise.resolve({ data: [], error: undefined, response: new Response() });
      }
      return Promise.resolve({
        data: {
          id: "c1",
          titulo: "¿Cuál es el límite de viáticos?",
          fecha_creacion: "2026-10-13T10:00:00Z",
          mensajes: [
            { id: "m1", rol: "user", contenido: "¿Cuál es el límite de viáticos?", fecha_hora: "2026-10-13T10:00:00Z" },
            {
              id: "m2",
              rol: "assistant",
              contenido: "El límite diario es Q300.",
              fecha_hora: "2026-10-13T10:01:00Z",
              fuentes_citadas: [{ fuente_id: "POL-001", version: "2026-01", seccion: "§3" }],
            },
          ],
        },
        error: undefined,
        response: new Response(),
      });
    }) as never);
    vi.mocked(clienteApi.POST).mockResolvedValue({
      data: CONVERSACION,
      error: undefined,
      response: new Response(),
    } as never);
    // Promesa controlada manualmente: deja verificar el aviso de "pensando"
    // antes de que la respuesta (real: puede tardar minutos) llegue.
    let resolverFetch: (valor: unknown) => void = () => {};
    const promesaFetch = new Promise((resolve) => {
      resolverFetch = resolve;
    });
    vi.stubGlobal("fetch", vi.fn().mockReturnValue(promesaFetch));

    render(<Chat />);
    await waitFor(() => expect(clienteApi.GET).toHaveBeenCalled());

    fireEvent.change(
      screen.getByPlaceholderText("Pregunta algo sobre la base de conocimiento…"),
      { target: { value: "¿Cuál es el límite de viáticos?" } },
    );
    fireEvent.click(screen.getByRole("button", { name: "Enviar" }));

    // Optimista: el mensaje del usuario aparece de inmediato, mientras la
    // respuesta real (controlada manualmente acá) todavía no llega.
    await waitFor(() =>
      expect(screen.getByText("¿Cuál es el límite de viáticos?")).toBeInTheDocument(),
    );
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("pensando"));
    await waitFor(() => expect(clienteApi.POST).toHaveBeenCalledWith("/chat/conversaciones"));

    resolverFetch(
      _respuestaFetchFalsa({
        id: "m2",
        rol: "assistant",
        contenido: "El límite diario es Q300.",
        fecha_hora: "2026-10-13T10:01:00Z",
        fuentes_citadas: [{ fuente_id: "POL-001", version: "2026-01", seccion: "§3" }],
      }),
    );

    await waitFor(() => expect(screen.getByText("El límite diario es Q300.")).toBeInTheDocument());
    expect(screen.getByText(/POL-001 v2026-01, §3/)).toBeInTheDocument();
  });

  it("muestra un error si el envío falla", async () => {
    vi.mocked(clienteApi.GET).mockResolvedValue({
      data: [],
      error: undefined,
      response: new Response(),
    } as never);
    vi.mocked(clienteApi.POST).mockResolvedValue({
      data: CONVERSACION,
      error: undefined,
      response: new Response(),
    } as never);
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(_respuestaFetchFalsa({ detail: "no se pudo generar" }, false)),
    );

    render(<Chat />);
    await waitFor(() => expect(clienteApi.GET).toHaveBeenCalled());

    fireEvent.change(
      screen.getByPlaceholderText("Pregunta algo sobre la base de conocimiento…"),
      { target: { value: "una pregunta" } },
    );
    fireEvent.click(screen.getByRole("button", { name: "Enviar" }));

    await waitFor(() => expect(screen.getByText("no se pudo generar")).toBeInTheDocument());
  });

  it("al hacer clic en 'Nueva conversación' limpia la conversación activa", async () => {
    vi.mocked(clienteApi.GET).mockResolvedValue({
      data: [{ id: "c1", titulo: "Anterior", fecha_creacion: "2026-10-13T10:00:00Z" }],
      error: undefined,
      response: new Response(),
    } as never);

    render(<Chat />);
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Anterior" })).toBeInTheDocument(),
    );

    fireEvent.click(screen.getByRole("button", { name: "Nueva conversación" }));

    expect(
      screen.getByText("Escribe una pregunta sobre la base de conocimiento para empezar."),
    ).toBeInTheDocument();
  });
});
