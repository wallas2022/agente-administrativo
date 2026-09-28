import { defineConfig, devices } from "@playwright/test";

/**
 * Suite E2E permanente (Bloque U5). Corre contra el stack local ya
 * levantado (docker compose, ver infra/) — no arranca un servidor propio:
 * en este proyecto la UI y la API viven en contenedores con dependencias
 * reales (Postgres, Qdrant, LocalStack, Ollama) que un `webServer` de
 * Playwright no podría replicar.
 */
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  retries: 0,
  reporter: [["list"], ["html", { open: "never", outputFolder: "playwright-report" }]],
  use: {
    baseURL: "http://127.0.0.1:5173",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
});
