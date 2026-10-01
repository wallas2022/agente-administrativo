import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ResultadoRedaccion } from "./ResultadoRedaccion";

const estadoMock = vi.hoisted(() => ({
  analisis: {
    id: "an-1",
    nombre_documento: "memo.docx",
    estado: "en_revision",
    puede_decidir: true,
  },
  hallazgos: [] as unknown[],
}));

const postMock = vi.hoisted(() => vi.fn());

vi.mock("../api/cliente", () => ({
  clienteApi: {
    GET: vi.fn((ruta: string) => {
      if (ruta === "/analisis/{analisis_id}") {
        return Promise.resolve({ data: estadoMock.analisis, error: undefined });
      }
      if (ruta === "/analisis/{analisis_id}/hallazgos") {
        return Promise.resolve({ data: estadoMock.hallazgos, error: undefined });
      }
      return Promise.resolve({ data: undefined, error: "ruta no mockeada" });
    }),
    POST: postMock,
  },
  obtenerTokenActual: () => "token-de-prueba",
  URL_BASE_API: "http://127.0.0.1:8000",
}));

function respuestaSseFalsa(cuerpo: string): Response {
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      controller.enqueue(new TextEncoder().encode(cuerpo));
      controller.close();
    },
  });
  return new Response(stream, { status: 200 });
}

function evento(nombre: string, datos: object): string {
  return `event: ${nombre}\ndata: ${JSON.stringify(datos)}\n\n`;
}

beforeEach(() => {
  estadoMock.hallazgos = [];
  postMock.mockReset();
  postMock.mockResolvedValue({ error: undefined });
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("ResultadoRedaccion (protocolo SSE escalonado)", () => {
  it("muestra el original y las opciones aprobadas conforme van llegando, con la primera elegida por defecto", async () => {
    const cuerpo =
      evento("inicio", { total_parrafos: 1 }) +
      evento("parrafo_inicio", { indice: 0, ubicacion: "Párrafo 1" }) +
      evento("opcion", {
        indice: 0,
        ubicacion: "Párrafo 1",
        hallazgo_id: "h-1",
        estilo: "Formal",
        texto: "Hola, este es un párrafo formal.",
        motivos: ["tono institucional"],
        aprobada_guardia: true,
        razon_descarte: null,
      }) +
      evento("opcion", {
        indice: 0,
        ubicacion: "Párrafo 1",
        hallazgo_id: "h-1",
        estilo: "Breve",
        texto: "Párrafo breve.",
        motivos: [],
        aprobada_guardia: true,
        razon_descarte: null,
      }) +
      evento("parrafo_fin", {
        indice: 0,
        ubicacion: "Párrafo 1",
        hallazgo_id: "h-1",
        parrafo_original: "hola, este es un parrafo.",
        parrafo_base: "hola, este es un parrafo.",
        fuente_citada: null,
        omitido: false,
        tiene_opciones_aprobadas: true,
      }) +
      "event: fin\ndata: {}\n\n";
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(respuestaSseFalsa(cuerpo)));

    render(<ResultadoRedaccion analisisId="an-1" />);

    await waitFor(() => {
      expect(screen.getAllByText(/Hola, este es un párrafo formal\./).length).toBeGreaterThan(0);
    });
    expect(screen.getByText(/Párrafo breve\./)).toBeInTheDocument();
    expect(screen.getByText("tono institucional")).toBeInTheDocument();

    const radios = screen.getAllByRole("radio") as HTMLInputElement[];
    const elegido = radios.find((r) => r.checked);
    expect(elegido).toBeDefined();
    expect(elegido?.disabled).toBe(false);
  });

  it("no ofrece una opción descartada por la guardia como elegible", async () => {
    const cuerpo =
      evento("inicio", { total_parrafos: 1 }) +
      evento("parrafo_inicio", { indice: 0, ubicacion: "Párrafo 1" }) +
      evento("opcion", {
        indice: 0,
        ubicacion: "Párrafo 1",
        hallazgo_id: "h-1",
        estilo: "Formal",
        texto: "El gasto fue de Q 200.00.",
        motivos: [],
        aprobada_guardia: false,
        razon_descarte: "cambió un monto",
      }) +
      evento("parrafo_fin", {
        indice: 0,
        ubicacion: "Párrafo 1",
        hallazgo_id: "h-1",
        parrafo_original: "el gasto fue de Q 100.00.",
        parrafo_base: "el gasto fue de Q 100.00.",
        fuente_citada: null,
        omitido: false,
        tiene_opciones_aprobadas: false,
      }) +
      "event: fin\ndata: {}\n\n";
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(respuestaSseFalsa(cuerpo)));

    render(<ResultadoRedaccion analisisId="an-1" />);

    await waitFor(() => {
      expect(screen.getByText(/cambió un monto/)).toBeInTheDocument();
    });
    const radios = screen.getAllByRole("radio") as HTMLInputElement[];
    const radioDescartada = radios.find((r) => r.disabled);
    expect(radioDescartada).toBeDefined();
    const elegido = radios.find((r) => r.checked);
    expect(elegido?.disabled).toBe(false); // se eligió "Sin cambio", no la descartada
  });

  it("un párrafo omitido (Bloque 4) se muestra sin opciones, sin llamar más al LLM", async () => {
    const cuerpo =
      evento("inicio", { total_parrafos: 1 }) +
      evento("parrafo_inicio", { indice: 0, ubicacion: "Párrafo 1" }) +
      evento("parrafo_fin", {
        indice: 0,
        ubicacion: "Párrafo 1",
        hallazgo_id: null,
        parrafo_original: "Todo quedó en orden.",
        parrafo_base: "Todo quedó en orden.",
        fuente_citada: null,
        omitido: true,
        tiene_opciones_aprobadas: false,
      }) +
      "event: fin\ndata: {}\n\n";
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(respuestaSseFalsa(cuerpo)));

    render(<ResultadoRedaccion analisisId="an-1" />);

    await waitFor(() => {
      expect(screen.getByText(/Sin cambios \(párrafo corto, sin hallazgos\)/)).toBeInTheDocument();
    });
    expect(screen.queryAllByRole("radio")).toHaveLength(0);
  });

  it("el botón 'Copiar' arma el texto final a partir de la opción elegida por defecto", async () => {
    const cuerpo =
      evento("inicio", { total_parrafos: 1 }) +
      evento("parrafo_inicio", { indice: 0, ubicacion: "Párrafo 1" }) +
      evento("opcion", {
        indice: 0,
        ubicacion: "Párrafo 1",
        hallazgo_id: "h-1",
        estilo: "Formal",
        texto: "Texto final formal.",
        motivos: [],
        aprobada_guardia: true,
        razon_descarte: null,
      }) +
      evento("parrafo_fin", {
        indice: 0,
        ubicacion: "Párrafo 1",
        hallazgo_id: "h-1",
        parrafo_original: "texto original.",
        parrafo_base: "texto original.",
        fuente_citada: null,
        omitido: false,
        tiene_opciones_aprobadas: true,
      }) +
      "event: fin\ndata: {}\n\n";
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(respuestaSseFalsa(cuerpo)));
    const escribirPortapapeles = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, { clipboard: { writeText: escribirPortapapeles } });

    render(<ResultadoRedaccion analisisId="an-1" />);

    await waitFor(() => {
      expect(screen.getByText("Texto final")).toBeInTheDocument();
    });
    screen.getByText("Copiar").click();

    await waitFor(() => {
      expect(escribirPortapapeles).toHaveBeenCalledWith("Texto final formal.");
    });
  });

  it("muestra 'generando…' para un párrafo que todavía no llegó a parrafo_fin", async () => {
    const cuerpo =
      evento("inicio", { total_parrafos: 2 }) +
      evento("parrafo_inicio", { indice: 0, ubicacion: "Párrafo 1" }) +
      "event: fin\ndata: {}\n\n"; // el stream se corta antes de parrafo_fin (simula lentitud)
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(respuestaSseFalsa(cuerpo)));

    render(<ResultadoRedaccion analisisId="an-1" />);

    await waitFor(() => {
      expect(screen.getByText("Generando…")).toBeInTheDocument();
    });
  });
});
