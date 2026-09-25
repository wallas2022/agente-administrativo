import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useTiempoTranscurrido } from "./useTiempoTranscurrido";

describe("useTiempoTranscurrido", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-01-01T10:00:00Z"));
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("devuelve — sin fecha de inicio", () => {
    const { result } = renderHook(() => useTiempoTranscurrido(undefined, null));
    expect(result.current).toBe("—");
  });

  it("calcula el tiempo transcurrido desde el inicio hasta ahora", () => {
    const { result } = renderHook(() =>
      useTiempoTranscurrido("2026-01-01T09:58:30Z", null),
    );
    expect(result.current).toBe("1m 30s");
  });

  it("se congela en la fecha de fin cuando el análisis ya terminó", () => {
    const { result } = renderHook(() =>
      useTiempoTranscurrido("2026-01-01T09:58:00Z", "2026-01-01T09:59:05Z"),
    );
    expect(result.current).toBe("1m 05s");
  });

  it("sigue avanzando cada segundo mientras no hay fecha de fin", () => {
    const { result } = renderHook(() =>
      useTiempoTranscurrido("2026-01-01T10:00:00Z", null),
    );
    expect(result.current).toBe("0m 00s");

    act(() => {
      vi.advanceTimersByTime(5000);
    });
    expect(result.current).toBe("0m 05s");
  });
});
