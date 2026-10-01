"""Modelo de datos (SQLAlchemy) — refleja docs/03-diseno/er/modelo-datos.md.

Sin lógica de negocio: solo la estructura de las 17 entidades y sus relaciones
(15 originales + CuentaContable/ChecklistCierre del Bloque K1, CU-08).
Las migraciones (Alembic) viven en src/api/migraciones/.
"""

import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid


class Base(DeclarativeBase):
    pass


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)


class Area(Base):
    __tablename__ = "area"

    id: Mapped[uuid.UUID] = _uuid_pk()
    nombre: Mapped[str] = mapped_column(String(200), nullable=False)


class Rol(Base):
    __tablename__ = "rol"

    id: Mapped[uuid.UUID] = _uuid_pk()
    nombre: Mapped[str] = mapped_column(String(100), nullable=False)
    descripcion: Mapped[str | None] = mapped_column(String(500))


class Permiso(Base):
    __tablename__ = "permiso"

    id: Mapped[uuid.UUID] = _uuid_pk()
    rol_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("rol.id"), nullable=False)
    recurso: Mapped[str] = mapped_column(String(100), nullable=False)
    accion: Mapped[str] = mapped_column(String(100), nullable=False)


class Usuario(Base):
    __tablename__ = "usuario"

    id: Mapped[uuid.UUID] = _uuid_pk()
    nombre: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    area_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("area.id"), nullable=False)
    rol_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("rol.id"), nullable=False)
    origen_autenticacion: Mapped[str] = mapped_column(String(20), default="local")
    activo: Mapped[bool] = mapped_column(Boolean, default=True)


class Documento(Base):
    __tablename__ = "documento"

    id: Mapped[uuid.UUID] = _uuid_pk()
    nombre_original: Mapped[str] = mapped_column(String(500), nullable=False)
    tipo_archivo: Mapped[str] = mapped_column(String(20), nullable=False)
    tamano_bytes: Mapped[int] = mapped_column(nullable=False)
    area_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("area.id"), nullable=False)
    usuario_carga_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("usuario.id"), nullable=False)
    fecha_carga: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    fecha_expiracion: Mapped[date] = mapped_column(Date, nullable=False)
    estado: Mapped[str] = mapped_column(String(20), nullable=False)

    versiones: Mapped[list["VersionDocumento"]] = relationship(back_populates="documento")


class VersionDocumento(Base):
    __tablename__ = "version_documento"

    id: Mapped[uuid.UUID] = _uuid_pk()
    documento_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documento.id"), nullable=False)
    numero_version: Mapped[int] = mapped_column(nullable=False)
    ruta_almacenamiento: Mapped[str] = mapped_column(String(1000), nullable=False)
    es_corregida: Mapped[bool] = mapped_column(Boolean, default=False)
    fecha_creacion: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    documento: Mapped["Documento"] = relationship(back_populates="versiones")


class TipoRevision(Base):
    __tablename__ = "tipo_revision"

    id: Mapped[uuid.UUID] = _uuid_pk()
    nombre: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)


class Analisis(Base):
    __tablename__ = "analisis"

    id: Mapped[uuid.UUID] = _uuid_pk()
    documento_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documento.id"), nullable=False)
    tipo_revision_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tipo_revision.id"), nullable=False
    )
    usuario_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("usuario.id"), nullable=False)
    fecha_inicio: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    fecha_fin: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    modelo_llm: Mapped[str | None] = mapped_column(String(200))
    version_prompt: Mapped[str | None] = mapped_column(String(50))
    estado: Mapped[str] = mapped_column(String(20), nullable=False)
    # Período contable que se está cerrando/revisando ("AAAA-MM"), distinto de
    # fecha_inicio (momento en que se ejecuta el análisis) — usado por RN-03.
    periodo_cierre: Mapped[str | None] = mapped_column(String(7))
    # Totales reales del libro (suma de Debe/Haber de todas las partidas),
    # calculados por validadores.contable.reglas — nunca por el LLM (RNF-03).
    # No es un solo código ISO 4217: puede ser la combinación de monedas
    # mezcladas en el documento (RN-05), igual que Hallazgo.moneda.
    total_debe: Mapped[float | None] = mapped_column(Numeric(18, 2))
    total_haber: Mapped[float | None] = mapped_column(Numeric(18, 2))
    moneda: Mapped[str | None] = mapped_column(String(10))
    # Solo aplica a tipo_revision=="redaccion" (CU-02): Correo|Memo|
    # Procedimiento|Informe (solo "Procedimiento" activa RD-01, secciones
    # obligatorias) y Corregir|Aclarar|Formalizar (fase 2, por párrafo).
    tipo_documento: Mapped[str | None] = mapped_column(String(20))
    accion: Mapped[str | None] = mapped_column(String(20))

    hallazgos: Mapped[list["Hallazgo"]] = relationship(back_populates="analisis")


class Hallazgo(Base):
    __tablename__ = "hallazgo"

    id: Mapped[uuid.UUID] = _uuid_pk()
    analisis_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("analisis.id"), nullable=False)
    version_documento_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("version_documento.id"), nullable=False
    )
    regla_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("regla.id"))
    fragmento_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("fragmento.id"))
    severidad: Mapped[str] = mapped_column(String(10), nullable=False)
    ubicacion: Mapped[str] = mapped_column(String(200), nullable=False)
    descripcion: Mapped[str] = mapped_column(Text, nullable=False)
    correccion_sugerida: Mapped[str | None] = mapped_column(Text)
    # Texto exacto marcado como incorrecto (CU-05, RF-14): permite reaplicar
    # solo las correcciones aceptadas sobre el documento original sin tener
    # que volver a correr LanguageTool/LLM. None para hallazgos de CU-01
    # (contable), que no corrigen texto -- solo marcan celdas.
    texto_original: Mapped[str | None] = mapped_column(String(500))
    monto: Mapped[float | None] = mapped_column(Numeric(18, 2))
    # No es un solo código ISO 4217 (3 letras): RN-05 registra la combinación de
    # monedas mezcladas en la partida, p. ej. "Q/USD".
    moneda: Mapped[str | None] = mapped_column(String(10))
    estado: Mapped[str] = mapped_column(String(20), default="pendiente")
    # Cita que FUNDA el hallazgo (Bloque K4, RF-16): "Regla aplicada:
    # POL-001 §3 (v2026-01)" -- nunca proviene de un fragmento tipo=
    # "referencia" (ver rag.busqueda.construir_citas/ExplicacionGenerada.
    # fuente_citada). No es una FK real: el RAG hoy vive en Qdrant, no hay
    # garantía de que exista una fila FuenteConocimiento con ese mismo id.
    fuente_citada: Mapped[str | None] = mapped_column(String(300))
    # Cita complementaria, nunca fundamento por sí sola: "Referencia:
    # <fuente> cap./pág." (Bloque K4) -- mismo criterio que fuente_citada.
    referencia_citada: Mapped[str | None] = mapped_column(String(300))

    analisis: Mapped["Analisis"] = relationship(back_populates="hallazgos")
    decisiones: Mapped[list["Decision"]] = relationship(back_populates="hallazgo")


class Decision(Base):
    __tablename__ = "decision"

    id: Mapped[uuid.UUID] = _uuid_pk()
    hallazgo_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("hallazgo.id"), nullable=False)
    usuario_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("usuario.id"), nullable=False)
    resultado: Mapped[str] = mapped_column(String(20), nullable=False)
    comentario: Mapped[str | None] = mapped_column(Text)
    fecha: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    hallazgo: Mapped["Hallazgo"] = relationship(back_populates="decisiones")


class FuenteConocimiento(Base):
    """RF-16, CU-08 (Bloque K1). Cada fila es UNA versión de una fuente; el
    mismo `fuente_id` de negocio (p. ej. "POL-001") puede repetirse en
    varias filas a lo largo del tiempo, pero como mucho una puede estar
    `estado="vigente"` a la vez -- reforzado también a nivel de base de
    datos (ver la migración: índice único parcial sobre `fuente_id` WHERE
    `estado='vigente'`). Aprobar una versión nueva pasa la anterior a
    "obsoleta" automáticamente (no se borra, RNF-06) -- ver `kb.fuentes.
    aprobar_fuente`, que es quien aplica esta transición."""

    __tablename__ = "fuente_conocimiento"
    __table_args__ = (
        # Invariante "una sola versión vigente por fuente_id" (Bloque K1) --
        # reforzado a nivel de base de datos, no solo confiado a
        # kb.fuentes.aprobar_fuente. Índice parcial: varias filas pueden
        # compartir fuente_id (una por versión histórica), pero como mucho
        # una con estado="vigente" a la vez.
        Index(
            "ux_fuente_conocimiento_una_vigente",
            "fuente_id",
            unique=True,
            postgresql_where=text("estado = 'vigente'"),
            sqlite_where=text("estado = 'vigente'"),
        ),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    # Identificador legible de negocio (p. ej. "POL-001", "CAT-001",
    # "GLO-001") -- el que usan la plantilla de importación (Bloque K2) y las
    # citas de "Regla aplicada" (Bloque K4). Distinto del `id` UUID (la FK
    # real que usan fragmento/regla/glosario/cuenta_contable/checklist).
    fuente_id: Mapped[str] = mapped_column(String(50), nullable=False)
    titulo: Mapped[str] = mapped_column(String(300), nullable=False)
    # regla_interna | normativa | referencia -- determina `prioridad`
    # (ver kb.fuentes.prioridad_de_tipo); validado en la capa de dominio,
    # no con un CHECK de base de datos (mismo criterio que el resto del
    # proyecto para campos "enum" en String, p. ej. Hallazgo.estado).
    tipo: Mapped[str] = mapped_column(String(20), nullable=False)
    # 1 (regla_interna) / 2 (normativa) / 3 (referencia) -- derivado de
    # `tipo`, no lo captura el curador directamente (Bloque K4 ordena por
    # esto antes que por similitud semántica).
    prioridad: Mapped[int] = mapped_column(nullable=False)
    version: Mapped[str] = mapped_column(String(50), nullable=False)
    vigente_desde: Mapped[date] = mapped_column(Date, nullable=False)
    # borrador | vigente | obsoleta (RF-16): toda fuente nueva entra como
    # "borrador" -- pasa a "vigente" solo cuando el Curador la aprueba.
    estado: Mapped[str] = mapped_column(String(20), nullable=False, default="borrador")
    area_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("area.id"), nullable=False)
    # Dueño de negocio del contenido (p. ej. "Jefatura de Contabilidad") --
    # texto libre, distinto de `cargado_por`/`aprobado_por` (usuarios reales
    # del sistema) y distinto de `area_id` (una misma área puede tener
    # varios dueños de distintas fuentes).
    dueno: Mapped[str] = mapped_column(String(200), nullable=False)
    archivo: Mapped[str] = mapped_column(String(1000), nullable=False)
    # Integridad del binario cargado (detecta reemplazos fuera de banda del
    # archivo en MinIO) -- hexdigest de 64 caracteres. Nulo mientras el
    # curador registró la fuente (Bloque K2, plantilla) pero el binario real
    # todavía no se adjuntó -- no es un valor inventado, es "pendiente".
    sha256: Mapped[str | None] = mapped_column(String(64))
    cargado_por: Mapped[uuid.UUID] = mapped_column(ForeignKey("usuario.id"), nullable=False)
    # Nulo mientras la fuente sigue en "borrador".
    aprobado_por: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("usuario.id"))
    fecha_carga: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    fecha_aprobacion: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Fragmento(Base):
    __tablename__ = "fragmento"

    id: Mapped[uuid.UUID] = _uuid_pk()
    fuente_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("fuente_conocimiento.id"), nullable=False
    )
    contenido: Mapped[str] = mapped_column(Text, nullable=False)
    referencia_vector: Mapped[str | None] = mapped_column(String(100))
    pagina_o_seccion: Mapped[str | None] = mapped_column(String(50))


class Regla(Base):
    __tablename__ = "regla"

    id: Mapped[uuid.UUID] = _uuid_pk()
    codigo: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    descripcion: Mapped[str] = mapped_column(Text, nullable=False)
    area_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("area.id"), nullable=False)
    tipo_documento: Mapped[str | None] = mapped_column(String(20))
    severidad: Mapped[str | None] = mapped_column(String(10))
    fuente_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("fuente_conocimiento.id"))
    vigente_desde: Mapped[date] = mapped_column(Date, nullable=False)
    version: Mapped[str] = mapped_column(String(50), nullable=False)
    estado: Mapped[str] = mapped_column(String(20), default="vigente")
    moneda: Mapped[str | None] = mapped_column(String(10))


class Glosario(Base):
    __tablename__ = "glosario"

    id: Mapped[uuid.UUID] = _uuid_pk()
    area_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("area.id"), nullable=False)
    termino: Mapped[str] = mapped_column(String(200), nullable=False)
    definicion: Mapped[str] = mapped_column(Text, nullable=False)
    fuente_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("fuente_conocimiento.id"))
    # Bloque K1: snapshot de la versión de `fuente_id` al momento de importar
    # esta fila (hoja "Glosario" de la plantilla, Bloque K2) -- si la fuente
    # gana una versión nueva, las filas de la versión anterior no se
    # sobrescriben, quedan como historial (mismo criterio que fuente_conocimiento).
    version: Mapped[str | None] = mapped_column(String(50))
    vigente_desde: Mapped[date | None] = mapped_column(Date)


class CuentaContable(Base):
    """RF-16, CU-08 (Bloque K1): reemplaza `kb/fuentes/catalogo-cuentas-
    contabilidad.csv` como fuente de verdad para RN-02 (cuenta vs. catálogo)
    -- ver `orquestador.pipeline_contable.cargar_catalogo` (Bloque K4, que
    es quien cambia esa función para consultar esta tabla en vez del CSV)."""

    __tablename__ = "cuenta_contable"
    __table_args__ = (UniqueConstraint("area_id", "codigo", name="ux_cuenta_contable_area_codigo"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    codigo: Mapped[str] = mapped_column(String(20), nullable=False)
    nombre: Mapped[str] = mapped_column(String(300), nullable=False)
    # Clasificación contable (activo/pasivo/patrimonio/ingreso/gasto) -- no
    # confundir con FuenteConocimiento.tipo (regla_interna/normativa/referencia).
    tipo: Mapped[str | None] = mapped_column(String(50))
    naturaleza: Mapped[str | None] = mapped_column(String(20))
    acepta_movimiento: Mapped[bool] = mapped_column(Boolean, default=True)
    notas: Mapped[str | None] = mapped_column(Text)
    area_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("area.id"), nullable=False)
    fuente_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("fuente_conocimiento.id"))
    version: Mapped[str | None] = mapped_column(String(50))


class ChecklistCierre(Base):
    """RF-16, CU-08 (Bloque K1): actividades de control de cierre que el
    agente puede verificar (CU-04, entrega 2) -- hoja "Checklist de cierre"
    de la plantilla de importación (Bloque K2). No existía como tabla antes
    de este bloque (no reemplaza ningún CSV previo)."""

    __tablename__ = "checklist_cierre"

    id: Mapped[uuid.UUID] = _uuid_pk()
    numero: Mapped[int] = mapped_column(nullable=False)
    actividad: Mapped[str] = mapped_column(Text, nullable=False)
    responsable: Mapped[str | None] = mapped_column(String(200))
    plazo: Mapped[str | None] = mapped_column(String(100))
    evidencia_requerida: Mapped[str | None] = mapped_column(String(300))
    area_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("area.id"), nullable=False)
    fuente_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("fuente_conocimiento.id"))
    version: Mapped[str | None] = mapped_column(String(50))


class Bitacora(Base):
    __tablename__ = "bitacora"

    id: Mapped[uuid.UUID] = _uuid_pk()
    usuario_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("usuario.id"), nullable=False)
    accion: Mapped[str] = mapped_column(String(100), nullable=False)
    entidad_tipo: Mapped[str] = mapped_column(String(50), nullable=False)
    entidad_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    fecha_hora: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    detalle: Mapped[str | None] = mapped_column(Text)
    # SRS v0.9 (RNF-02, RG-06): el rol se guarda en el momento del hecho, no se
    # resuelve al consultar -- si el rol de un usuario cambia después, el
    # historial de bitácora no debe cambiar retroactivamente. Nullable porque
    # los demás sitios que escriben en Bitacora (curaduria, etc.) no lo
    # llenan todavía -- solo decidir_hallazgo lo hace, ver api/main.py.
    rol: Mapped[str | None] = mapped_column(String(20))
    # True cuando quien decide es el mismo que cargó el documento -- permitido
    # por defecto desde SRS v0.9 (SEGREGACION_APROBACION=false), antes
    # bloqueado sin excepción (RN-07). Reemplaza "0 autoaprobaciones
    # permitidas" (PP-09 anterior) por "0 aprobaciones sin registro": toda
    # autoaprobación debe quedar marcada así en la bitácora.
    autoaprobado: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
