"""Importador de la plantilla de base de conocimiento (RF-16, CU-08, Bloque
K2) -- `Plantilla_Base_Conocimiento_SFC.xlsx`: Inventario de fuentes,
Catálogo de cuentas, Reglas contables, Glosario y Checklist de cierre.

Dos pasos deliberadamente separados:
- `leer_plantilla`: solo lee y valida (columnas requeridas, códigos
  únicos, estados/naturaleza válidos, fechas, referencias cruzadas de
  fuente_id entre hojas) -- nunca toca la base de datos. Reúne TODOS los
  errores de TODAS las hojas antes de devolver el resultado (no se detiene
  en el primero), para que el reporte sea completo.
- `cargar_plantilla`: persiste -- se niega a hacerlo si `leer_plantilla`
  encontró algún error (nunca carga nada parcial). Todo entra como
  "borrador" (RF-16): la plantilla nunca aprueba nada por sí sola, eso es
  el curador (ver curaduria.fuentes.aprobar_fuente, Bloque K5).
"""

from __future__ import annotations

import hashlib
import io
import re
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import BinaryIO

from openpyxl import load_workbook
from sqlalchemy.orm import Session

from comun.modelos import ChecklistCierre, CuentaContable, FuenteConocimiento, Glosario, Regla
from curaduria.fuentes import clasificar_tipo_fuente, prioridad_de_tipo

FILA_ENCABEZADO = 4
FILA_PRIMER_DATO = FILA_ENCABEZADO + 1

HOJA_FUENTES = "Inventario de fuentes"
HOJA_CATALOGO = "Catálogo de cuentas"
HOJA_REGLAS = "Reglas contables"
HOJA_GLOSARIO = "Glosario"
HOJA_CHECKLIST = "Checklist de cierre"

_HOJAS_REQUERIDAS = (HOJA_FUENTES, HOJA_CATALOGO, HOJA_REGLAS, HOJA_GLOSARIO, HOJA_CHECKLIST)

_COLUMNAS_FUENTES = (
    "fuente_id",
    "titulo",
    "tipo",
    "version",
    "vigente_desde",
    "estado",
    "dueno_area",
    "archivo_entregado",
    "observaciones",
)
_COLUMNAS_CATALOGO = ("codigo", "nombre", "tipo", "naturaleza", "acepta_movimiento", "notas")
_COLUMNAS_REGLAS = (
    "id_regla",
    "descripcion",
    "area",
    "tipo_documento",
    "severidad",
    "moneda",
    "fuente_id",
    "estado_validacion",
)
_COLUMNAS_GLOSARIO = ("termino", "definicion", "area", "fuente_id", "vigente_desde")
_COLUMNAS_CHECKLIST = ("n", "actividad", "responsable", "plazo", "evidencia_requerida")

_ESTADOS_FUENTE_VALIDOS = frozenset({"borrador", "vigente", "obsoleta"})
_NATURALEZAS_VALIDAS = frozenset({"deudora", "acreedora"})
_VALORES_SI = frozenset({"sí", "si", "s", "yes"})
_VALORES_NO = frozenset({"no", "n"})

# "POL-001 §3" -> fuente_id="POL-001", cita="§3". "CAT-001" -> cita="".
_PATRON_FUENTE_ID_CON_CITA = re.compile(r"^([A-Za-z]+-\d+)\s*(.*)$")


@dataclass(frozen=True)
class ErrorImportacion:
    hoja: str
    fila: int | None
    columna: str | None
    mensaje: str

    def __str__(self) -> str:
        ubicacion = self.hoja
        if self.fila is not None:
            ubicacion += f", fila {self.fila}"
        if self.columna is not None:
            ubicacion += f", columna '{self.columna}'"
        return f"{ubicacion}: {self.mensaje}"


@dataclass(frozen=True)
class FuenteImportada:
    fuente_id: str
    titulo: str
    tipo_libre: str
    version: str
    vigente_desde: date
    estado_plantilla: str
    dueno_area: str
    archivo_entregado: str
    observaciones: str | None


@dataclass(frozen=True)
class CuentaImportada:
    codigo: str
    nombre: str
    tipo: str | None
    naturaleza: str | None
    acepta_movimiento: bool
    notas: str | None


@dataclass(frozen=True)
class ReglaImportada:
    id_regla: str
    descripcion: str
    area: str
    tipo_documento: str | None
    severidad: str | None
    moneda: str | None
    fuente_id: str | None
    cita: str


@dataclass(frozen=True)
class GlosarioImportado:
    termino: str
    definicion: str
    area: str
    fuente_id: str | None
    vigente_desde: date | None


@dataclass(frozen=True)
class ChecklistImportado:
    numero: int
    actividad: str
    responsable: str | None
    plazo: str | None
    evidencia_requerida: str | None


@dataclass
class ResultadoImportacion:
    fuentes: list[FuenteImportada] = field(default_factory=list)
    cuentas: list[CuentaImportada] = field(default_factory=list)
    reglas: list[ReglaImportada] = field(default_factory=list)
    glosario: list[GlosarioImportado] = field(default_factory=list)
    checklist: list[ChecklistImportado] = field(default_factory=list)
    errores: list[ErrorImportacion] = field(default_factory=list)

    @property
    def es_valido(self) -> bool:
        return not self.errores


def _texto(valor: object) -> str:
    if valor is None:
        return ""
    return str(valor).strip()


def _fecha(valor: object) -> date | None:
    """Acepta tanto celdas de fecha real de Excel (datetime/date) como texto
    "AAAA-MM-DD" (la plantilla de referencia usa texto)."""
    if valor is None:
        return None
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    try:
        return date.fromisoformat(str(valor).strip())
    except ValueError:
        return None


def _encabezados(hoja_excel) -> tuple[object, ...]:  # type: ignore[no-untyped-def]
    filas = hoja_excel.iter_rows(min_row=FILA_ENCABEZADO, max_row=FILA_ENCABEZADO, values_only=True)
    return next(filas)


def _mapa_de_columnas(
    hoja_excel, columnas_requeridas: tuple[str, ...], *, hoja: str  # type: ignore[no-untyped-def]
) -> tuple[dict[str, int], list[ErrorImportacion]]:
    indice_por_nombre = {
        _texto(valor): indice
        for indice, valor in enumerate(_encabezados(hoja_excel))
        if _texto(valor)
    }
    faltantes = [c for c in columnas_requeridas if c not in indice_por_nombre]
    if faltantes:
        return {}, [
            ErrorImportacion(
                hoja=hoja,
                fila=FILA_ENCABEZADO,
                columna=None,
                mensaje=f"faltan columnas requeridas: {', '.join(faltantes)}",
            )
        ]
    return indice_por_nombre, []


def _filas_de_datos(hoja_excel, indice_por_nombre: dict[str, int]):  # type: ignore[no-untyped-def]
    for numero_fila, fila in enumerate(
        hoja_excel.iter_rows(min_row=FILA_PRIMER_DATO, values_only=True), start=FILA_PRIMER_DATO
    ):
        if all(valor is None for valor in fila):
            continue
        yield numero_fila, {
            nombre: (fila[indice] if indice < len(fila) else None)
            for nombre, indice in indice_por_nombre.items()
        }


def _leer_fuentes(hoja_excel) -> tuple[list[FuenteImportada], list[ErrorImportacion]]:  # type: ignore[no-untyped-def]
    indices, errores = _mapa_de_columnas(hoja_excel, _COLUMNAS_FUENTES, hoja=HOJA_FUENTES)
    if errores:
        return [], errores

    def err(fila: int, columna: str, mensaje: str) -> ErrorImportacion:
        return ErrorImportacion(HOJA_FUENTES, fila, columna, mensaje)

    fuentes: list[FuenteImportada] = []
    vistos: set[str] = set()
    for numero_fila, valores in _filas_de_datos(hoja_excel, indices):
        fuente_id = _texto(valores["fuente_id"])
        titulo = _texto(valores["titulo"])
        tipo_libre = _texto(valores["tipo"])
        version = _texto(valores["version"])
        vigente_desde = _fecha(valores["vigente_desde"])
        estado_plantilla = _texto(valores["estado"]).lower()
        dueno_area = _texto(valores["dueno_area"])
        archivo_entregado = _texto(valores["archivo_entregado"])
        observaciones = _texto(valores["observaciones"]) or None

        if not fuente_id:
            errores.append(err(numero_fila, "fuente_id", "no puede estar vacío"))
            continue
        if fuente_id in vistos:
            errores.append(err(numero_fila, "fuente_id", f"'{fuente_id}' duplicado en esta hoja"))
            continue
        vistos.add(fuente_id)

        if not titulo:
            errores.append(err(numero_fila, "titulo", "no puede estar vacío"))
        if not tipo_libre:
            errores.append(err(numero_fila, "tipo", "no puede estar vacío"))
        if not version:
            errores.append(err(numero_fila, "version", "no puede estar vacío"))
        if vigente_desde is None:
            errores.append(err(numero_fila, "vigente_desde", "fecha inválida (use AAAA-MM-DD)"))
        if estado_plantilla and estado_plantilla not in _ESTADOS_FUENTE_VALIDOS:
            errores.append(
                err(
                    numero_fila,
                    "estado",
                    f"'{estado_plantilla}' inválido (use {sorted(_ESTADOS_FUENTE_VALIDOS)})",
                )
            )
        if not dueno_area:
            errores.append(err(numero_fila, "dueno_area", "no puede estar vacío"))
        if not archivo_entregado:
            errores.append(err(numero_fila, "archivo_entregado", "no puede estar vacío"))

        if titulo and tipo_libre and version and vigente_desde and dueno_area and archivo_entregado:
            fuentes.append(
                FuenteImportada(
                    fuente_id=fuente_id,
                    titulo=titulo,
                    tipo_libre=tipo_libre,
                    version=version,
                    vigente_desde=vigente_desde,
                    estado_plantilla=estado_plantilla or "borrador",
                    dueno_area=dueno_area,
                    archivo_entregado=archivo_entregado,
                    observaciones=observaciones,
                )
            )

    return fuentes, errores


def _leer_catalogo(hoja_excel) -> tuple[list[CuentaImportada], list[ErrorImportacion]]:  # type: ignore[no-untyped-def]
    indices, errores = _mapa_de_columnas(hoja_excel, _COLUMNAS_CATALOGO, hoja=HOJA_CATALOGO)
    if errores:
        return [], errores

    def err(fila: int, columna: str, mensaje: str) -> ErrorImportacion:
        return ErrorImportacion(HOJA_CATALOGO, fila, columna, mensaje)

    cuentas: list[CuentaImportada] = []
    vistos: set[str] = set()
    for numero_fila, valores in _filas_de_datos(hoja_excel, indices):
        codigo = _texto(valores["codigo"])
        nombre = _texto(valores["nombre"])
        tipo = _texto(valores["tipo"]) or None
        naturaleza = _texto(valores["naturaleza"]).lower() or None
        acepta_texto = _texto(valores["acepta_movimiento"]).lower()
        notas = _texto(valores["notas"]) or None

        if not codigo:
            errores.append(err(numero_fila, "codigo", "no puede estar vacío"))
            continue
        if codigo in vistos:
            errores.append(err(numero_fila, "codigo", f"'{codigo}' duplicado en esta hoja"))
            continue
        vistos.add(codigo)

        if not nombre:
            errores.append(err(numero_fila, "nombre", "no puede estar vacío"))
        if naturaleza and naturaleza not in _NATURALEZAS_VALIDAS:
            errores.append(
                err(
                    numero_fila,
                    "naturaleza",
                    f"'{naturaleza}' inválida (use {sorted(_NATURALEZAS_VALIDAS)})",
                )
            )
        if acepta_texto not in _VALORES_SI | _VALORES_NO:
            errores.append(err(numero_fila, "acepta_movimiento", "use 'Sí' o 'No'"))
            continue

        if nombre:
            cuentas.append(
                CuentaImportada(
                    codigo=codigo,
                    nombre=nombre,
                    tipo=tipo,
                    naturaleza=naturaleza,
                    acepta_movimiento=acepta_texto in _VALORES_SI,
                    notas=notas,
                )
            )

    return cuentas, errores


def _leer_reglas(hoja_excel) -> tuple[list[ReglaImportada], list[ErrorImportacion]]:  # type: ignore[no-untyped-def]
    indices, errores = _mapa_de_columnas(hoja_excel, _COLUMNAS_REGLAS, hoja=HOJA_REGLAS)
    if errores:
        return [], errores

    def err(fila: int, columna: str, mensaje: str) -> ErrorImportacion:
        return ErrorImportacion(HOJA_REGLAS, fila, columna, mensaje)

    reglas: list[ReglaImportada] = []
    vistos: set[str] = set()
    for numero_fila, valores in _filas_de_datos(hoja_excel, indices):
        id_regla = _texto(valores["id_regla"])
        descripcion = _texto(valores["descripcion"])
        area = _texto(valores["area"])
        tipo_documento = _texto(valores["tipo_documento"]) or None
        severidad = _texto(valores["severidad"]) or None
        moneda = _texto(valores["moneda"]) or None
        fuente_id_con_cita = _texto(valores["fuente_id"])

        if not id_regla:
            errores.append(err(numero_fila, "id_regla", "no puede estar vacío"))
            continue
        if id_regla in vistos:
            errores.append(err(numero_fila, "id_regla", f"'{id_regla}' duplicado en esta hoja"))
            continue
        vistos.add(id_regla)

        if not descripcion:
            errores.append(err(numero_fila, "descripcion", "no puede estar vacío"))
        if not area:
            errores.append(err(numero_fila, "area", "no puede estar vacío"))

        fuente_id: str | None = None
        cita = ""
        if fuente_id_con_cita:
            coincidencia = _PATRON_FUENTE_ID_CON_CITA.match(fuente_id_con_cita)
            if coincidencia:
                fuente_id, cita = coincidencia.group(1), coincidencia.group(2).strip()
            else:
                errores.append(
                    err(
                        numero_fila,
                        "fuente_id",
                        f"'{fuente_id_con_cita}' no tiene forma de fuente_id (p. ej. 'POL-001 §3')",
                    )
                )

        if descripcion and area:
            reglas.append(
                ReglaImportada(
                    id_regla=id_regla,
                    descripcion=descripcion,
                    area=area,
                    tipo_documento=tipo_documento,
                    severidad=severidad,
                    moneda=moneda,
                    fuente_id=fuente_id,
                    cita=cita,
                )
            )

    return reglas, errores


def _leer_glosario(hoja_excel) -> tuple[list[GlosarioImportado], list[ErrorImportacion]]:  # type: ignore[no-untyped-def]
    indices, errores = _mapa_de_columnas(hoja_excel, _COLUMNAS_GLOSARIO, hoja=HOJA_GLOSARIO)
    if errores:
        return [], errores

    def err(fila: int, columna: str, mensaje: str) -> ErrorImportacion:
        return ErrorImportacion(HOJA_GLOSARIO, fila, columna, mensaje)

    glosario: list[GlosarioImportado] = []
    for numero_fila, valores in _filas_de_datos(hoja_excel, indices):
        termino = _texto(valores["termino"])
        definicion = _texto(valores["definicion"])
        area = _texto(valores["area"])
        fuente_id = _texto(valores["fuente_id"]) or None
        vigente_desde_valor = valores["vigente_desde"]
        vigente_desde = _fecha(vigente_desde_valor) if vigente_desde_valor else None

        if not termino:
            errores.append(err(numero_fila, "termino", "no puede estar vacío"))
            continue
        if not definicion:
            errores.append(err(numero_fila, "definicion", "no puede estar vacío"))
        if not area:
            errores.append(err(numero_fila, "area", "no puede estar vacío"))
        if vigente_desde_valor and vigente_desde is None:
            errores.append(err(numero_fila, "vigente_desde", "fecha inválida (use AAAA-MM-DD)"))

        if definicion and area:
            glosario.append(
                GlosarioImportado(
                    termino=termino,
                    definicion=definicion,
                    area=area,
                    fuente_id=fuente_id,
                    vigente_desde=vigente_desde,
                )
            )

    return glosario, errores


def _leer_checklist(hoja_excel) -> tuple[list[ChecklistImportado], list[ErrorImportacion]]:  # type: ignore[no-untyped-def]
    indices, errores = _mapa_de_columnas(hoja_excel, _COLUMNAS_CHECKLIST, hoja=HOJA_CHECKLIST)
    if errores:
        return [], errores

    def err(fila: int, columna: str, mensaje: str) -> ErrorImportacion:
        return ErrorImportacion(HOJA_CHECKLIST, fila, columna, mensaje)

    checklist: list[ChecklistImportado] = []
    vistos: set[int] = set()
    for numero_fila, valores in _filas_de_datos(hoja_excel, indices):
        crudo = valores["n"]
        try:
            numero = int(crudo)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            errores.append(err(numero_fila, "n", "debe ser un número entero"))
            continue
        if numero in vistos:
            errores.append(err(numero_fila, "n", f"'{numero}' duplicado en esta hoja"))
            continue
        vistos.add(numero)

        actividad = _texto(valores["actividad"])
        if not actividad:
            errores.append(err(numero_fila, "actividad", "no puede estar vacío"))
            continue

        checklist.append(
            ChecklistImportado(
                numero=numero,
                actividad=actividad,
                responsable=_texto(valores["responsable"]) or None,
                plazo=_texto(valores["plazo"]) or None,
                evidencia_requerida=_texto(valores["evidencia_requerida"]) or None,
            )
        )

    return checklist, errores


def _validar_referencias_cruzadas(resultado: ResultadoImportacion) -> list[ErrorImportacion]:
    fuentes_conocidas = {f.fuente_id for f in resultado.fuentes}
    errores: list[ErrorImportacion] = []
    for regla in resultado.reglas:
        if regla.fuente_id and regla.fuente_id not in fuentes_conocidas:
            errores.append(
                ErrorImportacion(
                    HOJA_REGLAS,
                    None,
                    "fuente_id",
                    f"'{regla.fuente_id}' (regla {regla.id_regla}) no está en {HOJA_FUENTES}",
                )
            )
    for entrada in resultado.glosario:
        if entrada.fuente_id and entrada.fuente_id not in fuentes_conocidas:
            errores.append(
                ErrorImportacion(
                    HOJA_GLOSARIO,
                    None,
                    "fuente_id",
                    f"'{entrada.fuente_id}' (término '{entrada.termino}') "
                    f"no está en {HOJA_FUENTES}",
                )
            )
    return errores


def leer_plantilla(archivo: BinaryIO | bytes | str) -> ResultadoImportacion:
    """Lee y valida la plantilla completa -- no toca la base de datos. Reúne
    todos los errores de todas las hojas (no se detiene en el primero)."""
    resultado = ResultadoImportacion()

    # load_workbook exige una ruta/nombre de archivo o un objeto con .read()
    # -- bytes crudos (p. ej. el cuerpo de una carga HTTP) no sirven tal
    # cual, hay que envolverlos.
    if isinstance(archivo, bytes):
        archivo = io.BytesIO(archivo)
    libro = load_workbook(archivo, data_only=True)
    faltantes = [h for h in _HOJAS_REQUERIDAS if h not in libro.sheetnames]
    if faltantes:
        resultado.errores.append(
            ErrorImportacion(
                hoja="(plantilla)",
                fila=None,
                columna=None,
                mensaje=f"faltan hojas requeridas: {', '.join(faltantes)}",
            )
        )
        return resultado

    resultado.fuentes, errores_fuentes = _leer_fuentes(libro[HOJA_FUENTES])
    resultado.cuentas, errores_catalogo = _leer_catalogo(libro[HOJA_CATALOGO])
    resultado.reglas, errores_reglas = _leer_reglas(libro[HOJA_REGLAS])
    resultado.glosario, errores_glosario = _leer_glosario(libro[HOJA_GLOSARIO])
    resultado.checklist, errores_checklist = _leer_checklist(libro[HOJA_CHECKLIST])
    resultado.errores = [
        *errores_fuentes,
        *errores_catalogo,
        *errores_reglas,
        *errores_glosario,
        *errores_checklist,
    ]
    resultado.errores.extend(_validar_referencias_cruzadas(resultado))
    return resultado


def _fuente_de_hoja_embebida(
    resultado: ResultadoImportacion, nombre_hoja: str
) -> FuenteImportada | None:
    """La fuente cuyo archivo_entregado es 'hoja "<nombre_hoja>"' -- Catálogo
    de cuentas, Glosario y Checklist de cierre no son documentos aparte,
    son hojas de la propia plantilla (ver Inventario de fuentes)."""
    referencia = f'hoja "{nombre_hoja.lower()}"'
    return next(
        (f for f in resultado.fuentes if f.archivo_entregado.lower() == referencia), None
    )


def cargar_plantilla(
    sesion: Session,
    resultado: ResultadoImportacion,
    *,
    area_id_por_defecto: uuid.UUID,
    cargado_por: uuid.UUID,
    ahora: datetime,
    contenido_plantilla: bytes | None = None,
) -> dict[str, int]:
    """Persiste un `ResultadoImportacion` ya validado (`es_valido`) --
    siempre como "borrador" (RF-16): la plantilla nunca aprueba nada por sí
    sola, eso lo hace el curador después (Bloque K5, `curaduria.fuentes.
    aprobar_fuente`). Se niega a persistir nada si hay errores -- llamar
    primero a `leer_plantilla` y no invocar esto si `not resultado.es_valido`.

    `area_id_por_defecto` se usa para catálogo/reglas/glosario/checklist
    cuando su columna "area" no mapea a un Area existente por nombre (ver
    Bloque K5 para asignación de área por curador); en el piloto (una sola
    área) es siempre la misma.
    """
    if not resultado.es_valido:
        raise ValueError(
            "no se puede cargar una plantilla con errores -- llamar primero a leer_plantilla"
        )

    sha256_plantilla = (
        hashlib.sha256(contenido_plantilla).hexdigest() if contenido_plantilla else None
    )

    fuente_por_negocio_id: dict[str, FuenteConocimiento] = {}
    for fuente in resultado.fuentes:
        es_hoja_embebida = fuente.archivo_entregado.lower().startswith('hoja "')
        fila = FuenteConocimiento(
            fuente_id=fuente.fuente_id,
            titulo=fuente.titulo,
            tipo=clasificar_tipo_fuente(fuente.tipo_libre),
            prioridad=prioridad_de_tipo(clasificar_tipo_fuente(fuente.tipo_libre)),
            version=fuente.version,
            vigente_desde=fuente.vigente_desde,
            estado="borrador",
            area_id=area_id_por_defecto,
            dueno=fuente.dueno_area,
            archivo=fuente.archivo_entregado,
            sha256=sha256_plantilla if es_hoja_embebida else None,
            cargado_por=cargado_por,
            fecha_carga=ahora,
        )
        sesion.add(fila)
        fuente_por_negocio_id[fuente.fuente_id] = fila
    sesion.flush()

    fuente_catalogo = _fuente_de_hoja_embebida(resultado, HOJA_CATALOGO)
    id_fuente_catalogo = (
        fuente_por_negocio_id[fuente_catalogo.fuente_id].id if fuente_catalogo else None
    )
    for cuenta in resultado.cuentas:
        sesion.add(
            CuentaContable(
                codigo=cuenta.codigo,
                nombre=cuenta.nombre,
                tipo=cuenta.tipo,
                naturaleza=cuenta.naturaleza,
                acepta_movimiento=cuenta.acepta_movimiento,
                notas=cuenta.notas,
                area_id=area_id_por_defecto,
                fuente_id=id_fuente_catalogo,
                version=fuente_catalogo.version if fuente_catalogo else None,
            )
        )

    for regla in resultado.reglas:
        fuente_regla = fuente_por_negocio_id.get(regla.fuente_id) if regla.fuente_id else None
        sesion.add(
            Regla(
                codigo=regla.id_regla,
                descripcion=regla.descripcion,
                area_id=area_id_por_defecto,
                tipo_documento=regla.tipo_documento,
                severidad=regla.severidad,
                fuente_id=fuente_regla.id if fuente_regla else None,
                vigente_desde=fuente_regla.vigente_desde if fuente_regla else ahora.date(),
                version=fuente_regla.version if fuente_regla else "1.0",
                estado="borrador",
                moneda=regla.moneda,
            )
        )

    for entrada in resultado.glosario:
        fuente_glosario = (
            fuente_por_negocio_id.get(entrada.fuente_id) if entrada.fuente_id else None
        )
        sesion.add(
            Glosario(
                area_id=area_id_por_defecto,
                termino=entrada.termino,
                definicion=entrada.definicion,
                fuente_id=fuente_glosario.id if fuente_glosario else None,
                version=fuente_glosario.version if fuente_glosario else None,
                vigente_desde=entrada.vigente_desde,
            )
        )

    fuente_checklist = _fuente_de_hoja_embebida(resultado, HOJA_CHECKLIST)
    id_fuente_checklist = (
        fuente_por_negocio_id[fuente_checklist.fuente_id].id if fuente_checklist else None
    )
    for actividad in resultado.checklist:
        sesion.add(
            ChecklistCierre(
                numero=actividad.numero,
                actividad=actividad.actividad,
                responsable=actividad.responsable,
                plazo=actividad.plazo,
                evidencia_requerida=actividad.evidencia_requerida,
                area_id=area_id_por_defecto,
                fuente_id=id_fuente_checklist,
                version=fuente_checklist.version if fuente_checklist else None,
            )
        )

    sesion.flush()
    return {
        "fuentes": len(resultado.fuentes),
        "cuentas": len(resultado.cuentas),
        "reglas": len(resultado.reglas),
        "glosario": len(resultado.glosario),
        "checklist": len(resultado.checklist),
    }
