# src/validadores/contable

**Versión:** 0.1.0
**Fecha:** 2026-09-24
**Relacionado con:** RF-06

## Propósito

Valida archivos Excel contables: detecta descuadres, verifica fórmulas y consistencia de partidas, aplica reglas de mezcla de moneda (Q/$).

## Entradas

Archivo Excel (.xlsx) parseado por `src/parsers`. Reglas de negocio contables (`kb/reglas`).

## Salidas

Lista de hallazgos (descuadres, inconsistencias) con celda/hoja de referencia y severidad.

## RF que cubre

RF-06 (ver [docs/01-requerimientos/04-matriz-trazabilidad.md](../../../docs/01-requerimientos/04-matriz-trazabilidad.md)).

Sin lógica de negocio implementada (solo esqueleto/interfaces).
