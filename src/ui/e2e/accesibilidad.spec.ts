import path from "node:path";
import { fileURLToPath } from "node:url";
import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import { iniciarSesion, USUARIOS } from "./ayudantes";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ARCHIVO_RN02 = path.resolve(
  __dirname,
  "../../../tests/dataset/cu-01/cu01-03-cuenta-inexistente.xlsx",
);

// Bloque U5: auditoría de accesibilidad AA con axe-core sobre las pantallas
// reales (no una copia aislada) — solo se excluyen las reglas de "color de
// marca" (best-practice, no forman parte del criterio WCAG AA) si llegaran a
// dispararse por los colores del logo, que no se pueden ajustar.
const ESTANDARES = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"];

test.describe("Accesibilidad AA (axe-core)", () => {
  test("Pantalla de login", async ({ page }) => {
    await page.goto("/login");
    const resultados = await new AxeBuilder({ page }).withTags(ESTANDARES).analyze();
    expect(resultados.violations, JSON.stringify(resultados.violations, null, 2)).toEqual([]);
  });

  test("Pantalla 1 · Nuevo análisis", async ({ page }) => {
    await iniciarSesion(page, USUARIOS.analista);
    const resultados = await new AxeBuilder({ page }).withTags(ESTANDARES).analyze();
    expect(resultados.violations, JSON.stringify(resultados.violations, null, 2)).toEqual([]);
  });

  test("Pantalla 2 · Agente trabajando y Pantalla 3 · Hallazgos", async ({ page }) => {
    await iniciarSesion(page, USUARIOS.analista);
    await page.locator('input[type="month"]').fill("2026-01");
    await page.locator('input[type="file"]').setInputFiles(ARCHIVO_RN02);
    await page.getByRole("button", { name: "Iniciar análisis" }).click();
    await page.waitForURL(/\/analisis\/[^/]+$/, { timeout: 15000 });

    const resultadosPantalla2 = await new AxeBuilder({ page }).withTags(ESTANDARES).analyze();
    expect(
      resultadosPantalla2.violations,
      JSON.stringify(resultadosPantalla2.violations, null, 2),
    ).toEqual([]);

    await page.getByRole("link", { name: "Ver hallazgos" }).click({ timeout: 60000 });
    await page.waitForURL(/\/analisis\/[^/]+\/hallazgos$/);

    const resultadosPantalla3 = await new AxeBuilder({ page }).withTags(ESTANDARES).analyze();
    expect(
      resultadosPantalla3.violations,
      JSON.stringify(resultadosPantalla3.violations, null, 2),
    ).toEqual([]);
  });
});
