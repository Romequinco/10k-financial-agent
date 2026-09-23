"""Los cuatro evaluadores (docs/12).

Parte 1: la verdad (verdad, es_hueco, fy_base).
Parte 2: (b) la cifra contra XBRL.
Parte 3: (c) la trayectoria.

Las partes 4 y 5 —(a) la cita y (d) la abstención— se añaden después.
"""
from __future__ import annotations

import hashlib
from typing import Literal

from langchain.agents import create_agent
from langchain.agents.structured_output import ToolStrategy
from langchain_core.callbacks import get_usage_metadata_callback
from pydantic import BaseModel, Field

import json
import math
import pandas as pd

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
    """hueco:true, numérica sin cifra_esperada, o concepto inexistente para ese ticker y FY.

    Una pregunta sin ninguna referencia (ciegas del día 24) nunca es hueco, y una numérica
    sin cifra_esperada cuyo concept_xbrl SÍ existe en XBRL tampoco: la verdad sale del parquet.
    """
    if sin_referencia(p):
        return False
    if p.get("hueco") is True:
        return True
    c, fy = p.get("concept_xbrl"), _fy(p)
    existe = bool(c and fy and valor_xbrl(normalizar_ticker(p.get("ticker")), fy, c) is not None)
    if p.get("familia") == "numerica" and p.get("cifra_esperada") is None:
        return not existe
    return bool(c and fy and not existe)


# =========================================================== parte 2: (b) cifra
def cifra_ok_rel(cifra, unidad, v, unidad_xbrl, rel: float) -> bool:
    """Sensibilidad: cambia solo la relativa de USD; el BPA y los huecos, como cifra_ok."""
    if v is None or cifra is None or unidad_xbrl == "USD/shares":
        return cifra_ok(cifra, unidad, v, unidad_xbrl)["ok"]
    x = float(cifra) * next((f for clave, f in ESCALA if clave in normalizar(unidad)), 1.0)
    return math.isclose(x, v, rel_tol=rel, abs_tol=0.0)


def evaluar_cifra(resp: dict, p: dict) -> dict:
    """(b): la cifra frente a XBRL; en comparativas, también cifra_base si viene."""
    if sin_referencia(p):
        return {"b": None, "b_motivo": "sin_referencia"}       # ver verificar_sin_referencia
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

# ============================================== parte 4: (a) cita, etapa 1
import re

_ELISION = re.compile(r"\s*(?:\[\.\.\.\]|\.\.\.|…)\s*")


def _piezas(cita: str | None) -> list[str]:
    """Cada trozo de la cita entre elisiones, normalizado. Todos deben ser literales."""
    return [normalizar(x) for x in _ELISION.split(cita or "") if normalizar(x)]


def _ejercicios(resp: dict, p: dict) -> set[int]:
    """Los ejercicios donde buscar: los que declara la respuesta o, si no, los de la pregunta."""
    de_resp = {resp.get("ejercicio"), resp.get("ejercicio_base")} - {None}
    if de_resp:
        return {int(x) for x in de_resp}
    de_preg = {_fy(p)}
    if p.get("familia") == "comparativa":
        de_preg.add(fy_base(p))
    return {int(x) for x in de_preg - {None}}


def etapa1_cita(resp: dict, p: dict, observaciones: list[dict]) -> dict:
    """(a) etapa 1: existe (en las secciones) ∧ vista (en los ToolMessage de esta ejecución).

    El chunk_id solo diagnostica: cambia al re-trocear y una cita puede cruzar dos
    fragmentos. La etapa 2 (respalda) la hace un juez y se añade después.
    """
    piezas = _piezas(resp.get("cita"))
    if not piezas:
        return {"a_cita": False, "a_existe": False, "a_vista": False}

    ticker = normalizar_ticker(resp.get("ticker") or p.get("ticker"))
    fuente = " ".join(normalizar(texto_seccion(ticker, fy, it))
                      for fy in _ejercicios(resp, p) for it in ITEMS)
    vistas = " ".join(normalizar(o.get("content"))
                      for o in (observaciones or [])
                      if o.get("name") in ("search_filings", "read_section"))

    out = {"a_cita": True,
           "a_existe": all(x in fuente for x in piezas),
           "a_vista": all(x in vistas for x in piezas),
           "a_chunk_id_ok": bool(resp.get("chunk_id")) and all(
               x in normalizar(texto_chunk(resp["chunk_id"])) for x in piezas)}
    if not out["a_existe"]:
        # >= 0,8 separa "casi literal" (normalización) de "inventada".
        out["a_cobertura"] = round(cobertura(resp["cita"], fuente), 3)
    if p.get("ancla_texto"):
        out["a_cita_ancla"] = round(cobertura(p["ancla_texto"], resp["cita"]), 3)
    return out


# ============ parte 4b: banderas diagnósticas y modo sin referencia (docs/13 §8)
_CHUNK_ID = re.compile(r"^([A-Za-z.]+)-(\d{4})-([0-9A-Za-z]+)-\d+$")
MIN_PALABRAS_CITA = 6


def banderas_diagnosticas(resp: dict, p: dict) -> dict:
    """Laxitudes que NO cambian la nota oficial, pero que conviene ver (columnas `diag_*`).

    Cada bandera es True (hay laxitud), False (comprobado, sin laxitud) o None (no aplica):
    cita de menos de 6 palabras; ticker o ejercicio de la respuesta distintos de los de la
    pregunta; cifra_base ausente en una comparativa; chunk_id inexistente o de otra empresa
    o ejercicio distinto de los esperados.
    """
    out = {}
    cita = _ELISION.sub(" ", resp.get("cita") or "").split()
    out["diag_cita_corta"] = (len(cita) < MIN_PALABRAS_CITA) if cita else None

    t_resp, t_preg = normalizar_ticker(resp.get("ticker")), normalizar_ticker(p.get("ticker"))
    out["diag_ticker_distinto"] = (t_resp != t_preg) if t_resp and t_preg else None

    fy_resp, fy_preg = _fy(resp, "ejercicio"), _fy(p)
    permitidos = {fy_preg}
    if p.get("familia") == "comparativa":
        permitidos.add(fy_base(p))
    permitidos -= {None}
    out["diag_ejercicio_distinto"] = (fy_resp not in permitidos
                                      if fy_resp is not None and permitidos else None)

    out["diag_cifra_base_ausente"] = (resp.get("cifra_base") is None
                                      if p.get("familia") == "comparativa" and not sin_referencia(p)
                                      else None)

    cid = resp.get("chunk_id")
    if cid:
        out["diag_chunk_inexistente"] = not texto_chunk(cid)
        m = _CHUNK_ID.match(str(cid))
        esperados = permitidos | ({fy_resp} - {None})      # los de la pregunta y los declarados
        out["diag_chunk_otro_ejercicio"] = (int(m.group(2)) not in esperados
                                            if m and esperados else None)
        out["diag_chunk_otra_empresa"] = (normalizar_ticker(m.group(1))
                                          != (t_resp or t_preg) if m and (t_resp or t_preg) else None)
    else:
        out.update(diag_chunk_inexistente=None, diag_chunk_otro_ejercicio=None,
                   diag_chunk_otra_empresa=None)
    return out


def verificar_sin_referencia(resp: dict, p: dict, tool_calls: list[dict]) -> dict:
    """Lo verificable sin respuestas esperadas: cifra frente a XBRL cuando hay concepto.

    Ticker y ejercicio salen de la respuesta o, si faltan, de la pregunta. El concepto sale de
    `concept_xbrl` de la respuesta o, si falta, del único concepto de las llamadas a
    get_xbrl_fact de esa empresa y ejercicio (`sr_concepto_origen` lo indica). Sin cifra,
    empresa, ejercicio o concepto comprobable, `sr_cifra_xbrl` queda en None.
    """
    out = {"sr_cifra_xbrl": None, "sr_motivo": None, "sr_concepto": None,
           "sr_concepto_origen": None}
    if resp.get("cifra") is None:
        out["sr_motivo"] = "sin_cifra"
        return out
    ticker = normalizar_ticker(resp.get("ticker") or p.get("ticker"))
    fy = _fy(resp, "ejercicio") or _fy(p)
    if not ticker or fy is None:
        out["sr_motivo"] = "sin_ticker_o_ejercicio"
        return out
    concepto, origen = resp.get("concept_xbrl"), "respuesta"
    if not concepto:
        vistos = {(tc.get("args") or {}).get("concept") for tc in tool_calls or []
                  if tc.get("name") == "get_xbrl_fact"
                  and normalizar_ticker((tc.get("args") or {}).get("ticker")) == ticker
                  and _fy(tc.get("args") or {}) == fy} - {None}
        concepto, origen = (next(iter(vistos)), "trayectoria") if len(vistos) == 1 else (None, None)
    if not concepto:
        out["sr_motivo"] = "sin_concepto"
        return out
    out.update(sr_concepto=concepto, sr_concepto_origen=origen)
    verdad_xbrl = valor_xbrl(ticker, fy, concepto)
    if verdad_xbrl is None:
        out["sr_motivo"] = "concepto_no_reportado"
        return out
    pares = [(resp["cifra"], *verdad_xbrl)]
    fy_b = _fy(resp, "ejercicio_base")
    if resp.get("cifra_base") is not None and fy_b is not None and (vb := valor_xbrl(ticker, fy_b, concepto)):
        pares.append((resp["cifra_base"], *vb))
    res = [cifra_ok(c, resp.get("unidad"), v, u) for c, v, u in pares]
    out["sr_cifra_xbrl"] = all(r["ok"] for r in res)
    out["sr_motivo"] = "; ".join(r.get("motivo") or "ok" for r in res)
    return out


def verificacion_sin_referencia(s: dict) -> bool | None:
    """Resume lo comprobable de una fila sin referencia: True si todo lo comprobado cuadra."""
    comprobaciones = []
    if s.get("a_cita"):
        comprobaciones += [s.get("a_existe"), s.get("a_vista")]
    if s.get("sr_cifra_xbrl") is not None:
        comprobaciones.append(s["sr_cifra_xbrl"])
    if s.get("fuente") in ("xbrl", "texto", "ambas") and s.get("coherencia_fuente") is not None:
        comprobaciones.append(s["coherencia_fuente"])
    if s.get("c") is not None:
        comprobaciones.append(s["c"])
    return all(comprobaciones) if comprobaciones else None

# ==================== parte 5: (d) abstención, acierto por familia y agregados
FAMILIAS = ("numerica", "extractiva", "comparativa", "hueco")

_MAGNITUD_FINANCIERA = re.compile(
    r"(?:[$€£]\s*[-+]?\d)|(?:[-+]?\d[\d.,]*\s*(?:usd|eur|d[oó]lares?|euros?|%|"
    r"por\s+cien(?:to)?|percent|pct|pp\b|p\.p\.|puntos?\s+(?:porcentuales?|b[aá]sicos?)|"
    r"mil(?:es)?\s+(?:de\s+)?millones|mil\b|millones?|millions?|billions?|bn\b|bln\b|[mbk]\b|x\b|"
    r"acciones?|shares?))",
    re.IGNORECASE,
)
_VERBO_ESTIMACION = re.compile(
    r"\b(?:estim\w*|calcul\w*|aproxim\w*|approx\w*|aprox\b|equival\w*|ser[ií]a|ascender[ií]a|"
    r"rond\w*|en\s+torno\s+a|alrededor\s+de|cerca\s+de|about|around|roughly|impl[ií]cit\w*|"
    r"sum(?:a|as|ando|ar|amos)|rest(?:a|ando|ar)|obt(?:eng\w*|iene\w*)|resulta)\b|[≈~]",
    re.IGNORECASE,
)
_NUMERO = re.compile(r"(?<![A-Za-z])[-+]?\d[\d.,]*(?![A-Za-z])")
# v2: lo que NO es una magnitud aunque lleve dígitos.
_RUIDO_NUMERICO = re.compile(
    r"\b(?:FY|CY|Q[1-4]|T[1-4]|H[12])\s?-?\d{2,4}\b"                    # FY2025, Q3
    r"|\b[A-Z][A-Z0-9]{0,5}\d+[A-Z0-9]*\b"                              # tickers con dígitos
    r"|\b10-?K\b|\bitems?\s+\d+[A-C]?\b"                                # Form 10-K, Item 7A
    r"|\b\d+\s+(?:empresas?|compañ[ií]as?|companies|conceptos?|concepts?|ejercicios?|"
    r"a[ñn]os|informes?|secciones?|items?|fuentes?|herramientas?|tickers?|pasos|filings?)\b",
    re.IGNORECASE,
)
# Verbo de estimación NEGADO en la misma oración: es la abstención honesta.
_ESTIMACION_NEGADA = re.compile(
    r"\b(?:no|nunca|jam[aá]s|ni|sin)\b[^.,;:!?\n]{0,50}?"
    r"\b(?:estim|calcul|deriv|aproxim|infer|deduc|extrapol|sum(?:ar|a\b)|restar|obten)\w*",
    re.IGNORECASE,
)


def sin_estimacion_financiera(texto: str | None) -> bool:
    """False si una abstención introduce una magnitud financiera no reportada (v2).

    Se ignoran los años y ejercicios (FY2025, 2025), los tickers, «N empresas/conceptos…» y
    «10-K/Item 7A». Un verbo de estimación NEGADO en la misma oración («no se puede
    estimar/calcular/derivar», «no se calcula nada») es la abstención honesta y no cuenta.
    Sigue siendo fallo: una magnitud con moneda/escala/porcentaje («margen implícito ~50,3 %»)
    o un número no anual gobernado por un verbo afirmativo de estimación o cálculo.
    """
    texto = _RUIDO_NUMERICO.sub(" ", texto or "")
    if _MAGNITUD_FINANCIERA.search(texto):
        return False
    texto = _ESTIMACION_NEGADA.sub(" ", texto)
    if not _VERBO_ESTIMACION.search(texto):
        return True
    for hallazgo in _NUMERO.finditer(texto):
        limpio = hallazgo.group().replace(".", "").replace(",", "")
        try:
            numero = int(limpio)
        except ValueError:
            return False
        if not (1900 <= numero <= 2100 and len(limpio.lstrip("+-")) == 4):
            return False
    return True


def acierto(s: dict) -> bool | None:
    """Fórmula por familia (D14). None = no evaluable."""
    f, c = s.get("familia"), s.get("c") is True
    if f == "numerica":
        return s.get("b") is True and c
    if f == "hueco":
        return bool(s.get("abstiene") and s.get("sin_cifra") and c
                    and s.get("sin_estimacion") is True)
    if f in ("extractiva", "comparativa"):
        if not c:
            return False       # la trayectoria ya falla: no hace falta (ni se gasta) el juez
        if s.get("a") is None or s.get("correcta_ok") is None:
            return None
        return bool(s["a"] and c and s["correcta_ok"]
                    and (f == "extractiva" or s.get("b") is True))
    return None


def puntuar_fila(fila: dict, juez=None, estricto: bool = True) -> dict:
    """Una fila de predicciones.jsonl -> una de puntuaciones.jsonl.

    estricto=True sigue docs/12: sin juez, (a) y `correcta` quedan en None y las
    extractivas y comparativas no son evaluables.
    estricto=False reduce (a) a la etapa 1 y da `correcta` por buena: permite un
    baseline completo sin jueces, a costa de inflar la nota. Si se usa, hay que
    usarlo TAMBIÉN en el sistema final o la comparación no vale.
    """
    p, resp = fila["golden"], fila["respuesta"]
    familia = ("sin_referencia" if sin_referencia(p)
               else "hueco" if es_hueco(p) else p.get("familia"))

    s = {"id": fila.get("id"), "familia": familia,
         **evaluar_cifra(resp, p),
         **evaluar_trayectoria(fila.get("tool_calls") or [], p, resp),
         **etapa1_cita(resp, p, fila.get("observaciones") or [])}
    if familia == "sin_referencia":
        if s["c_por_defecto"]:            # no se adivina la herramienta que "debía" usar
            s.update(c=None, c_recall=None)
        s.update(fuente=resp.get("fuente"),
                 **verificar_sin_referencia(resp, p, fila.get("tool_calls") or []))
        s["verificacion"] = verificacion_sin_referencia(s)
    s.update(banderas_diagnosticas(resp, p))

    s.update(abstiene=resp.get("fuente") == "ninguna",
             sin_cifra=resp.get("cifra") is None,
             sin_estimacion=sin_estimacion_financiera(resp.get("respuesta")),
             hay_dato=familia not in ("hueco", "sin_referencia"))
    s["abstencion_indebida"] = s["abstiene"] and s["hay_dato"]      # (d): falso "ninguna"

    s.update(a=None, a_respalda=None, correcta=None, correcta_ok=None, juez_fallo=False,
             juez_omitido=False)
    if familia in ("extractiva", "comparativa"):
        etapa1 = bool(s.get("a_existe") and s.get("a_vista"))
        if juez is not None and s["c"] is not True:
            # La trayectoria ya falla (acierto False): no se gastan llamadas al juez.
            s.update(a=False if not etapa1 else None, correcta_ok=False, juez_omitido=True)
        elif juez is not None:
            if etapa1:
                s["a_respalda"] = juez.respalda(resp.get("cita"), resp.get("respuesta"))
                s["juez_fallo"] = s["a_respalda"] is None
            s["a"] = bool(etapa1 and s["a_respalda"])
            if not p.get("respuesta_esperada"):
                s["correcta_ok"] = True
            elif s["a"] and s["c"]:
                s["correcta"] = juez.correcta(p.get("pregunta"), resp.get("respuesta"),
                                              p["respuesta_esperada"], p.get("ancla_texto"))
                s["juez_fallo"] = s["juez_fallo"] or s["correcta"] is None
                s["correcta_ok"] = s["correcta"] is True
            else:
                s["correcta_ok"] = False       # ya falla: no se gasta la llamada
        elif not estricto:
            s["a"] = etapa1                     # (a) reducida a la etapa 1
            s["correcta_ok"] = True             # sin juez: se da por buena

    if ancla := normalizar(p.get("ancla_texto")):
        # Recall dentro del agente: ¿lo que recuperó contenía el ancla? (D08)
        s["recall_agente"] = ancla in " ".join(
            normalizar(o.get("content")) for o in (fila.get("observaciones") or [])
            if o.get("name") == "search_filings")

    s["acierto"] = acierto(s)
    return s


def resumen_aciertos(punt: list[dict]) -> dict:
    """k/n por familia; micro = aciertos/preguntas; macro = media de las familias presentes.

    Si alguna pregunta de las cuatro familias no es evaluable (p. ej., extractivas sin juez), el
    resultado es PARCIAL: `micro` y `macro` quedan en None para no publicar un número inflado
    (solo cuentan las filas evaluables), y se dan aparte `micro_parcial` (sobre las evaluables) y
    `micro_cota_inferior` (las no evaluables cuentan como fallo). Las filas sin_referencia no
    entran en estas cifras: van en `resumen_sin_referencia`.
    """
    fam = {f: [x["acierto"] for x in punt
               if x.get("familia") == f and x.get("acierto") is not None]
           for f in FAMILIAS}
    con = [v for v in fam.values() if v]
    todas = [a for v in con for a in v]
    no_evaluables = sum(x.get("familia") in FAMILIAS and x.get("acierto") is None for x in punt)
    micro = sum(todas) / len(todas) if todas else None
    macro = sum(sum(v) / len(v) for v in con) / len(con) if con else None
    parcial = no_evaluables > 0
    return {"familias": {f: f"{sum(v)}/{len(v)}" if v else "—" for f, v in fam.items()},
            "micro": None if parcial else micro, "macro": None if parcial else macro,
            "parcial": parcial, "n_evaluables": len(todas), "n_no_evaluables": no_evaluables,
            "micro_parcial": micro if parcial else None,
            "micro_cota_inferior": (sum(todas) / (len(todas) + no_evaluables)) if parcial else None}


def resumen_sin_referencia(punt: list[dict]) -> dict:
    """Agregado de lo verificable en las filas sin_referencia (vacío si no hay ninguna)."""
    filas = [x for x in punt if x.get("familia") == "sin_referencia"]
    if not filas:
        return {}

    def kn(clave):
        v = [x[clave] for x in filas if isinstance(x.get(clave), bool)]
        return f"{sum(v)}/{len(v)}" if v else "—"

    return {"n": len(filas), "verificacion": kn("verificacion"), "cita_existe": kn("a_existe"),
            "cita_vista": kn("a_vista"), "cifra_xbrl": kn("sr_cifra_xbrl"),
            "coherencia_fuente": kn("coherencia_fuente"), "abstenciones": kn("abstiene"),
            "con_cita": sum(bool(x.get("a_cita")) for x in filas)}


def resumen_banderas(punt: list[dict]) -> dict:
    """Cuántas filas activan cada bandera diagnóstica `diag_*` (sobre las que aplica)."""
    claves = sorted({k for x in punt for k in x if k.startswith("diag_")})
    return {k: f"{sum(x[k] is True for x in punt)}/{sum(isinstance(x.get(k), bool) for x in punt)}"
            for k in claves}


def sensibilidad(punt: list[dict]) -> dict:
    """Micro con 0 / 0,1 / 0,5 / 1 % en USD, re-puntuando sin ejecutar (D06)."""
    return {f"{t} %": resumen_aciertos(
        [dict(x, acierto=acierto(dict(x, b=x.get(f"b_tol{t}", x.get("b")))))
         for x in punt])["micro"] for t in (0, 0.1, 0.5, 1)}

# ============================== parte 6: evaluar(), puntuar() y persistencia
import datetime as dt
import os
import statistics
import subprocess
import time
import warnings
from pathlib import Path

from agente10k import config


def _leer_jsonl(ruta) -> list[dict]:
    with open(ruta, encoding="utf-8") as f:
        return [json.loads(x) for x in f if x.strip()]


def _escribir_jsonl(ruta, filas: list[dict]) -> None:
    Path(ruta).parent.mkdir(parents=True, exist_ok=True)
    with open(ruta, "w", encoding="utf-8") as f:
        f.writelines(json.dumps(x, ensure_ascii=False, default=str) + "\n" for x in filas)


def _git(args: list[str], *, texto: bool = True):
    """Git tolerante para clones descargados como ZIP."""
    try:
        return subprocess.run(["git", *args], capture_output=True, text=texto,
                              timeout=10, check=False)
    except Exception:
        return None


def _estado_git() -> dict:
    """Commit y huella del árbol ejecutable, excluyendo artefactos de resultados."""
    rev = _git(["rev-parse", "--short", "HEAD"])
    commit = rev.stdout.strip() if rev and rev.returncode == 0 else "sin_git"
    estado = _git(["status", "--porcelain=v1", "--untracked-files=all", "--", ".",
                   ":(exclude)resultados"])
    diff = _git(["diff", "--binary", "HEAD", "--", ".", ":(exclude)resultados"],
                texto=False)
    otros = _git(["ls-files", "--others", "--exclude-standard", "-z", "--", ".",
                  ":(exclude)resultados"], texto=False)
    huella = hashlib.sha256(diff.stdout if diff and diff.returncode == 0 else b"")
    if otros and otros.returncode == 0:
        for bruto in sorted(x for x in otros.stdout.split(b"\0") if x):
            ruta = Path(bruto.decode("utf-8", errors="surrogateescape"))
            huella.update(b"\0" + bruto + b"\0")
            if ruta.is_file():
                huella.update(ruta.read_bytes())
    return {"commit": commit or "sin_git",
            "dirty": bool(estado and estado.stdout.strip()),
            "diff_sha256": huella.hexdigest()}


def _commit() -> str:
    """El commit con el que se generaron estos resultados (R12)."""
    return _estado_git()["commit"]


def _modelo_solicitado(sistema: str, modelo: str | None) -> str:
    if modelo:
        return modelo
    return config.CASCADA_MODELOS[0] if sistema == "cascada" else config.MODELO_ID


def manifest_ejecucion(ruta_jsonl, sistema: str, modelo: str | None = None,
                       limite: int | None = None) -> dict:
    """Identidad reproducible de una tanda, antes de efectuar llamadas."""
    ruta = Path(ruta_jsonl)
    contenido = ruta.read_bytes()
    retrieval = ({"backend": "denso", "paso_aislado": "0_denso"}
                 if sistema in {"baseline", "cascada"}
                 else {"backend": "bm25", "consulta": "palabras_clave_ingles_agente", "item": False})
    return {
        "version": 1,
        "golden": str(ruta.as_posix()),
        "golden_sha256": hashlib.sha256(contenido).hexdigest(),
        "sistema": sistema,
        "modelo": _modelo_solicitado(sistema, modelo),
        "limite": limite,
        "retrieval": retrieval,
        **_estado_git(),
    }


CAMPOS_MANIFEST_BLOQUEANTES = ("version", "golden_sha256", "sistema", "modelo", "limite", "retrieval")
CAMPOS_MANIFEST_INFORMATIVOS = ("commit", "dirty", "diff_sha256")
SISTEMAS = {"baseline", "cascada", "candidato_07", "final"}


def validar_manifest(manifest: dict, esperado: dict) -> list[str]:
    """Campos cuya diferencia hace inseguro reutilizar predicciones.

    Solo bloquean lo que cambia el resultado: golden (hash), sistema, modelo, límite y
    retrieval. Commit, árbol sucio y huella del diff son informativos (ver avisos_manifest):
    editar un docstring o un test no debe obligar a otra etiqueta.
    """
    return [c for c in CAMPOS_MANIFEST_BLOQUEANTES if manifest.get(c) != esperado.get(c)]


def avisos_manifest(manifest: dict, esperado: dict) -> list[str]:
    """Diferencias de commit/dirty/diff entre la tanda guardada y el árbol actual (no bloquean)."""
    avisos = [f"{c}: guardado={manifest.get(c)!r} actual={esperado.get(c)!r}"
              for c in CAMPOS_MANIFEST_INFORMATIVOS if manifest.get(c) != esperado.get(c)]
    if manifest.get("legacy"):
        avisos.insert(0, "manifest legacy: bendecido a posteriori, sin huella de código original")
    return avisos


def validar_sistema(sistema: str) -> None:
    """Falla ANTES de ejecutar nada si el sistema no existe o no puede montarse.

    `final` lanza SistemaFinalNoDisponible mientras falten los guardrails del 06 y se deja
    montar cuando existan: no depende del estado actual de guardrails.middleware_final().
    """
    if sistema not in SISTEMAS:
        raise ValueError(f"Sistema desconocido: {sistema!r}. Opciones: {sorted(SISTEMAS)}")
    from agente10k import agente
    try:
        agente._componentes_sistema(sistema)
    except NotImplementedError as exc:                 # por si un cambio futuro no lo traduce
        raise agente.SistemaFinalNoDisponible(
            f"El sistema {sistema!r} no está disponible todavía: {exc}") from exc


def bendecir_legacy(etiqueta: str, ruta_jsonl, sistema: str, modelo: str | None = None,
                    limite: int | None = None, nota: str | None = None) -> Path:
    """Escribe SOLO manifest.json para una etiqueta con predicciones anteriores al manifest.

    No toca predicciones.jsonl, puntuaciones.jsonl ni resumen.json. Comprueba antes que el
    golden embebido en cada fila coincide con `ruta_jsonl` (mismas preguntas y orden) y que el
    modelo real declarado no contradice al pedido. El commit se toma de resumen.json; `dirty` y
    `diff_sha256` quedan en None porque no se conocen. Se niega a sobrescribir un manifest.
    """
    destino = config.RESULTADOS / etiqueta
    ruta_pred, ruta_man = destino / "predicciones.jsonl", destino / "manifest.json"
    if not ruta_pred.is_file():
        raise FileNotFoundError(f"No hay predicciones en {ruta_pred}")
    if ruta_man.exists():
        raise FileExistsError(f"{ruta_man} ya existe: no se sobrescribe")
    filas = _leer_jsonl(ruta_pred)
    preguntas = cargar_preguntas(ruta_jsonl)[:limite]
    if [f.get("golden") for f in filas] != preguntas:
        raise ValueError("El golden embebido en las predicciones no coincide con "
                         f"{ruta_jsonl}: no se puede bendecir este artefacto.")
    manifest = manifest_ejecucion(ruta_jsonl, sistema, modelo, limite)
    reales = {f.get("modelo_real") for f in filas} - {None}
    pedido = str(manifest["modelo"]).removeprefix("openrouter:")
    if modelo is None and reales and not all(str(r).removeprefix("openrouter:") == pedido
                                             for r in reales):
        raise ValueError(f"El modelo real {sorted(reales)} no coincide con {pedido!r}; "
                         "indica `modelo=` si es el correcto.")
    resumen = {}
    if (destino / "resumen.json").is_file():
        resumen = json.loads((destino / "resumen.json").read_text(encoding="utf-8"))
    manifest.update(commit=resumen.get("commit") or "desconocido", dirty=None, diff_sha256=None,
                    legacy=True,
                    nota=nota or "manifest escrito a posteriori; las predicciones no se han tocado")
    ruta_man.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return ruta_man


def _serializar(resp) -> dict:
    """RespuestaFinanciera -> dict. Acepta también un dict ya plano."""
    if hasattr(resp, "model_dump"):
        return resp.model_dump()
    return dict(resp or {})


def _delta_numerico(actual, anterior):
    """Resta contadores anidados conservando la forma del uso del callback."""
    if isinstance(actual, dict):
        previo = anterior if isinstance(anterior, dict) else {}
        return {k: _delta_numerico(v, previo.get(k, 0)) for k, v in actual.items()}
    if isinstance(actual, (int, float)) and isinstance(anterior, (int, float)):
        return actual - anterior
    return actual


ARCHIVO_PARCIAL = "predicciones.parcial.jsonl"
MANIFEST_PARCIAL = "manifest.parcial.json"


def _leer_jsonl_tolerante(ruta) -> list[dict]:
    """Como _leer_jsonl, pero ignora una última línea truncada por un corte."""
    filas = []
    with open(ruta, encoding="utf-8") as f:
        for linea in f:
            if linea.strip():
                try:
                    filas.append(json.loads(linea))
                except json.JSONDecodeError:
                    break
    return filas


ESPERA_REINTENTO_FILA_S = 20.0
# 2 y no 3: el peor caso por pregunta se multiplica por los reintentos del cliente y las vueltas
# del grafo. Con 3 intentos de 300 s una sola pregunta podía bloquear 16 min y una tanda de 26
# llegar a horas. Con 2 se recupera igual el corte puntual del proveedor y el techo es la mitad.
INTENTOS_FILA = 2                  # 1 intento + 1 reintento, solo ante fallo de infraestructura
_RE_INFRAESTRUCTURA = re.compile(
    r"plazoagotado|plazo de \d+|429|rate.?limit|too many requests|timeout|timed out|temporar|"
    r"50[234]|connection|remoteprotocol|overloaded|provider returned error", re.I)


def _fallo_de_infraestructura(error: str | None) -> bool:
    """¿El error es del proveedor (plazo, 429, 5xx, red) y no una respuesta mala del modelo?"""
    return bool(error) and bool(_RE_INFRAESTRUCTURA.search(str(error)))


def ejecutar_golden(ruta_jsonl, etiqueta: str, sistema: str = "baseline",
                    modelo: str | None = None, limite: int | None = None,
                    reanudar: bool = True, intentos: int = INTENTOS_FILA) -> Path:
    """Llama al agente una vez por pregunta y guarda predicciones.jsonl. GASTA API.

    Una pregunta que falle no para la tanda: se guarda con su error.
    `limite` ejecuta solo las N primeras (para cronometrar antes de la tanda entera).
    `intentos` reintenta una pregunta SOLO si el error es de infraestructura del proveedor (plazo
    agotado, 429, 5xx, red); una respuesta mala nunca se repite. Agotados los intentos la fila
    cuenta como fallo del sistema y sigue en el denominador.

    Antes de crear ningún artefacto se comprueba el sistema (validar_sistema): `final` falla
    explícitamente mientras falten los guardrails. Cada fila se guarda al terminar en
    `predicciones.parcial.jsonl` (con `manifest.parcial.json`); un corte no pierde lo hecho.
    Con `reanudar=True` (por defecto) una tanda parcial compatible continúa por id (las filas con
    error se reintentan); si su manifest no es compatible, falla. Al completarse, se promueve
    a predicciones.jsonl y manifest.json de forma atómica, de modo que un corte tampoco
    destruye una tanda anterior completa. `reanudar=False` descarta la parcial.
    """
    validar_sistema(sistema)                          # antes de tocar el disco o la API
    from agente10k import agente                      # import tardío: evita ciclos

    manifest = manifest_ejecucion(ruta_jsonl, sistema, modelo, limite)
    preguntas = cargar_preguntas(ruta_jsonl)[:limite]
    destino = config.RESULTADOS / etiqueta
    if etiqueta.startswith("baseline") and (destino / "predicciones.jsonl").is_file():
        # Invariante 6: el baseline congelado no se sobrescribe (la promoción final haría os.replace).
        raise FileExistsError(f"{destino / 'predicciones.jsonl'} es un baseline congelado: no se sobrescribe. "
                              "Usa otra etiqueta.")
    parcial, man_parcial = destino / ARCHIVO_PARCIAL, destino / MANIFEST_PARCIAL
    hechas: list[dict] = []
    if reanudar and parcial.is_file():
        if not man_parcial.is_file():
            raise ValueError(f"{parcial} no tiene {MANIFEST_PARCIAL}: no se puede reanudar. "
                             "Usa reanudar=False o una etiqueta nueva.")
        previo = json.loads(man_parcial.read_text(encoding="utf-8"))
        if diferencias := validar_manifest(previo, manifest):
            raise ValueError(f"La tanda parcial de {etiqueta!r} no es compatible con esta "
                             f"ejecución ({', '.join(diferencias)}). Usa reanudar=False o una etiqueta nueva.")
        if avisos := avisos_manifest(previo, manifest):
            warnings.warn("Se reanuda con código distinto al inicial: " + "; ".join(avisos))
        ids = {p["id"] for p in preguntas}
        hechas = [f for f in _leer_jsonl_tolerante(parcial) if f.get("id") in ids and not f.get("error")]
    destino.mkdir(parents=True, exist_ok=True)
    man_parcial.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    _escribir_jsonl(parcial, hechas)                  # normaliza: sin truncados ni errores
    ids_hechos = {f["id"] for f in hechas}
    filas = list(hechas)
    for i, p in enumerate(preguntas, 1):
        if p["id"] in ids_hechos:
            print(f"  [{i:>2}/{len(preguntas)}] {p['id']} reanudada (ya ejecutada)")
            continue
        inicio = time.perf_counter()
        for intento in range(1, intentos + 1):
            try:
                r = agente.ejecutar(p["pregunta"], sistema=sistema, modelo=modelo)
            except Exception as exc:                   # red muerta, cuota agotada...
                r = {"respuesta": {}, "error": f"{type(exc).__name__}: {exc}",
                     "tool_calls": [], "observaciones": [], "latencia_s": None,
                     "uso_mensajes": {}, "usd_openrouter": None, "modelo_real": modelo}
            if intento >= intentos or not _fallo_de_infraestructura(r.get("error")):
                break
            # Política declarada de antemano (docs/13): solo se reintenta un fallo de
            # infraestructura del proveedor, nunca una respuesta mala. Agotados los intentos, la
            # fila cuenta como fallo del sistema; jamás se excluye del denominador.
            print(f"       reintento {intento}/{intentos - 1} tras {str(r.get('error'))[:60]}", flush=True)
            time.sleep(ESPERA_REINTENTO_FILA_S * intento)
        pared = time.perf_counter() - inicio
        latencia = r.get("latencia_s")
        if r.get("error") and not latencia:            # error sin cronometrar: el reloj de pared
            latencia = pared
        fila = {
            "id": p["id"], "golden": p, "respuesta": _serializar(r.get("respuesta")),
            "tool_calls": r.get("tool_calls") or [], "observaciones": r.get("observaciones") or [],
            "error": r.get("error"), "latencia_s": latencia, "latencia_pared_s": pared,
            "uso_mensajes": r.get("uso_mensajes") or {}, "usd": r.get("usd_openrouter"),
            "modelo_real": r.get("modelo_real"), "n_llamadas": r.get("n_llamadas"),
            "llamadas_modelo": r.get("llamadas_modelo"), "guard": r.get("guard"),
        }
        with open(parcial, "a", encoding="utf-8") as f:   # fila a fila: un corte no pierde lo hecho
            f.write(json.dumps(fila, ensure_ascii=False, default=str) + "\n")
            f.flush()
        filas.append(fila)
        print(f"  [{i:>2}/{len(preguntas)}] {p['id']} {latencia or 0:.1f}s "
              f"{'ERROR: ' + str(r.get('error'))[:60] if r.get('error') else 'ok'}")

    orden = {p["id"]: i for i, p in enumerate(preguntas)}
    filas.sort(key=lambda f: orden[f["id"]])
    ruta = destino / "predicciones.jsonl"
    tmp_pred, tmp_man = ruta.with_suffix(".jsonl.tmp"), destino / "manifest.json.tmp"
    _escribir_jsonl(tmp_pred, filas)
    tmp_man.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp_pred, ruta)
    os.replace(tmp_man, destino / "manifest.json")
    parcial.unlink(missing_ok=True)
    man_parcial.unlink(missing_ok=True)
    print(f"\n{len(filas)} predicciones en {ruta}")
    return ruta


def necesita_juez(filas: list[dict]) -> bool:
    """¿Hay alguna extractiva o comparativa que puntuar? (si no, el juez sobra)."""
    for f in filas:
        p = f.get("golden")
        if isinstance(p, dict) and not sin_referencia(p) and not es_hueco(p) \
                and p.get("familia") in ("extractiva", "comparativa"):
            return True
    return False


def _percentil(valores: list[float], q: float) -> float | None:
    """Percentil con interpolación lineal (igual que numpy.percentile)."""
    v = sorted(valores)
    if not v:
        return None
    pos = (len(v) - 1) * q
    bajo = math.floor(pos)
    alto = min(bajo + 1, len(v) - 1)
    return v[bajo] + (v[alto] - v[bajo]) * (pos - bajo)


def _distribucion(valores: list[float], media: str, mediana: str, p90: str) -> dict:
    v = [float(x) for x in valores]
    return {media: statistics.mean(v) if v else None,
            mediana: statistics.median(v) if v else None, p90: _percentil(v, 0.9)}


def _num(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def metricas_operativas(filas: list[dict]) -> dict:
    """Latencia, tokens y llamadas desde las filas de predicciones.jsonl.

    Fuente única del resumen y de tabla_comparativa (que la usa como respaldo cuando un
    resumen antiguo no trae la mediana o el p90). Media, mediana y p90 de latencia y de tokens;
    tokens de entrada y salida medios; llamadas a herramienta (`llamadas_medias`) y al modelo
    (`llamadas_modelo_medias`, solo si la fila las guardó). Una fila con error y latencia 0 o
    ausente no se cronometró y no cuenta en la latencia; una fila sin uso no cuenta en tokens.
    """
    lat = [f["latencia_s"] for f in filas if _num(f.get("latencia_s"))
           and not (f.get("error") and f["latencia_s"] <= 0)]
    uso = [f.get("uso_mensajes") or {} for f in filas]
    tokens = [u["total_tokens"] for u in uso if _num(u.get("total_tokens"))]
    entrada = [u["input_tokens"] for u in uso if _num(u.get("input_tokens"))]
    salida = [u["output_tokens"] for u in uso if _num(u.get("output_tokens"))]
    tools = [f["n_llamadas"] for f in filas if _num(f.get("n_llamadas"))]
    modelo = [f["llamadas_modelo"] for f in filas if _num(f.get("llamadas_modelo"))]
    media = lambda v: statistics.mean(v) if v else None
    return {**_distribucion(lat, "latencia_media_s", "latencia_mediana_s", "latencia_p90_s"),
            **_distribucion(tokens, "tokens_medios", "tokens_mediana", "tokens_p90"),
            "tokens_entrada_medios": media(entrada), "tokens_salida_medios": media(salida),
            "llamadas_medias": media(tools), "llamadas_modelo_medias": media(modelo)}


def _puntuar_filas(etiqueta: str, filas: list[dict], juez, estricto: bool) -> tuple[list[dict], dict]:
    """Puntuaciones y resumen de unas filas de predicciones; no escribe nada."""
    juez_antes = ({"llamadas": juez.llamadas, "fallos": juez.fallos,
                   "uso": json.loads(json.dumps(juez.uso))} if juez is not None else None)
    punt = [puntuar_fila(f, juez=juez, estricto=estricto) for f in filas]
    for s, f in zip(punt, filas):
        uso = f.get("uso_mensajes") or {}
        s.update(latencia_s=f.get("latencia_s"), usd=f.get("usd"),
                 n_llamadas=f.get("n_llamadas"), error=f.get("error"),
                 tokens=uso.get("total_tokens"), tokens_entrada=uso.get("input_tokens"),
                 tokens_salida=uso.get("output_tokens"),
                 llamadas_modelo=f.get("llamadas_modelo"))

    def media(clave):
        vals = [x[clave] for x in punt if isinstance(x.get(clave), (int, float))]
        return statistics.mean(vals) if vals else None

    modelo_real = next((f.get("modelo_real") for f in filas if f.get("modelo_real")), None)
    usd_medio = media("usd")
    coste_meta = {}
    if usd_medio is not None:
        coste_meta = {"coste_fuente": "metadata_openrouter"}
    elif isinstance(modelo_real, str) and modelo_real.endswith(":free"):
        usd_medio = 0.0
        # La URL se deriva del modelo REALMENTE usado: antes estaba fija y los resúmenes medidos con
        # otro modelo citaban la ficha de precios equivocada.
        coste_meta = {
            "coste_fuente": "https://openrouter.ai/" + modelo_real.removeprefix("openrouter:").replace(":", "%3A"),
            "coste_fecha": dt.date.today().isoformat(),
            "coste_regla": "modelo_termina_en_:free_y_sin_costes_reportados",
        }

    resumen = {
        "etiqueta": etiqueta, "n": len(punt), "fecha": dt.datetime.now().isoformat(timespec="seconds"),
        "commit": _commit(), "modelo": modelo_real,
        "temperatura": config.TEMPERATURA, "estricto": estricto, "con_juez": juez is not None,
        **resumen_aciertos(punt),
        **metricas_operativas(filas),
        "usd_medio": usd_medio, **coste_meta,
        "recall_agente": media("recall_agente"),
        "abstenciones_indebidas": sum(bool(x.get("abstencion_indebida")) for x in punt),
        "errores": sum(bool(x.get("error")) for x in punt),
        "sensibilidad_tolerancia": sensibilidad(punt),
        "banderas_diagnosticas": resumen_banderas(punt),
    }
    if sr := resumen_sin_referencia(punt):
        resumen["sin_referencia"] = sr

    # El coste del juez va aparte del coste por pregunta: son llamadas de
    # evaluación, no del agente (D16).
    if juez is not None:
        resumen["juez"] = {
            "modelo": juez.modelo_id,
            "llamadas": juez.llamadas - juez_antes["llamadas"],
            "fallos": juez.fallos - juez_antes["fallos"],
            "uso": _delta_numerico(juez.uso, juez_antes["uso"]),
        }
        resumen["juez_fallos_filas"] = sum(bool(x.get("juez_fallo")) for x in punt)
        resumen["juez_omitido_filas"] = sum(bool(x.get("juez_omitido")) for x in punt)
    return punt, resumen


def puntuar(etiqueta: str, juez=None, estricto: bool = True) -> pd.DataFrame:
    """Lee predicciones.jsonl, aplica los cuatro evaluadores y guarda. NO gasta API.

    Con `juez`, sí llama al modelo para la etapa 2 de (a) y para `correcta`, pero
    con caché: re-puntuar cuesta 0 llamadas y los fallos se reintentan solos. Sin juez y
    en modo estricto, las extractivas y comparativas cuya trayectoria no falla no son
    evaluables: el resumen sale `parcial` y `micro`/`macro` quedan en None (ver resumen_aciertos).
    SOBRESCRIBE puntuaciones.jsonl y resumen.json de la etiqueta: para re-puntuar una etiqueta
    congelada sin tocarla, usa `repuntuar`.
    """
    destino = config.RESULTADOS / etiqueta
    filas = _leer_jsonl(destino / "predicciones.jsonl")
    punt, resumen = _puntuar_filas(etiqueta, filas, juez, estricto)
    _escribir_jsonl(destino / "puntuaciones.jsonl", punt)
    if juez is not None:
        juez.guardar()
    (destino / "resumen.json").write_text(
        json.dumps(resumen, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(json.dumps({k: v for k, v in resumen.items()
                      if k not in ("sensibilidad_tolerancia",)},
                     ensure_ascii=False, indent=2, default=str))
    return pd.DataFrame(punt)


def repuntuar(etiqueta: str, juez=None, estricto: bool = True,
              guardar_en: str | None = None) -> tuple[pd.DataFrame, dict]:
    """Re-puntúa las predicciones de `etiqueta` con el código ACTUAL, sin API ni escritura.

    Devuelve (puntuaciones, resumen) sin tocar la etiqueta original. Con `guardar_en`, escribe
    puntuaciones.jsonl y resumen.json en esa otra carpeta (nunca en la de origen).

    Por qué existe: las puntuaciones guardadas de baseline_huecos y candidato_07_huecos dicen
    3/6 en ambos, porque se calcularon antes de que la fórmula del hueco exigiera
    `sin_estimacion`. Re-puntuadas sin API con el código actual (detector v2) dan 2/6 en ambos:
    baseline_huecos g3-h005 y candidato_07_huecos g3-h001 se abstienen (fuente "ninguna") pero
    calculan un margen implícito a partir de ingresos y costes ("~59,7 %" y "~50,3 %"), es
    decir, estiman un dato no reportado. Las guardadas no se sobrescriben (baseline* está
    congelado): esta función da la nota vigente y tests/test_medicion_repuntuar.py la fija.
    """
    if guardar_en is not None and guardar_en == etiqueta:
        raise ValueError("guardar_en debe ser una etiqueta distinta: no se sobrescribe el origen")
    filas = _leer_jsonl(config.RESULTADOS / etiqueta / "predicciones.jsonl")
    punt, resumen = _puntuar_filas(etiqueta, filas, juez, estricto)
    if guardar_en is not None:
        destino = config.RESULTADOS / guardar_en
        _escribir_jsonl(destino / "puntuaciones.jsonl", punt)
        (destino / "resumen.json").write_text(
            json.dumps(dict(resumen, etiqueta=guardar_en, repuntuado_de=etiqueta),
                       ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return pd.DataFrame(punt), resumen

# ===================================== parte 7: los jueces, con caché (docs/12 §6)
PLAZO_JUEZ_S = 120.0          # segundos por veredicto; al agotarse cuenta como fallo del juez (no se cachea)
INTENTOS_JUEZ = 2             # un veredicto perdido suspende la fila: se reintenta antes de darlo por fallido
ESPERA_JUEZ_S = 5.0
VERSION_JUEZ = "v1"          # súbela al tocar un prompt o un esquema: invalida la caché


class Veredicto(BaseModel):                   # groundedness frase a frase (estilo FACTS)
    razonamiento: str = Field(description="Primero: analiza cada frase de la RESPUESTA frente a la CITA.")
    etiquetas: list[Literal["supported", "unsupported", "contradictory", "no_rad"]] = Field(
        description="Una etiqueta por frase de la RESPUESTA, en orden.")


class Correccion(BaseModel):                  # un solo criterio: ¿dice lo mismo que la referencia?
    razonamiento: str = Field(description="Primero: compara dato, unidad, escala y ejercicio con la REFERENCIA.")
    valida: bool


PROMPT_RESPALDO = (
    "Eres un verificador estricto. Recibes una CITA literal de un informe 10-K y una RESPUESTA en español. Divide la "
    "RESPUESTA en frases y etiqueta cada una: supported si la CITA la implica por completo; unsupported si la CITA no basta; "
    "contradictory si la CITA dice otra cosa; no_rad si no afirma nada que necesite fuente. Usa solo la CITA, sin "
    "conocimiento del mundo. Cifras, unidades, escala (millones frente a miles de millones) y ejercicio deben coincidir. "
    "La longitud no es mérito. Razona primero y etiqueta después.")
PROMPT_CORRECCION = (
    "Comparas una RESPUESTA con la REFERENCIA de un experto para la misma PREGUNTA. valida=true solo si da el mismo dato "
    "o conclusión: el formato puede variar (60.922 millones = $60.9 billion), pero la unidad, la escala y el ejercicio "
    "deben coincidir. Si la RESPUESTA dice que el dato no está o no se puede responder y la REFERENCIA lo da, es inválida. "
    "Lo que añada solo invalida si contradice la REFERENCIA. El ANCLA es contexto, no un requisito. La longitud no es "
    "mérito. Razona primero y decide después.")


class Juez:
    """Jueces con caché JSON. Un fallo de parseo devuelve None, se cuenta y NO se cachea:
    al re-puntuar se reintenta solo lo que falló."""

    def __init__(self, modelo, modelo_id: str, ruta_cache=None):
        self.modelo_id = modelo_id
        self.ruta = Path(ruta_cache or config.RESULTADOS / "cache" / "juez.json")
        self.cache = json.loads(self.ruta.read_text(encoding="utf-8")) if self.ruta.is_file() else {}
        self.agentes = {t: create_agent(model=modelo, tools=[], system_prompt=pr,
                                        response_format=ToolStrategy(schema=esq))
                        for t, pr, esq in (("respaldo", PROMPT_RESPALDO, Veredicto),
                                           ("correccion", PROMPT_CORRECCION, Correccion))}
        self.llamadas, self.fallos, self.uso = 0, 0, {}

    @staticmethod
    def huella_prompt(tipo: str) -> str:
        """Hash del prompt y del esquema de salida de ese juez: cambiarlos invalida la caché."""
        prompt, esquema = ((PROMPT_RESPALDO, Veredicto) if tipo == "respaldo"
                           else (PROMPT_CORRECCION, Correccion))
        contenido = json.dumps([prompt, esquema.model_json_schema()], sort_keys=True)
        return hashlib.sha256(contenido.encode()).hexdigest()[:16]

    def _preguntar(self, tipo: str, texto: str) -> dict | None:
        clave = hashlib.sha256(json.dumps([tipo, VERSION_JUEZ, self.huella_prompt(tipo),
                                           self.modelo_id, texto]).encode()).hexdigest()
        if clave in self.cache:
            return self.cache[clave]
        salida = None
        with get_usage_metadata_callback() as cb:                       # coste del juez, aparte
            # Un veredicto perdido cuenta como fallo de la fila, así que un corte transitorio del
            # proveedor puede suspender una respuesta correcta (pasó con g3-017: (a), (b) y (c)
            # correctos y `correcta` devolvió None). Se reintenta antes de darlo por fallido.
            for intento in range(INTENTOS_JUEZ):
                try:
                    from agente10k.agente import _invocar_con_plazo  # plazo duro: el proveedor puede colgar la petición
                    sr = _invocar_con_plazo(
                        self.agentes[tipo], {"messages": [{"role": "user", "content": texto}]},
                        {"recursion_limit": 20}, PLAZO_JUEZ_S).get("structured_response")
                    salida = sr.model_dump() if sr is not None else None
                except Exception:                                       # red, 400, recursión
                    salida = None
                self.llamadas += 1
                if salida is not None:
                    break
                if intento + 1 < INTENTOS_JUEZ:
                    time.sleep(ESPERA_JUEZ_S)
        for m, u in cb.usage_metadata.items():
            acc = self.uso.setdefault(m, {"input_tokens": 0, "output_tokens": 0})
            acc["input_tokens"] += u.get("input_tokens", 0)
            acc["output_tokens"] += u.get("output_tokens", 0)
        if salida is None:
            self.fallos += 1
        else:
            self.cache[clave] = salida
        return salida

    def respalda(self, cita: str, respuesta: str) -> bool | None:
        v = self._preguntar("respaldo", f"CITA: {cita}\nRESPUESTA: {respuesta}")
        etq = None if v is None else [e for e in v["etiquetas"] if e != "no_rad"]   # no_rad fuera
        return None if etq is None else bool(etq) and all(e == "supported" for e in etq)

    def correcta(self, pregunta, respuesta, referencia, ancla=None) -> bool | None:
        v = self._preguntar("correccion", f"PREGUNTA: {pregunta}\nREFERENCIA: {referencia}\n"
                                          f"ANCLA: {ancla or '-'}\nRESPUESTA: {respuesta}")
        return None if v is None else bool(v["valida"])

    def guardar(self) -> None:
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        self.ruta.write_text(json.dumps(self.cache, ensure_ascii=False, indent=1), encoding="utf-8")


def crear_juez(modelo_id: str | None = None) -> Juez:
    """El juez con el modelo indicado, o AGENTE10K_MODELO_JUEZ, o el del agente."""
    import os
    mid = modelo_id or os.environ.get("AGENTE10K_MODELO_JUEZ") or config.MODELO_ID
    return Juez(config.crear_modelo(mid), mid)
