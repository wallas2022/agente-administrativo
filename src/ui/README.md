# src/ui

**Versión:** 0.2.0
**Fecha:** 2026-09-25
**Relacionado con:** RF-03, RF-04, RF-05, RF-12, RF-13, RF-15, docs/03-diseno/secuencia/cu-01-excel-contable.md, docs/03-diseno/estados/estados-analisis.md

## Propósito

Interfaz web para CU-01 (revisión contable de Excel): carga de documentos, seguimiento del análisis, visualización de hallazgos y decisión (aceptar/rechazar) con segregación de funciones (PP-09).

## Stack

React + TypeScript + Vite. Sin librería de componentes pesada — CSS propio. Cliente de API tipado generado desde `/openapi.json` de `src/api` (`npm run generar-tipos-api`, ver `package.json`).

## Estructura

- `src/api/` — cliente HTTP tipado y tipos generados desde el OpenAPI de la API.
- `src/auth/` — contexto de autenticación (token en memoria, no en `localStorage`), rutas protegidas por rol.
- `src/paginas/` — pantallas de la aplicación.

## Entradas

Respuestas de `src/api` (backend FastAPI).

## Salidas

Interacciones de usuario (carga, aprobación, rechazo) enviadas a `src/api`.

## RF que cubre

RF-03, RF-04, RF-05, RF-12, RF-13, RF-15 (ver [docs/01-requerimientos/04-matriz-trazabilidad.md](../../docs/01-requerimientos/04-matriz-trazabilidad.md)).
