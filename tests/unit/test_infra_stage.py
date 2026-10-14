"""P-15 Bloque 5: infraestructura de stage versionada (Garage, sin LocalStack,
límites de memoria, alembic y sin secretos en el repositorio)."""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
INFRA = RAIZ / "infra"

pytestmark = pytest.mark.skipif(shutil.which("docker") is None, reason="requiere docker compose")


def _config(tmp: Path, ambiente: str) -> dict:
    """Renderiza compose.yml + compose.<ambiente>.yml sobre una copia temporal de infra/, con
    la plantilla .env.<ambiente>.example como .env.<ambiente> (los env_file deben existir)."""
    shutil.copytree(INFRA, tmp / "infra", ignore=shutil.ignore_patterns("proxmox"))
    env = tmp / f".env.{ambiente}"
    shutil.copy(RAIZ / f".env.{ambiente}.example", env)
    comando = ["docker", "compose", "--env-file", str(env)]
    for archivo in ("compose.yml", f"compose.{ambiente}.yml"):
        comando += ["-f", str(tmp / "infra" / archivo)]
    resultado = subprocess.run(
        [*comando, "config", "--format", "json"], capture_output=True, text=True, check=False
    )
    assert resultado.returncode == 0, resultado.stderr
    return json.loads(resultado.stdout)


@pytest.fixture(scope="module")
def stage(tmp_path_factory) -> dict:
    return _config(tmp_path_factory.mktemp("stage"), "stage")


@pytest.fixture(scope="module")
def local(tmp_path_factory) -> dict:
    return _config(tmp_path_factory.mktemp("local"), "local")


def _bytes(valor: str | int) -> int:
    if isinstance(valor, int):
        return valor
    unidades = {"K": 1024, "M": 1024**2, "G": 1024**3}
    m = re.fullmatch(r"(\d+(?:\.\d+)?)([KMG]?)B?", valor.strip().upper())
    assert m, valor
    return int(float(m.group(1)) * unidades.get(m.group(2), 1))


def test_stage_define_garage_con_imagen_fijada_y_sin_puertos(stage) -> None:
    garage = stage["services"]["garage"]

    assert garage["image"] == "dxflrs/garage:v1.0.1"
    assert "ports" not in garage
    assert list(garage["networks"]) == ["red_interna"]
    assert garage["restart"] == "unless-stopped"


def test_garage_monta_meta_data_y_el_toml_de_solo_lectura(stage) -> None:
    volumenes = {v["source"]: v for v in stage["services"]["garage"]["volumes"]}

    assert volumenes["/srv/agente/garage/meta"]["target"] == "/var/lib/garage/meta"
    assert volumenes["/srv/agente/garage/data"]["target"] == "/var/lib/garage/data"
    toml = volumenes["/srv/agente/garage/garage.toml"]
    assert toml["target"] == "/etc/garage.toml"
    assert toml.get("read_only") is True
    assert all(v["type"] == "bind" for v in volumenes.values())


def test_stage_no_levanta_localstack_pero_local_si(stage, local) -> None:
    assert "localstack" not in stage["services"]
    assert "localstack" in local["services"]
    assert "garage" not in local["services"]


def test_la_api_de_stage_espera_a_garage_y_no_a_localstack(stage) -> None:
    dependencias = stage["services"]["api"]["depends_on"]

    assert "garage" in dependencias
    assert "localstack" not in dependencias
    assert {"redis", "postgres", "qdrant"} <= set(dependencias)


def test_la_api_local_sigue_dependiendo_de_localstack(local) -> None:
    assert "localstack" in local["services"]["api"]["depends_on"]


def test_stage_solo_publica_el_puerto_443_del_proxy(stage) -> None:
    publicados = {n: s["ports"] for n, s in stage["services"].items() if s.get("ports")}

    assert list(publicados) == ["proxy"]
    assert [p["published"] for p in publicados["proxy"]] == ["443"]


def test_limites_de_memoria_caben_en_la_vm_de_60_gb(stage) -> None:
    servicios = stage["services"]

    ollama = _bytes(servicios["ollama"]["deploy"]["resources"]["limits"]["memory"])
    assert 40 * 1024**3 <= ollama <= 48 * 1024**3  # antes 64G en una VM de 60 GB

    proxy = _bytes(servicios["proxy"]["deploy"]["resources"]["limits"]["memory"])
    assert proxy <= 1024**3  # antes 64G para un proxy

    garage = servicios["garage"]["deploy"]["resources"]["limits"]
    assert _bytes(garage["memory"]) <= 1024**3


def test_env_stage_apunta_a_garage() -> None:
    texto = (RAIZ / ".env.stage.example").read_text(encoding="utf-8")

    assert re.search(r"^MINIO_ENDPOINT=garage:3900$", texto, re.M)
    assert "minio:9000" not in texto


def test_plantilla_de_garage_no_trae_secretos_y_usa_la_region_del_cliente() -> None:
    texto = (INFRA / "garage" / "garage.toml.example").read_text(encoding="utf-8")

    assert 's3_region = "us-east-1"' in texto
    assert "replication_factor = 1" in texto
    secreto = re.search(r'^rpc_secret\s*=\s*"([^"]*)"', texto, re.M)
    assert secreto and not re.fullmatch(r"[0-9a-f]{64}", secreto.group(1))
    assert "openssl rand -hex 32" in texto


def test_el_repositorio_no_contiene_un_rpc_secret_real() -> None:
    for archivo in list(INFRA.rglob("*")) + [RAIZ / ".env.stage.example"]:
        if archivo.is_file() and archivo.suffix in {".toml", ".yml", ".sh", ".example", ".md"}:
            texto = archivo.read_text(encoding="utf-8", errors="ignore")
            assert not re.search(r'rpc_secret\s*=\s*"[0-9a-f]{64}"', texto), archivo


def test_el_toml_real_de_garage_esta_ignorado_por_git() -> None:
    resultado = subprocess.run(
        ["git", "check-ignore", "infra/garage/garage.toml"],
        cwd=RAIZ,
        capture_output=True,
        text=True,
        check=False,
    )

    assert resultado.returncode == 0, "infra/garage/garage.toml debe estar en .gitignore"


def test_script_de_inicializacion_es_idempotente_y_crea_los_buckets() -> None:
    ruta = INFRA / "scripts" / "inicializar-garage.sh"
    texto = ruta.read_text(encoding="utf-8")

    assert texto.startswith("#!/usr/bin/env bash")
    assert "set -euo pipefail" in texto
    for fragmento in (
        "layout assign",
        "layout apply",
        "key create",
        "bucket create",
        "bucket allow",
    ):
        assert fragmento in texto
    assert "conocimiento" in texto and "documentos" in texto
    # cada creación está precedida de una consulta de existencia
    assert "bucket info" in texto and "key info" in texto

    bash = shutil.which("bash")
    if bash:
        sintaxis = subprocess.run([bash, "-n", str(ruta)], capture_output=True, text=True)
        assert sintaxis.returncode == 0, sintaxis.stderr


def test_alembic_esta_en_los_requirements_de_la_api() -> None:
    lineas = (RAIZ / "src" / "api" / "requirements.txt").read_text(encoding="utf-8").splitlines()

    assert lineas.count("alembic==1.14.0") == 1
