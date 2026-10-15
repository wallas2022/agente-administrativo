#!/usr/bin/env python3
# ruff: noqa: E501
"""Prueba de carga con usuarios simultáneos del Agente Administrativo (PP-12, PP-13, RNF-04/05).

Simula N usuarios que hacen lo mismo a la vez por la API (igual que la interfaz) y mide:
  - t_primeros: segundos hasta que aparecen los primeros hallazgos (o la respuesta del chat)
  - t_total:    segundos hasta que el análisis termina (o la respuesta del chat)
  - errores y tiempos excedidos, y documentos por hora

Escenarios:  contable (Excel), ortografia (texto), chat (pregunta a la base), mixto.

Solo las cifras medidas en stage valen para RNF-04/RNF-05; en local son una referencia.
La contraseña va en la variable CARGA_PASSWORD (no como argumento, para no dejarla en el historial).

Ejemplo:
    CARGA_PASSWORD=... python carga_concurrente.py --base http://127.0.0.1:8001 \
        --email analista@local --escenario contable --usuarios 1,3,5 --salida resultados.json
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import httpx

RAIZ = Path(__file__).resolve().parents[2]
EXCEL_POR_DEFECTO = RAIZ / "tests" / "dataset" / "cu-01" / "cu01-08-multiples-errores.xlsx"
PERIODO_POR_DEFECTO = "2026-01"  # período con el que se generó el dataset de CU-01
MAXIMO_USUARIOS = 20
# La API devuelve el estado del documento: estos dos significan "todavía en curso".
ESTADOS_EN_CURSO = {"cargado", "procesando"}
ESTADOS_FALLIDOS = {"fallido", "excedido", "error"}

TEXTO_ORTOGRAFIA = (
    "Estimados compañeros: les informamos que el cierre contable de este mes se realizará "
    "el día viernes. Aver si todos los reportes estan listos antes de esa fecha, porque "
    "cualquier diferencia debe ser revisada por la jefatura. Les recordamos que las "
    "conciliaciones bancarias deven estar completas y que los asientos de ajuste se "
    "registran con su respectivo soporte. Agradecemos su colaboración y puntualidad en la "
    "entrega de la información solicitada."
)
PREGUNTA_CHAT = "¿Cuál es el plazo para cerrar el período contable y qué documentos se necesitan?"


@dataclass
class Medicion:
    escenario: str
    ok: bool
    t_primeros: float | None
    t_total: float | None
    estado: str
    error: str | None = None


def percentil(valores: list[float], p: float) -> float | None:
    """Percentil por rango más cercano (p entre 0 y 100)."""
    if not valores:
        return None
    ordenados = sorted(valores)
    posicion = max(1, math.ceil(p / 100 * len(ordenados)))
    return ordenados[posicion - 1]


def resumir(mediciones: list[Medicion], duracion_s: float, usuarios: int, escenario: str) -> dict:
    exitosas = [m for m in mediciones if m.ok]
    primeros = [m.t_primeros for m in exitosas if m.t_primeros is not None]
    totales = [m.t_total for m in exitosas if m.t_total is not None]
    return {
        "escenario": escenario,
        "usuarios": usuarios,
        "peticiones": len(mediciones),
        "ok": len(exitosas),
        "fallos": len(mediciones) - len(exitosas),
        "estados": {e: sum(1 for m in mediciones if m.estado == e) for e in sorted({m.estado for m in mediciones})},
        "errores": sorted({m.error for m in mediciones if m.error}),
        "t_primeros_p50_s": percentil(primeros, 50),
        "t_primeros_p90_s": percentil(primeros, 90),
        "t_total_p50_s": percentil(totales, 50),
        "t_total_p90_s": percentil(totales, 90),
        "t_total_max_s": max(totales) if totales else None,
        "duracion_s": round(duracion_s, 1),
        "docs_por_hora": round(len(exitosas) / duracion_s * 3600, 1) if duracion_s > 0 else None,
    }


def estados_texto(r: dict) -> str:
    return ", ".join(f"{e}: {n}" for e, n in r.get("estados", {}).items()) or "—"


def tabla_markdown(resumenes: list[dict]) -> str:
    def f(v: float | None) -> str:
        return "—" if v is None else f"{v:.1f}"

    lineas = [
        "| Escenario | Usuarios | OK / total | 1ros. hallazgos p50 (s) | Total p50 (s) | Total p90 (s) "
        "| Total máx. (s) | Duración (s) | Docs/hora | Estados finales | Errores |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for r in resumenes:
        lineas.append(
            f"| {r['escenario']} | {r['usuarios']} | {r['ok']} / {r['peticiones']} "
            f"| {f(r['t_primeros_p50_s'])} | {f(r['t_total_p50_s'])} | {f(r['t_total_p90_s'])} "
            f"| {f(r['t_total_max_s'])} | {r['duracion_s']} | {f(r['docs_por_hora'])} "
            f"| {estados_texto(r)} | {'; '.join(r['errores']) or '—'} |"
        )
    return "\n".join(lineas)


# --- cliente de la API -------------------------------------------------------------------


class Api:
    def __init__(self, base: str, token: str, timeout_s: float) -> None:
        self.cliente = httpx.Client(
            base_url=base, headers={"Authorization": f"Bearer {token}"}, timeout=timeout_s
        )

    def subir_y_analizar(
        self, nombre: str, tipo_archivo: str, contenido: bytes, cuerpo_completar: dict
    ) -> str:
        r = self.cliente.post(
            "/documentos/iniciar",
            json={
                "nombre_original": nombre,
                "tipo_archivo": tipo_archivo,
                "tamano_bytes": len(contenido),
            },
        )
        r.raise_for_status()
        carga = r.json()
        parametros = {
            "upload_id": carga["upload_id"],
            "llave_almacenamiento": carga["llave_almacenamiento"],
        }
        r = self.cliente.put(
            f"/documentos/{carga['documento_id']}/partes/1", params=parametros, content=contenido
        )
        r.raise_for_status()
        parte = r.json()
        cuerpo = {
            "partes": [{"numero_parte": parte["numero_parte"], "etag": parte["etag"]}],
            **cuerpo_completar,
        }
        r = self.cliente.post(
            f"/documentos/{carga['documento_id']}/completar", params=parametros, json=cuerpo
        )
        r.raise_for_status()
        return r.json()["analisis_id"]

    def esperar(
        self, analisis_id: str, t0: float, limite_s: float, cada_s: float
    ) -> tuple[float | None, float | None, str]:
        t_primeros: float | None = None
        while time.monotonic() - t0 < limite_s:
            if t_primeros is None:
                h = self.cliente.get(f"/analisis/{analisis_id}/hallazgos")
                if h.status_code == 200 and h.json():
                    t_primeros = time.monotonic() - t0
            a = self.cliente.get(f"/analisis/{analisis_id}")
            a.raise_for_status()
            estado = a.json()["estado"]
            if estado not in ESTADOS_EN_CURSO:
                total = time.monotonic() - t0
                return (t_primeros if t_primeros is not None else total), total, estado
            time.sleep(cada_s)
        return t_primeros, None, "excedido"

    def chat(self, pregunta: str) -> float:
        c = self.cliente.post("/chat/conversaciones")
        c.raise_for_status()
        inicio = time.monotonic()
        m = self.cliente.post(
            f"/chat/conversaciones/{c.json()['id']}/mensajes", data={"contenido": pregunta}
        )
        m.raise_for_status()
        return time.monotonic() - inicio


def tarea_contable(api: Api, excel: Path, periodo: str, limite_s: float, cada_s: float) -> Medicion:
    t0 = time.monotonic()
    aid = api.subir_y_analizar(
        excel.name,
        "xlsx",
        excel.read_bytes(),
        {"tipo_revision": "contable", "periodo_cierre": periodo},
    )
    primeros, total, estado = api.esperar(aid, t0, limite_s, cada_s)
    return Medicion("contable", estado not in ESTADOS_FALLIDOS, primeros, total, estado)


def tarea_ortografia(api: Api, limite_s: float, cada_s: float) -> Medicion:
    t0 = time.monotonic()
    aid = api.subir_y_analizar(
        "texto-pegado.txt", "txt", TEXTO_ORTOGRAFIA.encode(), {"tipo_revision": "ortografia"}
    )
    primeros, total, estado = api.esperar(aid, t0, limite_s, cada_s)
    return Medicion("ortografia", estado not in ESTADOS_FALLIDOS, primeros, total, estado)


def tarea_chat(api: Api) -> Medicion:
    segundos = api.chat(PREGUNTA_CHAT)
    return Medicion("chat", True, segundos, segundos, "respondido")


def un_usuario(
    i: int, escenario: str, args, base: str, token: str, salida: list[Medicion], barrera
) -> None:
    api = Api(base, token, args.timeout_peticion_s)
    if escenario == "mixto":
        escenario_usuario = ("contable", "ortografia", "chat")[i % 3]
    else:
        escenario_usuario = escenario
    barrera.wait()
    try:
        if escenario_usuario == "contable":
            m = tarea_contable(
                api, args.excel, args.periodo, args.timeout_analisis_s, args.sondeo_s
            )
        elif escenario_usuario == "ortografia":
            m = tarea_ortografia(api, args.timeout_analisis_s, args.sondeo_s)
        else:
            m = tarea_chat(api)
    except Exception as error:  # noqa: BLE001 - toda falla cuenta como fallo medido
        m = Medicion(
            escenario_usuario, False, None, None, "error", f"{type(error).__name__}: {error}"[:200]
        )
    salida.append(m)


def ejecutar_nivel(args, base: str, token: str, usuarios: int, escenario: str) -> dict:
    mediciones: list[Medicion] = []
    barrera = threading.Barrier(usuarios + 1)
    hilos = [
        threading.Thread(
            target=un_usuario, args=(i, escenario, args, base, token, mediciones, barrera)
        )
        for i in range(usuarios)
    ]
    for h in hilos:
        h.start()
    barrera.wait()
    inicio = time.monotonic()
    for h in hilos:
        h.join()
    return resumir(mediciones, time.monotonic() - inicio, usuarios, escenario)


def iniciar_sesion(base: str, email: str, password: str) -> str:
    r = httpx.post(f"{base}/auth/login", json={"email": email, "password": password}, timeout=30)
    r.raise_for_status()
    return r.json()["access_token"]


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--base", required=True, help="URL de la API, p. ej. http://127.0.0.1:8001")
    p.add_argument("--email", required=True)
    p.add_argument(
        "--escenario", choices=["contable", "ortografia", "chat", "mixto"], default="contable"
    )
    p.add_argument(
        "--usuarios", default="1,3,5", help="niveles de usuarios simultáneos, separados por coma"
    )
    p.add_argument("--excel", type=Path, default=EXCEL_POR_DEFECTO)
    p.add_argument("--periodo", default=PERIODO_POR_DEFECTO)
    p.add_argument("--timeout-analisis-s", type=float, default=1800)
    p.add_argument("--timeout-peticion-s", type=float, default=900)
    p.add_argument("--sondeo-s", type=float, default=3)
    p.add_argument("--pausa-entre-niveles-s", type=float, default=30)
    p.add_argument(
        "--sin-calentamiento",
        action="store_true",
        help="no hacer una petición previa (sin medir) que cargue los modelos en memoria",
    )
    p.add_argument("--salida", type=Path, help="archivo JSON de resultados")
    p.add_argument("--md", type=Path, help="archivo Markdown con la tabla de resultados")
    args = p.parse_args(argv)

    niveles = [int(x) for x in args.usuarios.split(",") if x.strip()]
    if not niveles or max(niveles) > MAXIMO_USUARIOS or min(niveles) < 1:
        p.error(f"--usuarios debe tener valores entre 1 y {MAXIMO_USUARIOS}")
    password = os.environ.get("CARGA_PASSWORD")
    if not password:
        p.error("defina la variable de entorno CARGA_PASSWORD")
    if args.escenario in ("contable", "mixto") and not args.excel.exists():
        p.error(f"no existe el Excel de prueba: {args.excel}")

    base = args.base.rstrip("/")
    print(f"Probando {base} · escenario {args.escenario} · niveles {niveles}", file=sys.stderr)
    token = iniciar_sesion(base, args.email, password)

    if not args.sin_calentamiento:
        print("-> calentamiento (1 petición, no se mide)...", file=sys.stderr)
        calentamiento = ejecutar_nivel(args, base, token, 1, args.escenario)
        print(json.dumps(calentamiento, ensure_ascii=False), file=sys.stderr)
        time.sleep(args.pausa_entre_niveles_s)

    resumenes = []
    for indice, usuarios in enumerate(niveles):
        if indice:
            time.sleep(args.pausa_entre_niveles_s)  # deja que la cola y la IA se vacíen
        print(f"-> {usuarios} usuario(s) simultáneo(s)...", file=sys.stderr)
        r = ejecutar_nivel(args, base, token, usuarios, args.escenario)
        resumenes.append(r)
        print(json.dumps(r, ensure_ascii=False), file=sys.stderr)

    tabla = tabla_markdown(resumenes)
    print(tabla)
    if args.salida:
        args.salida.write_text(
            json.dumps({"base": base, "resumenes": resumenes}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    if args.md:
        args.md.write_text(tabla + "\n", encoding="utf-8")
    return 0 if all(r["fallos"] == 0 for r in resumenes) else 1


if __name__ == "__main__":
    sys.exit(main())
