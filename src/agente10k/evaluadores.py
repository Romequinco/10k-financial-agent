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

# ==================== parte 5: (d) abstención, acierto por familia y agregados
FAMILIAS = ("numerica", "extractiva", "comparativa", "hueco")


def acierto(s: dict) -> bool | None:
    """Fórmula por familia (D14). None = no evaluable."""
    f, c = s.get("familia"), s.get("c") is True
    if f == "numerica":
        return s.get("b") is True and c
    if f == "hueco":
        return bool(s.get("abstiene") and s.get("sin_cifra") and c)
    if f in ("extractiva", "comparativa"):
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

    s.update(abstiene=resp.get("fuente") == "ninguna",
             sin_cifra=resp.get("cifra") is None,
             hay_dato=familia not in ("hueco", "sin_referencia"))
    s["abstencion_indebida"] = s["abstiene"] and s["hay_dato"]      # (d): falso "ninguna"

    s.update(a=None, a_respalda=None, correcta=None, correcta_ok=None, juez_fallo=False)
    if familia in ("extractiva", "comparativa"):
        etapa1 = bool(s.get("a_existe") and s.get("a_vista"))
        if juez is not None:
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
    """k/n por familia; micro = aciertos/preguntas; macro = media de las familias presentes."""
    fam = {f: [x["acierto"] for x in punt
               if x.get("familia") == f and x.get("acierto") is not None]
           for f in FAMILIAS}
    con = [v for v in fam.values() if v]
    todas = [a for v in con for a in v]
    return {"familias": {f: f"{sum(v)}/{len(v)}" if v else "—" for f, v in fam.items()},
            "micro": sum(todas) / len(todas) if todas else None,
            "macro": sum(sum(v) / len(v) for v in con) / len(con) if con else None}


def sensibilidad(punt: list[dict]) -> dict:
    """Micro con 0 / 0,1 / 0,5 / 1 % en USD, re-puntuando sin ejecutar (D06)."""
    return {f"{t} %": resumen_aciertos(
        [dict(x, acierto=acierto(dict(x, b=x.get(f"b_tol{t}", x.get("b")))))
         for x in punt])["micro"] for t in (0, 0.1, 0.5, 1)}

# ============================== parte 6: evaluar(), puntuar() y persistencia
import datetime as dt
import statistics
import subprocess
from pathlib import Path

from agente10k import config


def _leer_jsonl(ruta) -> list[dict]:
    with open(ruta, encoding="utf-8") as f:
        return [json.loads(x) for x in f if x.strip()]


def _escribir_jsonl(ruta, filas: list[dict]) -> None:
    Path(ruta).parent.mkdir(parents=True, exist_ok=True)
    with open(ruta, "w", encoding="utf-8") as f:
        f.writelines(json.dumps(x, ensure_ascii=False, default=str) + "\n" for x in filas)


def _commit() -> str:
    """El commit con el que se generaron estos resultados (R12)."""
    try:
        r = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                           capture_output=True, text=True, timeout=10)
        return r.stdout.strip() or "sin_git"
    except Exception:
        return "sin_git"                      # clon descargado como ZIP


def _serializar(resp) -> dict:
    """RespuestaFinanciera -> dict. Acepta también un dict ya plano."""
    if hasattr(resp, "model_dump"):
        return resp.model_dump()
    return dict(resp or {})


def ejecutar_golden(ruta_jsonl, etiqueta: str, sistema: str = "baseline",
                    modelo: str | None = None, limite: int | None = None) -> Path:
    """Llama al agente una vez por pregunta y guarda predicciones.jsonl. GASTA API.

    Una pregunta que falle no para la tanda: se guarda con su error.
    `limite` ejecuta solo las N primeras (para cronometrar antes de la tanda entera).
    """
    from agente10k import agente                      # import tardío: evita ciclos

    preguntas = cargar_preguntas(ruta_jsonl)[:limite]
    destino = config.RESULTADOS / etiqueta
    filas = []
    for i, p in enumerate(preguntas, 1):
        try:
            r = agente.ejecutar(p["pregunta"], sistema=sistema, modelo=modelo)
        except Exception as exc:                       # red muerta, cuota agotada...
            r = {"respuesta": {}, "error": f"{type(exc).__name__}: {exc}",
                 "tool_calls": [], "observaciones": [], "latencia_s": 0.0,
                 "uso_mensajes": {}, "usd_openrouter": None, "modelo_real": modelo}
        filas.append({
            "id": p["id"], "golden": p, "respuesta": _serializar(r.get("respuesta")),
            "tool_calls": r.get("tool_calls") or [], "observaciones": r.get("observaciones") or [],
            "error": r.get("error"), "latencia_s": r.get("latencia_s"),
            "uso_mensajes": r.get("uso_mensajes") or {}, "usd": r.get("usd_openrouter"),
            "modelo_real": r.get("modelo_real"), "n_llamadas": r.get("n_llamadas"),
        })
        print(f"  [{i:>2}/{len(preguntas)}] {p['id']} "
              f"{r.get('latencia_s') or 0:.1f}s "
              f"{'ERROR: ' + str(r.get('error'))[:60] if r.get('error') else 'ok'}")

    ruta = destino / "predicciones.jsonl"
    _escribir_jsonl(ruta, filas)
    print(f"\n{len(filas)} predicciones en {ruta}")
    return ruta


def puntuar(etiqueta: str, juez=None, estricto: bool = True) -> pd.DataFrame:
    """Lee predicciones.jsonl, aplica los cuatro evaluadores y guarda. NO gasta API.

    Con `juez`, sí llama al modelo para la etapa 2 de (a) y para `correcta`, pero
    con caché: re-puntuar cuesta 0 llamadas y los fallos se reintentan solos.
    """
    destino = config.RESULTADOS / etiqueta
    filas = _leer_jsonl(destino / "predicciones.jsonl")
    punt = [puntuar_fila(f, juez=juez, estricto=estricto) for f in filas]
    for s, f in zip(punt, filas):
        s.update(latencia_s=f.get("latencia_s"), usd=f.get("usd"),
                 n_llamadas=f.get("n_llamadas"), error=f.get("error"),
                 tokens=(f.get("uso_mensajes") or {}).get("total_tokens"))

    _escribir_jsonl(destino / "puntuaciones.jsonl", punt)

    def media(clave):
        vals = [x[clave] for x in punt if isinstance(x.get(clave), (int, float))]
        return statistics.mean(vals) if vals else None

    resumen = {
        "etiqueta": etiqueta, "n": len(punt), "fecha": dt.datetime.now().isoformat(timespec="seconds"),
        "commit": _commit(), "modelo": next((f.get("modelo_real") for f in filas
                                             if f.get("modelo_real")), None),
        "temperatura": config.TEMPERATURA, "estricto": estricto, "con_juez": juez is not None,
        **resumen_aciertos(punt),
        "latencia_media_s": media("latencia_s"), "usd_medio": media("usd"),
        "tokens_medios": media("tokens"), "llamadas_medias": media("n_llamadas"),
        "abstenciones_indebidas": sum(bool(x.get("abstencion_indebida")) for x in punt),
        "errores": sum(bool(x.get("error")) for x in punt),
        "sensibilidad_tolerancia": sensibilidad(punt),
    }

    # El coste del juez va aparte del coste por pregunta: son llamadas de
    # evaluación, no del agente (D16).
    if juez is not None:
        resumen["juez"] = {"modelo": juez.modelo_id, "llamadas": juez.llamadas,
                           "fallos": juez.fallos, "uso": juez.uso}
        resumen["juez_fallos_filas"] = sum(bool(x.get("juez_fallo")) for x in punt)
        juez.guardar()

    (destino / "resumen.json").write_text(
        json.dumps(resumen, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(json.dumps({k: v for k, v in resumen.items()
                      if k not in ("sensibilidad_tolerancia",)},
                     ensure_ascii=False, indent=2, default=str))
    return pd.DataFrame(punt)

# ===================================== parte 7: los jueces, con caché (docs/12 §6)
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

    def _preguntar(self, tipo: str, texto: str) -> dict | None:
        clave = hashlib.sha256(json.dumps([tipo, VERSION_JUEZ, self.modelo_id, texto]).encode()).hexdigest()
        if clave in self.cache:
            return self.cache[clave]
        salida = None
        with get_usage_metadata_callback() as cb:                       # coste del juez, aparte
            try:
                sr = self.agentes[tipo].invoke(
                    {"messages": [{"role": "user", "content": texto}]},
                    config={"recursion_limit": 20}).get("structured_response")
                salida = sr.model_dump() if sr is not None else None
            except Exception:                                           # red, 400, recursión
                salida = None
        self.llamadas += 1
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