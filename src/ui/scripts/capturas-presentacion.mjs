// Capturas reales de la interfaz local para la presentación a directivos.
// Requiere el stack local levantado (infra/) y los usuarios semilla (contraseña "cambiar123").
//   cd src/ui && node scripts/capturas-presentacion.mjs
import { chromium } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const AQUI = path.dirname(fileURLToPath(import.meta.url));
const SALIDA = path.resolve(AQUI, "../../../docs/presentacion/capturas");
const BASE = process.env.UI_URL ?? "http://127.0.0.1:5173";
const CLAVE = "cambiar123";
const PREGUNTA =
  process.env.PREGUNTA_CHAT ??
  "¿Qué establece el compendio de leyes financieras sobre la elaboración del presupuesto público?";

fs.mkdirSync(SALIDA, { recursive: true });
const navegador = await chromium.launch();
const resultados = [];

async function contexto(correo) {
  const ctx = await navegador.newContext({
    viewport: { width: 1440, height: 900 },
    deviceScaleFactor: 1.5,
    locale: "es-GT",
  });
  const page = await ctx.newPage();
  await page.goto(`${BASE}/login`);
  await page.getByLabel("Correo").fill(correo);
  await page.getByLabel("Contraseña").fill(CLAVE);
  await page.getByRole("button", { name: "Ingresar" }).click();
  await page.waitForURL((u) => u.pathname !== "/login");
  return { ctx, page };
}

// El token de sesión vive solo en memoria: recargar la página la cierra. Se navega dentro de la app.
async function ir(page, ruta) {
  await page.evaluate((r) => {
    window.history.pushState({}, "", r);
    window.dispatchEvent(new PopStateEvent("popstate"));
  }, ruta);
  await page.waitForLoadState("networkidle");
  await page.waitForTimeout(800);
}

async function foto(page, nombre) {
  await page.waitForTimeout(1200);
  const archivo = path.join(SALIDA, `${nombre}.png`);
  await page.screenshot({ path: archivo });
  resultados.push(nombre);
  console.log("capturada", nombre);
}

const SOLO = (process.env.SOLO ?? "").split(",").filter(Boolean);

async function intentar(nombre, fn) {
  if (SOLO.length && !SOLO.some((s) => nombre.startsWith(s))) return;
  try {
    await fn();
  } catch (error) {
    console.log(`FALLÓ ${nombre}: ${String(error).split("\n")[0]}`);
  }
}

// 01 inicio de sesión
await intentar("01-login", async () => {
  const ctx = await navegador.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1.5 });
  const page = await ctx.newPage();
  await page.goto(`${BASE}/login`);
  await foto(page, "01-login");
  await ctx.close();
});

// 02-03 chat (usuario sin historial)
if (!process.env.OMITIR_CHAT) await intentar("chat", async () => {
  const { ctx, page } = await contexto("revisor@local");
  await ir(page, `/`);
  await foto(page, "02-chat-inicio");
  await page.getByPlaceholder("Pregunta algo sobre la base de conocimiento…").fill(PREGUNTA);
  await page.getByRole("button", { name: "Enviar" }).click();
  const enviando = page.getByRole("button", { name: "Enviando…" });
  await enviando.waitFor({ state: "visible", timeout: 30000 }).catch(() => {});
  await enviando.waitFor({ state: "detached", timeout: 420000 });
  await page.waitForTimeout(1500);
  await foto(page, "03-chat-respuesta");
  await ctx.close();
});

// 04 nuevo análisis
await intentar("04-nuevo-analisis", async () => {
  const { ctx, page } = await contexto("analista@local");
  await ir(page, `/nuevo-analisis`);
  await foto(page, "04-nuevo-analisis");
  await ctx.close();
});

// 05-06 resultados (análisis ya hechos en local)
const ANALISIS = [
  ["05-hallazgos-contable", "4b0e9147-c9e0-468c-a3ec-224aab99d768"],
  ["06-hallazgos-ortografia", "8adfe489-18c9-4a58-8858-a9a35a34c63f"],
];
for (const [nombre, id] of ANALISIS) {
  await intentar(nombre, async () => {
    for (const correo of ["analista@local", "administrador@local"]) {
      const { ctx, page } = await contexto(correo);
      await ir(page, `/analisis/${id}/hallazgos`);
      await page.waitForLoadState("networkidle");
      await page.waitForTimeout(1500);
      const texto = await page.locator("body").innerText();
      if (/otra área|no encontrad|sin acceso/i.test(texto)) {
        await ctx.close();
        continue;
      }
      await foto(page, nombre);
      await ctx.close();
      return;
    }
    throw new Error("sin acceso con ningún usuario");
  });
}

// 07 historial
await intentar("07-historial", async () => {
  const { ctx, page } = await contexto("administrador@local");
  await ir(page, `/historial`);
  await page.waitForLoadState("networkidle");
  await foto(page, "07-historial");
  await ctx.close();
});

// 08 base de conocimiento (curador)
await intentar("08-base-conocimiento", async () => {
  const { ctx, page } = await contexto("curador@local");
  await ir(page, `/base-de-conocimiento`);
  await page.waitForLoadState("networkidle");
  await foto(page, "08-base-conocimiento");
  await ctx.close();
});

// 09-10 dashboard, 11 configuración, 12 bitácora (administrador)
await intentar("admin", async () => {
  const { ctx, page } = await contexto("administrador@local");
  await ir(page, `/dashboard`);
  await page.waitForLoadState("networkidle");
  await foto(page, "09-dashboard-consumo");
  await page.getByRole("tab", { name: /Recursos/ }).click().catch(async () => {
    await page.getByText("Recursos", { exact: true }).first().click();
  });
  await page.waitForLoadState("networkidle");
  await page.waitForTimeout(7000);
  await foto(page, "10-dashboard-recursos");
  await ir(page, `/configuracion`);
  await page.waitForLoadState("networkidle");
  await foto(page, "11-configuracion-usuarios");
  await ir(page, `/bitacora`);
  await page.waitForLoadState("networkidle");
  await foto(page, "12-bitacora");
  await ctx.close();
});

await navegador.close();
fs.writeFileSync(path.join(SALIDA, "indice.json"), JSON.stringify(resultados, null, 2));
console.log(`${resultados.length} capturas en ${SALIDA}`);
