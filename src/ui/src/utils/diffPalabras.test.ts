import { describe, expect, it } from "vitest";
import { resaltarDiferencias } from "./diffPalabras";

function textoDe(segmentos: ReturnType<typeof resaltarDiferencias>): string {
  return segmentos.map((s) => s.texto).join("");
}

describe("resaltarDiferencias", () => {
  it("no marca nada cuando los textos son iguales", () => {
    const resultado = resaltarDiferencias("hola mundo", "hola mundo");
    expect(resultado.every((s) => !s.cambiado)).toBe(true);
    expect(textoDe(resultado)).toBe("hola mundo");
  });

  it("marca solo la palabra que cambió", () => {
    const resultado = resaltarDiferencias(
      "el pago fue aprobado por la DAF",
      "el pago fue aprobado por la Gerencia",
    );
    const cambiadas = resultado.filter((s) => s.cambiado).map((s) => s.texto);
    expect(cambiadas).toEqual(["Gerencia"]);
    expect(textoDe(resultado)).toBe("el pago fue aprobado por la Gerencia");
  });

  it("marca una palabra agregada al final", () => {
    const resultado = resaltarDiferencias("el pago fue aprobado", "el pago fue aprobado ayer");
    const cambiadas = resultado
      .filter((s) => s.cambiado)
      .map((s) => s.texto)
      .join("");
    expect(cambiadas.trim()).toBe("ayer");
  });

  it("el texto reconstruido siempre es el actualizado completo", () => {
    const original = "hola, este es un parrafo de prueba.";
    const actualizado = "Hola, este es un párrafo de prueba corregido.";
    const resultado = resaltarDiferencias(original, actualizado);
    expect(textoDe(resultado)).toBe(actualizado);
  });
});
