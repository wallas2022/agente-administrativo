import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  type DependenciasSubida,
  type ParteSubida,
  calcularNumeroPartes,
  claveReanudable,
  extensionDe,
  obtenerParteBytes,
  subirDocumento,
  TAMANO_PARTE_BYTES,
} from "./subirDocumento";

function archivoDePrueba(nombre: string, tamanoBytes: number): File {
  return new File([new Uint8Array(tamanoBytes)], nombre, { lastModified: 12345 });
}

function depsFalsas(overrides: Partial<DependenciasSubida> = {}): DependenciasSubida {
  return {
    iniciarCarga: vi.fn().mockResolvedValue({
      documento_id: "doc-1",
      upload_id: "upload-1",
      llave_almacenamiento: "area/doc-1/archivo.xlsx",
    }),
    listarPartesSubidas: vi.fn().mockResolvedValue([]),
    subirParte: vi.fn(async (_doc, numeroParte, _u, _l, datos: Blob) => ({
      numeroParte,
      etag: `etag-${numeroParte}-${datos.size}`,
    })),
    completarCarga: vi.fn().mockResolvedValue({
      documento_id: "doc-1",
      analisis_id: "analisis-1",
      estado: "cargado",
    }),
    ...overrides,
  };
}

beforeEach(() => {
  localStorage.clear();
});

describe("calcularNumeroPartes", () => {
  it("un archivo pequeño es 1 sola parte", () => {
    expect(calcularNumeroPartes(1024)).toBe(1);
  });

  it("un archivo exacto a un múltiplo del tamaño de parte no agrega una parte vacía", () => {
    expect(calcularNumeroPartes(TAMANO_PARTE_BYTES * 2)).toBe(2);
  });

  it("redondea hacia arriba cuando sobra una fracción", () => {
    expect(calcularNumeroPartes(TAMANO_PARTE_BYTES * 2 + 1)).toBe(3);
  });
});

describe("obtenerParteBytes", () => {
  it("recorta cada parte al tamaño esperado, incluida la última parcial", () => {
    const archivo = archivoDePrueba("x.xlsx", TAMANO_PARTE_BYTES + 100);
    expect(obtenerParteBytes(archivo, 1).size).toBe(TAMANO_PARTE_BYTES);
    expect(obtenerParteBytes(archivo, 2).size).toBe(100);
  });
});

describe("extensionDe", () => {
  it("devuelve la extensión en minúsculas", () => {
    expect(extensionDe("Cierre-Enero.XLSX")).toBe("xlsx");
  });

  it("devuelve vacío si no hay extensión", () => {
    expect(extensionDe("archivo")).toBe("");
  });
});

describe("subirDocumento", () => {
  it("sube un archivo de una sola parte y completa la carga", async () => {
    const deps = depsFalsas();
    const archivo = archivoDePrueba("cierre.xlsx", 1024);

    const resultado = await subirDocumento(
      archivo,
      { tipoRevision: "contable", periodoCierre: "2026-01" },
      deps,
    );

    expect(resultado).toEqual({ documentoId: "doc-1", analisisId: "analisis-1" });
    expect(deps.subirParte).toHaveBeenCalledTimes(1);
    expect(deps.completarCarga).toHaveBeenCalledWith(
      "doc-1",
      "upload-1",
      "area/doc-1/archivo.xlsx",
      [{ numeroParte: 1, etag: "etag-1-1024" }],
      "contable",
      "2026-01",
    );
  });

  it("sube varias partes para un archivo grande, en orden", async () => {
    const deps = depsFalsas();
    const archivo = archivoDePrueba("grande.xlsx", TAMANO_PARTE_BYTES * 2 + 500);

    await subirDocumento(archivo, { tipoRevision: "contable", periodoCierre: "2026-01" }, deps);

    expect(deps.subirParte).toHaveBeenCalledTimes(3);
    const numerosLlamados = vi.mocked(deps.subirParte).mock.calls.map((c) => c[1]);
    expect(numerosLlamados).toEqual([1, 2, 3]);
  });

  it("reanuda una carga interrumpida sin volver a subir las partes ya confirmadas", async () => {
    const archivo = archivoDePrueba("grande.xlsx", TAMANO_PARTE_BYTES * 2);
    const clave = claveReanudable(archivo, "contable");
    localStorage.setItem(
      clave,
      JSON.stringify({
        documentoId: "doc-existente",
        uploadId: "upload-existente",
        llaveAlmacenamiento: "area/doc-existente/grande.xlsx",
      }),
    );

    const parteYaSubida: ParteSubida = { numeroParte: 1, etag: "etag-viejo-1" };
    const deps = depsFalsas({
      listarPartesSubidas: vi.fn().mockResolvedValue([parteYaSubida]),
    });

    const resultado = await subirDocumento(
      archivo,
      { tipoRevision: "contable", periodoCierre: "2026-01" },
      deps,
    );

    // No debió llamar iniciarCarga (reanuda la carga existente)...
    expect(deps.iniciarCarga).not.toHaveBeenCalled();
    // ...y solo subió la parte 2, que era la que faltaba.
    expect(deps.subirParte).toHaveBeenCalledTimes(1);
    expect(vi.mocked(deps.subirParte).mock.calls[0][1]).toBe(2);
    expect(deps.completarCarga).toHaveBeenCalledWith(
      "doc-existente",
      "upload-existente",
      "area/doc-existente/grande.xlsx",
      [parteYaSubida, { numeroParte: 2, etag: `etag-2-${TAMANO_PARTE_BYTES}` }],
      "contable",
      "2026-01",
    );
    expect(resultado.documentoId).toBe("doc-1"); // viene de completarCarga (respuesta del servidor)
  });

  it("si el servidor ya no reconoce la carga guardada, empieza una nueva", async () => {
    const archivo = archivoDePrueba("grande.xlsx", 1024);
    const clave = claveReanudable(archivo, "contable");
    localStorage.setItem(
      clave,
      JSON.stringify({
        documentoId: "doc-expirado",
        uploadId: "upload-expirado",
        llaveAlmacenamiento: "area/doc-expirado/grande.xlsx",
      }),
    );

    const deps = depsFalsas({
      listarPartesSubidas: vi.fn().mockRejectedValue(new Error("404")),
    });

    await subirDocumento(archivo, { tipoRevision: "contable", periodoCierre: "2026-01" }, deps);

    expect(deps.iniciarCarga).toHaveBeenCalledTimes(1);
    expect(deps.subirParte).toHaveBeenCalledTimes(1);
  });

  it("borra el estado reanudable tras completar la carga", async () => {
    const deps = depsFalsas();
    const archivo = archivoDePrueba("cierre.xlsx", 1024);
    const clave = claveReanudable(archivo, "contable");

    await subirDocumento(archivo, { tipoRevision: "contable", periodoCierre: "2026-01" }, deps);

    expect(localStorage.getItem(clave)).toBeNull();
  });

  it("rechaza archivos de más de 1 GB sin llamar al servidor", async () => {
    const deps = depsFalsas();
    // Sin asignar 1 GB real: subirDocumento revisa `archivo.size` antes de
    // tocar el contenido, así que alcanza con un archivo chico cuyo `.size`
    // reportado se sobreescribe para simular uno enorme.
    const archivo = archivoDePrueba("enorme.xlsx", 1024);
    Object.defineProperty(archivo, "size", { value: 1024 * 1024 * 1024 + 1 });

    await expect(
      subirDocumento(archivo, { tipoRevision: "contable", periodoCierre: "2026-01" }, deps),
    ).rejects.toThrow(/1 GB/);
    expect(deps.iniciarCarga).not.toHaveBeenCalled();
  });

  it("informa el progreso durante la subida", async () => {
    const deps = depsFalsas();
    const archivo = archivoDePrueba("cierre.xlsx", 1024);
    const eventos: number[] = [];

    await subirDocumento(
      archivo,
      {
        tipoRevision: "contable",
        periodoCierre: "2026-01",
        onProgreso: (p) => eventos.push(p.bytesSubidos),
      },
      deps,
    );

    expect(eventos.at(-1)).toBe(1024);
  });
});
