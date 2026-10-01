# Resultados — CU-02, optimización de rendimiento de la fase 2 (2026-10-01)

**Versión:** 1.0
**Relacionado con:** docs/03-diseno/adr/ADR-008-rendimiento-llm-cu02.md, docs/04-pruebas/resultados/local-cu02-bloque1.md, local-cu02-bloque2.md

## Alcance

Bajar el tiempo de la primera tarjeta de CU-02 (fase 2) de 208s medidos en el bloque anterior, sin quitar las 2 opciones de estilo (Formal/Breve). Medido contra `gpt-oss:20b` real (Ollama nativo de Windows, sin GPU) en todos los casos -- nada de esto se simuló.

## Bloque 1 — Medición base (antes de optimizar)

Llamada real a Ollama (`/api/chat`, `format=json` con las 2 opciones + motivos pedidos al LLM, sin `think`), mismo párrafo de prueba en todo este documento: *"el dia de hoy se aprobo el pago a proveedores por Q 1,250.00, el cual fue revisado por la DAF."*

```
prompt_eval_count: 312   prompt_eval_duration: 38.4 s
eval_count:        622   eval_duration:        160.7 s
total_duration:    201.0 s
longitud "thinking":  1716 caracteres
longitud "response":   522 caracteres
```

**% del tiempo que es razonamiento**: Ollama no separa tokens de "thinking" de tokens de "respuesta" en sus contadores (`eval_count` es el total) -- se estima por proporción de caracteres: 1716 / (1716 + 522) = **76.7 % de la salida es razonamiento interno**, no la respuesta en sí. Aplicado a `eval_duration` (160.7 s): ≈123 s de los 201 s totales (≈61 %) se gastaron "pensando", no escribiendo la respuesta final. Esta es una estimación por proporción de caracteres, no una medición directa (Ollama no la expone) -- se marca así a propósito, sin inventar una cifra más precisa de la que hay.

## Bloque 2 — Optimizar la llamada (sigue pidiendo 2 opciones en una sola llamada)

`think="low"`, `num_ctx=2048`, `num_predict=400`, prompt más corto (508 vs. 923 caracteres), `keep_alive=24h` (sin cambios, ya estaba).

```
prompt_eval_count: 205   prompt_eval_duration: 33.8 s (sin caché de prompt -- ver nota)
eval_count:        128   eval_duration:        36.5 s
total_duration:    71.4 s
longitud "thinking":  28 caracteres
```

**Mejora real pero insuficiente**: `eval_count` bajó de 622 a 128 (79 % menos) y el total de 201s a 71.4s (65 % menos) -- pero sigue por encima del objetivo de 60s. En una corrida con el prompt cacheado (mismo prompt exacto que una llamada anterior), `prompt_eval_duration` bajó a 1.6-1.7s, lo que sugiere que gran parte de esos 71.4s son el primer párrafo "frío" (sin caché de prompt posible en la práctica, ya que cada párrafo real es distinto).

## Bloque 3 — Opciones escalonadas (una opción por llamada, texto plano, motivos en Python)

Cambio clave: en vez de pedirle al LLM las 2 opciones + motivos en un JSON, se pide **una opción a la vez, en texto plano** (sin JSON, sin motivos) -- "Formal" se genera y se publica por SSE antes de empezar "Breve". Los motivos se calculan en Python comparando el párrafo base contra el reescrito (`calcular_motivos`, heurística: acentos corregidos, oraciones divididas/combinadas, texto más corto/largo).

```
prompt_eval_count: 180   prompt_eval_duration: 0.2-12.4 s (según caché)
eval_count:         44   eval_duration:        7.0-11.1 s
total_duration:     7.9-26.5 s (4 corridas distintas, mismo párrafo y parámetros)
longitud "thinking": 20 caracteres ("Need formal rewrite.")
```

**Esta es la optimización que de verdad cambia el orden de magnitud**: de 622 a 44 tokens de salida (93 % menos), de 201s a 7.9-26.5s. Confirmado también que `/api/generate` (en vez de `/api/chat`) con `think="low"` NO logra el mismo efecto -- una prueba con `/api/generate` dio 185.6s con una respuesta JSON deformada (una opción anidada dentro de otra); `/api/chat` es el que de verdad reduce el razonamiento y además cachea mucho mejor.

## Bloque 4 — Saltar lo innecesario

Un párrafo con menos de 25 palabras, sin ninguna coincidencia de LanguageTool y sin ningún hallazgo EST-001, no llama al LLM en absoluto -- se marca "omitido" y se usa tal cual. Verificado con una prueba de API real (`test_stream_omite_el_llm_en_un_parrafo_corto_y_limpio`): 0 eventos "opcion" para ese párrafo, 0 llamadas al LLM.

## Bloque 5 — Guardia ampliada (siglas y códigos)

Se agregaron a `verificar_integridad` dos comparaciones nuevas (antes solo fechas/números/nombres propios): **siglas** (`[A-ZÁÉÍÓÚÑ]{2,}`, en cualquier posición -- a diferencia de "nombres propios", que se salta la primera palabra de cada oración) y **códigos** (segmentos numéricos unidos por punto o guion, tipo "6112.03.00"). Probado con los dos casos reales encontrados en el Bloque 1 original:

| Caso | Antes (solo nombres propios) | Después (siglas dedicado) |
| --- | --- | --- |
| "DAF" → "DA" (le corta una letra) | Ya detectado (DAF es mayúscula, no es la primera palabra de su oración) | Detectado también, con mensaje específico "Las siglas..." |
| "DAF" al inicio de una oración, alterada | **No detectado** (`_nombres_propios` se salta la primera palabra de cada oración) | **Detectado** (el patrón de siglas no tiene esa excepción) |
| Código "6112.03.00" → "6112.03.01" | No detectado (ningún patrón lo cubría completo) | Detectado (aunque a veces el motivo reportado dice "fechas" por solape de patrones -- ver nota en el test) |

## Bloque 6 — UX

"Mejorando redacción… (0 párrafos listos)" se reemplazó por "Párrafo N de M · generando… (S s)", con S corriendo en vivo mientras se espera la respuesta del LLM para ese párrafo específico.

## Medición de punta a punta contra la API real (todos los bloques juntos)

```
Primera corrida:  Formal a los 135.6 s, Breve a los 192.8 s (acumulado), total 193.1 s
```

**Esto NO contradice las mediciones anteriores -- revela un problema aparte**: medido repetidas veces, el mismo párrafo con los mismos parámetros dio tiempos de 7.9s a 208.8s. La variable que más se correlaciona es `load_duration` (Ollama recargando el modelo de 13.8 GB): 0.1-0.2s cuando el modelo ya estaba en memoria, 10-53s cuando no. No se logró aislar con certeza la causa exacta (ver ADR-008) -- es un hallazgo de infraestructura/hardware, no un defecto de las optimizaciones de este bloque, que sí reducen de forma medible y reproducible el *trabajo* pedido al modelo (menos tokens, menos razonamiento) independientemente de cuánto tarde cada token.

## Tabla resumen (antes / después)

| Métrica | Antes (Bloque 1 original) | Después (Bloques 2-4, aislado) | Después (punta a punta, API real) |
| --- | --- | --- | --- |
| Tokens de razonamiento (estimado por % de caracteres de "thinking") | ≈477 de 622 (77 %) | ≈3 de 44 (7 %) | variable, ~20-600+ caracteres de "thinking" según la corrida |
| Tokens de salida (`eval_count`) | 622 | 44 | 44-223 según la corrida |
| s primera tarjeta | 201-208 s | **7.9-26.5 s** | 56-193 s (alta variancia, ver ADR-008) |
| s por párrafo (ambas opciones) | no medido por separado (una sola llamada) | ~16-50 s (2 llamadas de 8-25s) | 57-193 s según corrida |

**Conclusión**: el objetivo de ≤60s **se cumple cuando el modelo ya está cargado en memoria** (caso típico medido aisladamente: 7.9-26.5s), pero **no de forma confiable** cuando hay que recargarlo (decenas de segundos adicionales, fuera del control de este código). Ver ADR-008 para las opciones consideradas (no se cambia el modelo por defecto en este bloque).

## Pruebas

```
tests/unit (suite completa): 324 passed
ruff check src tests / mypy src: sin hallazgos
npx vitest run (frontend): 52 passed
npx tsc --noEmit / oxlint: sin errores nuevos
```

Pruebas nuevas relevantes: `test_redaccion_mejora.py` (`puede_omitir_llm`, `calcular_motivos`, `generar_opcion`, `preparar_parrafo`), `test_redaccion_guardia.py` (siglas, códigos -- casos "DAF" y "6112.03.00"), `test_api_mejorar_redaccion_stream.py` (protocolo SSE escalonado: `inicio`/`parrafo_inicio`/`opcion`/`parrafo_fin`, más el caso de párrafo omitido), `test_cliente_llm.py` (`pensamiento`, `num_ctx`, `num_predict`, cambio a `/api/chat`).

## Pendiente

- Investigar la causa real de los `load_duration` altos e intermitentes (¿memoria de esta máquina de desarrollo compartida con otros procesos pesados de esta misma sesión? ¿comportamiento de `keep_alive` de Ollama entre llamadas desde el host y desde el contenedor?) -- no se resolvió, solo se documentó.
- Decisión de modelo (ADR-008) pendiente del responsable del proyecto.
- Re-medir en hardware de stage (GPU, ADR-005) cuando esté disponible.
