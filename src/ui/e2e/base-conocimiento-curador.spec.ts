import path from "node:path";
import { fileURLToPath } from "node:url";
import { expect, test } from "@playwright/test";
import { iniciarSesion, USUARIOS } from "./ayudantes";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// Bloque K5 (RF-16, RF-17, CU-08): mismo archivo real que usan las pruebas
// de API (tests/unit/test_curaduria_api.py) -- un PDF con texto extraíble,
// para no depender de OCR (iteración 2, fuera de alcance).
const ARCHIVO_FUENTE = path.resolve(
  __dirname,
  "../../../kb/plantillas/ejemplos/POL-001_Politica_Cierre_EJEMPLO.pdf",
);

function fuenteIdUnico(): string {
  // Cada corrida necesita un fuente_id nuevo -- el backend no permite
  // reutilizar uno ya cargado por otra corrida previa del mismo entorno.
  return `E2E-${Date.now()}`;
}

test.describe("CU-08: pantalla del curador (Base de conocimiento)", () => {
  test("el Curador sube una fuente, la aprueba, la marca obsoleta y gestiona el glosario", async ({
    page,
  }) => {
    const fuenteId = fuenteIdUnico();

    await iniciarSesion(page, USUARIOS.curador);
    await page.getByRole("link", { name: "Base de conocimiento" }).click();
    await page.waitForURL("/base-de-conocimiento");

    // --- subir nueva fuente ------------------------------------------------
    await page.getByLabel("fuente_id").fill(fuenteId);
    await page.getByLabel("Título").fill("Política de cierre E2E");
    await page.getByLabel("Tipo").fill("regla_interna");
    await page.getByLabel("Versión").fill("v2026-01");
    await page.getByLabel("Vigente desde").fill("2026-01-01");
    await page.getByLabel("Dueño").fill("Contabilidad");
    await page.getByLabel("Archivo").setInputFiles(ARCHIVO_FUENTE);
    await page.getByRole("button", { name: "Subir nueva fuente" }).click();

    const fila = page.locator("tr", { hasText: fuenteId });
    await expect(fila).toBeVisible({ timeout: 15000 });
    await expect(fila.locator(".base-conocimiento__estado")).toHaveText("borrador");

    // --- vista previa de fragmentos extraídos -------------------------------
    await fila.getByRole("button", { name: "Vista previa" }).click();
    await expect(page.locator(`text=Vista previa — ${fuenteId}`)).toBeVisible();
    await expect(page.locator(".base-conocimiento__fragmento").first()).toBeVisible();
    await page.getByRole("button", { name: "Cerrar" }).click();

    // --- aprobar como vigente (RF-16: única versión vigente por fuente_id) --
    await fila.getByRole("button", { name: "Aprobar" }).click();
    await expect(fila.locator(".base-conocimiento__estado")).toHaveText("vigente", {
      timeout: 15000,
    });

    // --- marcar obsoleta -----------------------------------------------------
    await fila.getByRole("button", { name: "Marcar obsoleta" }).click();
    await expect(fila.locator(".base-conocimiento__estado")).toHaveText("obsoleta", {
      timeout: 15000,
    });

    // --- glosario: agregar y eliminar un término ----------------------------
    const termino = `termino-e2e-${Date.now()}`;
    await page.getByLabel("Término").fill(termino);
    await page.getByLabel("Definición").fill("Definición de prueba E2E");
    await page.getByRole("button", { name: "Agregar término" }).click();

    const filaGlosario = page.locator("li", { hasText: termino });
    await expect(filaGlosario).toBeVisible({ timeout: 15000 });

    await filaGlosario.getByRole("button", { name: "Eliminar" }).click();
    await expect(filaGlosario).toHaveCount(0);
  });

  test("el Administrador solo puede leer (sin formularios de escritura)", async ({ page }) => {
    await iniciarSesion(page, USUARIOS.administrador);
    await page.getByRole("link", { name: "Base de conocimiento" }).click();
    await page.waitForURL("/base-de-conocimiento");

    await expect(page.getByLabel("fuente_id")).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Subir nueva fuente" })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Agregar término" })).toHaveCount(0);
  });
});
