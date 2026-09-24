# Plan de pruebas del prototipo

Versión 0.2 · 2026-09-24 · Objetivo: validar con datos reales (anonimizados) del área de Contabilidad que el agente cumple los objetivos OE-01..OE-07 antes de escalar. Umbrales alineados con `docs/01-requerimientos/01-requerimiento-formal.md` v0.6. Entrega 1 prioriza CU-01, CU-02 y CU-05.

## 1. Conjunto de pruebas (dataset)
- 30 documentos mínimo, con errores **sembrados y conocidos** (respuesta esperada documentada):
  - 10 Excel contables · 8 Word · 4 PowerPoint · 6 PDF (4 digitales, 2 escaneados) · 2 imágenes (iteración 2).
  - Incluir al menos 5 documentos "complejos" (varias hojas, > 5,000 filas o > 50 páginas) y 2 archivos cercanos a 1 GB.
- Cada documento tiene su "hoja de respuestas": lista de errores esperados con ubicación.
- Línea base: tiempo de revisión manual por documento (hasta 60 min).

## 2. Casos de prueba
| ID | Prueba | HU / RF | Métrica | Umbral | Entrega |
| --- | --- | --- | --- | --- | --- |
| PP-01 | Detección de descuadres y errores contables | HU-03 / RF-06 | Recall de errores sembrados | ≥ 90 % | 1 |
| PP-02 | Exactitud de cifras reportadas (Q y $) | RNF-03 | Cifras incorrectas | 0 | 1 |
| PP-03 | Ortografía en Word, Excel, PowerPoint, PDF y texto | HU-04 / RF-10 | Recall / falsos positivos | ≥ 90 % / ≤ 10 % | 1 |
| PP-04 | Conservación de formato del archivo corregido | HU-10 / RF-14 | Archivos que abren sin daño y conservan estilos | 100 % | 1 |
| PP-05 | OCR de imágenes legibles | HU-05 / RF-11 | Precisión de caracteres (CER) | ≥ 95 % | 2 |
| PP-06 | OCR de imágenes de baja calidad | HU-05 | Informa ilegibilidad en lugar de inventar | 100 % | 2 |
| PP-07 | Citas a la base de conocimiento | RF-12 / RNF-06 | Hallazgos con fuente correcta y vigente | ≥ 95 % | 1 |
| PP-08 | Uso solo de fuentes vigentes | HU-11 / RF-16 | Citas a versiones obsoletas | 0 | 1 |
| PP-09 | Segregación de funciones | HU-09 / RNF-02 | Autoaprobaciones permitidas | 0 | 1 |
| PP-10 | Permisos por área | HU-02 / RF-02 | Accesos a documentos de otra área | 0 | 1 |
| PP-11 | Bitácora completa | HU-13 / RF-19 | Acciones sin registro | 0 | 1 |
| PP-12 | Tiempo por documento complejo (solo CPU, en stage) | RNF-04 | Tiempo p90 | ≤ 10 min (meta 5–10) | 1 |
| PP-13 | Capacidad diaria: ~50 documentos con 5–10 usuarios | RNF-05 | Documentos procesados en jornada / errores | ≥ 50 / 0 | 1 |
| PP-14 | Sin salida a internet | RNF-01 | Conexiones externas detectadas | 0 | 1 |
| PP-15 | Restauración desde respaldo | RNF-07 | Tiempo de recuperación | ≤ 4 h | 1 |
| PP-16 | Satisfacción de usuarios de Contabilidad | OE-07 | Encuesta 1–5 | ≥ 4 | 1 |
| PP-17 | Ahorro de tiempo vs. revisión manual | OE-07 | Reducción de tiempo por documento | ≥ 83 % (60 → ≤ 10 min) | 1 |
| PP-18 | Carga de archivo de 1 GB | RF-03 | Carga completa y reanudable sin error | 100 % | 1 |
| PP-19 | Depuración por retención de 3 meses | RNF-12 | Documentos > 3 meses eliminados y registrados en bitácora | 100 % | 1 |

## 3. Comparación de modelos
Ejecutar PP-01, PP-03, PP-07 y PP-12 con 2–3 modelos candidatos (p. ej. gpt-oss-120b, gpt-oss-20b, Qwen3-30B-A3B), primero en local (PC Core Ultra 7, 128 GB) y luego en stage (desde 28-oct-2026). Registrar precisión, tiempo y RAM usada. La decisión se documenta como ADR.

## 4. Registro de resultados
| Fecha | Ambiente | Prueba | Modelo / versión | Resultado | Cumple | Observaciones |
| --- | --- | --- | --- | --- | --- | --- |
| | | | | | | |

## 5. Criterio de salida del piloto
Se recomienda escalar si PP-02, PP-08, PP-09, PP-10, PP-11 y PP-14 se cumplen al 100 % (bloqueantes) y al menos 80 % del resto de pruebas de la entrega 1 alcanza su umbral. Las metas de rendimiento (PP-12, PP-13, PP-17) solo se consideran válidas medidas en stage.
