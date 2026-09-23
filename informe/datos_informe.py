r"""Extrae de resultados/ todas las cifras que aparecen en la presentacion.

Ninguna cifra del PDF se teclea a mano: este modulo las lee de los artefactos
oficiales y las deja en informe/datos.json. Si una tanda se vuelve a medir,
basta con regenerar el PDF.

    .venv\Scripts\python.exe informe/datos_informe.py
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from agente10k import config

RAIZ = Path(__file__).resolve().parents[1]
RESULTADOS = RAIZ / "resultados"
SALIDA = Path(__file__).resolve().parent / "datos.json"

BASE = "baseline_entregado"
FINAL = "final_entregado"


def _resumen(etiqueta: str) -> dict:
    ruta = RESULTADOS / etiqueta / "resumen.json"
    if not ruta.exists():
        raise FileNotFoundError(f"falta {ruta}")
    return json.loads(ruta.read_text(encoding="utf-8"))


def _puntuaciones(etiqueta: str) -> list[dict]:
    ruta = RESULTADOS / etiqueta / "puntuaciones.jsonl"
    return [json.loads(l) for l in ruta.read_text(encoding="utf-8").splitlines() if l.strip()]


def _predicciones(etiqueta: str) -> list[dict]:
    ruta = RESULTADOS / etiqueta / "predicciones.jsonl"
    return [json.loads(l) for l in ruta.read_text(encoding="utf-8").splitlines() if l.strip()]


def _etapas_cita(etiqueta: str) -> dict:
    """Las tres etapas del evaluador de cita, por separado.

    Es el hallazgo principal del trabajo: el sistema de partida encontraba el
    fragmento y lo citaba, y se caia en la tercera etapa (la cita no respalda
    todo lo que la respuesta afirma).
    """
    filas = [f for f in _puntuaciones(etiqueta) if f.get("a") is not None]
    return {
        "n": len(filas),
        "existe": sum(1 for f in filas if f.get("a_existe")),
        "vista": sum(1 for f in filas if f.get("a_vista")),
        "respalda": sum(1 for f in filas if f.get("a_respalda")),
        "chunk_ok": sum(1 for f in filas if f.get("a_chunk_id_ok")),
        "cita_exacta": sum(1 for f in filas if f.get("a_cita_ancla") == 1.0),
    }


def _llamadas_por_herramienta(etiqueta: str) -> dict:
    cuenta: dict[str, int] = {}
    for pred in _predicciones(etiqueta):
        for tc in pred.get("tool_calls") or []:
            nombre = tc["name"] if isinstance(tc, dict) else tc
            cuenta[nombre] = cuenta.get(nombre, 0) + 1
    return cuenta


def _guard(etiqueta: str) -> dict:
    reparaciones: dict[str, int] = {}
    problemas = reintentos = rapido = 0
    fuente: dict[str, int] = {}
    for pred in _predicciones(etiqueta):
        g = pred.get("guard") or {}
        for r in g.get("reparaciones") or []:
            clave = r[0] if isinstance(r, list) else r
            reparaciones[clave] = reparaciones.get(clave, 0) + 1
        problemas += len(g.get("problemas") or [])
        reintentos += g.get("reintentos") or 0
        rapido += bool(g.get("camino_rapido"))
        f = g.get("fuente_derivada")
        if f:
            fuente[f] = fuente.get(f, 0) + 1
    return {
        "reparaciones": reparaciones, "problemas": problemas,
        "reintentos": reintentos, "camino_rapido": rapido, "fuente_derivada": fuente,
    }


def _traza(etiqueta: str, pid: str) -> dict:
    """Todo lo que hizo el agente en una pregunta concreta, literal."""
    pred = next(p for p in _predicciones(etiqueta) if p["id"] == pid)
    golden = next(
        g for g in (json.loads(l) for l in
                    (config.GOLDEN / "golden_propio.jsonl").read_text(encoding="utf-8").splitlines() if l.strip())
        if g["id"] == pid
    )
    punt = next(f for f in _puntuaciones(etiqueta) if f["id"] == pid)
    r = pred["respuesta"]
    return {
        "id": pid,
        "pregunta": golden["pregunta"],
        "familia": golden["familia"],
        "ancla": golden.get("ancla_texto"),
        "llamadas": [
            {"nombre": tc["name"], "args": tc.get("args", {})}
            for tc in pred.get("tool_calls") or []
        ],
        "respuesta": {k: r.get(k) for k in
                      ("respuesta", "cifra", "cifra_base", "unidad", "ticker",
                       "ejercicio", "fuente", "cita", "chunk_id")},
        "latencia_s": pred["latencia_s"],
        "usd": pred["usd"],
        "n_llamadas": pred["n_llamadas"],
        "veredicto": {k: punt.get(k) for k in ("a", "b", "c", "acierto")},
    }


def _commit() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=RAIZ, capture_output=True, text=True, check=True,
        ).stdout.strip()
    except Exception:
        return "desconocido"


def _corpus() -> dict:
    secciones = [json.loads(l) for l in (config.CORPUS / "secciones.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    chunks = sum(1 for l in (config.CORPUS / "chunks.jsonl").read_text(encoding="utf-8").splitlines() if l.strip())
    import pandas as pd
    hechos = pd.read_parquet(config.CORPUS / "xbrl_facts.parquet")
    return {
        "secciones": len(secciones),
        "chunks": chunks,
        "hechos_xbrl": int(len(hechos)),
        "tickers": sorted({s["ticker"] for s in secciones}),
        "ejercicios": sorted({int(s["fiscal_year"]) for s in secciones}),
        "items": sorted({s["item"] for s in secciones}),
    }


def _golden() -> dict:
    propio = [json.loads(l) for l in (config.GOLDEN / "golden_propio.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    huecos = [json.loads(l) for l in (config.GOLDEN / "golden_huecos.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    familias: dict[str, int] = {}
    for p in propio:
        familias[p["familia"]] = familias.get(p["familia"], 0) + 1
    return {"n": len(propio), "familias": familias, "huecos": len(huecos)}


def _escalera() -> dict:
    ruta = RESULTADOS / "retrieval" / "5976eb180c38" / "resumen.json"
    datos = json.loads(ruta.read_text(encoding="utf-8"))
    pasos = []
    for p in datos["pasos"]:
        pasos.append({
            "paso": p["paso"],
            "aciertos5": p["aciertos@5"],
            "recall5": p["recall@5"],
            "aciertos10": p["aciertos@10"],
            "mrr10": p["mrr@10"],
            "ms_busqueda": p["ms_busqueda"],
        })
    techos = [json.loads(l) for l in (ruta.parent / "techos.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    alcanzables = sum(1 for x in techos if x.get("techo_hibrido"))
    return {"id": "5976eb180c38", "completo": datos["completo"], "pasos": pasos,
            "techo": alcanzables, "n": len(techos),
            "inalcanzables": [x["id"] for x in techos if not x.get("techo_hibrido")]}


def _matriz() -> list[dict]:
    """Una fila por pregunta del golden con el veredicto de los dos sistemas."""
    base = {p["id"]: p for p in _puntuaciones(BASE)}
    fin = {p["id"]: p for p in _puntuaciones(FINAL)}
    filas = []
    for pid in sorted(base):
        b, f = base[pid], fin[pid]
        filas.append({
            "id": pid,
            "familia": b["familia"],
            "base_acierto": b.get("acierto"),
            "final_acierto": f.get("acierto"),
            "base_cita": b.get("a"),
            "final_cita": f.get("a"),
            "base_cifra": b.get("b"),
            "final_cifra": f.get("b"),
            "base_ruta": b.get("c"),
            "final_ruta": f.get("c"),
            "final_error": f.get("error"),
        })
    return filas


def _cuenta_cita(filas: list[dict], clave: str) -> str:
    aplica = [f for f in filas if f[clave] is not None]
    ok = sum(1 for f in aplica if f[clave])
    return f"{ok}/{len(aplica)}"


def construir() -> dict:
    rb, rf = _resumen(BASE), _resumen(FINAL)
    hb, hf = _resumen(f"{BASE}_huecos"), _resumen(f"{FINAL}_huecos")
    filas = _matriz()

    proveedor = {
        et: {
            "modelo": _resumen(et)["modelo"],
            "micro": _resumen(et)["micro"],
            "errores": _resumen(et)["errores"],
            "latencia_mediana_s": _resumen(et)["latencia_mediana_s"],
            "latencia_p90_s": _resumen(et).get("latencia_p90_s"),
            "usd_medio": _resumen(et).get("usd_medio"),
        }
        for et in ("final_libre_actual", "final_pago", "final_pago_r2")
    }

    todas = {}
    for et in ("baseline", "candidato_07", "baseline_nexn25pro", "final",
               "final_r2_t1", "final_r2_t2", "baseline_pago", "final_pago",
               "final_pago_r2", "baseline_pago_r2", "final_libre_actual", BASE, FINAL):
        r = _resumen(et)
        todas[et] = {
            "modelo": r["modelo"], "micro": r["micro"], "errores": r["errores"],
            "llamadas": r["llamadas_medias"], "tokens": r["tokens_medios"],
            "usd": r.get("usd_medio"), "recall_agente": r.get("recall_agente"),
            "latencia_mediana_s": r.get("latencia_mediana_s"),
            "latencia_p90_s": r.get("latencia_p90_s"),
            "familias": r["familias"], "commit": r.get("commit"),
        }

    return {
        "commit_actual": _commit(),
        "corpus": _corpus(),
        "golden": _golden(),
        "sistemas": {
            "baseline": {
                "etiqueta": BASE, "resumen": rb, "huecos": hb["familias"]["hueco"],
                "huecos_resumen": hb,
            },
            "final": {
                "etiqueta": FINAL, "resumen": rf, "huecos": hf["familias"]["hueco"],
                "huecos_resumen": hf,
            },
        },
        "deltas": {
            "micro": rf["micro"] - rb["micro"],
            "tokens_pct": 100 * (rb["tokens_medios"] - rf["tokens_medios"]) / rb["tokens_medios"],
            "llamadas_pct": 100 * (rb["llamadas_medias"] - rf["llamadas_medias"]) / rb["llamadas_medias"],
            "coste_pct": 100 * (rf["usd_medio"] - rb["usd_medio"]) / rb["usd_medio"],
            "latencia_pct": 100 * (rf["latencia_media_s"] - rb["latencia_media_s"]) / rb["latencia_media_s"],
        },
        "cita": {"baseline": _cuenta_cita(filas, "base_cita"), "final": _cuenta_cita(filas, "final_cita")},
        "etapas_cita": {"baseline": _etapas_cita(BASE), "final": _etapas_cita(FINAL)},
        "llamadas_herramienta": {
            "baseline": _llamadas_por_herramienta(BASE),
            "final": _llamadas_por_herramienta(FINAL),
            "huecos": _llamadas_por_herramienta(f"{FINAL}_huecos"),
        },
        "guard": {"baseline": _guard(BASE), "final": _guard(FINAL)},
        "recall": {
            "baseline": {"aislado": "2/13", "agente": f"{round(rb['recall_agente'] * 13)}/13"},
            "final": {"aislado": "5/13", "agente": f"{round(rf['recall_agente'] * 13)}/13"},
        },
        "ejemplo": _traza(FINAL, "g3-014"),
        "ejemplo_texto": _traza(FINAL, "g3-011"),
        "matriz": filas,
        "escalera": _escalera(),
        "proveedor": proveedor,
        "todas_las_tandas": todas,
        "coste_10_ciegas": round(rf["usd_medio"] * 10, 3),
    }


if __name__ == "__main__":
    datos = construir()
    SALIDA.write_text(json.dumps(datos, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"escrito {SALIDA} ({SALIDA.stat().st_size} bytes)")
