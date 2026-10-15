"""El tiempo de espera de LanguageTool: la primera petición tras un rato sin uso es lenta (arranque
en frío de la JVM) y 20 s fijos la hacían fallar (hallazgo de la prueba de carga en stage)."""

import httpx

from ortografia import cliente_languagetool


class _Respuesta:
    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict:
        return {"matches": []}


def _capturar_timeout(monkeypatch) -> dict:
    visto: dict = {}

    def _post(url: str, *, data: dict, timeout: float):
        visto["timeout"] = timeout
        return _Respuesta()

    monkeypatch.setattr(httpx, "post", _post)
    return visto


def test_el_timeout_por_defecto_es_60_s(monkeypatch) -> None:
    monkeypatch.delenv("LANGUAGETOOL_TIMEOUT_S", raising=False)
    visto = _capturar_timeout(monkeypatch)

    cliente_languagetool.revisar_texto("hola")

    assert visto["timeout"] == 60.0


def test_el_timeout_se_configura_por_entorno_y_uno_explicito_manda(monkeypatch) -> None:
    monkeypatch.setenv("LANGUAGETOOL_TIMEOUT_S", "120")
    visto = _capturar_timeout(monkeypatch)

    cliente_languagetool.revisar_texto("hola")
    assert visto["timeout"] == 120.0

    cliente_languagetool.revisar_texto("hola", timeout=5)
    assert visto["timeout"] == 5


def test_un_valor_invalido_del_entorno_usa_el_defecto(monkeypatch) -> None:
    monkeypatch.setenv("LANGUAGETOOL_TIMEOUT_S", "abc")
    visto = _capturar_timeout(monkeypatch)

    cliente_languagetool.revisar_texto("hola")

    assert visto["timeout"] == 60.0
