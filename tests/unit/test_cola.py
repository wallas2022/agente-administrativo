import pytest

from comun.cola import construir_url_redis


def test_construir_url_redis_con_password(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REDIS_HOST", "midis")
    monkeypatch.setenv("REDIS_PORT", "6380")
    monkeypatch.setenv("REDIS_PASSWORD", "clave")

    assert construir_url_redis(db=1) == "redis://:clave@midis:6380/1"


def test_construir_url_redis_sin_password(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("REDIS_PASSWORD", raising=False)
    monkeypatch.setenv("REDIS_HOST", "midis")
    monkeypatch.setenv("REDIS_PORT", "6380")

    assert construir_url_redis(db=0) == "redis://midis:6380/0"
