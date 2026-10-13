# Resultados — P-15 (Aprobación de fuentes y Garage en stage)

**Versión:** 0.1.0
**Fecha:** 2026-10-13
**Relacionado con:** docs/05-prompts/P-15-aprobacion-fuentes-y-garage.md, ADR-006 v2, ADR-010

## Bloque 1 — Errores visibles

| Ruta | Cambio | Pruebas |
| --- | --- | --- |
| `src/comun/almacenamiento.py` | `ObjetoNoEncontradoError`; `descargar_objeto` la lanza cuando el objeto no existe (NoSuchKey/404) | ok |
| `src/api/main.py` | Manejadores: objeto ausente → 409 con "El archivo de la fuente no está en el almacenamiento; súbalo de nuevo"; `httpx.TimeoutException` → 504; cualquier otra excepción → 500 JSON `{error, detalle}` con cabeceras CORS (solo para orígenes permitidos) y sin filtrar el mensaje interno (se registra con traza) | ok |
| `src/ui/src/utils/errores.ts` | `mensajeDeError` (lee `detalle`/`detail`/422) y `MENSAJE_SIN_CONEXION` | ok |
| `src/ui/src/paginas/BaseConocimiento.tsx`, `Chat.tsx` | Aprobar, vista previa, subida de fuente/plantilla y chat muestran el mensaje del servidor en vez de textos genéricos; aprobar captura errores de red | ok |
| `tests/unit/test_errores_visibles.py`, `src/ui/src/utils/errores.test.ts` | 5 + 4 pruebas nuevas | ok |

Métricas: pytest 715 pasan (cobertura 94 %), mypy sin errores, vitest 127 pasan, tsc sin errores, oxlint solo advertencias preexistentes.

Nota: la respuesta incluye `detail` además de `detalle` para que la UI existente (que leía `detail`) siga funcionando.

## Bloque 2 — Fragmentación

| Ruta | Cambio | Pruebas |
| --- | --- | --- |
| `src/curaduria/extraccion.py` | Dentro de cada sección/página se divide por párrafos (luego oraciones y, en último caso, palabras) con tope `FRAGMENTO_MAX_TOKENS`=450 y solapamiento `FRAGMENTO_SOLAPE_TOKENS`=60, ambos configurables por variable de entorno. Un cambio de página en PDF abre un fragmento nuevo con su `pagina` y conserva la `seccion`. Se limpian líneas de índice con puntos guía, encabezados/pies repetidos (texto corto en 3 o más páginas, ignorando números) y caracteres de control. | ok |
| `tests/unit/test_curaduria_fragmentacion.py` | 13 pruebas: tope, solapamiento, sin pérdida de contenido, párrafo gigante, palabra sin espacios, configuración por entorno, páginas, limpieza y PDF de 300 páginas. | ok |

- `fuente_id` y `version` los agrega `indexar_fuente` al payload de cada fragmento; `seccion` y `pagina` se conservan desde la extracción. El contenido que va a embeddings es exactamente `fragmento.contenido`, ya acotado.
- Los tokens se estiman a ~3 caracteres por token, sin tokenizador (conservador, sobrestima el español con bge-m3). [POR CONFIRMAR] contra el tokenizador real de bge-m3 en stage.
- Métricas: pytest 728 pasan (cobertura 94 %), mypy sin errores.
