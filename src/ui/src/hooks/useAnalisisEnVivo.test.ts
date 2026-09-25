import { renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { clienteApi } from "../api/cliente";
import { useAnalisisEnVivo } from "./useAnalisisEnVivo";

vi.mock("../api/cliente", () => ({
  clienteApi: { GET: vi.fn() },
}));

function respuestaAnalisis(estado: string) {
  return {
    data: {
      id: "analisis-1",
      documento_id: "doc-1",
      nombre_documento: "cierre.xlsx",
      tipo_revision: "contable",
      estado,
      fecha_inicio: "2026-01-01T10:00:00Z",
      fecha_fin: estado === "con_hallazgos" ? "2026-01-01T10:01:00Z" : null,
    },
    error: undefined,
  };
}

const respuestaBitacoraVacia = { data: [], error: undefined };

// Intervalo real muy corto (no fake timers: chocan con el polling interno de
// waitFor de Testing Library) — suficiente para observar más de un ciclo.
const INTERVALO_PRUEBA_MS = 20;

describe("useAnalisisEnVivo", () => {
  afterEach(() => {
    vi.mocked(clienteApi.GET).mockReset();
  });

  it("consulta una vez y sigue consultando mientras está en proceso", async () => {
    vi.mocked(clienteApi.GET).mockImplementation((ruta: string) => {
      if (ruta === "/analisis/{analisis_id}") {
        return Promise.resolve(respuestaAnalisis("procesando")) as never;
      }
      return Promise.resolve(respuestaBitacoraVacia) as never;
    });

    renderHook(() => useAnalisisEnVivo("analisis-1", INTERVALO_PRUEBA_MS));

    await waitFor(() =>
      expect(vi.mocked(clienteApi.GET).mock.calls.length).toBeGreaterThanOrEqual(2),
    );
    // Al menos una ronda más (analisis + bitacora): confirma que sigue
    // consultando en vez de detenerse tras la primera vez.
    await waitFor(() =>
      expect(vi.mocked(clienteApi.GET).mock.calls.length).toBeGreaterThanOrEqual(4),
    );
  });

  it("deja de consultar al llegar a un estado terminal", async () => {
    vi.mocked(clienteApi.GET).mockImplementation((ruta: string) => {
      if (ruta === "/analisis/{analisis_id}") {
        return Promise.resolve(respuestaAnalisis("con_hallazgos")) as never;
      }
      return Promise.resolve(respuestaBitacoraVacia) as never;
    });

    const { result } = renderHook(() => useAnalisisEnVivo("analisis-1", INTERVALO_PRUEBA_MS));

    await waitFor(() => expect(result.current.analisis?.estado).toBe("con_hallazgos"));
    const llamadasTrasPrimeraConsulta = vi.mocked(clienteApi.GET).mock.calls.length;

    await new Promise((resolve) => setTimeout(resolve, INTERVALO_PRUEBA_MS * 5));
    expect(clienteApi.GET).toHaveBeenCalledTimes(llamadasTrasPrimeraConsulta); // no volvió a llamar
  });

  it("expone un error si la consulta falla", async () => {
    vi.mocked(clienteApi.GET).mockResolvedValue({
      data: undefined,
      error: { detail: "no encontrado" },
    } as never);

    const { result } = renderHook(() => useAnalisisEnVivo("analisis-1", INTERVALO_PRUEBA_MS));

    await waitFor(() => expect(result.current.error).not.toBeNull());
  });

  it("un error transitorio de red no detiene el sondeo (sigue reintentando)", async () => {
    // Reproduce el bug real encontrado en vivo: un rechazo sin capturar en
    // una ronda posterior de la cadena de setTimeout mataba el sondeo para
    // siempre, dejando la pantalla congelada aunque el analisis ya hubiera
    // terminado del lado del servidor.
    let intento = 0;
    vi.mocked(clienteApi.GET).mockImplementation((ruta: string) => {
      intento += 1;
      if (intento === 2) return Promise.reject(new Error("network error"));
      if (ruta === "/analisis/{analisis_id}") {
        return Promise.resolve(respuestaAnalisis("con_hallazgos")) as never;
      }
      return Promise.resolve(respuestaBitacoraVacia) as never;
    });

    const { result } = renderHook(() => useAnalisisEnVivo("analisis-1", INTERVALO_PRUEBA_MS));

    await waitFor(() => expect(result.current.analisis?.estado).toBe("con_hallazgos"), {
      timeout: 3000,
    });
  });
});
