import { afterEach, describe, expect, it, vi } from "vitest";
import { descargarArchivo } from "./descargas";

describe("descargarArchivo", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("dispara la descarga con el nombre de archivo del header content-disposition", async () => {
    const contenido = new Blob(["contenido de prueba"]);
    const respuestaFalsa = {
      ok: true,
      headers: new Headers({ "content-disposition": 'attachment; filename="cierre.marcado.xlsx"' }),
      blob: () => Promise.resolve(contenido),
    };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(respuestaFalsa));

    const clicSimulado = vi.fn();
    const enlaceFalso = {
      href: "",
      download: "",
      click: clicSimulado,
      remove: vi.fn(),
    } as unknown as HTMLAnchorElement;
    vi.spyOn(document, "createElement").mockReturnValue(enlaceFalso);
    vi.spyOn(document.body, "appendChild").mockImplementation((n) => n);
    vi.stubGlobal("URL", {
      ...URL,
      createObjectURL: vi.fn().mockReturnValue("blob:falso"),
      revokeObjectURL: vi.fn(),
    });

    await descargarArchivo("/documentos/doc-1/version-corregida");

    expect(enlaceFalso.download).toBe("cierre.marcado.xlsx");
    expect(clicSimulado).toHaveBeenCalledOnce();
  });

  it("lanza un error si la respuesta no es exitosa", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false }));

    await expect(descargarArchivo("/documentos/doc-1/version-corregida")).rejects.toThrow();
  });
});
