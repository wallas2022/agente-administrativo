# Análisis — CU-02 "Mejorar redacción"

**Versión:** 0.1.0
**Fecha:** 2026-10-01
**Relacionado con:** docs/01-requerimientos/02-casos-de-uso.md#cu-02, docs/01-requerimientos/01-requerimiento-formal.md (RF-03, RF-07, RF-12, RF-13, RF-14), docs/03-diseno/secuencia/cu-02-redaccion.md

> **Origen de este documento:** el encargo de implementación de CU-02 citó este archivo como fuente de verdad, pero no existía en el repositorio. Este documento se construyó a partir del encargo mismo (instrucciones detalladas del responsable del proyecto, bloques 1-4) y del diagrama de secuencia preliminar que sí existía (`docs/03-diseno/secuencia/cu-02-redaccion.md`, v0.1.0) — se deja constancia explícita de cada decisión tomada para que el responsable del proyecto pueda corregirla.

## 1. Alcance de la entrega 1 (Bloque 1-2)

Una pantalla "Mejorar redacción", con dos formas de entrada (texto pegado o archivo) y un motor de dos fases:

1. **Reglas deterministas** contra la guía de estilo EST-001 (sin LLM, igual que RN-02/RN-06 en otros CU): secciones faltantes (para tipo "Procedimiento"), formato de montos (Q/USD), formato de fechas, siglas no definidas en su primer uso.
2. **LLM por párrafo**, con cita a EST-001 vía RAG (mismo patrón que `rag.busqueda.construir_citas`), `temperature=0`/`seed` fija (`rag.cliente_llm.generar_texto`, ya determinista desde el Bloque K7) y **streaming SSE** de los resultados conforme se van generando.

Acciones disponibles: Corregir | Aclarar | Formalizar. Tipos de documento: Correo | Memo | Procedimiento | Informe (solo "Procedimiento" activa la regla determinista de secciones del §2 de EST-001).

## 2. Decisiones de diseño tomadas en esta entrega (y por qué)

### 2.1 Streaming SSE sin pasar por Celery para la fase de LLM

El resto del sistema (CU-01, CU-05) usa `POST /documentos/.../completar` → encola en Redis → el worker procesa en segundo plano → el frontend hace *polling* del estado. Ese patrón no sirve tal cual para "streaming párrafo a párrafo": un worker de Celery no tiene una conexión HTTP abierta con el navegador para empujarle eventos.

Diseño adoptado (dos fases, mismo espíritu que el Bloque O6 de CU-05 — determinista primero, LLM después — pero con *push* en vez de *polling* para la fase 2):

1. La carga del documento (o del texto pegado) reutiliza **tal cual** `/documentos/iniciar` → `/partes` → `/completar` (RF-03, bitácora, retención de 90 días RN-08, permisos por área) — nada nuevo aquí, es exactamente el mismo mecanismo que ya usa CU-05.
2. El worker (`orquestador.tareas.ejecutar_analisis`, rama nueva `tipo_revision.nombre == "redaccion"`) hace **solo** la fase 1 (reglas deterministas, sin LLM) y persiste esos hallazgos de inmediato — igual que la fase 1 de CU-05.
3. El frontend, apenas aterriza en la pantalla de resultados, abre una conexión SSE a `GET /analisis/{id}/mejorar-stream`: ahí corre la fase 2 (LLM por párrafo, una llamada por párrafo -- no por lote, porque "párrafo a párrafo" es justamente el requisito de streaming) de forma síncrona dentro de esa misma conexión HTTP, persistiendo cada `Hallazgo` y emitiendo un evento SSE por párrafo resuelto.

**Esto es un patrón nuevo en el backend** (no existía ningún `StreamingResponse`/SSE antes de este bloque) pero no es un cambio de stack: FastAPI lo soporta de forma nativa (`starlette.responses.StreamingResponse`, `media_type="text/event-stream"`), sin agregar ninguna librería nueva.

**Trade-off aceptado:** si el navegador cierra la conexión SSE a medio camino (recarga, pérdida de red), los párrafos ya resueltos quedan persistidos pero los restantes no se generan automáticamente — el frontend debe poder reabrir la conexión. [POR CONFIRMAR] si se quiere un botón explícito "continuar mejorando" para ese caso, o si basta con que la fase 2 sea reentrante (reprocesa solo los párrafos que no tengan hallazgo todavía).

### 2.2 LLM por párrafo, no por lote

CU-01 y CU-05 agrupan varios hallazgos en una sola llamada al LLM (`explicacion.py::generar_explicaciones_lote`) para minimizar latencia total. CU-02 **no puede** usar ese patrón si quiere streaming real por párrafo: se hace una llamada a `generar_texto` por cada párrafo con contenido sustantivo (se saltan párrafos vacíos/solo blancos). Esto es más lento en total que un lote, pero es exactamente lo que pide "streaming párrafo a párrafo, primer párrafo ≤20s" (Bloque 4) — más llamadas pero cada una aparece en pantalla apenas termina, en vez de esperar todo el documento.

### 2.3 Guardia anti-alteración de cifras/fechas/nombres propios (bloque 1, punto 4)

El diagrama de secuencia preliminar (supuesto 1) decía "RNF-03 no aplica" a CU-02, porque ahí el LLM sí genera contenido (no es un cálculo numérico). El encargo de esta entrega pide explícitamente una guardia nueva, más estrecha que RNF-03 tal como existe hoy: no un "no inventes cifras" a nivel de prompt (eso ya se instruye igual que en `explicacion.py`), sino una **verificación automática post-LLM**: extraer del párrafo original y del párrafo sugerido (a) números/montos, (b) fechas, (c) nombres propios (heurística: palabras con mayúscula inicial que no son la primera palabra de una oración ni palabras comunes del propio texto -- **es una heurística, no NLP real; puede dar falsos positivos/negativos, documentado explícitamente en el código**). Si los conjuntos no coinciden exactamente, se descarta la sugerencia del LLM, se conserva el párrafo original, y el hallazgo queda marcado `estado="sin_cambio_por_seguridad"` con la razón.

Esto **actualiza el supuesto 1** del diagrama de secuencia preliminar (`docs/03-diseno/secuencia/cu-02-redaccion.md`), que queda desactualizado por esta decisión -- se corrige en este mismo bloque.

### 2.4 EST-001 como precondición real, no simulada

Confirmado al investigar: EST-001 **no existe hoy como `FuenteConocimiento` vigente** en ningún ambiente — solo existe el archivo de ejemplo `kb/plantillas/ejemplos/EST-001_Guia_Estilo_EJEMPLO.docx`, usado en pruebas. El supuesto 2 del diagrama preliminar lo dejaba `[POR CONFIRMAR]`. Esta entrega lo resuelve así: si el área no tiene ninguna guía de estilo vigente, el motor **igual corre** (reglas deterministas + LLM), pero el hallazgo del LLM queda **sin "Regla aplicada"** (ninguna cita, ningún fragmento RAG de respaldo) -- mismo criterio de resiliencia que ya usa `orquestador.pipeline_contable.cargar_catalogo` (RN-02) cuando un área no tiene catálogo cargado todavía: el sistema no se bloquea, degrada con una señal visible en vez de fallar. La demo de punta a punta de este bloque carga y aprueba EST-001 real (vía la pantalla del curador, CU-08, Bloque K5) para que sí haya citas en la verificación en vivo.

### 2.5 "Documento virtual" para texto pegado

No existe (ni hace falta) un concepto nuevo de "documento sin archivo": igual que CU-05, el texto pegado se empaqueta como un archivo `.txt` sintético (`texto-pegado.txt`) y sube por el mismo flujo multiparte de siempre -- hereda retención (RN-08) y permisos por área sin ningún cambio de modelo.

### 2.6 Conversor de salida (Bloque 3) -- fuera del alcance de este documento

Se detalla en el reporte del Bloque 3 cuando se ejecute: reutiliza `parsers.runs`/`parsers.correcciones` (mismo patrón que `ortografia.generar_corregido`) para `.docx`, y agrega un módulo nuevo `src/salidas/conversor.py` para `.txt`/`.xlsx`. La interfaz para `.pptx` (Sprint 3, fuera de esta entrega) se deja declarada pero sin implementar.

## 3. Reglas deterministas EST-001 (Bloque 1, punto 3) -- detalle

Basadas en el contenido real de `EST-001_Guia_Estilo_EJEMPLO.docx` (§1-§4, ver `curaduria.extraccion.extraer_fragmentos`):

| Regla | Dispara cuando | Severidad | Cita |
| --- | --- | --- | --- |
| RD-01 Secciones faltantes | tipo="Procedimiento" y falta alguna de: objetivo, alcance, responsables, actividades, registros, control de versiones (§2) | media | EST-001 §2 |
| RD-02 Formato de montos | un monto no sigue "Q 1,250.00" / "USD 500.00" (§3) | baja | EST-001 §3 |
| RD-03 Formato de fechas | una fecha no sigue "28 de septiembre de 2026" (texto) o "28/09/2026" (tabla) (§3) | baja | EST-001 §3 |
| RD-04 Sigla no definida | una sigla (2+ mayúsculas seguidas) aparece sin su forma completa entre paréntesis en su primer uso (§4) | baja | EST-001 §4 |

Estas reglas son texto/regex puro (sin LLM), mismo criterio que `validadores.contable.reglas` (RNF-03: ningún cálculo determinista lo hace el LLM).

## 4. Pendientes explícitos de este análisis

- [POR CONFIRMAR] Reconexión de la fase 2 (SSE) tras una desconexión a medio camino (ver §2.1).
- [POR CONFIRMAR] Si la organización quiere una guía de estilo EST-001 "de producción" con más reglas que el ejemplo de 4 secciones -- esta entrega solo puede citar lo que exista cargado.
- [POR CONFIRMAR] Umbral exacto de la heurística de "nombres propios" (§2.3) -- es deliberadamente conservador (prefiere descartar de más, no alterar de más), pero no se ha medido su tasa de falsos positivos con texto real todavía (PP nuevo, análogo a PP-03, queda para el Bloque 4).
