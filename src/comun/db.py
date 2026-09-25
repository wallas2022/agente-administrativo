"""Conexión a PostgreSQL. Sin lógica de negocio: solo construcción de la URL,
el engine y la fábrica de sesiones usados por api y orquestador.
"""

import os
from collections.abc import Iterator

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker


def construir_url_bd() -> str:
    host = os.environ.get("POSTGRES_HOST", "postgres")
    port = os.environ.get("POSTGRES_PORT", "5432")
    db = os.environ.get("POSTGRES_DB", "agente_administrativo")
    user = os.environ.get("POSTGRES_USER", "")
    password = os.environ.get("POSTGRES_PASSWORD", "")
    return f"postgresql+psycopg://{user}:{password}@{host}:{port}/{db}"


_engine: Engine | None = None
_fabrica_sesion: sessionmaker[Session] | None = None


def obtener_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = create_engine(construir_url_bd(), pool_pre_ping=True)
    return _engine


def obtener_fabrica_sesion() -> sessionmaker[Session]:
    global _fabrica_sesion
    if _fabrica_sesion is None:
        _fabrica_sesion = sessionmaker(bind=obtener_engine())
    return _fabrica_sesion


def obtener_sesion() -> Iterator[Session]:
    """Dependencia de FastAPI: entrega una sesión y la cierra al terminar."""
    sesion = obtener_fabrica_sesion()()
    try:
        yield sesion
    finally:
        sesion.close()
