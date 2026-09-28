# src/ortografia

**Versión:** 0.1.0
**Fecha:** 2026-09-24
**Relacionado con:** RF-10, RF-17

## Propósito

Corrección ortográfica y de redacción sobre texto extraído de Excel, Word, PowerPoint y PDF, usando LanguageTool. `LANGUAGETOOL_LOCALE=es-GT` no es un código soportado por LanguageTool 6.5 (devuelve 400); se usa `es` (genérico), no hay variante de Guatemala disponible.

## Entradas

`SegmentoTexto` (texto + ubicación) extraído por `src/parsers` — ver `parsers.segmentos`.

## Salidas

`HallazgoOrtografico` (severidad, ubicación, descripción, corrección sugerida, regla RN-06) por cada error confirmado.

## RF que cubre

RF-10, RF-17 (ver [docs/01-requerimientos/04-matriz-trazabilidad.md](../../docs/01-requerimientos/04-matriz-trazabilidad.md)).

## Diseño (Bloque O2)

- `cliente_languagetool.py`: transporte HTTP puro hacia el servicio LanguageTool (`infra/compose.yml`).
- `revision.py` (RN-06): LanguageTool decide qué está mal escrito (determinista). Los términos del glosario del área y los números/códigos se excluyen antes de clasificar. Categoría LanguageTool `TYPOS` (palabra inexistente en el diccionario) → hallazgo directo, sin LLM. Cualquier otra categoría (`DIACRITICS`: de/dé, se/sé...; `MISSPELLING` de `grammar.xml`: a/ha...) depende del contexto gramatical → se acumula y se valida con **una sola llamada al LLM por lote** (igual que CU-01); el LLM solo confirma o descarta lo que LanguageTool ya marcó, nunca escanea texto por su cuenta.
- Verificado contra el servicio LanguageTool 6.5 real (no mockeado) con los 4 documentos de `tests/dataset/cu-05/`: encuentra 23 de los 24 errores sembrados de la hoja de respuestas (el restante, "Indicadores claves" → "Indicadores clave", es un error de concordancia que la edición gratuita de LanguageTool no detecta — no hay ninguna coincidencia que filtrar o clasificar porque LanguageTool nunca la reporta). Medición formal de recall/falsos positivos con el LLM real: Bloque O5 (`docs/04-pruebas/resultados/local-S2.md`).
