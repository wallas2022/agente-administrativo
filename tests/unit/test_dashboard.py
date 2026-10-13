"""P-13 (Bloque 3): lógica del Dashboard del Administrador -- consumo
(HU-26..28), recursos (HU-29, vía Prometheus/Ollama simulados) y
configuración vigente (HU-30, RNF-17: lista blanca, nunca un secreto).
"""

import re
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from comun.dashboard import (
    UMBRAL_DISCO_ALERTA_PCT,
    UMBRAL_MEMORIA_OLLAMA_ALERTA_PCT,
    UMBRAL_TIMEOUTS_ALERTA_PCT,
    VARIABLES_CONFIGURACION_VISIBLES,
    _calcular_alertas,
    _consultar_contenedores,
    _consultar_host,
    _consultar_ollama,
    calcular_consumo,
    calcular_consumo_por_usuario,
    consultar_recursos,
    obtener_configuracion_vigente,
)
from comun.modelos import Area, Base, Rol, Usuario

RAIZ_PROYECTO = Path(__file__).resolve().parents[2]


@pytest.fixture()
def sesion() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


@pytest.fixture()
def usuario_y_area(sesion: Session) -> tuple[Usuario, Area]:
    area = Area(nombre="Contabilidad")
    rol = Rol(nombre="analista")
    sesion.add_all([area, rol])
    sesion.flush()
    usuario = Usuario(nombre="Ana", email="ana@local", area_id=area.id, rol_id=rol.id)
    sesion.add(usuario)
    sesion.commit()
    return usuario, area


def _agregar_uso(
    sesion: Session,
    *,
    usuario: Usuario,
    area: Area,
    analisis_id=None,
    caso_uso: str = "contable",
    modelo: str = "gpt-oss:20b",
    tokens_entrada: int | None = 100,
    tokens_salida: int | None = 50,
    duracion_total_ms: int | None = 2000,
    duracion_generacion_ms: int | None = 1500,
    resultado: str = "ok",
    fecha_hora=None,
):
    from comun.modelos import UsoLlm

    sesion.add(
        UsoLlm(
            usuario_id=usuario.id,
            area_id=area.id,
            analisis_id=analisis_id,
            caso_uso=caso_uso,
            modelo=modelo,
            fecha_hora=fecha_hora or datetime.now(UTC),
            tokens_entrada=tokens_entrada,
            tokens_salida=tokens_salida,
            duracion_total_ms=duracion_total_ms,
            duracion_carga_ms=None,
            duracion_lectura_ms=None,
            duracion_generacion_ms=duracion_generacion_ms,
            resultado=resultado,
        )
    )
    sesion.commit()


# --- calcular_consumo -------------------------------------------------------


def test_calcular_consumo_tarjetas_y_serie_diaria(sesion, usuario_y_area) -> None:
    usuario, area = usuario_y_area
    hoy = datetime.now(UTC)
    _agregar_uso(sesion, usuario=usuario, area=area, fecha_hora=hoy)
    _agregar_uso(
        sesion,
        usuario=usuario,
        area=area,
        fecha_hora=hoy,
        resultado="timeout",
        tokens_entrada=None,
        tokens_salida=None,
        duracion_total_ms=None,
        duracion_generacion_ms=None,
    )
    _agregar_uso(sesion, usuario=usuario, area=area, fecha_hora=hoy - timedelta(days=1))

    resultado = calcular_consumo(sesion)

    assert resultado["tarjetas"]["llamadas"] == 3
    assert resultado["tarjetas"]["tokens_entrada"] == 200
    assert resultado["tarjetas"]["tokens_salida"] == 100
    assert resultado["tarjetas"]["tokens_totales"] == 300
    assert resultado["tarjetas"]["pct_timeouts"] == pytest.approx(33.33, abs=0.01)
    assert len(resultado["serie_diaria"]) == 2


def test_calcular_consumo_tokens_por_segundo(sesion, usuario_y_area) -> None:
    usuario, area = usuario_y_area
    _agregar_uso(sesion, usuario=usuario, area=area, tokens_salida=100, duracion_generacion_ms=2000)
    resultado = calcular_consumo(sesion)
    assert resultado["tarjetas"]["tokens_por_segundo_promedio"] == pytest.approx(50.0)


def test_calcular_consumo_filtra_por_caso_uso_y_modelo(sesion, usuario_y_area) -> None:
    usuario, area = usuario_y_area
    _agregar_uso(sesion, usuario=usuario, area=area, caso_uso="contable", modelo="gpt-oss:20b")
    _agregar_uso(sesion, usuario=usuario, area=area, caso_uso="ortografia", modelo="bge-m3")

    assert calcular_consumo(sesion, caso_uso="contable")["tarjetas"]["llamadas"] == 1
    assert calcular_consumo(sesion, modelo="bge-m3")["tarjetas"]["llamadas"] == 1
    assert calcular_consumo(sesion, caso_uso="redaccion")["tarjetas"]["llamadas"] == 0


def test_calcular_consumo_filtra_por_rango_de_fechas(sesion, usuario_y_area) -> None:
    usuario, area = usuario_y_area
    hoy = datetime.now(UTC)
    _agregar_uso(sesion, usuario=usuario, area=area, fecha_hora=hoy)
    _agregar_uso(sesion, usuario=usuario, area=area, fecha_hora=hoy - timedelta(days=10))

    resultado = calcular_consumo(sesion, desde=(hoy - timedelta(days=1)).date(), hasta=hoy.date())
    assert resultado["tarjetas"]["llamadas"] == 1


def test_calcular_consumo_ranking_por_caso_de_uso_y_modelo(sesion, usuario_y_area) -> None:
    usuario, area = usuario_y_area
    _agregar_uso(
        sesion, usuario=usuario, area=area, caso_uso="contable", tokens_entrada=100, tokens_salida=0
    )
    _agregar_uso(
        sesion, usuario=usuario, area=area, caso_uso="contable", tokens_entrada=100, tokens_salida=0
    )
    _agregar_uso(
        sesion,
        usuario=usuario,
        area=area,
        caso_uso="ortografia",
        tokens_entrada=10,
        tokens_salida=0,
    )

    resultado = calcular_consumo(sesion)
    ranking = {r["caso_uso"]: r for r in resultado["ranking_caso_uso"]}
    assert ranking["contable"]["tokens_totales"] == 200
    assert ranking["contable"]["llamadas"] == 2
    assert ranking["ortografia"]["tokens_totales"] == 10
    # El primero del ranking es el de más tokens.
    assert resultado["ranking_caso_uso"][0]["caso_uso"] == "contable"


def test_calcular_consumo_duracion_media_del_analisis_por_caso_de_uso(
    sesion, usuario_y_area
) -> None:
    usuario, area = usuario_y_area
    from comun.modelos import Analisis, TipoRevision

    tipo = TipoRevision(nombre="contable")
    sesion.add(tipo)
    sesion.flush()
    inicio = datetime.now(UTC) - timedelta(minutes=5)
    analisis = Analisis(
        documento_id=uuid.uuid4(),
        tipo_revision_id=tipo.id,
        usuario_id=usuario.id,
        fecha_inicio=inicio,
        fecha_fin=inicio + timedelta(minutes=2),
        estado="completado",
    )
    # documento_id apunta a un documento inexistente -- no hace falta uno
    # real, calcular_consumo solo lee fecha_inicio/fecha_fin de Analisis.
    sesion.add(analisis)
    sesion.flush()
    _agregar_uso(sesion, usuario=usuario, area=area, caso_uso="contable", analisis_id=analisis.id)

    resultado = calcular_consumo(sesion)
    ranking = {r["caso_uso"]: r for r in resultado["ranking_caso_uso"]}
    assert ranking["contable"]["duracion_media_analisis_ms"] == pytest.approx(120_000.0)


def test_calcular_consumo_embeddings_kb_sin_analisis_no_tiene_duracion(
    sesion, usuario_y_area
) -> None:
    usuario, area = usuario_y_area
    _agregar_uso(sesion, usuario=usuario, area=area, caso_uso="embeddings_kb", analisis_id=None)

    resultado = calcular_consumo(sesion)
    ranking = {r["caso_uso"]: r for r in resultado["ranking_caso_uso"]}
    assert ranking["embeddings_kb"]["duracion_media_analisis_ms"] is None


# --- calcular_consumo_por_usuario -------------------------------------------


def test_calcular_consumo_por_usuario_agrega_correctamente(sesion, usuario_y_area) -> None:
    usuario, area = usuario_y_area
    analisis_id_1 = uuid.uuid4()
    analisis_id_2 = uuid.uuid4()
    _agregar_uso(
        sesion,
        usuario=usuario,
        area=area,
        analisis_id=analisis_id_1,
        tokens_entrada=10,
        tokens_salida=5,
    )
    _agregar_uso(
        sesion,
        usuario=usuario,
        area=area,
        analisis_id=analisis_id_1,
        tokens_entrada=10,
        tokens_salida=5,
    )
    _agregar_uso(
        sesion,
        usuario=usuario,
        area=area,
        analisis_id=analisis_id_2,
        tokens_entrada=10,
        tokens_salida=5,
        resultado="timeout",
    )

    filas = calcular_consumo_por_usuario(sesion)
    assert len(filas) == 1
    fila = filas[0]
    assert fila["usuario_email"] == "ana@local"
    assert fila["area_nombre"] == "Contabilidad"
    assert fila["numero_analisis"] == 2
    assert fila["tokens_entrada"] == 30
    assert fila["timeouts"] == 1


def test_calcular_consumo_por_usuario_ordena_de_mayor_a_menor() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    sesion = Session(engine)
    area = Area(nombre="Contabilidad")
    rol = Rol(nombre="analista")
    sesion.add_all([area, rol])
    sesion.flush()
    usuario_poco = Usuario(nombre="Poco", email="poco@local", area_id=area.id, rol_id=rol.id)
    usuario_mucho = Usuario(nombre="Mucho", email="mucho@local", area_id=area.id, rol_id=rol.id)
    sesion.add_all([usuario_poco, usuario_mucho])
    sesion.commit()

    _agregar_uso(sesion, usuario=usuario_poco, area=area, tokens_entrada=1, tokens_salida=1)
    _agregar_uso(sesion, usuario=usuario_mucho, area=area, tokens_entrada=1000, tokens_salida=1000)

    filas = calcular_consumo_por_usuario(sesion)
    assert filas[0]["usuario_email"] == "mucho@local"
    assert filas[1]["usuario_email"] == "poco@local"


# --- Recursos (Prometheus/Ollama simulados) ---------------------------------


def test_consultar_host_con_prometheus_simulado(monkeypatch) -> None:
    respuestas = {
        "node_memory_MemTotal_bytes": 16_000_000_000,
        "node_memory_MemAvailable_bytes": 4_000_000_000,
        'node_filesystem_size_bytes{mountpoint="/"}': 500_000_000_000,
        'node_filesystem_avail_bytes{mountpoint="/"}': 100_000_000_000,
        '100 - (avg(rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100)': 42.5,
        "node_load1": 1.5,
    }

    def _get_falso(url, *, params, timeout):
        valor = respuestas.get(params["query"])
        if valor is None and 'node_cpu_seconds_total{mode="idle"}' == params["query"]:
            resultado = [{"metric": {"cpu": "0"}}, {"metric": {"cpu": "1"}}]
        else:
            resultado = [{"value": [0, str(valor)]}]

        class _Respuesta:
            def raise_for_status(self) -> None:
                pass

            def json(self) -> dict:
                return {"status": "success", "data": {"result": resultado}}

        return _Respuesta()

    monkeypatch.setattr(httpx, "get", _get_falso)

    host = _consultar_host("http://prometheus:9090")
    assert host is not None
    assert host["memoria_usada_bytes"] == 12_000_000_000
    assert host["memoria_total_bytes"] == 16_000_000_000
    assert host["disco_usado_bytes"] == 400_000_000_000
    assert host["cpu_ocupado_pct"] == 42.5
    assert host["vcpus"] == 2
    assert host["carga_1m"] == 1.5


def test_consultar_host_devuelve_none_si_prometheus_no_responde(monkeypatch) -> None:
    def _get_que_falla(url, *, params, timeout):
        raise httpx.ConnectError("no se pudo conectar")

    monkeypatch.setattr(httpx, "get", _get_que_falla)

    assert _consultar_host("http://prometheus:9090") is None


def test_consultar_contenedores_calcula_pct_del_limite(monkeypatch) -> None:
    def _get_falso(url, *, params, timeout):
        query = params["query"]

        class _Respuesta:
            def raise_for_status(self) -> None:
                pass

            def json(self) -> dict:
                if "container_cpu_usage_seconds_total" in query:
                    resultado = [{"metric": {"name": "infra-ollama-1"}, "value": [0, "15.0"]}]
                elif "container_spec_memory_limit_bytes" in query:
                    resultado = [{"metric": {"name": "infra-ollama-1"}, "value": [0, "1000000000"]}]
                else:  # container_memory_usage_bytes
                    resultado = [{"metric": {"name": "infra-ollama-1"}, "value": [0, "950000000"]}]
                return {"status": "success", "data": {"result": resultado}}

        return _Respuesta()

    monkeypatch.setattr(httpx, "get", _get_falso)

    contenedores = _consultar_contenedores("http://prometheus:9090")
    assert contenedores is not None
    assert len(contenedores) == 1
    assert contenedores[0]["nombre"] == "infra-ollama-1"
    assert contenedores[0]["cpu_pct"] == 15.0
    assert contenedores[0]["memoria_pct_del_limite"] == pytest.approx(95.0)


def test_consultar_contenedores_sin_limite_configurado_no_calcula_pct(monkeypatch) -> None:
    def _get_falso(url, *, params, timeout):
        query = params["query"]

        class _Respuesta:
            def raise_for_status(self) -> None:
                pass

            def json(self) -> dict:
                if "container_cpu_usage_seconds_total" in query:
                    resultado = [{"metric": {"name": "infra-api-1"}, "value": [0, "5.0"]}]
                elif "container_spec_memory_limit_bytes" in query:
                    # cAdvisor reporta el total del host cuando no hay límite.
                    resultado = [
                        {"metric": {"name": "infra-api-1"}, "value": [0, "9223372036854771712"]}
                    ]
                else:
                    resultado = [{"metric": {"name": "infra-api-1"}, "value": [0, "200000000"]}]
                return {"status": "success", "data": {"result": resultado}}

        return _Respuesta()

    monkeypatch.setattr(httpx, "get", _get_falso)

    contenedores = _consultar_contenedores("http://prometheus:9090")
    assert contenedores[0]["memoria_limite_bytes"] is None
    assert contenedores[0]["memoria_pct_del_limite"] is None


def test_consultar_ollama_con_respuesta_real(monkeypatch) -> None:
    def _get_falso(url, *, timeout):
        class _Respuesta:
            def raise_for_status(self) -> None:
                pass

            def json(self) -> dict:
                if url.endswith("/api/ps"):
                    return {"models": [{"name": "gpt-oss:20b", "size": 13_000_000_000}]}
                return {"models": [{"name": "gpt-oss:20b"}, {"name": "bge-m3"}]}

        return _Respuesta()

    monkeypatch.setattr(httpx, "get", _get_falso)

    ollama = _consultar_ollama("http://ollama:11434")
    assert ollama is not None
    assert len(ollama["modelos_en_memoria"]) == 1
    assert len(ollama["modelos_instalados"]) == 2


def test_consultar_ollama_devuelve_none_si_no_responde(monkeypatch) -> None:
    def _get_que_falla(url, *, timeout):
        raise httpx.ConnectError("no se pudo conectar")

    monkeypatch.setattr(httpx, "get", _get_que_falla)
    assert _consultar_ollama("http://ollama:11434") is None


def test_consultar_recursos_corta_temprano_si_prometheus_no_responde(sesion, monkeypatch) -> None:
    """Antes de este fix, con Prometheus apagado se intentaban igual las ~10
    consultas PromQL de _consultar_host/_consultar_contenedores (cada una
    con su propio timeout de 5 s) antes de darse por vencido -- contra un
    servidor real que nunca responde, eso tardaba decenas de segundos
    (medido en vivo: ~36 s). Una sola comprobación de disponibilidad evita
    las demás consultas."""
    llamadas_prometheus = []

    def _get_que_falla(url, **kwargs):
        if "9090" in url:
            llamadas_prometheus.append(url)
        raise httpx.ConnectError("no se pudo conectar")

    monkeypatch.setattr(httpx, "get", _get_que_falla)

    resultado = consultar_recursos(sesion)

    assert resultado["prometheus_disponible"] is False
    assert resultado["host"] is None
    assert resultado["contenedores"] is None
    assert len(llamadas_prometheus) == 1


def test_consultar_recursos_consulta_host_y_contenedores_si_prometheus_responde(
    sesion, monkeypatch
) -> None:
    def _get_falso(url, **kwargs):
        class _Respuesta:
            status_code = 200

            def raise_for_status(self) -> None:
                pass

            def json(self) -> dict:
                return {"status": "success", "data": {"result": []}}

        return _Respuesta()

    monkeypatch.setattr(httpx, "get", _get_falso)

    resultado = consultar_recursos(sesion)

    assert resultado["prometheus_disponible"] is True


# --- Alertas -----------------------------------------------------------------


def test_alerta_de_disco_se_dispara_sobre_el_umbral(sesion) -> None:
    host = {"disco_total_bytes": 100, "disco_usado_bytes": UMBRAL_DISCO_ALERTA_PCT}
    alertas = _calcular_alertas(sesion, host=host, contenedores=None)
    assert any(a["tipo"] == "disco" for a in alertas)


def test_sin_alerta_de_disco_bajo_el_umbral(sesion) -> None:
    host = {"disco_total_bytes": 100, "disco_usado_bytes": UMBRAL_DISCO_ALERTA_PCT - 10}
    alertas = _calcular_alertas(sesion, host=host, contenedores=None)
    assert not any(a["tipo"] == "disco" for a in alertas)


def test_alerta_de_memoria_ollama_se_dispara_sobre_el_umbral(sesion) -> None:
    contenedores = [
        {"nombre": "infra-ollama-1", "memoria_pct_del_limite": UMBRAL_MEMORIA_OLLAMA_ALERTA_PCT}
    ]
    alertas = _calcular_alertas(sesion, host=None, contenedores=contenedores)
    assert any(a["tipo"] == "memoria_ollama" for a in alertas)


def test_alerta_de_timeouts_se_dispara_sobre_el_umbral(sesion, usuario_y_area) -> None:
    usuario, area = usuario_y_area
    for _ in range(2):
        _agregar_uso(sesion, usuario=usuario, area=area, resultado="timeout")
    _agregar_uso(sesion, usuario=usuario, area=area, resultado="ok")
    # 2/3 = 66.7 % > 10 %.
    alertas = _calcular_alertas(sesion, host=None, contenedores=None)
    assert any(a["tipo"] == "timeouts_llm" for a in alertas)


def test_sin_alerta_de_timeouts_bajo_el_umbral(sesion, usuario_y_area) -> None:
    usuario, area = usuario_y_area
    for _ in range(19):
        _agregar_uso(sesion, usuario=usuario, area=area, resultado="ok")
    _agregar_uso(sesion, usuario=usuario, area=area, resultado="timeout")
    # 1/20 = 5 % < 10 %.
    alertas = _calcular_alertas(sesion, host=None, contenedores=None)
    assert not any(a["tipo"] == "timeouts_llm" for a in alertas)
    assert UMBRAL_TIMEOUTS_ALERTA_PCT == 10.0


# --- Configuración vigente (RNF-17) ------------------------------------------


def test_obtener_configuracion_vigente_solo_expone_la_lista_blanca(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("API_SECRET_KEY", "no-deberia-aparecer-nunca")
    monkeypatch.setenv("POSTGRES_PASSWORD", "tampoco-esta")

    configuracion = obtener_configuracion_vigente()

    assert configuracion["variables"]["APP_ENV"] == "local"
    assert "API_SECRET_KEY" not in configuracion["variables"]
    assert "POSTGRES_PASSWORD" not in configuracion["variables"]
    assert "no-deberia-aparecer-nunca" not in str(configuracion)
    assert "tampoco-esta" not in str(configuracion)


def test_obtener_configuracion_vigente_omite_una_variable_no_definida(monkeypatch) -> None:
    monkeypatch.delenv("QDRANT_COLECCION", raising=False)
    configuracion = obtener_configuracion_vigente()
    assert "QDRANT_COLECCION" not in configuracion["variables"]


_PATRON_NOMBRE_SECRETO = re.compile(r"(PASSWORD|SECRET|KEY|TOKEN)", re.IGNORECASE)


def test_ninguna_variable_de_la_lista_blanca_parece_un_secreto() -> None:
    """RNF-17 (lista blanca, no lista negra): ninguna de las variables que
    SÍ se muestran tiene un nombre que sugiera un secreto -- una defensa
    extra sobre la propia lista, no solo "no está en la lista negra"."""
    for nombre in VARIABLES_CONFIGURACION_VISIBLES:
        assert not _PATRON_NOMBRE_SECRETO.search(nombre), nombre


def test_ninguna_variable_marcada_como_secreta_en_env_local_example_esta_en_la_lista_blanca() -> (
    None
):
    """P-13 §4 (R-D2): "prueba automática que falla si aparece un valor de
    .env marcado como secreto" -- se asume "marcado como secreto" un
    nombre que contiene PASSWORD/SECRET/KEY/TOKEN (mismo criterio de
    RNF-17), leído del .env.local.example real del repo."""
    contenido = (RAIZ_PROYECTO / ".env.local.example").read_text(encoding="utf-8")
    nombres_del_env = {
        linea.split("=", 1)[0].strip()
        for linea in contenido.splitlines()
        if linea.strip() and not linea.strip().startswith("#") and "=" in linea
    }
    nombres_secretos = {n for n in nombres_del_env if _PATRON_NOMBRE_SECRETO.search(n)}
    assert nombres_secretos, "la lista de nombres secretos no debería salir vacía"

    interseccion = nombres_secretos & set(VARIABLES_CONFIGURACION_VISIBLES)
    assert interseccion == set()
