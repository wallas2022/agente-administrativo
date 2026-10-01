"""Reglas deterministas de redacción contra EST-001 (RD-01 a RD-04, RF-07,
CU-02) -- ver docs/02-analisis/02-analisis-cu02-redaccion-amigable.md §3.

Mismo principio que `validadores.contable.reglas` (RNF-03): todo lo que se
pueda detectar sin LLM, se detecta aquí -- la fase 2 (LLM por párrafo, ver
`orquestador.pipeline_redaccion` y la ruta SSE en `api/main.py`) solo entra
para la reescritura de redacción en sí, nunca para decidir si falta una
sección, un monto está mal formateado, una fecha está mal formateada o una
sigla no se definió.

Heurísticas basadas en texto/regex, no en NLP real -- documentadas caso por
caso donde pueden fallar (falsos positivos/negativos). EST-001 (ejemplo,
ver kb/plantillas/ejemplos/EST-001_Guia_Estilo_EJEMPLO.docx) define: §1
tipografía/tono, §2 secciones de un procedimiento, §3 formato de montos y
fechas, §4 siglas.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from parsers.segmentos import SegmentoTexto

# §2 EST-001: secciones que debe tener un "Procedimiento".
SECCIONES_PROCEDIMIENTO = (
    "objetivo",
    "alcance",
    "responsables",
    "actividades",
    "registros",
    "control de versiones",
)

# §3 EST-001: "Q 1,250.00" / "USD 500.00" -- símbolo, espacio, coma de
# miles, punto decimal con 2 cifras.
_PATRON_MONTO_CANDIDATO = re.compile(r"\b(Q|USD)\s?[\d][\d,.]*\b")
_PATRON_MONTO_CORRECTO = re.compile(r"^(Q|USD) \d{1,3}(,\d{3})*\.\d{2}$")

# §3 EST-001: "28 de septiembre de 2026" en texto corrido, "28/09/2026" en
# tablas. Candidatos: cualquier cosa con forma de fecha (numérica en
# cualquier separador, ISO, o textual con/sin año) para detectar variantes
# mal formateadas, no solo ausencia total de fecha.
_PATRON_FECHA_TEXTO_OK = re.compile(r"^\d{1,2} de [a-záéíóúñ]+ de \d{4}$", re.IGNORECASE)
_PATRON_FECHA_TABLA_OK = re.compile(r"^\d{2}/\d{2}/\d{4}$")
_PATRON_FECHA_CANDIDATA = re.compile(
    r"\b\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4}\b"
    r"|\b\d{4}-\d{2}-\d{2}\b"
    r"|\b\d{1,2}\s+de\s+[a-záéíóúñ]+(?:\s+de\s+\d{2,4})?\b",
    re.IGNORECASE,
)

# §4 EST-001: siglas = 2+ mayúsculas seguidas, con una lista corta de
# palabras cortas en mayúscula que no son siglas de negocio (conectores,
# si aparecieran todo en mayúscula por énfasis).
_PATRON_SIGLA = re.compile(r"\b[A-ZÁÉÍÓÚÑ]{2,}\b")
_PALABRAS_EXCLUIDAS_DE_SIGLA = frozenset(
    {"Y", "O", "DE", "LA", "EL", "UN", "EN", "AL", "NO", "SI", "SFC"}
)


@dataclass(frozen=True)
class HallazgoRedaccion:
    regla_codigo: str
    severidad: str  # "alta" | "media" | "baja"
    ubicacion: str
    descripcion: str
    cita_est001: str | None = None  # "§N", para armar "Regla aplicada: EST-001 §N"


def _validar_secciones_procedimiento(
    segmentos: list[SegmentoTexto], tipo_documento: str
) -> list[HallazgoRedaccion]:
    if tipo_documento.lower() != "procedimiento":
        return []

    textos_normalizados = [s.texto.strip().lower() for s in segmentos]
    faltantes = [
        seccion
        for seccion in SECCIONES_PROCEDIMIENTO
        if not any(t.startswith(seccion) for t in textos_normalizados)
    ]
    if not faltantes:
        return []

    return [
        HallazgoRedaccion(
            regla_codigo="RD-01",
            severidad="media",
            ubicacion="Documento completo",
            descripcion=(
                "Faltan secciones obligatorias de un Procedimiento (EST-001 §2): "
                + ", ".join(faltantes)
            ),
            cita_est001="§2",
        )
    ]


def _validar_montos(segmentos: list[SegmentoTexto]) -> list[HallazgoRedaccion]:
    hallazgos: list[HallazgoRedaccion] = []
    for segmento in segmentos:
        for coincidencia in _PATRON_MONTO_CANDIDATO.finditer(segmento.texto):
            candidato = coincidencia.group(0)
            normalizado = re.sub(r"^(Q|USD)\s*", r"\1 ", candidato)
            if not _PATRON_MONTO_CORRECTO.match(normalizado):
                hallazgos.append(
                    HallazgoRedaccion(
                        regla_codigo="RD-02",
                        severidad="baja",
                        ubicacion=segmento.ubicacion,
                        descripcion=(
                            f"Monto '{candidato}' no sigue el formato de EST-001 §3 "
                            '(p. ej. "Q 1,250.00" o "USD 500.00")'
                        ),
                        cita_est001="§3",
                    )
                )
    return hallazgos


def _validar_fechas(segmentos: list[SegmentoTexto]) -> list[HallazgoRedaccion]:
    hallazgos: list[HallazgoRedaccion] = []
    for segmento in segmentos:
        es_tabla = segmento.ubicacion.lower().startswith("tabla")
        patron_ok = _PATRON_FECHA_TABLA_OK if es_tabla else _PATRON_FECHA_TEXTO_OK
        formato_esperado = '"28/09/2026"' if es_tabla else '"28 de septiembre de 2026"'
        for coincidencia in _PATRON_FECHA_CANDIDATA.finditer(segmento.texto):
            candidato = coincidencia.group(0).strip()
            if not patron_ok.match(candidato):
                hallazgos.append(
                    HallazgoRedaccion(
                        regla_codigo="RD-03",
                        severidad="baja",
                        ubicacion=segmento.ubicacion,
                        descripcion=(
                            f"Fecha '{candidato}' no sigue el formato de EST-001 §3 "
                            f"(p. ej. {formato_esperado})"
                        ),
                        cita_est001="§3",
                    )
                )
    return hallazgos


def _validar_siglas(segmentos: list[SegmentoTexto]) -> list[HallazgoRedaccion]:
    """Primer uso de cada sigla distinta en todo el documento (en orden de
    aparición de los segmentos); se espera "Forma completa (SIGLA)" -- si el
    carácter inmediatamente anterior a la sigla en el texto no es "(",
    se considera no definida. Heurística de texto, no gramatical: puede
    marcar falsos positivos con nombres propios todo en mayúscula."""
    vistas: set[str] = set()
    hallazgos: list[HallazgoRedaccion] = []
    for segmento in segmentos:
        for coincidencia in _PATRON_SIGLA.finditer(segmento.texto):
            sigla = coincidencia.group(0)
            if sigla in _PALABRAS_EXCLUIDAS_DE_SIGLA or sigla in vistas:
                continue
            vistas.add(sigla)
            inicio = coincidencia.start()
            precedido_por_parentesis = inicio > 0 and segmento.texto[inicio - 1] == "("
            if not precedido_por_parentesis:
                hallazgos.append(
                    HallazgoRedaccion(
                        regla_codigo="RD-04",
                        severidad="baja",
                        ubicacion=segmento.ubicacion,
                        descripcion=(
                            f"Sigla '{sigla}' no está definida en su primer uso "
                            "(EST-001 §4: forma completa seguida de la sigla entre paréntesis)"
                        ),
                        cita_est001="§4",
                    )
                )
    return hallazgos


def validar_redaccion(
    segmentos: list[SegmentoTexto], *, tipo_documento: str
) -> list[HallazgoRedaccion]:
    """Punto de entrada de la fase 1 (determinista, sin LLM) de CU-02."""
    return [
        *_validar_secciones_procedimiento(segmentos, tipo_documento),
        *_validar_montos(segmentos),
        *_validar_fechas(segmentos),
        *_validar_siglas(segmentos),
    ]


# --- Corrección determinista (fase 2, antes del LLM) ------------------------

_PATRON_MONTO_A_FORMATEAR = re.compile(r"\b(Q|USD)\s?(\d[\d,]*(?:\.\d+)?)\b")
_PATRON_FECHA_NUMERICA = re.compile(r"\b(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})\b")

_MESES_ES = (
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
)


def _normalizar_monto(coincidencia: re.Match[str]) -> str:
    moneda = coincidencia.group(1)
    numero = float(coincidencia.group(2).replace(",", ""))
    return f"{moneda} {numero:,.2f}"


def _formatear_fecha_numerica(coincidencia: re.Match[str], *, es_tabla: bool) -> str:
    dia, mes = int(coincidencia.group(1)), int(coincidencia.group(2))
    anio = coincidencia.group(3)
    if not (1 <= dia <= 31 and 1 <= mes <= 12):
        return coincidencia.group(0)  # no es una fecha real -- no se toca
    if es_tabla:
        return f"{dia:02d}/{mes:02d}/{anio}"
    return f"{dia} de {_MESES_ES[mes - 1]} de {anio}"


def aplicar_formatos_deterministas(texto: str, *, es_tabla: bool = False) -> str:
    """Corrige en Python (RNF-03: nunca el LLM) el formato de montos y de
    fechas numéricas antes de pasar el párrafo a la reescritura de estilo
    (fase 2, ver validadores.redaccion.mejora) -- mismo principio que
    `validadores.contable.reglas` con los cuadres: lo que se pueda corregir
    determinísticamente, se corrige acá, no se delega.

    Heurística limitada a fechas en forma numérica con año de 4 dígitos
    ("5/10/2026", con cualquier separador) -- una fecha ISO (AAAA-MM-DD) o
    ya en forma textual no se toca; `validar_redaccion` las sigue marcando
    como hallazgo si están mal formateadas, solo no se autocorrigen en esta
    primera iteración."""
    texto = _PATRON_MONTO_A_FORMATEAR.sub(_normalizar_monto, texto)
    return _PATRON_FECHA_NUMERICA.sub(
        lambda m: _formatear_fecha_numerica(m, es_tabla=es_tabla), texto
    )
