import boto3
import pytest
from moto import mock_aws
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from comun.modelos import Base
from comun.semillas import sembrar_datos_de_prueba


@pytest.fixture()
def sesion_bd() -> Session:
    # check_same_thread=False: los endpoints síncronos de FastAPI corren en un
    # threadpool (starlette.concurrency.run_in_threadpool), distinto del hilo
    # donde pytest crea esta sesión de SQLite en memoria.
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    fabrica = sessionmaker(bind=engine)
    sesion = fabrica()
    sembrar_datos_de_prueba(sesion)
    try:
        yield sesion
    finally:
        sesion.close()


@pytest.fixture()
def cliente_s3_bucket():
    with mock_aws():
        cliente = boto3.client("s3", region_name="us-east-1")
        cliente.create_bucket(Bucket="documentos")
        yield cliente
