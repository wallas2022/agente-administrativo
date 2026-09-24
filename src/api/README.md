# src/api

**Versión:** 0.1.0
**Fecha:** 2026-09-24
**Relacionado con:** RF-01, RF-03, RF-04, RF-05, RF-12, RF-13, RF-18, RF-19

## Propósito

Capa HTTP (FastAPI) que expone los endpoints del sistema: carga de documentos, consulta de estado de análisis, revisión/aprobación de hallazgos y consulta de bitácora. Punto de entrada único para la UI y para integraciones.

## Entradas

- Peticiones HTTP autenticadas (token emitido tras validación contra AD/LDAP vía `src/auth`).
- Archivos de documentos administrativos (Excel, Word, PDF, PowerPoint, imágenes).

## Salidas

- Respuestas JSON con estado de análisis, hallazgos y decisiones.
- Eventos encolados hacia `src/orquestador` (vía Redis) para procesamiento asíncrono.

## RF que cubre

RF-01, RF-03, RF-04, RF-05, RF-12, RF-13, RF-18, RF-19 (ver [docs/01-requerimientos/04-matriz-trazabilidad.md](../../docs/01-requerimientos/04-matriz-trazabilidad.md)).

Sin lógica de negocio implementada (solo esqueleto/interfaces).
