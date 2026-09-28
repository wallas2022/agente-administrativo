import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/pruebas/configurar.ts"],
    // e2e/ son pruebas de Playwright (npm run test:e2e), no de Vitest —
    // sin esto, vitest las recoge por el patrón *.spec.ts y fallan porque
    // usan la API de @playwright/test, no la de vitest.
    exclude: ["**/node_modules/**", "e2e/**"],
  },
});
