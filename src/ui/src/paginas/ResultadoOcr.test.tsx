import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Hallazgo } from "../componentes/TarjetaHallazgo";
import { ResultadoOcr } from "./ResultadoOcr";

function renderizar() {
  return render(
    <MemoryRouter>
      <ResultadoOcr analisisId="an-1" />
    </MemoryRouter>,
  );
}

const descargarArchivoMock = vi.hoisted(() => vi.fn());
vi.mock("../api/descargas", () => ({ descargarArchivo: descargarArchivoMock }));

const vivoMock = vi.hoisted(() => ({
  analisis: {
    id: "an-1",
    documento_id: "doc-1",
    nombre_documento: "escaneo.png",
    tipo_revision: "ocr",
    estado: "en_revision",
    fecha_inicio: "2026-10-08T10:00:00Z",
  },
  hallazgos: [] as Hallazgo[],
  error: null as string | null,
}));

vi.mock("../hooks/useAnalisisEnVivo", () => ({
  useAnalisisEnVivo: () => vivoMock,
}));

const subirDocumentoMock = vi.hoisted(() => vi.fn());
vi.mock("../subida/subirDocumento", () => ({ subirDocumento: subirDocumentoMock }));
vi.mock("../subida/dependenciasReales", () => ({ dependenciasReales: {} }));

function imagenBlob(): Blob {
  return new Blob(["bytes de imagen"], { type: "image/png" });
}

beforeEach(() => {
  vivoMock.analisis.estado = "en_revision";
  vivoMock.hallazgos = [];
  vivoMock.error = null;
  descargarArchivoMock.mockReset();
  subirDocumentoMock.mockReset();

  vi.stubGlobal(
    "fetch",
    vi.fn((url: string, opciones?: RequestInit) => {
      if (url.includes("/version-original")) {
        return Promise.resolve({ ok: true, blob: () => Promise.resolve(imagenBlob()) });
      }
      if (url.includes("/version-corregida")) {
        return Promise.resolve({ ok: true, text: () => Promise.resolve("Hola mllndo") });
      }
      if (url.includes("/texto-ocr") && opciones?.method === "PUT") {
        return Promise.resolve({ ok: true });
      }
      return Promise.resolve({ ok: false });
    }),
  );
  vi.stubGlobal("open", vi.fn());
  Object.assign(navigator, { clipboard: { writeText: vi.fn().mockResolvedValue(undefined) } });
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("ResultadoOcr", () => {
  it("muestra el documento y, una vez terminado, el original y el texto reconocido", async () => {
    renderizar();

    expect(await screen.findByText("escaneo.png")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText("Hola mllndo")).toBeInTheDocument());
    expect(screen.getByAltText("escaneo.png")).toBeInTheDocument();
  });

  it("muestra 'Procesando documento…' mientras el análisis sigue en curso", async () => {
    vivoMock.analisis.estado = "procesando";
    renderizar();

    expect(await screen.findByText("Procesando documento…")).toBeInTheDocument();
  });

  it("resalta la palabra dudosa que coincide con el hallazgo de OCR", async () => {
    vivoMock.hallazgos = [
      {
        id: "h-1",
        severidad: "alta",
        ubicacion: "Página 1",
        descripcion: "Palabra reconocida con confianza dudosa (50%): «mllndo»",
        estado: "pendiente",
      },
    ];
    renderizar();

    await waitFor(() => {
      const marca = screen.getByText("mllndo", { selector: "mark" });
      expect(marca).toHaveClass("resultado-ocr__dudosa--dudosa");
    });
  });

  it("muestra el aviso cuando el documento completo quedó ilegible", async () => {
    vivoMock.hallazgos = [
      {
        id: "h-1",
        severidad: "alta",
        ubicacion: "Documento completo",
        descripcion: "Las 2 página(s) procesadas por OCR son ilegibles.",
        estado: "pendiente",
      },
    ];
    renderizar();

    expect(
      await screen.findByText("Las 2 página(s) procesadas por OCR son ilegibles."),
    ).toBeInTheDocument();
  });

  it("copia el texto reconocido al portapapeles", async () => {
    renderizar();
    await screen.findByText("Hola mllndo");

    fireEvent.click(screen.getByRole("button", { name: "Copiar" }));

    await waitFor(() => expect(navigator.clipboard.writeText).toHaveBeenCalledWith("Hola mllndo"));
    expect(await screen.findByText("¡Copiado!")).toBeInTheDocument();
  });

  it("permite editar el texto y guardarlo", async () => {
    renderizar();
    await screen.findByText("Hola mllndo");

    fireEvent.click(screen.getByRole("button", { name: "Editar texto" }));
    const area = screen.getByDisplayValue("Hola mllndo");
    fireEvent.change(area, { target: { value: "Hola mundo" } });
    fireEvent.click(screen.getByRole("button", { name: "Guardar" }));

    await waitFor(() => expect(screen.getByText("Hola mundo")).toBeInTheDocument());
    const llamada = (fetch as unknown as ReturnType<typeof vi.fn>).mock.calls.find(([url]: [string]) =>
      url.includes("/texto-ocr"),
    );
    expect(llamada).toBeTruthy();
    expect(JSON.parse(llamada![1].body as string)).toEqual({ texto: "Hola mundo" });
  });

  it("los botones de descarga llaman a descargarArchivo con la ruta correcta", async () => {
    renderizar();
    await screen.findByText("Hola mllndo");

    fireEvent.click(screen.getByRole("button", { name: "Descargar .txt" }));
    expect(descargarArchivoMock).toHaveBeenCalledWith("/documentos/doc-1/version-corregida");

    fireEvent.click(screen.getByRole("button", { name: /Descargar \.docx/ }));
    expect(descargarArchivoMock).toHaveBeenCalledWith("/documentos/doc-1/ocr-docx");
  });

  it("los botones de encadenar suben el texto actual como un análisis nuevo", async () => {
    subirDocumentoMock.mockResolvedValue({ documentoId: "doc-2", analisisId: "an-2" });
    renderizar();
    await screen.findByText("Hola mllndo");

    fireEvent.click(screen.getByRole("button", { name: "Revisar ortografía" }));

    await waitFor(() => expect(subirDocumentoMock).toHaveBeenCalledTimes(1));
    const [archivo, opciones] = subirDocumentoMock.mock.calls[0];
    expect(archivo.name).toBe("ocr-resultado.txt");
    expect(opciones.tipoRevision).toBe("ortografia");
  });
});
