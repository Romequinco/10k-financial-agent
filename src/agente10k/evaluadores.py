"""Los cuatro evaluadores (docs/12).

Parte 1: la verdad (verdad, es_hueco, fy_base).
Parte 2: (b) la cifra contra XBRL.
Parte 3: (c) la trayectoria.

Las partes 4 y 5 —(a) la cita y (d) la abstención— se añaden después.
"""
from __future__ import annotations

import json
import math

from agente10k.datos import texto_chunk, texto_seccion, valor_xbrl
from agente10k.normalizacion import ESCALA, cifra_ok, cobertura, normalizar, normalizar_ticker

FYS, ITEMS = (2024, 2025), ("1A", "7", "7A", "8")
POR_DEFECTO = {"numerica": [["get_xbrl_fact"]],
               "extractiva": [["search_filings", "read_section"]],
               "comparativa": [["get_xbrl_fact"], ["search_filings", "read_section"]]}
REALES = {"list_available", "get_xbrl_fact", "search_filings", "read_section"}
CORPUS = {"NVDA", "MSFT", "AAPL", "GOOGL", "META", "AMZN"}


# =========================================================== parte 1: la verdad
def cargar_preguntas(ruta) -> list[dict]:
    """JSONL tolerante: no exige validar(); ids ausentes o repetidos se desambiguan."""
    with open(ruta, encoding="utf-8") as f:
        preguntas = [json.loads(x) for x in f if x.strip()]
    vistos: dict[str, int] = {}
    for n, p in enumerate(preguntas, 1):
        pid = str(p.get("id") or f"linea-{n}")
        vistos[pid] = vistos.get(pid, 0) + 1
        p["id"] = pid if vistos[pid] == 1 else f"{pid}#{vistos[pid]}"
    return preguntas


def _fy(d: dict, campo: str = "fiscal_year") -> int | None:
    try:
        return int(d.get(campo))
    except (TypeError, ValueError):
        return None


def fy_base(p: dict) -> int | None:
    """Comparativas: fiscal_year_base o, si falta, el otro FY de {2024, 2025}."""
    if (b := _fy(p, "fiscal_year_base")) is not None:
        return b
    fy = _fy(p)
    return next((x for x in FYS if x != fy), None) if fy in FYS else None


def verdad(p: dict, fy: int | None = None, base: bool = False) -> tuple:
    """(valor, unidad XBRL): del parquet si hay concept_xbrl; si no, del golden reescalado."""
    ticker = normalizar_ticker(p.get("ticker"))
    concepto, fy = p.get("concept_xbrl"), fy or _fy(p)
    if concepto and fy and (v := valor_xbrl(ticker, fy, concepto)) is not None:
        return v
    esperada = p.get("cifra_esperada_base" if base else "cifra_esperada")
    if esperada is None:
        return None, None
    u = normalizar(p.get("unidad"))
    factor = next((f for clave, f in ESCALA if clave in u), 1.0)
    return float(esperada) * factor, ("USD/shares" if "share" in u or "acci" in u else "USD")


def sin_referencia(p: dict) -> bool:
    """Ciegas que llegaran sin respuestas: no se pueden puntuar."""
    return all(p.get(k) is None for k in
               ("cifra_esperada", "concept_xbrl", "ancla_texto", "respuesta_esperada", "hueco"))


def es_hueco(p: dict) -> bool:
    """hueco:true, numérica sin cifra_esperada, o concepto inexistente para ese ticker y FY."""
    if p.get("hueco") is True or (p.get("familia") == "numerica" and p.get("cifra_esperada") is None):
        return True
    c, fy = p.get("concept_xbrl"), _fy(p)
    return bool(c and fy and valor_xbrl(normalizar_ticker(p.get("ticker")), fy, c) is None)


# =========================================================== parte 2: (b) cifra
def cifra_ok_rel(cifra, unidad, v, unidad_xbrl, rel: float) -> bool:
    """Sensibilidad: cambia solo la relativa de USD; el BPA y los huecos, como cifra_ok."""
    if v is None or cifra is None or unidad_xbrl == "USD/shares":
        return cifra_ok(cifra, unidad, v, unidad_xbrl)["ok"]
    x = float(cifra) * next((f for clave, f in ESCALA if clave in normalizar(unidad)), 1.0)
    return math.isclose(x, v, rel_tol=rel, abs_tol=0.0)


def evaluar_cifra(resp: dict, p: dict) -> dict:
    """(b): la cifra frente a XBRL; en comparativas, también cifra_base si viene."""
    if es_hueco(p):
        return {"b": resp.get("cifra") is None, "b_motivo": "hueco"}
    v, u = verdad(p)
    if v is None:
        return {"b": None, "b_motivo": "sin_verdad"}          # extractiva: (b) no aplica
    pares = [(resp.get("cifra"), v, u)]
    if p.get("familia") == "comparativa" and resp.get("cifra_base") is not None:
        vb, ub = verdad(p, fy_base(p), base=True)
        if vb is not None:
            pares.append((resp["cifra_base"], vb, ub))
    res = [cifra_ok(c, resp.get("unidad"), x, ux) for c, x, ux in pares]
    out = {"b": all(r["ok"] for r in res),
           "b_motivo": "; ".join(r.get("motivo") or "ok" for r in res),
           "b_verdad": v, "b_unidad_xbrl": u, "b_con_base": len(pares) == 2,
           "b_unidad_ok": normalizar(resp.get("unidad")) == normalizar(u)}
    for t in (0, 0.1, 0.5, 1):                                 # sensibilidad sin reejecutar
        out[f"b_tol{t}"] = all(cifra_ok_rel(c, resp.get("unidad"), x, ux, t / 100)
                               for c, x, ux in pares)
    return out


# ===================================================== parte 3: (c) trayectoria
def esperadas(p: dict) -> tuple[list[list[str]], bool]:
    """(requisitos, por_defecto). Cada requisito es [nombre, *alternativas] (D12)."""
    lista = lambda x: [x] if isinstance(x, str) else list(x or [])
    h, alt = p.get("herramienta_esperada"), p.get("herramienta_alternativa")
    alt = alt if isinstance(alt, dict) else {}
    if h:
        return [[e, *lista(alt.get(e))] for e in lista(h)], False
    return [list(r) for r in POR_DEFECTO.get(p.get("familia"), [])], True


def _requisitos(p: dict) -> tuple[list[list[str]], bool]:
    req, por_defecto = esperadas(p)
    if req != [["list_available"]]:
        req = [r for r in req if r[0] != "list_available"]     # neutra, salvo universo
    return req, por_defecto


def _args_xbrl_ok(tcs: list[dict], p: dict) -> bool | None:
    """Alguna get_xbrl_fact con ticker, FY (los dos en comparativas) y concepto correctos."""
    concepto, fy = p.get("concept_xbrl"), _fy(p)
    if not concepto or fy is None:
        return None
    ticker, hueco = normalizar_ticker(p.get("ticker")), es_hueco(p)
    fys = {fy, fy_base(p)} - {None} if p.get("familia") == "comparativa" else {fy}
    vistos = set()
    for tc in tcs:
        a = tc.get("args") or {}
        f, c = _fy(a), a.get("concept")
        if tc["name"] != "get_xbrl_fact" or normalizar_ticker(a.get("ticker")) != ticker or f is None:
            continue
        v = valor_xbrl(ticker, f, c)
        # El concepto exacto, o uno de valor idéntico (GOOGL FY2024 tiene los dos de revenue).
        if c == concepto or (not hueco and v is not None and v == valor_xbrl(ticker, f, concepto)):
            vistos.add(f)
    return fys <= vistos


def evaluar_trayectoria(tool_calls: list[dict], p: dict, resp: dict) -> dict:
    """(c) = todas las herramientas esperadas ∧ argumentos correctos. Sin deduplicar."""
    tcs = [tc for tc in tool_calls if tc.get("name") in REALES]
    usadas = {tc["name"] for tc in tcs}
    req, por_defecto = _requisitos(p)
    tp = sum(bool(set(r) & usadas) for r in req)
    oblig = ["get_xbrl_fact"] in req
    en_corpus = normalizar_ticker(p.get("ticker")) in CORPUS
    args_ok = _args_xbrl_ok(tcs, p) if (oblig or "get_xbrl_fact" in usadas) and en_corpus else None
    c = (tp == len(req) and args_ok is not False) if req else None
    texto = bool(usadas & {"search_filings", "read_section"})
    coherencia = {"xbrl": "get_xbrl_fact" in usadas, "texto": texto,
                  "ambas": "get_xbrl_fact" in usadas and texto,
                  "ninguna": True}.get(resp.get("fuente"))
    return {"c": c, "c_recall": tp / len(req) if req else None, "c_args_ok": args_ok,
            "c_por_defecto": por_defecto, "coherencia_fuente": coherencia,
            "n_tools": len(tcs), "c_usadas": sorted(usadas)}