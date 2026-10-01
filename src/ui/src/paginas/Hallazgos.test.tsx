import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Hallazgos } from "./Hallazgos";

const estadoMock = vi.hoisted(() => ({
  analisis: {
    id: "an-1",
    documento_id: "doc-1",
    nombre_documento: "memo.docx",
    tipo_revision: "redaccion",
    estado: "en_revision",
    puede_decidir: true,
    tiene_version_corregida: false,
  },
  // Antes de la fase 2: sin hallazgos. Después (segunda llamada), uno nuevo.
  hallazgosPorLlamada: [[], [{
    id: "h-1",
    severidad: "baja",
    ubicacion: "Párrafo 1",
    descripcion: "Mejora de redacción sugerida (acción: corregir).",
    correccion_sugerida: "Texto mejorado.",
    estado: "pendiente",
  }]],
  llamadaHallazgos: 0,
}));

vi.mock("../api/cliente", () => ({
  clienteApi: {
    GET: vi.fn((ruta: string) => {
      if (ruta === "/analisis/{analisis_id}") {
        return Promise.resolve({ data: estadoMock.analisis, error: undefined });
      }
      if (ruta === "/analisis/{analisis_id}/hallazgos") {
        const datos =
          estadoMock.hallazgosPorLlamada[
            Math.min(estadoMock.llamadaHallazgos, estadoMock.hallazgosPorLlamada.length - 1)
          ];
        estadoMock.llamadaHallazgos += 1;
        return Promise.resolve({ data: datos, error: undefined });
      }
      return Promise.resolve({ data: undefined, error: "ruta no mockeada" });
    }),
    POST: vi.fn(),
  },
  obtenerTokenActual: () => "token-de-prueba",
  URL_BASE_API: "http://127.0.0.1:8000",
}));

vi.mock("../api/descargas", () => ({ descargarArchivo: vi.fn() }));

function respuestaSseFalsa(cuerpo: string): Response {
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      controller.enqueue(new TextEncoder().encode(cuerpo));
      controller.close();
    },
  });
  return new Response(stream, { status: 200 });
}

function renderizar() {
  return render(
    <MemoryRouter initialEntries={["/analisis/an-1/hallazgos"]}>
      <Routes>
        <Route path="/analisis/:analisisId/hallazgos" element={<Hallazgos />} />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  estadoMock.llamadaHallazgos = 0;
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("Hallazgos — fase 2 de CU-02 (mejora de redacción)", () => {
  it("dispara GET /mejorar-stream cuando el análisis es de redacción y la fase 1 ya terminó", async () => {
    const fetchFalso = vi.fn().mockResolvedValue(
      respuestaSseFalsa('event: parrafo\ndata: {"indice": 0}\n\nevent: fin\ndata: {}\n\n'),
    );
    vi.stubGlobal("fetch", fetchFalso);

    renderizar();

    await waitFor(() => {
      expect(fetchFalso).toHaveBeenCalledWith(
        "http://127.0.0.1:8000/analisis/an-1/mejorar-stream",
        { headers: { Authorization: "Bearer token-de-prueba" } },
      );
    });

    // Tras el evento "fin", se refresca la lista y aparece el hallazgo nuevo.
    await waitFor(() => {
      expect(screen.getByText("Texto mejorado.")).toBeInTheDocument();
    });
  });

  it("no dispara el stream otra vez si el análisis no es de redacción", async () => {
    estadoMock.analisis = { ...estadoMock.analisis, tipo_revision: "ortografia" };
    const fetchFalso = vi.fn();
    vi.stubGlobal("fetch", fetchFalso);

    renderizar();

    await waitFor(() => {
      expect(screen.getByText("memo.docx")).toBeInTheDocument();
    });
    expect(fetchFalso).not.toHaveBeenCalled();

    estadoMock.analisis = { ...estadoMock.analisis, tipo_revision: "redaccion" };
  });
});
