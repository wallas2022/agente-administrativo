# Casos de uso — Agente Administrativo

**Versión:** 0.6
**Fecha:** 2026-09-24
**Relacionado con:** RG-01 a RG-08 (ver 01-requerimiento-formal.md §8 y §12)

Actores: **Analista** (carga documentos y ejecuta el análisis), **Revisor/Aprobador** (acepta o rechaza hallazgos y libera documentos), **Curador de conocimiento** (gobierna la base de conocimiento), **Administrador** (usuarios, roles, infraestructura), **Auditor** (consulta de solo lectura).

**Entrega 1 (MVP):** CU-01, CU-02, CU-05, más los transversales CU-07, CU-08, CU-09, CU-10. **Entrega 2:** CU-03, CU-04, CU-06 (ver 01-requerimiento-formal.md §7 y §12).

---

## CU-01 — Validar Excel contable

**Entrega:** 1. **Actor principal:** Analista. **Secundario:** Revisor/Aprobador.
**RF relacionados:** RF-03, RF-04, RF-05, RF-06, RF-12, RF-13, RF-14, RF-15.

**Precondición:** El Analista tiene sesión autenticada; existen reglas de cuadre contable en `kb/reglas`.

**Flujo principal:**
1. El Analista carga un archivo Excel (.xlsx) de hasta 1 GB, con carga por partes y reanudable (RF-03; PP-18), y selecciona el tipo de revisión "contable" (RF-04) y las fuentes de conocimiento a consultar (RF-05).
2. El sistema extrae hojas, celdas y fórmulas (`src/parsers`).
3. El validador contable (`src/validadores/contable`) aplica reglas de cuadre debe/haber, totales, fórmulas, cuentas vs. catálogo, duplicados y período (RF-06; PP-01).
4. El sistema presenta cada hallazgo con severidad, ubicación, explicación, corrección sugerida y fuente citada (RF-12; PP-07).
5. El Analista o el Revisor acepta, rechaza o deshace cada hallazgo (RF-13); el sistema genera el documento corregido en su formato original con las correcciones aceptadas (RF-14; PP-04) y, si se solicita, un reporte PDF de hallazgos (RF-15).
6. El documento pasa a revisión final (CU-07).

**Flujos alternos:**
- 3a. No se detectan descuadres: el documento se marca "sin hallazgos" y pasa igualmente a revisión.
- 3b. Se detecta mezcla de moneda (Q/$) sin tipo de cambio: se genera hallazgo de severidad alta.

**Postcondición:** Documento con estado `con_hallazgos` o `en_revision` (ver docs/03-diseno/estados/estados-analisis.md).

---

## CU-02 — Revisar redacción PDF/Word

**Entrega:** 1. **Actor principal:** Analista. **Secundario:** Revisor/Aprobador.
**RF relacionados:** RF-03, RF-07, RF-12, RF-13, RF-14.

**Precondición:** El documento está en formato PDF o Word.

**Flujo principal:**
1. El Analista carga el documento (RF-03) y selecciona el tipo de revisión "redacción" (RF-04).
2. El sistema extrae texto y estructura (`src/parsers`).
3. El sistema revisa redacción, tono y estructura contra la guía de estilo (RF-07).
4. El sistema presenta cada sugerencia con severidad, ubicación, explicación y corrección sugerida (RF-12).
5. El Analista o el Revisor acepta, rechaza o deshace cada sugerencia (RF-13); el sistema genera el documento corregido en su formato original (RF-14; PP-04).

**Flujos alternos:**
- 2a. El PDF es una imagen escaneada: se deriva a CU-06 (OCR, entrega 2) antes de continuar.

**Postcondición:** Documento con sugerencias de redacción aplicadas o descartadas.

---

## CU-03 — Verificar actualización normativa

**Entrega:** 2. **Actor principal:** Analista. **Secundario:** Curador de conocimiento, Revisor/Aprobador.
**RF relacionados:** RF-03, RF-08, RF-12.

**Precondición:** Existe normativa vigente cargada en `kb/fuentes` con fecha de vigencia (RF-16).

**Flujo principal:**
1. El Analista carga un documento Word/PDF que referencia normativa (RF-03) y selecciona el tipo de revisión "actualización normativa" (RF-04).
2. El sistema extrae las referencias normativas del documento.
3. El sistema compara dichas referencias contra la normativa vigente en la base de conocimiento y detecta contenido desactualizado (RF-08).
4. El sistema presenta el hallazgo con severidad, ubicación, explicación y fuente vigente citada (RF-12).
5. El Revisor/Aprobador valida el hallazgo (CU-07).

**Flujos alternos:**
- 3a. No existe fuente vigente equivalente en la base de conocimiento: el hallazgo se marca `sin fuente de contraste`.

**Postcondición:** Documento con hallazgos de normativa desactualizada pendientes de revisión.

---

## CU-04 — Evaluar control/checklist

**Entrega:** 2. **Actor principal:** Analista. **Secundario:** Revisor/Aprobador.
**RF relacionados:** RF-03, RF-09, RF-12.

**Precondición:** Existe una plantilla de checklist/control vigente en la base de conocimiento.

**Flujo principal:**
1. El Analista carga el documento de checklist/control (Word, Excel o PDF) (RF-03) y selecciona el tipo de revisión "control" (RF-04).
2. El sistema extrae los ítems del checklist.
3. El validador de control (`src/validadores/control`) evalúa cada ítem contra la plantilla vigente: cumple / no cumple / revisar (RF-09).
4. El sistema presenta cada hallazgo con severidad, ubicación, explicación y fuente citada (RF-12).
5. El Revisor/Aprobador valida los hallazgos (CU-07).

**Postcondición:** Checklist con estado de cumplimiento por ítem, pendiente de aprobación.

---

## CU-05 — Revisar ortografía multi-formato

**Entrega:** 1. **Actor principal:** Analista. **Secundario:** Revisor/Aprobador.
**RF relacionados:** RF-03, RF-10, RF-14, RF-17.

**Precondición:** El documento está en un formato soportado (texto, Excel, Word, PowerPoint, PDF).

**Flujo principal:**
1. El Analista carga el documento (RF-03) y selecciona el tipo de revisión "ortografía" (RF-04).
2. El sistema extrae el texto según el formato (`src/parsers`, o `src/ocr` si es imagen/PDF escaneado — CU-06, entrega 2).
3. El módulo de ortografía (`src/ortografia`) ejecuta LanguageTool + Hunspell (es-GT) con ubicación exacta: celda (Excel), párrafo (Word), diapositiva/notas (PowerPoint), página (PDF) (RF-10; PP-03), consultando el glosario/diccionario interno para siglas y nombres propios (RF-17).
4. El Analista o el Revisor aplica o descarta cada sugerencia; el sistema genera el documento corregido en su formato original (RF-14; PP-04).

**Postcondición:** Documento con sugerencias ortográficas aplicadas o descartadas.

---

## CU-06 — Convertir imagen a texto (OCR)

**Entrega:** 2 (RF-11 marcado "iteración 2" en el SRS). **Actor principal:** Analista.
**RF relacionados:** RF-03, RF-11.

**Precondición:** El archivo cargado es una imagen (.jpg, .png, .tiff) o un PDF escaneado sin capa de texto.

**Flujo principal:**
1. El Analista carga la imagen o PDF escaneado (RF-03) y selecciona el tipo de revisión "OCR" (RF-04).
2. El sistema preprocesa la imagen (deskew, binarización, limpieza de ruido) con OpenCV.
3. El sistema ejecuta Tesseract y extrae el texto con nivel de confianza, generando salida en .docx/.txt/.xlsx según corresponda (RF-11; PP-05, PP-06).
4. El texto extraído queda disponible para CU-02, CU-03, CU-04 o CU-05 según corresponda.

**Flujos alternos:**
- 3a. Confianza de OCR por debajo de un umbral [POR CONFIRMAR]: el bloque se marca para revisión manual antes de continuar (ver R-05).

**Postcondición:** Texto extraído disponible como insumo para otros casos de uso.

---

## CU-07 — Aprobar o rechazar hallazgos

**Entrega:** 1 (transversal). **Actor principal:** Revisor/Aprobador. **Secundario:** Auditor (solo lectura, posterior).
**RF relacionados:** RF-13, RF-14, RF-20. **RNF relacionados:** RNF-02 (segregación de funciones; PP-09).

**Precondición:** Existen hallazgos generados por cualquiera de los CU-01 a CU-05 para un documento cuyo estado es `con_hallazgos` o `en_revision`.

**Flujo principal:**
1. El Analista envía el análisis a un Revisor y el sistema lo notifica (RF-20).
2. El Revisor/Aprobador consulta la lista de hallazgos con su evidencia y fuente.
3. El sistema verifica que el Revisor/Aprobador no sea el mismo usuario que cargó el documento (RNF-02, segregación de funciones; PP-09).
4. El Revisor/Aprobador acepta, rechaza o deshace cada hallazgo (RF-13).
5. El sistema genera el documento corregido en su formato original con las correcciones aceptadas (RF-14) y registra la decisión en la bitácora (RF-19, CU-10).

**Flujos alternos:**
- 3a. El Revisor/Aprobador es el mismo usuario que cargó el documento: el sistema bloquea la acción y exige un revisor distinto.

**Postcondición:** Documento en estado `aprobado`, `rechazado` o `cerrado` (ver docs/03-diseno/estados/estados-analisis.md).

---

## CU-08 — Gestionar base de conocimiento

**Entrega:** 1 (transversal). **Actor principal:** Curador de conocimiento.
**RF relacionados:** RF-16, RF-17.

**Precondición:** El Curador tiene sesión autenticada con permiso sobre su área.

**Flujo principal:**
1. El Curador carga una fuente de conocimiento (normativa, regla, checklist) con su versión y vigencia (RF-16).
2. El sistema indexa la fuente (RAG) tras la aprobación del Curador.
3. El Curador mantiene el glosario/diccionario interno del área (siglas, nombres propios, términos técnicos) (RF-17).
4. La versión anterior de una fuente actualizada queda marcada como no vigente sin eliminarse (PP-08: 0 citas a versiones obsoletas).

**Postcondición:** Base de conocimiento actualizada y reindexada, disponible para los CU-01 a CU-05.

---

## CU-09 — Administrar usuarios y roles

**Entrega:** 1 (transversal). **Actor principal:** Administrador.
**RF relacionados:** RF-01, RF-02.

**Precondición:** El Administrador tiene sesión autenticada con privilegios de administración.

**Flujo principal:**
1. El sistema autentica usuarios con cuentas de la organización (AD/LDAP) o locales (RF-01).
2. El Administrador administra usuarios, roles y permisos por área (RF-02; PP-10: 0 accesos a documentos de otra área).

**Flujos alternos:**
- 1a. Usuario autenticado sin rol asignado: el sistema deniega el acceso a funcionalidades.

**Postcondición:** Usuarios y roles vigentes, disponibles para el control de acceso de todos los demás CU.

---

## CU-10 — Consultar auditoría

**Entrega:** 1 (transversal). **Actor principal:** Auditor.
**RF relacionados:** RF-18, RF-19.

**Precondición:** Existen registros de bitácora generados por acciones de otros CU.

**Flujo principal:**
1. El sistema registra en bitácora toda acción relevante del sistema (RF-19; PP-11: 0 acciones sin registro).
2. El Auditor consulta el historial de análisis con filtros por usuario, área, tipo, estado y fecha (RF-18).
3. El Auditor no puede modificar ningún registro (solo lectura).

**Postcondición:** Consulta de auditoría entregada sin alteración del historial.
