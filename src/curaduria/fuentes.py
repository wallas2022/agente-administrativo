"""Ciclo de vida de una fuente de conocimiento (RF-16, CU-08, Bloque K1).

Paquete "curaduria" (no "kb"): un paquete `src/kb/` colisionaría con el
directorio de datos `kb/` en la raíz del repo -- `orquestador.rutas_kb.
encontrar_raiz_con_kb()` ubica la raíz buscando hacia arriba un directorio
que CONTENGA una carpeta `kb/`, y encontraría `src/kb/` primero (ver ese
módulo). Encontrado en vivo mientras se escribía este bloque: con `src/kb/`
existiendo, `cargar_glosario()` (CU-05) empezaba a buscar `src/kb/glosario/
glosario.csv` en vez del real y el análisis de ortografía fallaba.

Sin lógica de importación ni de indexación (eso es de los Bloques K2/K3) --
solo la regla de negocio explícita del Bloque K1: "una sola versión vigente
por fuente_id; al aprobar una nueva, la anterior pasa a obsoleta
automáticamente". El invariante también está reforzado a nivel de base de
datos (ver la migración: índice único parcial sobre `fuente_id` WHERE
`estado='vigente'`) -- esta función es la que hace la transición en el
orden correcto para no violarlo nunca, ni siquiera transitoriamente.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from comun.modelos import FuenteConocimiento

# tipo -> prioridad (Bloque K4: el RAG ordena por esto antes que por
# similitud semántica -- una regla interna siempre pesa más que una
# referencia, aunque la referencia tenga mejor puntuación de similitud).
_PRIORIDAD_POR_TIPO = {"regla_interna": 1, "normativa": 2, "referencia": 3}

TIPOS_VALIDOS = frozenset(_PRIORIDAD_POR_TIPO)


def clasificar_tipo_fuente(texto_libre: str) -> str:
    """Bloque K2: la hoja "Inventario de fuentes" de la plantilla describe el
    tipo con texto libre orientado al curador (p. ej. "política (Word)",
    "catálogo (Excel)", "checklist (Excel)") -- no los tres valores
    canónicos que exige `prioridad_de_tipo`. Esta función los traduce por
    palabras clave: "normativa" (ley/decreto/reglamento/norma externa) y
    "referencia" (material de apoyo, no vinculante) se reconocen
    explícitamente; cualquier otra cosa (política, procedimiento,
    lineamiento, guía, catálogo, glosario, checklist...) se clasifica como
    "regla_interna" -- son documentos que la propia organización produce y
    hace cumplir, el caso por defecto en este piloto (todo el inventario de
    ejemplo es contenido interno de SFC, no hay normativa externa todavía).
    Nunca falla: siempre devuelve uno de los tres tipos válidos."""
    texto = texto_libre.strip().lower()
    if any(palabra in texto for palabra in ("normativa", "ley", "decreto", "reglamento")):
        return "normativa"
    if "referencia" in texto:
        return "referencia"
    return "regla_interna"


def prioridad_de_tipo(tipo: str) -> int:
    """1 (regla_interna) / 2 (normativa) / 3 (referencia). Lanza ValueError
    para cualquier otro valor -- lo usa tanto la carga directa de una fuente
    como el importador de la plantilla (Bloque K2) para validar la columna
    "tipo" antes de persistir nada."""
    try:
        return _PRIORIDAD_POR_TIPO[tipo]
    except KeyError:
        raise ValueError(
            f"tipo de fuente inválido: {tipo!r} (debe ser uno de {sorted(TIPOS_VALIDOS)})"
        ) from None


def aprobar_fuente(
    sesion: Session,
    fuente: FuenteConocimiento,
    *,
    aprobado_por: uuid.UUID,
    ahora: datetime,
) -> FuenteConocimiento | None:
    """Aprueba `fuente` (debe estar en "borrador") como la versión vigente
    de su `fuente_id`. Si ya había otra versión vigente de la misma fuente,
    esa pasa a "obsoleta" -- nunca se borra (RNF-06, trazabilidad
    histórica) -- y la transición ocurre en ese orden (obsoletear primero,
    aprobar después) para no violar ni transitoriamente el índice único
    parcial de la base de datos. Devuelve la fila que quedó obsoleta, o
    `None` si no había ninguna versión vigente previa."""
    anterior = (
        sesion.query(FuenteConocimiento)
        .filter(
            FuenteConocimiento.fuente_id == fuente.fuente_id,
            FuenteConocimiento.estado == "vigente",
            FuenteConocimiento.id != fuente.id,
        )
        .one_or_none()
    )
    if anterior is not None:
        anterior.estado = "obsoleta"
        sesion.flush()

    fuente.estado = "vigente"
    fuente.aprobado_por = aprobado_por
    fuente.fecha_aprobacion = ahora
    sesion.flush()
    return anterior
