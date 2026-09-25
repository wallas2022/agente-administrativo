"""Modelo de datos (SQLAlchemy) — refleja docs/03-diseno/er/modelo-datos.md.

Sin lógica de negocio: solo la estructura de las 15 entidades y sus relaciones.
Las migraciones (Alembic) viven en src/api/migraciones/.
"""

import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Numeric, String, Text
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
    fecha_carga: Mapped[datetime] = mapped_column(DateTime, nullable=False)
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
    fecha_creacion: Mapped[datetime] = mapped_column(DateTime, nullable=False)

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
    fecha_inicio: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    fecha_fin: Mapped[datetime | None] = mapped_column(DateTime)
    modelo_llm: Mapped[str | None] = mapped_column(String(200))
    version_prompt: Mapped[str | None] = mapped_column(String(50))
    estado: Mapped[str] = mapped_column(String(20), nullable=False)

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
    monto: Mapped[float | None] = mapped_column(Numeric(18, 2))
    # No es un solo código ISO 4217 (3 letras): RN-05 registra la combinación de
    # monedas mezcladas en la partida, p. ej. "Q/USD".
    moneda: Mapped[str | None] = mapped_column(String(10))
    estado: Mapped[str] = mapped_column(String(20), default="pendiente")

    analisis: Mapped["Analisis"] = relationship(back_populates="hallazgos")
    decisiones: Mapped[list["Decision"]] = relationship(back_populates="hallazgo")


class Decision(Base):
    __tablename__ = "decision"

    id: Mapped[uuid.UUID] = _uuid_pk()
    hallazgo_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("hallazgo.id"), nullable=False)
    usuario_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("usuario.id"), nullable=False)
    resultado: Mapped[str] = mapped_column(String(20), nullable=False)
    comentario: Mapped[str | None] = mapped_column(Text)
    fecha: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    hallazgo: Mapped["Hallazgo"] = relationship(back_populates="decisiones")


class FuenteConocimiento(Base):
    __tablename__ = "fuente_conocimiento"

    id: Mapped[uuid.UUID] = _uuid_pk()
    nombre: Mapped[str] = mapped_column(String(300), nullable=False)
    area_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("area.id"), nullable=False)
    curador_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("usuario.id"), nullable=False)
    version: Mapped[str] = mapped_column(String(50), nullable=False)
    vigente_desde: Mapped[date] = mapped_column(Date, nullable=False)
    estado: Mapped[str] = mapped_column(String(20), default="vigente")
    ruta_archivo: Mapped[str] = mapped_column(String(1000), nullable=False)


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


class Bitacora(Base):
    __tablename__ = "bitacora"

    id: Mapped[uuid.UUID] = _uuid_pk()
    usuario_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("usuario.id"), nullable=False)
    accion: Mapped[str] = mapped_column(String(100), nullable=False)
    entidad_tipo: Mapped[str] = mapped_column(String(50), nullable=False)
    entidad_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    fecha_hora: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    detalle: Mapped[str | None] = mapped_column(Text)
