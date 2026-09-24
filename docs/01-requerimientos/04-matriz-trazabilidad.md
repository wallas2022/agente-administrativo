# Matriz de trazabilidad — Agente Administrativo

**Versión:** 0.6
**Fecha:** 2026-09-24
**Relacionado con:** docs/01-requerimientos/01-requerimiento-formal.md, 02-casos-de-uso.md, 03-historias-de-usuario.md, docs/04-pruebas/plan-pruebas-prototipo.md

Trazabilidad OE → RG → RF → CU → HU → PP, construida a partir del SRS v0.6 y el plan de pruebas v0.2. Columna **Entrega**: 1 = MVP (CU-01, CU-02, CU-05 y transversales CU-07..10); 2 = iteración siguiente (CU-03, CU-04, CU-06, incluido RF-11/OCR).

El SRS (§8, §12) define explícitamente RG→RF y CU→RF; **no define explícitamente OE→RG**. La columna OE es una inferencia razonable (ver Supuestos) y debe confirmarse con el responsable del proyecto. La columna RN referencia las reglas de negocio de [docs/02-analisis/02-reglas-de-negocio.md](../02-analisis/02-reglas-de-negocio.md).

| RF | OE | RG | CU | HU | PP | RN | Entrega |
| --- | --- | --- | --- | --- | --- | --- | --- |
| RF-01 | [POR CONFIRMAR: sin OE en el SRS] | [POR CONFIRMAR: sin RG en el SRS] | CU-09 | HU-14 | — | — | 1 |
| RF-02 | [POR CONFIRMAR: sin OE en el SRS] | [POR CONFIRMAR: sin RG en el SRS] | CU-09 | HU-02 | PP-10 | — | 1 |
| RF-03 | OE-01 | RG-01 | CU-01 | HU-01 | PP-18 | RN-09 | 1 |
| RF-04 | OE-01 | RG-01 | CU-01 | HU-01 | — | — | 1 |
| RF-05 | OE-01 | RG-01 | CU-01 | HU-01 | — | — | 1 |
| RF-06 | OE-01 | RG-01 | CU-01 | HU-03 | PP-01 | RN-01, RN-02, RN-03, RN-04, RN-05 | 1 |
| RF-07 | OE-02 | RG-02 | CU-02 | HU-06 | — | — | 1 |
| RF-08 | OE-03 | RG-03 | CU-03 | HU-07 | — | — | 2 |
| RF-09 | [POR CONFIRMAR: sin OE claro para controles/checklist] | RG-04 | CU-04 | HU-08 | — | — | 2 |
| RF-10 | OE-02 | RG-02 | CU-05 | HU-04 | PP-03 | RN-06 | 1 |
| RF-11 | OE-04 | RG-05 | CU-06 | HU-05 | PP-05, PP-06 | — | 2 |
| RF-12 | OE-01 | RG-01 | CU-01, CU-02, CU-03, CU-04 | HU-12 | PP-07 | — | 1 |
| RF-13 | OE-01, OE-06 | RG-01, RG-06 | CU-01, CU-02, CU-07 | HU-09, HU-10 | PP-09 | RN-07 | 1 |
| RF-14 | OE-01, OE-06 | RG-01, RG-06 | CU-01, CU-02, CU-05, CU-07 | HU-10 | PP-04 | — | 1 |
| RF-15 | OE-01 | RG-01 | CU-01 | HU-12 | — | — | 1 |
| RF-16 | OE-05 | RG-03 | CU-08 | HU-11 | PP-08 | — | 1 |
| RF-17 | OE-02 | RG-02 | CU-05, CU-08 | HU-04, HU-11 | — | RN-06 | 1 |
| RF-18 | [POR CONFIRMAR: sin OE claro] | [POR CONFIRMAR: sin RG en el SRS] | CU-10 | HU-14 | — | — | 1 |
| RF-19 | OE-06 | RG-04, RG-08 | CU-10 | HU-13 | PP-11 | — | 1 |
| RF-20 | OE-06 | [POR CONFIRMAR: sin RG en el SRS] | CU-07 | HU-14 | — | — | 1 |

## RN sin RF puntual (aplican de forma transversal)

| RN | Regla | Aplica a |
| --- | --- | --- |
| RN-08 | Retención de 90 días | Todos los documentos (RNF-12, PP-19) |

## RNF y OE con PP directa (no pasan por un RF)

Varias pruebas del plan validan un RNF u OE completo, no un RF puntual:

| ID | PP | Umbral |
| --- | --- | --- |
| RNF-01 (privacidad) | PP-14 | 0 conexiones externas |
| RNF-02 (segregación de funciones) | PP-09 | 0 autoaprobaciones |
| RNF-03 (exactitud) | PP-02 | 0 cifras incorrectas |
| RNF-04 (rendimiento) | PP-12 | ≤ 10 min p90 (meta 5–10) |
| RNF-05 (capacidad de proceso) | PP-13 | ≥ 50 documentos/jornada, 0 errores |
| RNF-06 (trazabilidad) | PP-07 | ≥ 95 % hallazgos con fuente correcta y vigente |
| RNF-07 (disponibilidad/recuperación) | PP-15 | ≤ 4 h de recuperación |
| RNF-12 (retención) | PP-19 | 100 % documentos > 3 meses eliminados y auditados |
| OE-07 (valor del piloto) | PP-16, PP-17 | Satisfacción ≥ 4/5; reducción de tiempo ≥ 83 % |

## RNF con RG asociado (según SRS §8)

| RNF | RG |
| --- | --- |
| RNF-01 | RG-07 |
| RNF-02 | RG-06, RG-07 |
| RNF-06 | RG-08 |

RNF-03, RNF-04, RNF-05, RNF-07 a RNF-14 no tienen un RG asociado explícito en el SRS (son atributos de calidad transversales, no derivados de una necesidad de negocio puntual); no se considera una brecha.

## Cobertura

- Los 20 RF (RF-01 a RF-20) del SRS v0.6 aparecen en esta matriz.
- Los 10 CU (CU-01 a CU-10) y las 14 HU (HU-01 a HU-14) están referenciados.
- Los 14 RNF (RNF-01 a RNF-14) están completos en el SRS ([01-requerimiento-formal.md](01-requerimiento-formal.md) §11).
- Las 19 PP (PP-01 a PP-19) del plan de pruebas ([docs/04-pruebas/plan-pruebas-prototipo.md](../04-pruebas/plan-pruebas-prototipo.md)) están referenciadas, directamente por RF o por RNF/OE.
- Los 10 riesgos (R-01 a R-10) están completos en [docs/02-analisis/03-riesgos.md](../02-analisis/03-riesgos.md).
- Las 9 reglas de negocio (RN-01 a RN-09) de [docs/02-analisis/02-reglas-de-negocio.md](../02-analisis/02-reglas-de-negocio.md) están referenciadas: RN-01 a RN-07 y RN-09 contra su RF, RN-08 (retención) de forma transversal.

## Brechas detectadas en el SRS (para el responsable del proyecto)

1. **RF-01, RF-02, RF-18, RF-20 sin RG asociado** en la tabla del §8: son funcionalidad base de plataforma (autenticación/roles, consulta de historial, notificación) que probablemente no necesite un RG de negocio dedicado, pero conviene confirmarlo explícitamente en la próxima revisión del SRS.
2. **RG-04 (controles internos evidenciables) sin OE asociado**: no hay un objetivo específico (OE-01..07) que cubra explícitamente los controles/checklists (RF-09); se sugiere evaluar agregar un OE dedicado o vincular RG-04 a uno existente.
3. **RF-04, RF-05, RF-07, RF-08, RF-09, RF-15, RF-17, RF-18, RF-20 sin PP directa** en el plan v0.2: son requerimientos cubiertos indirectamente por las pruebas de los CU en los que participan (p. ej. PP-01/PP-03/PP-07 ejercitan el flujo completo de CU-01/CU-05), pero no tienen un caso de prueba dedicado; sugerido para una futura revisión del plan de pruebas.

## Supuestos

1. La columna OE es una inferencia de quien construyó esta matriz (no está en el SRS); debe validarse con el responsable del proyecto (Rene Rosales) en la próxima revisión.
2. RF-03 (cargar documentos) se describe narrativamente como paso compartido por CU-01 a CU-06 en [02-casos-de-uso.md](02-casos-de-uso.md), pero el SRS (§12) solo lo asocia formalmente con CU-01; esta matriz sigue la asociación formal del SRS.
3. "RF-03..06" y "RF-12..15" en el SRS §8/§12 se interpretan como rangos inclusivos (RF-03,04,05,06 y RF-12,13,14,15).
4. La numeración HU-01 a HU-14 se fijó para coincidir exactamente con las referencias "HU-xx" del plan de pruebas v0.2 (no hay un documento fuente `03-historias-de-usuario.md` en `docs/_archivo/`; se construyó a partir de esas referencias y de los CU/RF del SRS).
