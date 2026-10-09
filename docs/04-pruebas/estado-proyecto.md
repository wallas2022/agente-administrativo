# Estado del proyecto — Agente Administrativo

**Versión:** 0.1.0
**Fecha:** 2026-10-09
**Relacionado con:** docs/01-requerimientos/04-matriz-trazabilidad.md, docs/04-pruebas/plan-pruebas-prototipo.md, docs/04-pruebas/resultados/

Snapshot basado únicamente en evidencia verificable (documentos de resultados en `docs/04-pruebas/resultados/`, ADRs aceptados y la matriz de trazabilidad) -- no son porcentajes estimados, son hechos ya documentados en otro lugar. [POR CONFIRMAR] marca lo que no se pudo verificar al escribir esto.

## Casos de uso (Entrega 1 = MVP, Entrega 2 = iteración siguiente)

| CU | Nombre | Entrega | Estado | Evidencia |
| --- | --- | --- | --- | --- |
| CU-01 | Validar Excel contable | 1 | En curso -- motor de reglas contables y detección de tabla genérica implementados | [local-S1.md](resultados/local-S1.md), [local-cu01-tabla-generica-bloque1.md](resultados/local-cu01-tabla-generica-bloque1.md) |
| CU-02 | Revisar redacción PDF/Word | 1 | En curso -- fase 1 (determinista) y fase 2 (LLM por párrafo, 2 opciones) implementadas; optimización de rendimiento documentada en ADR-008 (≤60 s no garantizado en todo hardware) | [local-cu02-bloque1.md](resultados/local-cu02-bloque1.md), [local-cu02-bloque2.md](resultados/local-cu02-bloque2.md), [local-cu02-rendimiento.md](resultados/local-cu02-rendimiento.md), ADR-008 |
| CU-03 | Verificar actualización normativa | 2 | No iniciado | — |
| CU-04 | Evaluar control/checklist | 2 | No iniciado | — |
| CU-05 | Revisar ortografía multi-formato | 1 | En curso -- LanguageTool + glosario + LLM para casos dudosos | [local-S2.md](resultados/local-S2.md) |
| CU-06 | Convertir imagen a texto (OCR) | 2 | **MVP completo (Bloques 1-4 de P-11)**: motor (Tesseract+OpenCV+PyMuPDF), calidad sin inventar (RN-06), interfaz básica, dataset y PP-05/PP-06 medidos | [local-cu06-bloque1.md](resultados/local-cu06-bloque1.md), [-bloque2.md](resultados/local-cu06-bloque2.md), [-bloque3.md](resultados/local-cu06-bloque3.md), [local-CU06.md](resultados/local-CU06.md), ADR-007 |
| CU-07 | Aprobar o rechazar hallazgos | 1 | Transversal, sin bloque dedicado -- `POST /hallazgos/{id}/decision` ya en uso desde CU-01/CU-02/CU-05 | [POR CONFIRMAR si cubre todos los casos de CU-07 del SRS] |
| CU-08 | Gestionar base de conocimiento | 1 | En curso -- ingesta y aprobación de fuentes (Bloque K5) | [local-SKB.md](resultados/local-SKB.md) |
| CU-09 | Administrar usuarios y roles | 1 | Soporte base (login, roles fijos de prueba) -- [POR CONFIRMAR] si existe pantalla de administración CRUD de usuarios | — |
| CU-10 | Consultar auditoría | 1 | Soporte base (`GET /analisis/{id}/bitacora`, pantalla "Agente trabajando") -- [POR CONFIRMAR] si existe una pantalla de auditoría dedicada e independiente | — |

## Infraestructura y decisiones (ADR)

| ADR | Decisión | Estado |
| --- | --- | --- |
| ADR-001 | Motor LLM en CPU | Aceptado |
| ADR-002 | Base vectorial | Aceptado |
| ADR-003 | Orquestación del agente | Aceptado |
| ADR-004 | Ambientes local/stage | Aceptado |
| ADR-005 | [POR CONFIRMAR] -- no existe todavía en `docs/03-diseno/adr/` | Pendiente |
| ADR-006 | Almacenamiento de objetos (S3/MinIO/LocalStack) | Aceptado |
| ADR-007 | Motor de OCR (Tesseract + OpenCV + PyMuPDF) | Aceptado, implementado (CU-06) |
| ADR-008 | Rendimiento LLM de CU-02 | Aceptado -- ≤60 s no se garantiza en todo hardware; modelo por defecto sin cambios |

**Ambiente**: local (Windows + WSL2 + Docker Desktop, Ollama nativo de Windows). Stage todavía no existe (pendiente desde el 28-oct-2026 según referencias en el plan de pruebas) -- todas las mediciones de este documento y de `docs/04-pruebas/resultados/` son de **local**, no de stage.

## Qué falta para considerar el piloto listo para escalar

Ver criterio de salida en [plan-pruebas-prototipo.md §5](plan-pruebas-prototipo.md#5-criterio-de-salida-del-piloto): PP-02, PP-08, PP-09, PP-10, PP-11 y PP-14 al 100 % (bloqueantes) + 80 % del resto de la Entrega 1. Varias de esas pruebas (PP-09 a PP-11, PP-13, PP-15, PP-16, PP-19) no tienen todavía una fila en `plan-pruebas-prototipo.md §4` -- [POR CONFIRMAR] si ya se midieron en algún documento no enlazado aquí.
