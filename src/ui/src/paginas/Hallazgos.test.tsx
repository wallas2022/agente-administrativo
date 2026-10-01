import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { Hallazgos } from "./Hallazgos";

const estadoMock = vi.hoisted(() => ({
  analisis: {
    id: "an-1",
    documento_id: "doc-1",
    nombre_documento: "memo.docx",
    tipo_revision: "ortografia",
    estado: "con_hallazgos",
    puede_decidir: true,
    tiene_version_corregida: false,
  },
  hallazgos: [] as unknown[],
}));

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
    POST: vi.fn(),
  },
  obtenerTokenActual: () => null,
  URL_BASE_API: "http://127.0.0.1:8000",
}));

vi.mock("../api/descargas", () => ({ descargarArchivo: vi.fn() }));

vi.mock("./ResultadoRedaccion", () => ({
  ResultadoRedaccion: ({ analisisId }: { analisisId: string }) => (
    <div>pantalla de resultado de redacción para {analisisId}</div>
  ),
}));

function renderizar() {
  return render(
    <MemoryRouter initialEntries={["/analisis/an-1/hallazgos"]}>
      <Routes>
        <Route path="/analisis/:analisisId/hallazgos" element={<Hallazgos />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("Hallazgos", () => {
  it("muestra la lista genérica de hallazgos para un análisis que no es de redacción", async () => {
    estadoMock.analisis = { ...estadoMock.analisis, tipo_revision: "ortografia" };
    estadoMock.hallazgos = [];
    renderizar();

    await waitFor(() => {
      expect(screen.getByText("Este análisis no tiene hallazgos.")).toBeInTheDocument();
    });
    expect(screen.queryByText(/pantalla de resultado de redacción/)).not.toBeInTheDocument();
  });

  it("delega en ResultadoRedaccion cuando el análisis es de redacción", async () => {
    estadoMock.analisis = { ...estadoMock.analisis, tipo_revision: "redaccion" };
    estadoMock.hallazgos = [];
    renderizar();

    await waitFor(() => {
      expect(screen.getByText("pantalla de resultado de redacción para an-1")).toBeInTheDocument();
    });
  });
});
