import { describe, expect, it } from "vitest";
import { mensajeDeError } from "./errores";

describe("mensajeDeError", () => {
  it("usa detail (HTTPException de FastAPI)", () => {
    expect(mensajeDeError({ detail: "Archivo ausente" }, "x")).toBe("Archivo ausente");
  });

  it("usa detalle (manejador global)", () => {
    expect(mensajeDeError({ error: "error_interno", detalle: "Falló" }, "x")).toBe("Falló");
  });

  it("une los mensajes de validación 422", () => {
    expect(mensajeDeError({ detail: [{ msg: "campo requerido" }] }, "x")).toBe("campo requerido");
  });

  it("cae al mensaje por defecto si no hay cuerpo útil", () => {
    expect(mensajeDeError(null, "No se pudo")).toBe("No se pudo");
    expect(mensajeDeError({}, "No se pudo")).toBe("No se pudo");
  });
});
