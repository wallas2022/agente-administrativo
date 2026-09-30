import path from "node:path";
import { fileURLToPath } from "node:url";
import { expect, test } from "@playwright/test";
import { iniciarSesion, USUARIOS } from "./ayudantes";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// SRS v0.9 (RNF-02, RG-06): el Administrador tiene rol Revisor/Administrador
// (puede decidir) Y puede cargar documentos (RolUsuario.ADMINISTRADOR está
// permitido en /documentos/iniciar) -- el único rol de prueba con el que se
// puede ejercitar la autoaprobación real de punta a punta en la UI, ya que
// el Revisor no tiene permiso de carga.
const ARCHIVO_RN02 = path.resolve(
  __dirname,
  "../../../tests/dataset/cu-01/cu01-03-cuenta-inexistente.xlsx",
);
const PERIODO_CIERRE = "2026-01";

test.describe("SRS v0.9: autoaprobación configurable (RN-07, PP-09)", () => {
  test("el Administrador decide sobre su propio hallazgo y queda en el reporte de ajustes autoaprobados", async ({
    page,
  }) => {
    await iniciarSesion(page, USUARIOS.administrador);

    await page.locator('input[type="month"]').fill(PERIODO_CIERRE);
    await page.locator('input[type="file"]').setInputFiles(ARCHIVO_RN02);
    await page.getByRole("button", { name: "Iniciar análisis" }).click();
    await page.waitForURL(/\/analisis\/[^/]+$/, { timeout: 15000 });

    await page.getByRole("link", { name: "Ver hallazgos" }).click({ timeout: 60000 });
    await page.waitForURL(/\/analisis\/[^/]+\/hallazgos$/);

    // A diferencia de flujo-analista-revisor.spec.ts (Analista, bloqueado
    // por rol), aquí el mismo Administrador que cargó SÍ ve "Aceptar" --
    // por defecto SEGREGACION_APROBACION=false (autoaprobación permitida).
    const botonAceptar = page.getByRole("button", { name: "Aceptar", exact: true });
    await expect(botonAceptar).toBeVisible();
    await botonAceptar.click();
    await expect(page.getByRole("button", { name: "Deshacer" })).toBeVisible();

    // El ajuste autoaprobado debe quedar visible en el reporte (RG-06,
    // PP-09: "0 aprobaciones sin registro").
    await page.getByRole("link", { name: "Ajustes autoaprobados" }).click();
    await page.waitForURL("/ajustes-autoaprobados");
    await page.getByRole("button", { name: "Buscar" }).click();

    // .first(): cada corrida de esta prueba crea su propia fuente/hallazgo
    // y los deja acumulados en la base real -- el backend ordena por
    // fecha_hora descendente, así que la fila de ESTA corrida es la primera.
    const filaDelAjuste = page.locator("tbody tr", { hasText: "administrador@local" }).first();
    await expect(filaDelAjuste).toBeVisible({ timeout: 10000 });
    await expect(filaDelAjuste).toContainText("no existe en el catálogo");
    await expect(filaDelAjuste).toContainText("aceptado");
  });
});
