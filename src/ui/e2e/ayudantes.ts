import type { Page } from "@playwright/test";

// Mismos usuarios semilla que comun/semillas.py (todos con contraseña
// "cambiar123"), documentados en docs/04-pruebas/.
export const USUARIOS = {
  analista: "analista@local",
  revisor: "revisor@local",
  administrador: "administrador@local",
  auditor: "auditor@local",
} as const;

const CONTRASENA = "cambiar123";

export async function iniciarSesion(page: Page, correo: string): Promise<void> {
  await page.goto("/");
  await page.getByLabel("Correo").fill(correo);
  await page.getByLabel("Contraseña").fill(CONTRASENA);
  await page.getByRole("button", { name: "Ingresar" }).click();
  await page.waitForURL("/");
}
