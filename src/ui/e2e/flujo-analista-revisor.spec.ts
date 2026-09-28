import path from "node:path";
import { fileURLToPath } from "node:url";
import { expect, test } from "@playwright/test";
import { iniciarSesion, USUARIOS } from "./ayudantes";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// RN-02 (cuenta inexistente): se explica por plantilla, sin llamada al LLM
// (ver validadores/contable/explicacion.py) — el análisis termina en
// segundos, así que sirve para una prueba E2E rápida y repetible.
const ARCHIVO_RN02 = path.resolve(
  __dirname,
  "../../../tests/dataset/cu-01/cu01-03-cuenta-inexistente.xlsx",
);
const PERIODO_CIERRE = "2026-01";

test.describe("CU-01: flujo Analista → Revisor", () => {
  test("el Analista sube un documento, ve el hallazgo, y el Revisor puede decidir sobre él", async ({
    browser,
  }) => {
    // --- Analista: sube el documento y llega a Pantalla 3 ---
    const contextoAnalista = await browser.newContext();
    const paginaAnalista = await contextoAnalista.newPage();
    await iniciarSesion(paginaAnalista, USUARIOS.analista);

    await expect(paginaAnalista.locator(".layout__logo")).toBeVisible();

    await paginaAnalista.locator('input[type="month"]').fill(PERIODO_CIERRE);
    await paginaAnalista.locator('input[type="file"]').setInputFiles(ARCHIVO_RN02);
    await paginaAnalista.getByRole("button", { name: "Iniciar análisis" }).click();

    await paginaAnalista.waitForURL(/\/analisis\/[^/]+$/, { timeout: 15000 });

    // RN-02 no pasa por el LLM: el análisis termina en segundos, sin
    // necesitar la vista progresiva (esa se cubre en el propio hook,
    // src/ui/src/hooks/useAnalisisEnVivo.test.ts, con un documento más
    // grande que si tarda más).
    await paginaAnalista.getByRole("link", { name: "Ver hallazgos" }).click({ timeout: 60000 });
    await paginaAnalista.waitForURL(/\/analisis\/[^/]+\/hallazgos$/);

    await expect(paginaAnalista.locator(".tarjeta-hallazgo")).toHaveCount(1);
    await expect(paginaAnalista.locator(".tarjeta-hallazgo__descripcion")).toContainText(
      "no existe en el catálogo",
    );

    // RN-07 (PP-09): el Analista nunca puede decidir, ni sobre lo suyo.
    await expect(paginaAnalista.getByRole("button", { name: "Aceptar" })).toHaveCount(0);

    await contextoAnalista.close();

    // --- Revisor: encuentra el mismo análisis y decide sobre el hallazgo ---
    // El token de sesión vive solo en memoria (ContextoAuth.tsx, sin
    // localStorage/cookies por diseño), así que hay que llegar por
    // navegación del cliente -- el panel "Análisis recientes" -- y no con
    // page.goto() a la URL directa, que recarga la SPA y cierra la sesión.
    const contextoRevisor = await browser.newContext();
    const paginaRevisor = await contextoRevisor.newPage();
    await iniciarSesion(paginaRevisor, USUARIOS.revisor);

    await paginaRevisor
      .getByRole("link", { name: /cu01-03-cuenta-inexistente/ })
      .first()
      .click({ timeout: 15000 });
    await paginaRevisor.waitForURL(/\/analisis\/[^/]+\/hallazgos$/);
    await expect(paginaRevisor.locator(".tarjeta-hallazgo")).toHaveCount(1);

    const botonAceptar = paginaRevisor.getByRole("button", { name: "Aceptar" });
    await expect(botonAceptar).toBeVisible();
    await botonAceptar.click();

    await expect(paginaRevisor.getByRole("button", { name: "Deshacer" })).toBeVisible();

    await contextoRevisor.close();
  });
});
