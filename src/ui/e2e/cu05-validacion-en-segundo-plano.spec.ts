import { expect, test } from "@playwright/test";
import { iniciarSesion, USUARIOS } from "./ayudantes";

// RNF-04 (Bloque O6, punto 1): un caso "dudoso" para LanguageTool ("de" vs
// "dé", DIACRITICS) que el análisis debe publicar de inmediato como "En
// validación", sin esperar al LLM -- confirmado contra el LanguageTool real
// antes de escribir esta prueba (categoría DIACRITICS, regla DE_TILDE).
const TEXTO_CON_CASO_DUDOSO =
  "Es necesario que se de seguimiento al hallazgo pendiente antes del cierre.";

// El LLM real (gpt-oss:20b sin GPU) puede tardar varios minutos en la única
// llamada por lote de la fase 2 (ver docs/04-pruebas/resultados/local-S2.md)
// -- este timeout cubre ese caso real, no uno simulado.
test.setTimeout(6 * 60 * 1000);

test.describe("CU-05: validación de casos dudosos en segundo plano (RNF-04, Bloque O6)", () => {
  test("el hallazgo dudoso se publica como 'En validación' y luego pasa a 'Confirmado' o 'Descartado' sin recargar", async ({
    page,
  }) => {
    await iniciarSesion(page, USUARIOS.analista);

    await page.getByRole("radio", { name: "Revisión ortográfica" }).check();
    await page.getByRole("radio", { name: "Pegar texto directamente" }).check();
    await page.getByLabel("Texto a revisar").fill(TEXTO_CON_CASO_DUDOSO);
    await page.getByRole("button", { name: "Iniciar análisis" }).click();

    await page.waitForURL(/\/analisis\/[^/]+$/, { timeout: 15000 });
    // Fase 1 (RNF-04): solo LanguageTool -- termina en segundos, sin esperar
    // al LLM, así que "Ver hallazgos" aparece rápido.
    await page.getByRole("link", { name: "Ver hallazgos" }).click({ timeout: 30000 });
    await page.waitForURL(/\/analisis\/[^/]+\/hallazgos$/);

    // "de" (DE_TILDE) es un texto de una sola palabra muy común -- se busca
    // por el <s>de</s> exacto tachado en la tarjeta, no por substring de
    // toda la tarjeta (que también coincidiría con "falta de tilde" en la
    // explicación del propio LanguageTool/LLM).
    const tarjeta = page
      .locator(".tarjeta-hallazgo")
      .filter({ has: page.locator("s", { hasText: /^de$/ }) });
    await expect(tarjeta).toBeVisible();

    // Recién llegado: el caso dudoso está "En validación" -- el LLM todavía
    // no lo resolvió -- y no hay botones Aceptar/Rechazar para él.
    await expect(tarjeta.locator(".estado-badge")).toHaveText("En validación", { timeout: 10000 });
    await expect(tarjeta.getByText("Verificando con IA…")).toBeVisible();
    await expect(tarjeta.getByRole("button", { name: "Aceptar" })).toHaveCount(0);

    // Fase 2 (segundo plano): sin recargar la página, el sondeo de
    // Hallazgos.tsx debe reflejar la resolución del LLM en cuanto el worker
    // la persista.
    await expect(tarjeta.locator(".estado-badge")).toHaveText(/Confirmado|Descartado/, {
      timeout: 5 * 60 * 1000,
    });
    await expect(tarjeta.getByText("Verificando con IA…")).toHaveCount(0);
  });
});
