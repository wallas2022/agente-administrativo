import { expect, test } from "@playwright/test";
import { iniciarSesion, USUARIOS } from "./ayudantes";

// P-12 (Bloque 5): un caso por rol -- el menú se arma desde los permisos
// reales de /auth/me (comun/permisos.py, MATRIZ_PERMISOS_DEFECTO v0.3), no
// del ejemplo narrativo de HU-20 (que no lista "Nuevo análisis" ni "Base de
// conocimiento" para Administrador, aunque sí tiene analisis:crear y
// conocimiento:ver -- ver docs/04-pruebas/resultados/local-P12-bloque2.md).
const MENU_ESPERADO_POR_ROL: Record<keyof typeof USUARIOS, string[]> = {
  analista: ["Nuevo análisis", "Historial"],
  revisor: ["Historial"],
  curador: ["Historial", "Base de conocimiento"],
  auditor: ["Historial", "Base de conocimiento", "Ajustes autoaprobados", "Bitácora"],
  administrador: [
    "Nuevo análisis",
    "Historial",
    "Base de conocimiento",
    "Ajustes autoaprobados",
    "Bitácora",
    "Configuración",
  ],
};

test.describe("HU-20: menú según mi rol", () => {
  for (const [rol, opcionesEsperadas] of Object.entries(MENU_ESPERADO_POR_ROL)) {
    test(`${rol} ve exactamente: ${opcionesEsperadas.join(", ")}`, async ({ page }) => {
      await iniciarSesion(page, USUARIOS[rol as keyof typeof USUARIOS]);

      const opciones = await page.locator(".layout__nav .layout__enlace").allTextContents();
      expect(opciones.sort()).toEqual([...opcionesEsperadas].sort());
    });
  }
});
