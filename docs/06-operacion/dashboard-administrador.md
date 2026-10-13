# Dashboard del Administrador

**Versión:** 0.1.0
**Fecha:** 2026-10-13
**Relacionado con:** HU-26..30, RF-21, RF-22, RNF-15..18, docs/06-operacion/monitoreo.md, docs/04-pruebas/resultados/local-P13-bloque1.md..bloque5.md

Guía para el Administrador: qué muestra cada pestaña del menú "Dashboard" (visible solo con el permiso `dashboard:ver`) y qué hacer cuando aparece una alerta. Distinto de [monitoreo.md](monitoreo.md), que describe la infraestructura de observabilidad (Prometheus/Grafana/Langfuse) para quien administra el servidor -- este documento es para quien usa la pantalla del agente, sin necesitar saber PromQL.

## Pestaña Consumo (HU-26, HU-28)

Qué muestra: tokens de entrada/salida/totales del período, llamadas al LLM, tokens/s promedio, % de llamadas con timeout, un gráfico de tokens por día y dos rankings (por caso de uso y por modelo) con la duración media del análisis asociado.

Filtros: rango de fechas, área, caso de uso (`contable`, `ortografia`, `redaccion`, `embeddings_kb`, `embeddings_busqueda`) y modelo.

Si aparece "Todavía no hay datos de consumo para estos filtros": no es un error -- el registro de uso (RF-21) solo existe desde que se instaló esta función (2026-10-12); no hay datos de análisis anteriores.

## Pestaña Usuarios (HU-27)

Tabla de consumo agregado por usuario (área, número de análisis, tokens, tiempo de LLM, timeouts), con un botón "Exportar CSV" para compartir el detalle fuera del agente.

## Pestaña Recursos (HU-29)

Host (CPU, memoria, disco, carga), por contenedor (CPU, memoria vs. su límite) y Ollama (modelos en memoria e instalados). Se actualiza sola cada 30 segundos.

Si aparece "Las métricas de host/por contenedor no están disponibles (Prometheus apagado en este entorno)": normal en local, donde Prometheus/node-exporter/cAdvisor son opcionales (`--profile observabilidad`, ADR-009). En stage deberían estar siempre activos -- si aparece ahí, avisar a TI.

### Qué hacer ante cada alerta

Las alertas (si las hay) se muestran siempre arriba de esta pestaña.

| Alerta | Condición | Qué hacer |
| --- | --- | --- |
| Disco al X % | Disco usado ≥ 70 % del total | Avisar a TI; revisar la retención de documentos (RN-08) y si hay archivos más grandes de lo esperado (R-07). No es necesario actuar de inmediato, pero sí dar seguimiento esa semana. |
| Memoria de Ollama al X % de su límite | El contenedor de Ollama usa ≥ 90 % de su límite de memoria | Puede provocar que un análisis falle por falta de memoria. Revisar si hay varios modelos cargados a la vez (pestaña Recursos → Ollama → "modelos en memoria") y si `OLLAMA_KEEP_ALIVE` (pestaña Configuración) es más largo de lo necesario. Si persiste, avisar a TI para revisar el límite del contenedor. |
| X % de llamadas al LLM con timeout en las últimas 24 h | Más del 10 % de las llamadas al LLM/embeddings de las últimas 24 h terminaron en timeout | El análisis que falló por timeout no se pierde silenciosamente (queda registrado), pero el usuario que lo generó no recibirá resultado. Revisar la pestaña Usuarios para identificar a quién afectó, y si coincide con un pico de uso o con un modelo más lento de lo normal (pestaña Consumo, filtrar por modelo). |

## Pestaña Configuración (HU-30)

Muestra la versión de la app, el commit (si se compiló con esa información) y una lista fija de variables de configuración -- nunca contraseñas, claves ni tokens (RNF-17, lista blanca explícita en `comun/dashboard.py`). Es de solo lectura: para cambiar algo hay que editar el `.env` del ambiente correspondiente y reiniciar, no desde esta pantalla.

## Quién puede ver esta pantalla

Solo el rol Administrador (permiso `dashboard:ver`, protegido -- no se puede quitar ni asignar a otro rol desde Configuración → Roles y permisos). El resto de roles no ve la opción "Dashboard" en el menú, y si intentan entrar a la URL directamente o llamar a los endpoints `/admin/dashboard/*`, reciben "Sin acceso" / `403`.
