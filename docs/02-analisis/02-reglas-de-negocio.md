# Reglas de negocio — Agente Administrativo

**Versión:** 0.1.0
**Fecha:** 2026-09-24
**Relacionado con:** docs/01-requerimientos/01-requerimiento-formal.md (RF-03, RF-06, RF-10, RF-17, RNF-02, RNF-03, RNF-12), docs/02-analisis/03-riesgos.md

Reglas de negocio (RN-xx) que el agente aplica durante la validación. Se cargan y versionan en [kb/reglas/reglas.csv](../../kb/reglas/reglas.csv) (columnas `version`, `estado`, `moneda`) y su detalle textual vive en este documento; el Curador de conocimiento del área es responsable de mantenerlas vigentes (CU-08).

| ID | Regla | Aplica a | Severidad del hallazgo | Origen |
| --- | --- | --- | --- | --- |
| RN-01 | Cuadre debe/haber: el total de débitos debe ser igual al total de créditos por comprobante y por hoja | Excel contable | Alta | RF-06 |
| RN-02 | Cuentas vs. catálogo: toda cuenta contable referenciada debe existir en el catálogo de cuentas vigente | Excel contable | Alta | RF-06 |
| RN-03 | Validación de período: la fecha de cada partida debe corresponder al período contable que se está revisando | Excel contable | Media | RF-06 |
| RN-04 | Duplicados: dos o más partidas con la misma cuenta, monto y fecha dentro del mismo documento se marcan como posible duplicado | Excel contable | Media | RF-06 |
| RN-05 | Mezcla de moneda sin tipo de cambio: si un documento contiene montos en Quetzales (Q) y en Dólares ($) sin un tipo de cambio explícito registrado, se genera un hallazgo; el sistema **no infiere ni aplica** un tipo de cambio automáticamente (ningún cálculo lo hace el LLM, RNF-03) | Excel contable, cualquier documento con montos | Alta | RF-06, RNF-03 |
| RN-06 | Ortografía con glosario: todo término presente en el glosario/diccionario interno del área (siglas, nombres propios, términos técnicos) se excluye de los hallazgos ortográficos, aunque no esté en el diccionario estándar es-GT | Texto, Excel, Word, PowerPoint, PDF | — (excluye hallazgo) | RF-10, RF-17 |
| RN-07 | Segregación de funciones: el usuario que cargó un documento no puede aprobar ni rechazar sus propios hallazgos; el sistema bloquea la acción si el usuario coincide | Todos los documentos | Bloqueante | RNF-02, RF-13 |
| RN-08 | Retención: documentos originales, corregidos y resultados se conservan 90 días desde su carga; al vencer se eliminan automáticamente y la eliminación queda registrada en bitácora | Todos los documentos | — (control de ciclo de vida) | RNF-12 |
| RN-09 | Tamaño máximo de archivo: ningún documento cargado puede exceder 1 GB (1024 MB); la carga se realiza por partes y es reanudable ante interrupciones | Todos los documentos | Bloqueante (rechazo de carga) | RF-03 |

## Notas

- RN-05 es la única regla que involucra cifras de conversión: por RNF-03 ("el LLM no genera cifras"), el hallazgo se limita a **señalar** la mezcla sin tipo de cambio; la corrección (aplicar un tipo de cambio) la decide una persona.
- RN-06 depende de que el glosario del área (RF-17, gestionado en CU-08) esté cargado y vigente antes de ejecutar CU-05; un glosario vacío no bloquea la revisión, solo reduce su precisión (ver R-06 en [03-riesgos.md](03-riesgos.md)).
- RN-08 y RN-09 están directamente ligadas al riesgo de capacidad de disco (R-07 en [03-riesgos.md](03-riesgos.md)) y se prueban en PP-19 y PP-18 respectivamente ([docs/04-pruebas/plan-pruebas-prototipo.md](../04-pruebas/plan-pruebas-prototipo.md)).
- RN-07 es la regla operativa detrás de RNF-02 y se prueba en PP-09.

## Pendientes

- [POR CONFIRMAR] Umbral exacto de tolerancia de RN-01 (¿cuadre exacto o con margen de redondeo?).
- [POR CONFIRMAR] Fuente autoritativa del catálogo de cuentas para RN-02 (¿un documento en `kb/fuentes` o una integración futura?).
- [POR CONFIRMAR] Retención de la bitácora de auditoría (RN-08 cubre documentos y resultados; la bitácora en sí tiene un plazo distinto según SRS §17.5, aún sin definir).
