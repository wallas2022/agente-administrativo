# Guion de demo (sandbox local)

**Versión:** 0.4.0
**Fecha:** 2026-10-13
**Relacionado con:** docs/04-pruebas/estado-proyecto.md, docs/04-pruebas/resultados/, docs/05-prompts/P-12-usuarios-roles-menu-historial.md, docs/05-prompts/P-13-dashboard-administrador-consumo.md, docs/05-prompts/P-14-chat-base-conocimiento.md

Pasos para demostrar el agente en el ambiente local (Docker Desktop), con datos sintéticos (sin datos reales de la organización). Requiere el stack levantado:
```bash
docker compose --env-file .env.local -f infra/compose.yml -f infra/compose.local.yml up -d
```

Este documento se arma por secciones a medida que cada caso de uso llega a un estado demostrable. Hoy tiene las secciones de CU-06 (OCR), P-12 (menú por rol, historial, configuración), P-13 (Dashboard del Administrador) y P-14 (Chat de la Base de Conocimiento); el resto queda pendiente.

## Usuarios de prueba por rol

Todos los usuarios semilla (`comun/semillas.py`, solo con `APP_ENV=local` -- nunca en stage, ver "Pendiente" en docs/06-operacion/instalacion.md) comparten la contraseña `cambiar123`:

| Rol | Correo | Qué puede hacer en la demo |
| --- | --- | --- |
| Analista | analista@local | Chat, Nuevo análisis, Historial (solo lo propio o de su área) |
| Revisor | revisor@local | Chat, decide hallazgos (aceptar/rechazar/deshacer), Historial |
| Curador | curador@local | Chat, Base de conocimiento (fuentes, glosario), Historial |
| Auditor | auditor@local | Chat, Historial (todas las áreas), Bitácora, Ajustes autoaprobados -- todo de solo lectura |
| Administrador | administrador@local | Todo lo anterior, más Dashboard (consumo, usuarios, recursos, configuración) y Configuración (Usuarios, Roles y permisos, Áreas) |

## P-12 — Menú por rol, Historial y Configuración

1. **Menú por rol (HU-20)**: iniciar sesión con cada usuario de la tabla de arriba y mostrar que el menú lateral cambia según el rol -- p. ej. Revisor y Curador no ven "Nuevo análisis"; solo Administrador ve "Configuración" (desde P-14, "Chat" es la única opción que ven todos, sin excepción). Entrar a una URL sin el permiso correspondiente (p. ej. `/configuracion` como Analista) muestra "Sin acceso", no un redirect silencioso.
2. **Cambio de contraseña obligatorio (HU-25)**: crear un usuario nuevo desde Configuración → Usuarios y, en una sesión aparte, iniciar sesión con la contraseña temporal mostrada -- la pantalla de cambio de contraseña aparece antes que cualquier otra pantalla.
3. **Historial (HU-21)**: con `administrador@local`, abrir Historial y cambiar el alcance (Mis análisis / Mi área / Todas las áreas); mostrar los filtros de fecha, tipo de revisión, estado y archivo, y la duración/número de hallazgos de cada fila.
4. **Bitácora**: con `auditor@local`, abrir Bitácora y filtrar por usuario o acción -- señalar que nunca aparece una contraseña ni su hash, ni siquiera tras crear o editar un usuario.
5. **Configuración (HU-22, HU-23, HU-24)**: con `administrador@local`, crear un usuario (la contraseña temporal solo se muestra una vez), des/activar uno existente, y mostrar que el sistema rechaza desactivar al único Administrador activo; en Roles y permisos, marcar/desmarcar una casilla y mostrar que una fila protegida (p. ej. `administrador:usuarios:administrar`) no se puede tocar; en Áreas, mostrar que una con usuarios o documentos asociados no se puede eliminar.

## P-13 — Dashboard del Administrador

**Precondición**: haber corrido al menos un análisis real (cualquier tipo de revisión) con alguno de los usuarios de la tabla de arriba, para que la pestaña Consumo no muestre "sin datos todavía".

1. **Menú y permiso (HU-26..30, RF-22)**: iniciar sesión con `administrador@local` y mostrar que "Dashboard" aparece en el menú; con cualquier otro rol (p. ej. `analista@local`), la opción no aparece, y entrar directo a `/dashboard` por URL muestra "Sin acceso".
2. **Consumo (HU-26, HU-28)**: pestaña "Consumo" -- tarjetas de tokens/llamadas/timeouts, gráfico de tokens por día y los dos rankings (por caso de uso y por modelo); cambiar los filtros de fecha/caso de uso/modelo y mostrar que los números cambian.
3. **Usuarios (HU-27)**: pestaña "Usuarios" -- tabla de consumo por usuario y botón "Exportar CSV".
4. **Recursos (HU-29)**: pestaña "Recursos" -- si el stack corre sin el perfil `observabilidad` (el caso normal en esta demo), mostrar el mensaje claro de "Prometheus apagado en este entorno" en vez de un error; la sección de Ollama (modelos en memoria/instalados) sí funciona siempre, sin depender de Prometheus.
5. **Configuración (HU-30)**: pestaña "Configuración" -- mostrar la lista de variables visibles y señalar que ninguna es una contraseña, clave o token (RNF-17).

## P-14 — Chat de la Base de Conocimiento

**Precondición**: la Base de Conocimiento tiene al menos una fuente vigente indexada (CU-08) para que el chat pueda citar algo real -- de lo contrario responderá correctamente "no tengo información", pero la demo es menos ilustrativa.

1. **Pantalla de inicio para todos los roles (HU-33)**: iniciar sesión con cualquier usuario de la tabla de arriba -- el chat es lo primero que se ve, sin excepción de rol.
2. **Pregunta con respuesta citada (HU-31)**: escribir una pregunta sobre un tema cubierto por una fuente vigente -- la respuesta cita la fuente, versión y sección/página. **Aviso para la demo**: la respuesta real no es instantánea (el LLM corre en CPU sin GPU) -- puede tardar un par de minutos; el aviso "El asistente está pensando…" de la pantalla existe justamente para eso, no asumir que se colgó.
3. **Pregunta sin respuesta en la base de conocimiento**: preguntar algo fuera de cualquier fuente indexada -- el chat dice explícitamente que no tiene información, sin inventar (RNF-03).
4. **Conversación con memoria**: hacer una pregunta de seguimiento relacionada con la anterior -- el chat usa el historial como contexto.
5. **Historial de conversaciones (HU-34)**: con "Nueva conversación", abrir una conversación distinta; la lista de la izquierda muestra ambas, cada una solo visible para el usuario que la creó.
6. **Adjuntar una imagen o documento (HU-32)**: adjuntar una imagen (OCR) o un Word/Excel/PDF a una pregunta -- el chat usa su contenido para responder esa pregunta puntual; señalar que ese archivo no queda en Base de Conocimiento (revisar esa pantalla después y confirmar que no aparece).
7. **"Nuevo análisis" sigue disponible**: con `analista@local` o `administrador@local`, mostrar que "Nuevo análisis" sigue siendo una opción de menú aparte, con el mismo formulario de siempre.

## CU-06 — Imagen a texto (OCR)

**Precondición**: tener a mano una imagen (png/jpg/tiff/bmp) o PDF escaneado. Para la demo se puede generar uno sintético con `tests/dataset/generar_cu06.py` (texto propio, sin datos reales) -- genera `tests/dataset/cu-06/legible_render_limpio.png`, entre otros.

1. **Nuevo análisis** → tipo de revisión "Imagen a texto" → seleccionar el archivo (o varios: se crea un análisis por archivo) → "Iniciar análisis".
2. **Agente trabajando**: mientras el worker procesa, la bitácora en vivo muestra "Análisis iniciado" y, al terminar el motor, "OCR completado — N página(s), confianza media X%, N ilegible(s)" (el resumen real del motor, no un contador de progreso por página -- ver docs/04-pruebas/resultados/local-cu06-bloque3.md, decisión de alcance #1).
3. **Resultado**: vista lado a lado -- la imagen original a la izquierda, el texto reconocido a la derecha. Si el motor marcó alguna palabra con confianza baja/media, aparece resaltada en rojo/amarillo.
   - Si el documento es demasiado ilegible para reconocer nada con confianza, se muestra un aviso en vez de un texto inventado (RN-06, PP-06) -- probar con una foto muy desenfocada o de muy bajo contraste para ver este caso.
4. **Editar texto**: botón "Editar texto" → corregir manualmente → "Guardar". El cambio queda persistido (y auditado en bitácora como "ocr_edicion_manual").
5. **Copiar** / **Descargar .txt** / **Descargar .docx** (esta última con las palabras dudosas resaltadas en el propio Word).
6. **Continuar con "Revisar ortografía" o "Mejorar redacción"**: toma el texto ya reconocido (con las ediciones manuales si las hubo) y abre un análisis nuevo de CU-05 o CU-02 sobre ese mismo texto -- sin tener que volver a cargar nada.

**Qué NO mostrar como garantizado**: el dataset de prueba es sintético (texto renderizado por computadora); sobre una fotografía real de un documento físico el CER puede ser mayor que en esta demo (ver [docs/04-pruebas/casos-prueba/PP-05.md](casos-prueba/PP-05.md), limitación documentada).

## Pendiente

- Secciones de CU-01 (Excel contable), CU-02 (redacción), CU-05 (ortografía) y CU-08 (base de conocimiento) -- ya tienen funcionalidad documentada en `docs/04-pruebas/resultados/`, pero no un guion de demo paso a paso todavía.
