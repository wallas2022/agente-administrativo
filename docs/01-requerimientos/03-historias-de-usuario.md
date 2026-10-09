# Historias de usuario — Agente Administrativo

**Versión:** 0.8
**Fecha:** 2026-10-09
**Relacionado con:** docs/01-requerimientos/02-casos-de-uso.md, docs/01-requerimientos/01-requerimiento-formal.md, docs/04-pruebas/plan-pruebas-prototipo.md, docs/05-prompts/P-12-usuarios-roles-menu-historial.md

Formato: Como / quiero / para, con criterios de aceptación en Gherkin (Dado/Cuando/Entonces). La numeración HU-01 a HU-14 se fijó para que coincida con las referencias del plan de pruebas ([docs/04-pruebas/plan-pruebas-prototipo.md](../04-pruebas/plan-pruebas-prototipo.md) §2).

---

## HU-01 — Carga de documento y selección de revisión

**CU:** CU-01 a CU-06 · **RF:** RF-03, RF-04, RF-05 · **Entrega:** 1

Como **Analista**, quiero cargar un documento (hasta 1 GB, con carga reanudable) y elegir el tipo de revisión y las fuentes a consultar, para iniciar cualquiera de los análisis disponibles.

```gherkin
Característica: Carga y selección de revisión

  Escenario: Carga exitosa de un archivo grande
    Dado que selecciono un archivo de hasta 1 GB
    Cuando la carga se interrumpe y la reanudo
    Entonces el sistema completa la carga sin corromper el archivo (PP-18)

  Escenario: Selección de tipo de revisión y fuentes
    Dado que cargué un documento
    Cuando selecciono el tipo de revisión y las fuentes de conocimiento a consultar
    Entonces el sistema inicia el análisis correspondiente (CU-01 a CU-06)
```

---

## HU-02 — Permisos por área

**CU:** CU-09 · **RF:** RF-02 · **Entrega:** 1

Como **Administrador**, quiero administrar usuarios, roles y permisos por área, para que cada usuario solo acceda a los documentos de su área.

```gherkin
Característica: Permisos por área

  Escenario: Acceso denegado a documento de otra área
    Dado que un usuario del área "Contabilidad" está autenticado
    Cuando intenta abrir un documento cargado por el área "Legal"
    Entonces el sistema deniega el acceso (PP-10: 0 accesos a documentos de otra área)
```

---

## HU-03 — Detección de descuadre contable

**CU:** CU-01 · **RF:** RF-06 · **Entrega:** 1

Como **Analista**, quiero cargar un archivo Excel contable, para que el sistema detecte automáticamente descuadres, cuentas inválidas y duplicados antes de enviarlo a revisión.

```gherkin
Característica: Detección de descuadre contable

  Escenario: Excel con descuadre en partidas
    Dado que cargo un archivo Excel con una hoja contable
    Y la hoja contiene una partida cuyo débito no coincide con su crédito
    Cuando el sistema procesa el archivo
    Entonces el sistema genera un hallazgo con severidad, celda/hoja, explicación y corrección sugerida
    Y el documento queda en estado "con_hallazgos"

  Escenario: Excel con cuenta contable duplicada
    Dado que una hoja contable tiene dos partidas con la misma cuenta y período duplicados
    Cuando el sistema procesa el archivo
    Entonces el sistema genera un hallazgo indicando las filas duplicadas

  Escenario: Excel sin descuadres
    Dado que cargo un archivo Excel con una hoja contable balanceada
    Cuando el sistema procesa el archivo
    Entonces el sistema no genera hallazgos de descuadre (PP-01: recall ≥ 90 % de errores sembrados)
```

---

## HU-04 — Revisión ortográfica multi-formato con ubicación exacta

**CU:** CU-05 · **RF:** RF-10 · **Entrega:** 1

Como **Analista**, quiero corregir la ortografía de mis documentos en cualquier formato soportado con ubicación exacta, para reducir errores de redacción sin perder contexto.

```gherkin
Característica: Corrección ortográfica

  Escenario: Documento con errores ortográficos
    Dado que cargo un documento con errores ortográficos en español
    Cuando el sistema ejecuta la revisión ortográfica
    Entonces el sistema presenta cada error con su sugerencia y ubicación exacta (celda, párrafo, diapositiva o página)
    Y el recall es ≥ 90 % con falsos positivos ≤ 10 % (PP-03)
```

---

## HU-05 — Conversión de imagen a texto (OCR)

**CU:** CU-06 · **RF:** RF-11 · **Entrega:** 2

Como **Analista**, quiero convertir imágenes y PDF escaneados a texto editable, para poder validarlos igual que un documento digital.

```gherkin
Característica: Extracción OCR

  Escenario: Imagen legible
    Dado que cargo una imagen escaneada de un documento administrativo
    Cuando el sistema ejecuta el proceso de OCR
    Entonces el sistema extrae el texto con precisión de caracteres ≥ 95 % (PP-05)

  Escenario: Imagen de baja calidad
    Dado que la imagen cargada es ilegible o de muy baja calidad
    Cuando el sistema ejecuta el proceso de OCR
    Entonces el sistema informa que el texto es ilegible en lugar de inventarlo (PP-06)
```

---

## HU-06 — Revisión de redacción PDF/Word

**CU:** CU-02 · **RF:** RF-07 · **Entrega:** 1

Como **Analista**, quiero recibir sugerencias de redacción sobre mis documentos PDF/Word, para mejorar tono y estructura antes de enviarlos a revisión.

```gherkin
Característica: Revisión de redacción

  Escenario: Documento con oraciones poco claras
    Dado que cargo un documento Word con un párrafo ambiguo
    Cuando el sistema analiza el documento contra la guía de estilo
    Entonces el sistema sugiere una redacción alternativa
    Y la sugerencia indica severidad, ubicación exacta y explicación
```

---

## HU-07 — Detección de normativa desactualizada

**CU:** CU-03 · **RF:** RF-08 · **Entrega:** 2

Como **Analista**, quiero que el sistema me indique cuándo un documento cita normativa desactualizada, para poder corregirla antes de enviarla a revisión.

```gherkin
Característica: Detección de normativa desactualizada

  Escenario: Documento cita una versión vencida de la normativa
    Dado que el documento referencia una norma con fecha de vigencia anterior a la vigente en la base de conocimiento
    Cuando el sistema analiza el documento
    Entonces el sistema genera un hallazgo citando la fuente vigente correspondiente

  Escenario: No existe fuente vigente equivalente
    Dado que el documento referencia una norma sin equivalente en la base de conocimiento
    Cuando el sistema analiza el documento
    Entonces el sistema marca el hallazgo como "sin fuente de contraste"
```

---

## HU-08 — Evaluación de checklist/control

**CU:** CU-04 · **RF:** RF-09 · **Entrega:** 2

Como **Analista**, quiero evaluar un checklist/control administrativo contra la plantilla vigente, para verificar el cumplimiento antes de someterlo a revisión.

```gherkin
Característica: Evaluación de checklist

  Escenario: Checklist con ítems incumplidos
    Dado que cargo un checklist con ítems que no cumplen la plantilla vigente
    Cuando el sistema evalúa el documento
    Entonces el sistema marca cada ítem como "cumple", "no cumple" o "revisar" con explicación
```

---

## HU-09 — Segregación de funciones en aprobación (configurable desde v0.9)

**CU:** CU-07 · **Relacionado con:** RNF-02 · **Entrega:** 1

**v0.9 (decisión del responsable del proyecto):** la segregación de funciones pasó de obligatoria a **configurable** mediante `SEGREGACION_APROBACION` (por defecto `false` = autoaprobación permitida). El escenario original (bloqueo) se conserva para cuando `SEGREGACION_APROBACION=true`; se agrega el escenario por defecto, donde lo que importa es que la autoaprobación quede siempre registrada.

Como **Revisor/Aprobador**, quiero poder decidir sobre hallazgos de documentos que yo mismo cargué cuando la organización lo permita, y que esa decisión quede siempre registrada, para no bloquear el trabajo sin perder trazabilidad.

```gherkin
Característica: Segregación de funciones configurable

  Escenario: SEGREGACION_APROBACION=false (por defecto) -- autoaprobación permitida y registrada
    Dado que un usuario con rol Revisor o Administrador cargó un documento
    Cuando ese mismo usuario decide sobre los hallazgos del documento
    Entonces el sistema permite la decisión
    Y la bitácora registra usuario, rol, fecha, hallazgo y la marca "autoaprobado"
    Y el ajuste aparece en el reporte "Ajustes autoaprobados" (CU-01) visible para Jefatura/Auditor (PP-09: 0 aprobaciones sin registro)

  Escenario: SEGREGACION_APROBACION=true -- el cargador intenta aprobar su propio documento
    Dado que un usuario cargó un documento
    Cuando ese mismo usuario intenta decidir sobre los hallazgos del documento
    Entonces el sistema bloquea la acción
    Y exige que la decisión la tome un usuario distinto con rol Revisor/Aprobador
```

---

## HU-10 — Documento corregido en su formato original

**CU:** CU-01, CU-02, CU-05, CU-07 · **RF:** RF-13, RF-14 · **Entrega:** 1

Como **Revisor/Aprobador**, quiero aceptar, rechazar o deshacer cada hallazgo y obtener el documento corregido en su formato original, para liberar solo lo que realmente corresponde aprobar sin dañar el archivo.

```gherkin
Característica: Decisión y generación del documento corregido

  Escenario: Aceptar hallazgos y generar documento corregido
    Dado que un documento tiene hallazgos pendientes de decisión
    Cuando el Revisor acepta un subconjunto de los hallazgos
    Entonces el sistema genera el documento corregido en su formato original aplicando solo las correcciones aceptadas
    Y el archivo abre sin daño y conserva sus estilos originales (PP-04: 100 %)
```

---

## HU-11 — Gestión de la base de conocimiento (fuentes vigentes)

**CU:** CU-08 · **RF:** RF-16, RF-17 · **Entrega:** 1

Como **Curador de conocimiento**, quiero cargar, versionar y aprobar fuentes normativas, reglas y glosario de mi área, para mantener la base de conocimiento vigente y gobernada.

```gherkin
Característica: Gestión de la base de conocimiento

  Escenario: Carga de una nueva fuente normativa
    Dado que subo un nuevo documento normativo con su versión y fecha de vigencia
    Cuando apruebo la fuente como Curador
    Entonces la fuente queda reindexada y disponible para el análisis a partir de su fecha de vigencia
    Y la versión anterior queda marcada como no vigente sin eliminarse (PP-08: 0 citas a versiones obsoletas)

  Escenario: Actualización del glosario interno
    Dado que agrego una sigla o nombre propio al glosario interno de mi área
    Cuando el módulo de ortografía procesa un documento de esa área
    Entonces ese término no se marca como error ortográfico
```

---

## HU-12 — Evidencia y reporte de hallazgos

**CU:** CU-01 a CU-04 (transversal) · **RF:** RF-12, RF-15 · **Entrega:** 1

Como **Revisor/Aprobador**, quiero ver severidad, ubicación, explicación, corrección sugerida y fuente citada de cada hallazgo, y poder generar un reporte PDF, para decidir con criterio informado y documentar la revisión.

```gherkin
Característica: Evidencia y reporte de hallazgos

  Escenario: Hallazgo con fuente asociada
    Dado que existe un hallazgo generado por el análisis de un documento
    Cuando el Revisor/Aprobador abre el hallazgo
    Entonces el sistema muestra severidad, ubicación, explicación, corrección sugerida y la fuente que lo respalda
    Y la fuente citada es correcta y vigente en al menos el 95 % de los hallazgos (PP-07)

  Escenario: Generar reporte PDF
    Dado que un documento tiene hallazgos resueltos
    Cuando el Revisor solicita el reporte
    Entonces el sistema genera un PDF con todos los hallazgos y sus decisiones
```

---

## HU-13 — Bitácora de auditoría

**CU:** CU-10 · **RF:** RF-19 · **Entrega:** 1

Como **Auditor**, quiero que toda acción relevante quede registrada en bitácora, para verificar cumplimiento y trazabilidad sin excepciones.

```gherkin
Característica: Bitácora de auditoría

  Escenario: Registro completo de acciones
    Dado que se ejecutan acciones de carga, análisis, revisión y aprobación/rechazo
    Cuando el Auditor revisa la bitácora del período
    Entonces ninguna de esas acciones aparece sin registro (PP-11: 0 acciones sin registro)
```

---

## HU-14 — Autenticación, notificación y consulta de historial

**CU:** CU-09, CU-07, CU-10 · **RF:** RF-01, RF-18, RF-20 · **Entrega:** 1

Como **usuario del sistema**, quiero autenticarme con mi cuenta de la organización, recibir notificación cuando se me asigna una revisión, y poder consultar el historial de análisis con filtros, para trabajar sin fricción y con visibilidad de lo ya procesado.

```gherkin
Característica: Autenticación, notificación y consulta de historial

  Escenario: Usuario sin rol asignado intenta acceder
    Dado que un usuario se autentica correctamente (AD/LDAP o local)
    Y no tiene ningún rol asignado en el sistema
    Cuando intenta acceder a una funcionalidad
    Entonces el sistema deniega el acceso

  Escenario: Notificación al enviar a revisión
    Dado que un Analista finaliza un análisis
    Cuando lo envía a un Revisor específico
    Entonces el sistema notifica al Revisor asignado

  Escenario: Consulta de historial con filtros
    Dado que existen análisis registrados con distintos usuarios, áreas, tipos, estados y fechas
    Cuando un usuario autorizado consulta el historial aplicando filtros
    Entonces el sistema muestra solo los registros que coinciden con los filtros
```

---

Numeración HU-15 a HU-19 reservada para otra iniciativa (no definida en este documento). HU-20 en adelante: P-12 (menú por permisos, historial, configuración), 2026-10-09.

## HU-20 — Menú según mi rol

**CU:** CU-09 · **RF:** RF-02, RNF-02 · **Entrega:** 1

Como **usuario del sistema**, quiero ver en el menú solo las opciones que mi rol me permite usar, para no toparme con pantallas que de todas formas me van a rechazar.

```gherkin
Característica: Menú y rutas según permisos

  Esquema del escenario: El menú muestra solo lo permitido
    Dado que inicio sesión como "<rol>"
    Entonces veo en el menú exactamente: "<opciones>"

    Ejemplos:
      | rol            | opciones                                                              |
      | Analista       | Nuevo análisis, Historial                                             |
      | Revisor        | Historial                                                             |
      | Curador        | Base de conocimiento, Historial                                      |
      | Auditor        | Historial, Bitácora, Ajustes autoaprobados                           |
      | Administrador  | Historial, Bitácora, Ajustes autoaprobados, Configuración            |

  Escenario: URL directa sin permiso
    Dado que un usuario no tiene el permiso de una pantalla
    Cuando entra directamente a esa URL
    Entonces ve la página "Sin acceso"
    Y el endpoint correspondiente responde 403 si lo llama de todas formas
```

## HU-21 — Consultar mi historial de análisis

**CU:** CU-10 · **RF:** RF-18 · **Entrega:** 1

Como **usuario del sistema**, quiero consultar el historial de análisis con filtros y ver el resultado de cualquiera de ellos, para encontrar trabajo pasado sin tener que recordar cuándo lo hice.

```gherkin
Característica: Historial de análisis

  Escenario: Alcance por defecto
    Dado que inicio sesión con cualquier rol
    Cuando abro Historial
    Entonces veo "Mis análisis" por defecto

  Escenario: Cambiar de alcance según mi permiso
    Dado que tengo el permiso "historial:area"
    Cuando cambio el alcance a "Mi área"
    Entonces veo los análisis de todos los usuarios de mi área

  Escenario: Filtrar y abrir un resultado
    Dado que estoy en Historial
    Cuando aplico un filtro de fecha, tipo de revisión, estado o archivo
    Y hago clic en una fila
    Entonces veo el resultado de ese análisis
```

## HU-22 — Gestionar usuarios

**CU:** CU-09 · **RF:** RF-02 · **Entrega:** 1

Como **Administrador**, quiero crear, editar, activar/desactivar usuarios y restablecerles la contraseña, para mantener al día quién puede usar el sistema sin tocar código ni la base de datos directamente.

```gherkin
Característica: Gestión de usuarios

  Escenario: Crear un usuario
    Dado que soy Administrador
    Cuando creo un usuario con nombre, email único, área y rol
    Entonces el sistema genera una contraseña temporal y la muestra una sola vez
    Y el usuario debe cambiarla en su primer ingreso

  Escenario: No autodesactivarse
    Dado que soy el usuario autenticado
    Cuando intento desactivar mi propia cuenta
    Entonces el sistema lo rechaza

  Escenario: Siempre un Administrador activo
    Dado que solo queda un Administrador activo
    Cuando intento desactivarlo o quitarle el rol
    Entonces el sistema lo rechaza

  Escenario: Nunca se borra un usuario
    Dado que un usuario ya no debe tener acceso
    Cuando el Administrador actúa sobre esa cuenta
    Entonces la única opción disponible es desactivarla, nunca eliminarla
```

## HU-23 — Ver y ajustar permisos por rol

**CU:** CU-09 · **RF:** RF-02 · **Entrega:** 1

Como **Administrador**, quiero ver la matriz de permisos por rol y ajustarla, para adaptar el acceso sin depender de un cambio de código.

```gherkin
Característica: Matriz de permisos editable

  Escenario: Ver y cambiar un permiso
    Dado que estoy en Configuración → Roles y permisos
    Cuando marco o desmarco una casilla de la matriz
    Entonces el cambio aplica desde el siguiente request de ese rol

  Escenario: Permisos protegidos
    Dado que una fila de la matriz está marcada como protegida
    Cuando intento editarla o borrarla
    Entonces el sistema lo rechaza

  Escenario: Restaurar matriz por defecto
    Dado que la matriz de permisos fue modificada
    Cuando elijo "Restaurar matriz por defecto"
    Entonces vuelve exactamente a la matriz v0.3 documentada
```

## HU-24 — Gestionar áreas

**CU:** CU-09 · **RF:** RF-02 · **Entrega:** 1

Como **Administrador**, quiero crear y renombrar áreas, para reflejar la estructura real de la organización.

```gherkin
Característica: Gestión de áreas

  Escenario: Crear o renombrar un área
    Dado que soy Administrador
    Cuando creo un área nueva o renombro una existente
    Entonces el cambio queda disponible para asignar a usuarios

  Escenario: No eliminar un área en uso
    Dado que un área tiene usuarios o documentos asociados
    Cuando intento eliminarla
    Entonces el sistema lo rechaza
```

## HU-25 — Cambiar mi contraseña temporal

**CU:** CU-09 · **RF:** RF-01 · **Entrega:** 1

Como **usuario nuevo**, quiero cambiar mi contraseña temporal en el primer ingreso, para que solo yo la conozca de ahí en adelante.

```gherkin
Característica: Cambio de contraseña obligatorio

  Escenario: Primer ingreso con contraseña temporal
    Dado que inicio sesión con una contraseña temporal
    Cuando el sistema detecta que debo cambiarla
    Entonces me pide una contraseña nueva antes de dejarme continuar

  Escenario: Requisitos de la contraseña nueva
    Dado que estoy cambiando mi contraseña
    Cuando ingreso una con menos de 10 caracteres o sin letras y números
    Entonces el sistema la rechaza

  Escenario: Bloqueo por intentos fallidos
    Dado que fallo 5 veces seguidas al iniciar sesión
    Cuando intento una vez más
    Entonces el sistema me bloquea por 15 minutos
```
