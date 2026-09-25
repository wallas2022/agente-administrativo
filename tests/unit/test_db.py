import pytest

from comun.db import construir_url_bd


def test_construir_url_bd_usa_variables_de_entorno(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("POSTGRES_HOST", "midb")
    monkeypatch.setenv("POSTGRES_PORT", "5433")
    monkeypatch.setenv("POSTGRES_DB", "midocumento")
    monkeypatch.setenv("POSTGRES_USER", "usuario")
    monkeypatch.setenv("POSTGRES_PASSWORD", "clave")

    url = construir_url_bd()

    assert url == "postgresql+psycopg://usuario:clave@midb:5433/midocumento"


def test_construir_url_bd_tiene_valores_por_defecto_razonables(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    variables = (
        "POSTGRES_HOST",
        "POSTGRES_PORT",
        "POSTGRES_DB",
        "POSTGRES_USER",
        "POSTGRES_PASSWORD",
    )
    for var in variables:
        monkeypatch.delenv(var, raising=False)

    url = construir_url_bd()

    assert url.startswith("postgresql+psycopg://")
    assert "@postgres:5432/" in url
