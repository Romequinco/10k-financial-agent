# Skill: los evaluadores y `evaluar(ruta_jsonl)`

> Requisitos: R09, R10, R11, R12 (y R14, R15) · Lee antes: [06_teoria_evaluacion_llms.md](06_teoria_evaluacion_llms.md),
> [08_skill_agente_salida_estructurada.md](08_skill_agente_salida_estructurada.md) §7 (`ejecutar()`),
> [09_skill_guardrails_middleware_xbrl.md](09_skill_guardrails_middleware_xbrl.md) §4 (`cifra_ok`),
> [10_skill_golden_set.md](10_skill_golden_set.md) §4–5 · Después: [13_skill_medicion_informe_presentacion.md](13_skill_medicion_informe_presentacion.md)

> Fuentes: [enunciado · §1, §4.3, §4.5, §5, §7]; [01 R09–R12, R14]; [notebook S1 · celdas 28–29, 32]; [transcripcion_10sep · 02:29];
> [16 §3.1–3.4, §3.6](16_repo_transformers_labs.md); [17 §3.1, §3.2, §3.9](17_repo_generative_ai.md); [15 §3.5](15_repo_genai_labs.md);
> [api_stack · create_agent, structured_output.ToolStrategy, ToolMessage]; decisiones D05, D06, D08 y D11–D20 del mapa de cobertura.

**v1.0 · 12-sep-2026.** Cómo se implementan y validan (a), (b), (c), la abstención (d), `correcta` y el acierto por familia, y cómo
`evaluar()` ejecuta, guarda y puntúa. El porqué está en [06](06_teoria_evaluacion_llms.md); la tabla baseline frente a final, el informe y
el protocolo del día 24, en [13](13_skill_medicion_informe_presentacion.md). Marcas: **(probado)** = ejecutado en el venv del stack con
datos sintéticos, un juez falso y `ejecutar()` simulado, sin red; ⚠️ = sin verificar. Módulos `agente10k/…`: **SUGERENCIA**.

## 1. Qué se construye

Flujo: `evaluar(ruta)` → `ejecutar()` por pregunta ([08 §7](08_skill_agente_salida_estructurada.md)) → `predicciones.jsonl` →
`puntuar(etiqueta)` → `puntuaciones.jsonl` + `resumen.json` → tablas de [13](13_skill_medicion_informe_presentacion.md). **Ejecutar ≠
puntuar:** lo segundo se repite cuantas veces haga falta sin llamar al agente.

| Evaluador | Regla (decisión) | Entrada |
| --- | --- | --- |
| (a) cita | `existe` ∧ `vista` ∧ `respalda` (D13) | `cita`, secciones del corpus, contenido de los `ToolMessage`, juez frase a frase |
| (b) cifra | `cifra_ok`: USD 0,5 % relativo, BPA 0,005 absoluto, hueco si `cifra is None` (D06) | `cifra`, `unidad`, `xbrl_facts.parquet` |
| (c) trayectoria | todas las esperadas (AND; alternativas del extra `herramienta_alternativa`; `list_available` neutra) ∧ argumentos de `get_xbrl_fact` (D12) | `tool_calls` sin deduplicar |
| (d) abstención | correcta = `ninguna` en hueco; indebida = `ninguna` con dato (D11) | `fuente`, ¿hay dato? |
| `correcta` | juez de un solo criterio contra `respuesta_esperada` (D14) | `respuesta`, referencia, ancla |
| acierto | numérica (b)∧(c) · extractiva (a)∧(c)∧correcta · comparativa (a)∧(b)∧(c)∧correcta · hueco `ninguna`∧`cifra None`∧(c) | lo anterior |

Resuelve C06 (BPA absoluto), C07 (literal para aprobar; la cobertura solo diagnostica), C10 (juez frase a frase), C14 (comparativas con
`get_xbrl_fact` + `search_filings`), C17 ("vista" por el contenido del `ToolMessage`, sin `content_and_artifact`), C26 (no deduplicar) y
los fallos de parseo del juez (cuentan como fallo y se reportan).

## 2. Paso 1: leer las preguntas sin exigir nada (D10, D11, D20)

`evaluar()` no llama a `validar()`: las ciegas pueden traer solo los campos oficiales, huecos o familias vacías. Todo se lee con `.get`.

```python
# agente10k/evaluadores.py (SUGERENCIA) · parte 1: preguntas y verdad
import json
import math
import re
# from agente10k.normalizacion import normalizar, cobertura, cifra_ok, ESCALA, normalizar_ticker  -> 16 §3.2-3.3, 09 §4
# from agente10k.datos import valor_xbrl, texto_seccion, texto_chunk  # valor_xbrl -> 09 §4; texto_seccion y texto_chunk (texto del chunk o "") -> 10 §6
FYS, ITEMS = (2024, 2025), ("1A", "7", "7A", "8")
POR_DEFECTO = {"numerica": [["get_xbrl_fact"]], "extractiva": [["search_filings", "read_section"]],   # si falta el campo:
               "comparativa": [["get_xbrl_fact"], ["search_filings", "read_section"]]}           # requisitos con alternativas (propio)

def cargar_preguntas(ruta: str) -> list[dict]:
    """JSONL tolerante: no exige validar(); ids ausentes o repetidos se desambiguan."""
    with open(ruta, encoding="utf-8") as f:
        preguntas = [json.loads(x) for x in f if x.strip()]
    vistos = {}
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
    """Comparativas (D10): fiscal_year_base o, si falta, el otro FY de {2024, 2025}."""
    if (b := _fy(p, "fiscal_year_base")) is not None:
        return b
    fy = _fy(p)
    return next((x for x in FYS if x != fy), None) if fy in FYS else None

def verdad(p: dict, fy: int | None = None, base: bool = False) -> tuple:
    """(valor, unidad XBRL): del parquet si hay concept_xbrl (state verification); si no, del golden reescalado."""
    ticker, concepto, fy = normalizar_ticker(p.get("ticker")), p.get("concept_xbrl"), fy or _fy(p)
    if concepto and fy and (v := valor_xbrl(ticker, fy, concepto)) is not None:
        return v
    esperada = p.get("cifra_esperada_base" if base else "cifra_esperada")
    if esperada is None:
        return None, None
    u = normalizar(p.get("unidad"))
    factor = next((f for clave, f in ESCALA if clave in u), 1.0)
    return float(esperada) * factor, ("USD/shares" if "share" in u or "acci" in u else "USD")

def sin_referencia(p: dict) -> bool:                       # p. ej., unas ciegas que llegaran sin respuestas
    return all(p.get(k) is None for k in ("cifra_esperada", "concept_xbrl", "ancla_texto", "respuesta_esperada", "hueco"))

def es_hueco(p: dict) -> bool:
    """D11: hueco:true, numérica sin cifra_esperada o concepto que no existe para ese ticker y FY."""
    if p.get("hueco") is True or (p.get("familia") == "numerica" and p.get("cifra_esperada") is None):
        return True
    c, fy = p.get("concept_xbrl"), _fy(p)
    return bool(c and fy and valor_xbrl(normalizar_ticker(p.get("ticker")), fy, c) is None)

def esperadas(p: dict) -> tuple[list[list[str]], bool]:
    """(requisitos, por_defecto): cada nombre de herramienta_esperada (solo nombres reales) con sus alternativas del
    extra herramienta_alternativa (D12), p. ej. {"search_filings": ["read_section"]}. Si falta el campo, los de la familia."""
    lista = lambda x: [x] if isinstance(x, str) else list(x or [])
    h, alt = p.get("herramienta_esperada"), p.get("herramienta_alternativa")
    alt = alt if isinstance(alt, dict) else {}
    if h:
        return [[e, *lista(alt.get(e))] for e in lista(h)], False
    return [list(r) for r in POR_DEFECTO.get(p.get("familia"), [])], True
```

La verdad sale del parquet con el `valor_xbrl` de [09 §4](09_skill_guardrails_middleware_xbrl.md) (`(valor, unidad)` o `None`), el mismo que
usan `get_xbrl_fact` y R05, y no del texto de la tool: es la *state verification* de [06 §5](06_teoria_evaluacion_llms.md).

## 3. Paso 2: evaluador (b), la cifra (D06)

```python
# agente10k/evaluadores.py · parte 2: (b)
def cifra_ok_rel(cifra, unidad, v, unidad_xbrl, rel: float) -> bool:
    """Sensibilidad (D06): cambia solo la relativa de USD; el BPA (0,005 absoluto) y los huecos, como cifra_ok."""
    if v is None or cifra is None or unidad_xbrl == "USD/shares":
        return cifra_ok(cifra, unidad, v, unidad_xbrl)["ok"]
    x = float(cifra) * next((f for clave, f in ESCALA if clave in normalizar(unidad)), 1.0)
    return math.isclose(x, v, rel_tol=rel, abs_tol=0.0)

def evaluar_cifra(resp: dict, p: dict) -> dict:
    """(b): cifra frente a XBRL; en comparativas, también cifra_base si existen la esperada y la respondida (D14)."""
    if es_hueco(p):
        return {"b": resp.get("cifra") is None, "b_motivo": "hueco"}
    v, u = verdad(p)
    if v is None:
        return {"b": None, "b_motivo": "sin_verdad"}                 # extractiva: (b) no aplica
    pares = [(resp.get("cifra"), v, u)]
    if p.get("familia") == "comparativa" and resp.get("cifra_base") is not None:
        vb, ub = verdad(p, fy_base(p), base=True)
        if vb is not None:
            pares.append((resp["cifra_base"], vb, ub))
    res = [cifra_ok(c, resp.get("unidad"), x, ux) for c, x, ux in pares]
    out = {"b": all(r["ok"] for r in res), "b_motivo": "; ".join(r.get("motivo") or "ok" for r in res),
           "b_verdad": v, "b_unidad_xbrl": u, "b_con_base": len(pares) == 2,
           "b_unidad_ok": normalizar(resp.get("unidad")) == normalizar(u)}           # diagnóstico
    for t in (0, 0.1, 0.5, 1):                                        # sensibilidad sin volver a ejecutar
        out[f"b_tol{t}"] = all(cifra_ok_rel(c, resp.get("unidad"), x, ux, t / 100) for c, x, ux in pares)
    return out
```

- **Tolerancia documentada (va al informe):** USD relativa 0,5 %; BPA absoluta 0,005 (al céntimo); hueco = acierto si `cifra is None`. El
  porqué, en [06 §7](06_teoria_evaluacion_llms.md) y [02 §5](02_datos_corpus_y_xbrl.md). Es **la misma** `cifra_ok` que usa R05.
- `b_motivo` separa `error_escala 1e3` de `fuera_de_tolerancia` y `sin_cifra`: en la presentación se cuenta cuántos fallos son de escala.
  `b_tol0.5` coincide con `b` por construcción (probado): así se comprueba que la sensibilidad está bien cableada.

## 4. Paso 3: evaluador (c), la trayectoria (D12)

```python
# agente10k/evaluadores.py · parte 3: (c) y enrutado
# metricas_trayectoria(pred, ref) -> exact, in_order, any_order, precision, recall, redundantes, eficiencia   -> 17 §3.1, sin cambios
REALES = {"list_available", "get_xbrl_fact", "search_filings", "read_section"}   # lista blanca (+ las que añadáis)

def _requisitos(p: dict) -> tuple[list[list[str]], bool]:
    req, por_defecto = esperadas(p)                                  # [[nombre, *alternativas], ...]
    if req != [["list_available"]]:
        req = [r for r in req if r[0] != "list_available"]           # neutra, salvo en preguntas sobre el universo
    return req, por_defecto

def _args_xbrl_ok(tcs: list[dict], p: dict) -> bool | None:
    """Alguna get_xbrl_fact con ticker, FY (los dos en comparativas) y concepto, o concepto de valor idéntico."""
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
        if c == concepto or (not hueco and v is not None and v == valor_xbrl(ticker, f, concepto)):   # GOOGL FY2024
            vistos.add(f)
    return fys <= vistos

def evaluar_trayectoria(tool_calls: list[dict], p: dict, resp: dict) -> dict:
    """(c) = recall de herramientas 1 ∧ argumentos ok. Sin deduplicar: las repetidas y las bloqueadas cuentan."""
    tcs = [tc for tc in tool_calls if tc["name"] in REALES]
    usadas = {tc["name"] for tc in tcs}
    req, por_defecto = _requisitos(p)
    tp = sum(bool(set(r) & usadas) for r in req)
    oblig = ["get_xbrl_fact"] in req                     # obligatoria; como alternativa (herramienta_alternativa) solo si se usó
    en_corpus = normalizar_ticker(p.get("ticker")) in {"NVDA", "MSFT", "AAPL", "GOOGL", "META", "AMZN"}
    args_ok = _args_xbrl_ok(tcs, p) if (oblig or "get_xbrl_fact" in usadas) and en_corpus else None
    c = (tp == len(req) and args_ok is not False) if req else None
    texto = bool(usadas & {"search_filings", "read_section"})
    coherencia = {"xbrl": "get_xbrl_fact" in usadas, "texto": texto,
                  "ambas": "get_xbrl_fact" in usadas and texto, "ninguna": True}.get(resp.get("fuente"))
    ref = [next((a for a in r if a in usadas), r[0]) for r in req]    # la alternativa usada, o la primera
    diag = metricas_trayectoria([tc for tc in tcs if tc["name"] != "list_available"], ref)
    return {"c": c, "c_recall": tp / len(req) if req else None, "c_args_ok": args_ok, "c_por_defecto": por_defecto,
            "coherencia_fuente": coherencia, "n_tools": len(tcs), **{f"tray_{k}": v for k, v in diag.items()}}

def enrutado(filas: list[dict]) -> dict:
    """P/R/F1 por herramienta (R15): TP = esperada y usada; FP = usada sin esperarse; FN = esperada y no usada."""
    cuenta = {}
    for f in filas:
        usadas = {tc["name"] for tc in f["tool_calls"]} & (REALES - {"list_available"})
        req, _ = _requisitos(f["golden"])
        esp = set().union(*[({a for a in r if a in usadas} or {r[0]}) for r in req]) - {"list_available"}
        for h in usadas | esp:
            c = cuenta.setdefault(h, {"tp": 0, "fp": 0, "fn": 0})
            c["tp" if h in usadas and h in esp else "fp" if h in usadas else "fn"] += 1
    for c in cuenta.values():
        c["precision"] = c["tp"] / (c["tp"] + c["fp"]) if c["tp"] + c["fp"] else None
        c["recall"] = c["tp"] / (c["tp"] + c["fn"]) if c["tp"] + c["fn"] else None
        c["f1"] = c["tp"] / (c["tp"] + (c["fp"] + c["fn"]) / 2) if c["tp"] + c["fp"] + c["fn"] else None
    return cuenta
```

- La trayectoria es la de `ejecutar()`: `tool_calls` de la invocación (hilo nuevo, D05), con lista blanca (fuera la tool sintética
  `RespuestaFinanciera`) y **sin deduplicar**. Generaliza el assert de la celda 29 (una `tool_call` con `name == "get_xbrl_fact"`) a
  `herramienta_esperada` [notebook S1 · celda 29].
- **Camino equivocado = fallo**: una cifra correcta leída de la prosa da `b` ✓ pero `c` ✗ y el acierto cae [enunciado · §1] (probado).
  Los argumentos cazan además la confusión de concepto (META FY2024 caja frente a R&D, 0,04 %) y la de año; en los huecos se exige el
  concepto exacto. Solo se miran si `get_xbrl_fact` es obligatoria o se usó, y nunca fuera de las 6 empresas: el hueco de una empresa
  fuera del corpus (`get_xbrl_fact` con alternativa `list_available`, [10 §5](10_skill_golden_set.md)) aprueba (c) solo con `list_available`
  (test de §10).
- `tray_*` (exact, in_order, precisión, redundancia, eficiencia) y `coherencia_fuente` (p. ej., `fuente="xbrl"` sin `get_xbrl_fact`) son
  diagnóstico: no sabemos qué exigirá el evaluador del 24 más allá de los nombres [enunciado · §7]. `enrutado()` alimenta la diapositiva de
  enrutado exacto/difuso (R15); por familia, se filtran las filas antes.

## 5. Paso 4: evaluador (a), etapa 1 determinista (D13)

```python
# agente10k/evaluadores.py · parte 4: (a) etapa 1
_ELISION = re.compile(r"\s*(?:\[\.\.\.\]|\.\.\.|…)\s*")

def _piezas(cita: str | None) -> list[str]:
    return [normalizar(x) for x in _ELISION.split(cita or "") if normalizar(x)]   # cada trozo, literal

def etapa1_cita(resp: dict, p: dict, observaciones: list[dict]) -> dict:
    """existe (secciones del ticker/FY de la respuesta) ∧ vista (ToolMessage de esta trayectoria); chunk_id_ok diagnostica."""
    piezas = _piezas(resp.get("cita"))
    if not piezas:
        return {"a_cita": False, "a_existe": False, "a_vista": False}
    ticker = normalizar_ticker(resp.get("ticker") or p.get("ticker"))
    fys = ({resp.get("ejercicio"), resp.get("ejercicio_base")} - {None}
           or {_fy(p), fy_base(p) if p.get("familia") == "comparativa" else None} - {None})   # si la respuesta no los trae
    fuente = " ".join(normalizar(texto_seccion(ticker, int(fy), it)) for fy in fys for it in ITEMS)
    vistas = " ".join(normalizar(o["content"]) for o in observaciones
                      if o.get("name") in ("search_filings", "read_section"))
    out = {"a_cita": True, "a_existe": all(x in fuente for x in piezas), "a_vista": all(x in vistas for x in piezas),
           "a_chunk_id_ok": bool(resp.get("chunk_id")) and all(x in normalizar(texto_chunk(resp["chunk_id"])) for x in piezas)}
    if not out["a_existe"]:
        out["a_cobertura"] = round(cobertura(resp["cita"], fuente), 3)   # ≥ 0,8: casi literal (normalización, no invención)
    if p.get("ancla_texto"):                                             # ¿citó la frase del golden? (diagnóstico R07)
        out["a_cita_ancla"] = round(cobertura(p["ancla_texto"], resp["cita"]), 3)
    return out
```

- **Existe** se busca en las secciones y no solo en el chunk citado: el `chunk_id` cambia al re-trocear [enunciado · §4.3] y una cita puede
  cruzar dos chunks. **Vista** usa el **contenido** de los `ToolMessage` de `search_filings` y `read_section`, que `ejecutar()` guarda en
  `observaciones`: ya trae el texto de los fragmentos, así que la anotación `-> str` del contrato no se toca (C17). Una cita que existe en el
  corpus pero el agente no vio viene de memoria o es inventada [17 §3.2](17_repo_generative_ai.md).
- Aprobar exige literal tras `normalizar()` (D07); `a_cobertura` solo separa "casi literal" de "inventada" (C07).

## 6. Paso 5: los jueces, con caché (D01, D02, D13, D14)

Dos jueces de **un solo criterio**: respaldo (etapa 2 de (a), frase a frase) y corrección (`correcta`). Mismo modelo que el agente a
`temperature=0` por defecto, configurable aparte (sugerencia `AGENTE10K_MODELO_JUEZ`, D01), con `create_agent(..., tools=[],
response_format=ToolStrategy(...))` y nunca `with_structured_output` (D02). Frente al SUPPORTS/REFUTES/NOT_ENOUGH_INFO de
[15 §3.5](15_repo_genai_labs.md): "todas `supported`" ≈ SUPPORTS, alguna `contradictory` ≈ REFUTES y alguna `unsupported` ≈
NOT_ENOUGH_INFO, pero por frase, así que una comparativa respaldada a medias suspende (C10).

```python
# agente10k/evaluadores.py · parte 5: jueces
import hashlib
from pathlib import Path
from typing import Literal
from langchain.agents import create_agent
from langchain.agents.structured_output import ToolStrategy
from langchain_core.callbacks import get_usage_metadata_callback
from pydantic import BaseModel, Field

VERSION_JUEZ = "v1"                          # subidla al tocar un prompt o un esquema: invalida la caché

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
    """Jueces con caché JSON. Un fallo de parseo devuelve None, se cuenta y no se cachea (se reintenta al re-puntuar)."""
    def __init__(self, modelo, modelo_id: str, ruta_cache="resultados/cache/juez.json"):
        self.modelo_id, self.ruta = modelo_id, Path(ruta_cache)
        self.cache = json.loads(self.ruta.read_text(encoding="utf-8")) if self.ruta.is_file() else {}
        self.agentes = {t: create_agent(model=modelo, tools=[], system_prompt=pr, response_format=ToolStrategy(schema=esq))
                        for t, pr, esq in (("respaldo", PROMPT_RESPALDO, Veredicto), ("correccion", PROMPT_CORRECCION, Correccion))}
        self.llamadas, self.fallos, self.uso = 0, 0, {}

    def _preguntar(self, tipo: str, texto: str) -> dict | None:
        clave = hashlib.sha256(json.dumps([tipo, VERSION_JUEZ, self.modelo_id, texto]).encode()).hexdigest()
        if clave in self.cache:
            return self.cache[clave]
        salida = None
        with get_usage_metadata_callback() as cb:                       # coste del juez, aparte (D16)
            try:
                sr = self.agentes[tipo].invoke({"messages": [{"role": "user", "content": texto}]},
                                               config={"recursion_limit": 20}).get("structured_response")
                salida = sr.model_dump() if sr is not None else None
            except Exception:                                           # red, 400, recursión por reintentos de esquema
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
        etq = None if v is None else [e for e in v["etiquetas"] if e != "no_rad"]   # no_rad fuera del denominador
        return None if etq is None else bool(etq) and all(e == "supported" for e in etq)

    def correcta(self, pregunta, respuesta, referencia, ancla=None) -> bool | None:
        v = self._preguntar("correccion", f"PREGUNTA: {pregunta}\nREFERENCIA: {referencia}\n"
                                          f"ANCLA: {ancla or '-'}\nRESPUESTA: {respuesta}")
        return None if v is None else bool(v["valida"])

    def guardar(self) -> None:
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        self.ruta.write_text(json.dumps(self.cache, ensure_ascii=False, indent=1), encoding="utf-8")
```

- **Coste.** Estimación propia ⚠️: ~600 tokens de entrada (prompt, esquema de la tool y textos) y ~150 de salida por llamada ≈ 0,001 USD con
  los precios de [01 §4]; con 14 extractivas y comparativas y hasta 2 llamadas, ≈ 0,03 USD por tanda. Se mide con el callback y va en
  `resumen["juez"]`, **fuera** del coste medio por pregunta (D16). Con la caché, re-puntuar cuesta 0 llamadas (probado).
- El juez de respaldo solo corre si pasa la etapa 1, y el de corrección solo si puede cambiar el acierto ((a) y (c) ya en verde).

## 7. Paso 6: abstención (d), acierto por familia y agregados (D11, D14)

```python
# agente10k/evaluadores.py · parte 6: una fila y los agregados
# metricas_abstencion(filas) -> cobertura, acierto_condicionado, tasa_alucinacion, abstencion_correcta/indebida, score -> 17 §3.9
FAMILIAS = ("numerica", "extractiva", "comparativa", "hueco")

def acierto(s: dict) -> bool | None:
    """D14. None = no evaluable (familia desconocida, sin referencia o puntuado sin juez)."""
    f, c = s.get("familia"), s.get("c") is True
    if f == "numerica":
        return s.get("b") is True and c
    if f == "hueco":
        return bool(s.get("abstiene") and s.get("sin_cifra") and c)
    if f in ("extractiva", "comparativa"):
        if s.get("a") is None or s.get("correcta_ok") is None:
            return None
        return bool(s["a"] and c and s["correcta_ok"] and (f == "extractiva" or s.get("b") is True))
    return None

def puntuar_fila(fila: dict, juez=None) -> dict:
    """Una fila de predicciones.jsonl -> una de puntuaciones.jsonl."""
    p, resp = fila["golden"], fila["respuesta"]
    familia = "sin_referencia" if sin_referencia(p) else "hueco" if es_hueco(p) else p.get("familia")
    s = {"id": fila["id"], "familia": familia, **evaluar_cifra(resp, p),
         **evaluar_trayectoria(fila["tool_calls"], p, resp), **etapa1_cita(resp, p, fila.get("observaciones", []))}
    s.update(abstiene=resp.get("fuente") == "ninguna", sin_cifra=resp.get("cifra") is None,
             hay_dato=familia not in ("hueco", "sin_referencia"))
    s["abstencion_indebida"] = s["abstiene"] and s["hay_dato"]                 # falso "ninguna" (D11)
    s.update(a=None, a_respalda=None, correcta=None, correcta_ok=None, juez_fallo=False)
    if familia in ("extractiva", "comparativa") and juez is not None:
        etapa1 = s["a_existe"] and s["a_vista"]
        if etapa1:
            s["a_respalda"] = juez.respalda(resp["cita"], resp.get("respuesta"))
            s["juez_fallo"] = s["a_respalda"] is None                           # cuenta como fallo de (a)
        s["a"] = bool(etapa1 and s["a_respalda"])
        if not p.get("respuesta_esperada"):
            s["correcta_ok"] = True                                             # sin referencia: no aplica
        elif s["a"] and s["c"]:
            s["correcta"] = juez.correcta(p.get("pregunta"), resp.get("respuesta"), p["respuesta_esperada"], p.get("ancla_texto"))
            s["juez_fallo"] = s["juez_fallo"] or s["correcta"] is None
            s["correcta_ok"] = s["correcta"] is True
        else:
            s["correcta_ok"] = False                                            # ya falla: no se gasta la llamada
    if ancla := normalizar(p.get("ancla_texto")):                               # recall dentro del agente (D08)
        s["recall_agente"] = ancla in " ".join(normalizar(o["content"]) for o in fila.get("observaciones", [])
                                               if o.get("name") == "search_filings")
    s["acierto"] = acierto(s)
    return s

def resumen_aciertos(punt: list[dict]) -> dict:
    """k/n por familia; micro = aciertos/preguntas; macro = media de las familias presentes ('—', nunca 0)."""
    fam = {f: [x["acierto"] for x in punt if x.get("familia") == f and x.get("acierto") is not None] for f in FAMILIAS}
    con = [v for v in fam.values() if v]
    todas = [a for v in con for a in v]
    return {"familias": {f: f"{sum(v)}/{len(v)}" if v else "—" for f, v in fam.items()},
            "micro": sum(todas) / len(todas) if todas else None,
            "macro": sum(sum(v) / len(v) for v in con) / len(con) if con else None}

def recall_desde_rankings(preguntas: list[dict], rankings: dict, ks=(1, 3, 5, 10)) -> dict:
    """Modo aislado (D08): un único top-20 por pregunta, recortado a cada k. Estricto: substring normalizado."""
    pos = []
    for p in (q for q in preguntas if q.get("ancla_texto")):
        a = normalizar(p["ancla_texto"])
        pos.append(next((i for i, t in enumerate(rankings.get(p["id"], []), 1) if a in normalizar(t)), None))
    n = len(pos)
    out = {f"recall@{k}": f"{sum(1 for x in pos if x and x <= k)}/{n}" for k in ks}
    out["mrr@10"] = round(sum(1 / x for x in pos if x and x <= 10) / n, 3) if n else None
    return out

def sensibilidad(punt: list[dict]) -> dict:
    """Micro con 0 / 0,1 / 0,5 / 1 % en USD, re-puntuando sin ejecutar (D06). La de 0,5 % debe ser igual a 'micro'."""
    return {f"{t} %": resumen_aciertos([dict(x, acierto=acierto(dict(x, b=x.get(f"b_tol{t}", x.get("b")))))
                                        for x in punt])["micro"] for t in (0, 0.1, 0.5, 1)}
```

- **(d) abstención:** `abstencion_indebida` por fila (el profesor pide detectar cuándo el agente "te ha dicho que no había respuesta cuando
  sí que había" [transcripcion_10sep · 02:29]) y, en el resumen, `metricas_abstencion` de [17 §3.9](17_repo_generative_ai.md). Los huecos
  van en `golden_huecos.jsonl` con su propia etiqueta (`final_huecos`, D11); la abstención indebida sale de las 20 con dato.
- Un fallo de parseo del juez deja (a) en falso, marca `juez_fallo` y se suma en el resumen: nunca se descarta en silencio, como hace
  `rate_batch` [17 §3.2](17_repo_generative_ai.md). `correcta` existe porque (a) mide si la cita respalda la respuesta, **no** si la
  respuesta contesta a la pregunta (D14).
- **Sensibilidad (D06):** con 0 % caen las respuestas redondeadas ("$391 billion"); de 0,5 % a 1 % no debería cambiar nada; si cambia, alguna
  cifra está en el límite y hay que mirarla.

## 8. Paso 7: `evaluar()` y `puntuar()` (D05, D16–D20)

```python
# agente10k/api.py (SUGERENCIA; junto a ejecutar() y responder() de 08 §7)
import datetime as dt
import os
import statistics
import subprocess
import uuid
import pandas as pd
# from agente10k.config import SISTEMA, MODELO_ID, MODELO_JUEZ_ID, PRECIOS, crear_modelo_juez   -> 08 §2 (D01, D19, D24)
# from agente10k.retrieval import calentar, top20_sistema     -> 24: la función del paso de la escalera que usa el sistema
# agente_sistema() = agente_final() o el baseline de construir_baseline(), según SISTEMA          -> 08 §6-7 (D21)
RESULTADOS = Path(os.environ.get("AGENTE10K_RESULTADOS", "resultados"))

def _leer_jsonl(ruta: Path) -> list[dict]:
    with open(ruta, encoding="utf-8") as f:
        return [json.loads(x) for x in f if x.strip()]

def _escribir_jsonl(ruta: Path, filas: list[dict], modo: str = "w") -> None:
    with open(ruta, modo, encoding="utf-8") as f:
        f.writelines(json.dumps(x, ensure_ascii=False, default=str) + "\n" for x in filas)

def _commit() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, timeout=10).stdout.strip() or "sin_git"
    except Exception:
        return "sin_git"                                                     # clon descargado como ZIP

def evaluar(ruta_jsonl: str, etiqueta: str | None = None) -> pd.DataFrame:
    """R10: ejecuta cada pregunta con un hilo nuevo, guarda las predicciones y puntúa. Una pregunta rota no para la tanda."""
    etiqueta = etiqueta or os.environ.get("AGENTE10K_ETIQUETA") or f"{SISTEMA}_{Path(ruta_jsonl).stem}"
    carpeta = RESULTADOS / etiqueta
    carpeta.mkdir(parents=True, exist_ok=True)
    preguntas, agente = cargar_preguntas(ruta_jsonl), agente_sistema()
    calentar()                                                               # FAISS, bge y BM25 sin LLM (D17)
    meta = {"sistema": SISTEMA, "modelo": MODELO_ID, "commit": _commit(),
            "fecha": dt.datetime.now().isoformat(timespec="seconds"), "fichero": str(ruta_jsonl)}
    ruta_pred, rankings = carpeta / "predicciones.jsonl", []
    ruta_pred.write_text("", encoding="utf-8")
    for i, p in enumerate(preguntas, 1):                                     # en secuencia y siempre en el mismo orden
        tid = f"{etiqueta}-{p['id']}-{uuid.uuid4().hex[:8]}"                 # D05: nunca se reutiliza
        try:
            r = ejecutar(agente, str(p.get("pregunta") or ""), tid)          # no lanza (08 §7)... pero por si acaso
        except Exception as e:
            r = {"respuesta": RespuestaFinanciera(**FALLBACK), "error": f"{type(e).__name__}: {e}",
                 "tool_calls": [], "n_llamadas": 0, "observaciones": []}
        fila = {"id": p["id"], "familia": p.get("familia"), "pregunta": p.get("pregunta"), **meta,
                **{k: v for k, v in r.items() if k != "respuesta"}, "respuesta": r["respuesta"].model_dump(), "golden": p}
        _escribir_jsonl(ruta_pred, [fila], modo="a")                         # fila a fila: un corte no pierde lo hecho
        if p.get("ancla_texto"):                                             # recall@k aislado, si aplica (D08)
            try:
                rankings.append({"id": p["id"], "top20": [d["texto"] for d in top20_sistema(p["pregunta"])]})
            except Exception as e:
                rankings.append({"id": p["id"], "top20": [], "error": repr(e)})
        print(f"[{i}/{len(preguntas)}] {p['id']}: fuente={fila['respuesta']['fuente']} · {r.get('error') or 'ok'}")
    _escribir_jsonl(carpeta / "rankings.jsonl", rankings)
    return puntuar(etiqueta)

def puntuar(etiqueta: str, juez=None, con_juez: bool = True) -> pd.DataFrame:
    """Ejecutar ≠ puntuar (D19): todo sale de predicciones.jsonl; el juez, de la caché. Reescribe puntuaciones y resumen."""
    carpeta = RESULTADOS / etiqueta
    filas = _leer_jsonl(carpeta / "predicciones.jsonl")
    if juez is None and con_juez:
        juez = Juez(crear_modelo_juez(), MODELO_JUEZ_ID, RESULTADOS / "cache" / "juez.json")
    punt = []
    for fila in filas:
        try:
            s = puntuar_fila(fila, juez)
        except Exception as e:                                               # un evaluador roto no tumba la tanda
            s = {"id": fila["id"], "familia": fila.get("familia"), "acierto": False, "error_puntuar": repr(e)}
        s.update({k: fila.get(k) for k in ("n_llamadas", "llamadas_modelo", "usd", "latencia_s", "error", "r05")})
        punt.append(s)
    if juez is not None:
        juez.guardar()
    _escribir_jsonl(carpeta / "puntuaciones.jsonl", punt)
    rk = {r["id"]: r["top20"] for r in _leer_jsonl(carpeta / "rankings.jsonl")} if (carpeta / "rankings.jsonl").is_file() else {}
    lat = [x["latencia_s"] for x in punt if x.get("latencia_s") is not None]
    media = lambda xs: statistics.fmean(xs) if xs else None
    ra = [x["recall_agente"] for x in punt if x.get("recall_agente") is not None]
    evaluables = [x for x in punt if x.get("acierto") is not None]
    resumen = {
        "etiqueta": etiqueta, **{k: (filas[0].get(k) if filas else None) for k in ("sistema", "modelo", "commit", "fecha", "fichero")},
        "n": len(punt), **resumen_aciertos(punt), **(recall_desde_rankings([f["golden"] for f in filas], rk) if rk else {}),
        "recall_agente": f"{sum(ra)}/{len(ra)}" if ra else "—",
        "usd_medio": media([x["usd"] for x in punt if x.get("usd") is not None]),
        "latencia_media_s": media(lat), "latencia_mediana_s": statistics.median(lat) if lat else None,
        "llamadas_media": media([x["n_llamadas"] for x in punt if x.get("n_llamadas") is not None]),
        "tasa_fallo": sum(bool(x.get("error")) for x in punt) / len(punt) if punt else None,
        "abstencion": metricas_abstencion(evaluables) if evaluables else None,
        "sensibilidad_micro": sensibilidad(punt), "enrutado": enrutado(filas),
        "juez_fallos_filas": sum(bool(x.get("juez_fallo")) for x in punt),
        "juez": None if juez is None else {"modelo": MODELO_JUEZ_ID, "llamadas": juez.llamadas, "fallos": juez.fallos,
                                           "usd": usd(juez.uso, PRECIOS)},                  # aparte del coste medio
    }
    (carpeta / "resumen.json").write_text(json.dumps(resumen, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    pct = lambda v: "—" if v is None else f"{v:.0%}"
    print(f"\n== {etiqueta} · {resumen['sistema']} · {resumen['modelo']} ==\naciertos: "
          + " · ".join(f"{f} {v}" for f, v in resumen["familias"].items()) + f" · micro {pct(resumen['micro'])} · macro "
          f"{pct(resumen['macro'])} · recall@5 {resumen.get('recall@5', '—')} · USD/pregunta {resumen['usd_medio']} · latencia "
          f"media {resumen['latencia_media_s']} s · llamadas {resumen['llamadas_media']} · fallos {pct(resumen['tasa_fallo'])}")
    return pd.DataFrame(punt)
```

- **Cada fila de `predicciones.jsonl`** lleva lo que devuelve `ejecutar()` (respuesta con `model_dump`, `tool_calls`, `n_llamadas`,
  `llamadas_modelo`, `uso`, `usd`, `usd_openrouter`, `latencia_s`, `error`, `r05`, `observaciones`), más `sistema`, `modelo`, `commit`, `fecha`
  y la pregunta completa (`golden`). Así `puntuar()` no necesita ni el JSONL original ni el agente (BYOD, [17 §3.1](17_repo_generative_ai.md)).
  `observaciones` pesa (una `read_section`, hasta ~140.000 caracteres): es el precio de poder recalcular "vista".
- **recall@k si aplica:** `rankings.jsonl` guarda el top-20 aislado de cada pregunta con ancla, calculado con la función del paso que usa
  el sistema en la escalera de [11](11_skill_mejora_retrieval.md) (paso 0 en el baseline, paso 3 en el final), y `puntuar()` recorta @1/3/5/10
  y MRR@10. `recall_agente` es el diagnóstico dentro del agente (D08).
- **Etiquetas (D19):** sin etiqueta, `f"{SISTEMA}_{stem}"`. Con `golden_propio.jsonl` el *stem* da `final_golden_propio`: pasad la etiqueta
  explícita (`baseline_golden`, `baseline_huecos`, `final_golden`, `final_huecos`) como en [13 §3–§4](13_skill_medicion_informe_presentacion.md), porque
  `generar()` busca esas (y avisa si falta alguna); `ciegas.jsonl` → `final_ciegas` sí sale sola. `SISTEMA` vale `"baseline"` en
  el commit `baseline-v1` y `"final"` después; los resultados del baseline se regeneran desde su etiqueta git. `puntuar("baseline_golden")`
  re-puntúa el baseline congelado con el evaluador actual sin ejecutarlo (R12); `con_juez=False` da una vista rápida sin LLM (extractivas y
  comparativas quedan "no evaluables"). La tabla baseline frente a final se genera desde los `resumen.json` en [13](13_skill_medicion_informe_presentacion.md).
- **CLI:** `agente10k/__main__.py` con `evaluar(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)` → `python -m agente10k ruta.jsonl`.
  Mejor que un módulo `agente10k/evaluar.py`, que se llamaría igual que la función que exporta el paquete.

## 9. Paso 8: validar a los jueces antes de fiarse (D13)

1. **Pares.** `golden/juez_respaldo.jsonl` con 30–40 filas `{"cita", "respuesta", "humano": 0|1, "tipo"}`, mitad y mitad, para que el kappa
   sea informativo. Positivos: pares reales de la ejecución del baseline y algunos escritos a mano. Negativos construidos: cifra alterada (un
   dígito o ×1.000), año cambiado, cita de otra pregunta, cita que menciona el tema sin la cifra y comparativa con una sola mitad respaldada
   [17 §3.2](17_repo_generative_ai.md). Para `correcta`, unos 20 pares `{"pregunta", "referencia", "respuesta", "humano"}` con un "no está"
   falso, escala ×1.000, otro FY, unidad cambiada y paráfrasis correctas.
2. **Etiquetado humano.** Dos personas del grupo etiquetan por separado y resuelven los desacuerdos, **antes** de mirar al juez.
3. **Medir** con el código de abajo: acuerdo, kappa, matriz de confusión, falsos positivos del juez (aprueba lo que el humano suspende: el
   error caro) y sin parsear.
4. **Criterio (propuesta propia):** κ ≥ 0,6, como mucho 2 falsos positivos en 40 y 0 sin parsear. Si no se cumple, se ajusta el prompt, se sube
   `VERSION_JUEZ` y se repite con pares **nuevos** (ajustar contra los mismos también es sobreajuste). Si sigue bajo, otro modelo de juez
   (auto-preferencia, [06 §6](06_teoria_evaluacion_llms.md)).
5. **Guardar** el resultado en `resultados/tablas/validacion_juez.md`: va al informe como garantía de (a).

```python
# agente10k/evaluadores.py · parte 7: validar al juez (sklearn no está en el stack: kappa en Python puro)
from collections import Counter

def kappa(h: list[int], j: list[int]) -> float:
    """Kappa de Cohen sin ponderar, etiquetas 0/1 [17 §3.2; generative-ai · ET/evaluate_autorater.ipynb · celda 25]."""
    n = len(h)
    po = sum(a == b for a, b in zip(h, j)) / n
    ch, cj = Counter(h), Counter(j)
    pe = sum(ch[k] * cj[k] for k in set(h) | set(j)) / n ** 2
    return (po - pe) / (1 - pe) if pe < 1 else 1.0

def validar_juez(pares: list[dict], decidir) -> dict:
    """decidir(par) -> bool | None, p. ej. lambda x: juez.respalda(x['cita'], x['respuesta'])."""
    pred = [decidir(x) for x in pares]
    ok = [(int(x["humano"]), int(v)) for x, v in zip(pares, pred) if v is not None]
    m = Counter(ok)                                                           # (humano, juez)
    return {"n": len(ok), "sin_parsear": len(pares) - len(ok),
            "acuerdo": sum(a == b for a, b in ok) / len(ok) if ok else None,
            "kappa": kappa([a for a, _ in ok], [b for _, b in ok]) if ok else None,
            "matriz": {"h1_j1": m[(1, 1)], "h1_j0": m[(1, 0)], "h0_j1": m[(0, 1)], "h0_j0": m[(0, 0)]}, "fp_juez": m[(0, 1)],
            "fallos_por_tipo": dict(Counter(x.get("tipo") for x, v in zip(pares, pred) if v is not None and int(v) != int(x["humano"])))}
```

Con 32 positivos de 40, un juez que siempre aprueba tiene un 80 % de acuerdo y κ = 0 ([06 §6](06_teoria_evaluacion_llms.md)).

## 10. Paso 9: tests sin LLM ni red

```python
# tests/test_evaluadores.py (SUGERENCIA) · pytest, sin LLM ni red; usa el parquet y las secciones reales
from types import SimpleNamespace
# from agente10k.evaluadores import puntuar_fila, kappa, resumen_aciertos, fy_base

def juez(r=True, c=True):                          # juez falso: respalda y corrige lo que se le diga
    return SimpleNamespace(respalda=lambda *a: r, correcta=lambda *a: c)

def tc(concepto, fy=2025, ticker="NVDA"):
    return {"name": "get_xbrl_fact", "args": {"ticker": ticker, "fiscal_year": fy, "concept": concepto}}

def fila(p, resp, tcs, obs=()):
    return {"id": p["id"], "golden": p, "respuesta": resp, "tool_calls": tcs, "observaciones": list(obs)}

def num(i, t, fy, c, v):
    return {"id": i, "familia": "numerica", "ticker": t, "fiscal_year": fy, "concept_xbrl": c, "cifra_esperada": v,
            "herramienta_esperada": ["get_xbrl_fact"]}

BPA, BUSQ = num("t1", "NVDA", 2025, "EarningsPerShareBasic", 2.97), {"name": "search_filings", "args": {"query": "EPS"}}
EXT = {"id": "t2", "familia": "extractiva", "ticker": "MSFT", "fiscal_year": 2025, "herramienta_esperada": ["search_filings"],
       "ancla_texto": "Our AI systems offer users powerful tools and capabilities.", "respuesta_esperada": "Uso indebido de la IA."}
CITA = {"respuesta": "Avisa del uso indebido de su IA.", "fuente": "texto", "ticker": "MSFT", "ejercicio": 2025,
        "cita": "Our AI systems offer users powerful  tools and capabilities."}           # doble espacio: normaliza
OBS = {"name": "search_filings", "content": "[MSFT-2025-1A-0004] Our AI systems offer users powerful tools and capabilities."}

def test_bpa_y_camino_equivocado():
    assert puntuar_fila(fila(BPA, {"cifra": 2.97, "unidad": "USD/shares", "fuente": "xbrl"}, [tc("EarningsPerShareBasic")]))["acierto"]
    assert not puntuar_fila(fila(BPA, {"cifra": 3.0, "fuente": "xbrl"}, [tc("EarningsPerShareBasic")]))["b"]    # fallo 8 de 01 §5
    assert not puntuar_fila(fila(BPA, {"cifra": 2.94, "fuente": "xbrl"}, [tc("EarningsPerShareBasic")]))["b"]   # el diluido
    s = puntuar_fila(fila(BPA, {"cifra": 2.97, "fuente": "texto"}, [BUSQ]))
    assert s["b"] and not s["c"] and not s["acierto"]                        # bien, pero por la prosa

def test_concepto_confundido_y_equivalente():
    s = puntuar_fila(fila(num("t3", "META", 2024, "ResearchAndDevelopmentExpense", 43873e6), {"cifra": 43889e6, "fuente": "xbrl"},
                          [tc("CashAndCashEquivalentsAtCarryingValue", 2024, "META")]))
    assert s["b"] and s["c_args_ok"] is False and not s["acierto"]           # 0,04 %: solo (c) lo caza
    g = num("t4", "GOOGL", 2024, "Revenues", 350018e6)
    rc = "RevenueFromContractWithCustomerExcludingAssessedTax"
    assert puntuar_fila(fila(g, {"cifra": 350018e6, "fuente": "xbrl"}, [tc(rc, 2024, "Alphabet")]))["acierto"]

def test_hueco_falso_ninguna_y_agregados():
    h = dict(num("t5", "AMZN", 2024, "GrossProfit", None), hueco=True)
    assert puntuar_fila(fila(h, {"fuente": "ninguna"}, [tc("GrossProfit", 2024, "AMZN")]))["acierto"]
    assert not puntuar_fila(fila(h, {"fuente": "ninguna"}, []))["acierto"]  # "ninguna" sin mirar XBRL
    s = puntuar_fila(fila(BPA, {"fuente": "ninguna"}, [tc("EarningsPerShareBasic")]))
    assert s["abstencion_indebida"] and not s["acierto"]
    r = resumen_aciertos([{"familia": "numerica", "acierto": True}, {"familia": "numerica", "acierto": False},
                          {"familia": "extractiva", "acierto": True}])
    assert r["familias"]["comparativa"] == "—" and r["micro"] == 2 / 3 and r["macro"] == 0.75
    assert kappa([1] * 32 + [0] * 8, [1] * 40) == 0.0

def test_hueco_fuera_del_corpus():                  # 10 §5: basta list_available, sin mirar argumentos de get_xbrl_fact
    t = dict(num("t7", "TSLA", 2025, "Revenues", None), hueco=True, herramienta_alternativa={"get_xbrl_fact": ["list_available"]})
    s = puntuar_fila(fila(t, {"fuente": "ninguna"}, [{"name": "list_available", "args": {}}]))
    assert s["c"] is True and s["c_args_ok"] is None and s["acierto"]

def test_cita_existe_vista_y_juez():
    assert puntuar_fila(fila(EXT, CITA, [BUSQ], [OBS]), juez())["acierto"]
    s = puntuar_fila(fila(EXT, CITA, [BUSQ], []), juez())                    # existe, pero el agente no la vio
    assert s["a_existe"] and not s["a_vista"] and not s["acierto"]
    s = puntuar_fila(fila(EXT, CITA, [BUSQ], [OBS]), juez(r=None))           # fallo de parseo del juez
    assert s["juez_fallo"] and s["a"] is False and not s["acierto"]
    assert puntuar_fila(fila(EXT, CITA, [BUSQ], [OBS]), None)["acierto"] is None   # sin juez: no evaluable

def test_comparativa_sin_campos_extra_y_sin_deduplicar():
    c = {"id": "t6", "familia": "comparativa", "ticker": "NVDA", "fiscal_year": 2025, "concept_xbrl": "Revenues",
         "cifra_esperada": 130497e6, "ancla_texto": "x", "herramienta_esperada": ["get_xbrl_fact", "search_filings"]}
    assert fy_base(c) == 2024                                                 # como en las ciegas
    s = puntuar_fila(fila(c, {"cifra": 130497e6, "cifra_base": 60922e6, "fuente": "ambas"}, [tc("Revenues"), tc("Revenues"), BUSQ]))
    assert s["b"] and s["b_con_base"] and s["c_args_ok"] is False            # falta la get_xbrl_fact de FY2024
    assert s["tray_redundantes"] == 1 and s["n_tools"] == 3                   # la repetida cuenta
```

Probado así, con un `valor_xbrl` y unas secciones de juguete con los valores reales de [02 §5](02_datos_corpus_y_xbrl.md): los seis tests,
`evaluar()` de principio a fin con `ejecutar()` simulado (ficheros de D19, ids repetidos, una pregunta que lanza `401`, re-puntuación sin
llamadas al juez) y `Juez` con el modelo falso de [08 §12](08_skill_agente_salida_estructurada.md) (`ToolStrategy` con `tools=[]` devuelve
`structured_response`). La prueba con la API real es `evaluar()` sobre 2 preguntas en un clon limpio ([13](13_skill_medicion_informe_presentacion.md)).

## 11. Las 10 ciegas sin tocar código (R10)

El día 24, en el commit `final-v1`: `python -m agente10k ciegas.jsonl` (o `from agente10k import evaluar; evaluar("ciegas.jsonl")`), que
escribe `resultados/final_ciegas/` e imprime el resumen. Protocolo del aula y delta frente al golden: [13](13_skill_medicion_informe_presentacion.md).
No sabemos el formato exacto ⚠️; esto es lo que ya aguanta el código:

| Si las ciegas… | Qué pasa |
| --- | --- |
| traen solo los campos oficiales | todo con `.get`; en comparativas, FY base = el otro de {2024, 2025} y su cifra sale del parquet |
| no traen `herramienta_esperada` | (c) usa la lista por familia (`c_por_defecto=True`; se dice en el informe) |
| traen `herramienta_esperada` sin `herramienta_alternativa` | (c) exige cada nombre tal cual, como el evaluador del profesor; las alternativas solo existen en nuestro golden (D12) |
| traen un hueco | `es_hueco` lo detecta (concepto inexistente o numérica sin cifra) y se puntúa como hueco |
| no traen ancla | no hay recall@k ("—") |
| traen una familia nueva o no traen respuestas | `acierto=None`, se cuenta aparte; las predicciones se guardan igual |
| traen `fiscal_year` como texto o ids repetidos | `int()` y sufijo `#2` |
| una pregunta revienta | *fallback* (D04), `error` en su fila y se sigue |

Ensayo antes del 23: alguien que no escribió el golden redacta 10 preguntas con **solo** los campos oficiales (una de ellas un hueco y otra
sin ancla) y se ejecutan en un clon limpio sin editar nada.

## 12. Trampas

1. Buscar la cita solo en el chunk citado (falla al re-trocear) o llamar al juez sin la etapa 1 (se cree citas inventadas).
2. Dejar `no_rad` en el denominador: suspende respuestas correctas con frases de relleno.
3. Descartar los fallos de parseo del juez, o cachear sin versión del prompt: al cambiarlo se reutilizan veredictos viejos.
4. Deduplicar la trayectoria o contar la tool sintética `RespuestaFinanciera` (C26, D12).
5. Tolerancia relativa en el BPA, o comparar cifras como cadenas ("60,922" frente a "60922").
6. Reutilizar `thread_id`: la trayectoria de una pregunta arrastra la anterior (D05).
7. Re-ejecutar el baseline para re-puntuarlo: se usa `puntuar()`. Ejecutarlo otra vez solo sirve para medir el ruido.
8. Leer campos con `p["…"]`: `KeyError` con las ciegas.
9. Familia vacía como 0 en la macro, coste del juez dentro del coste medio o recall laxo en la tabla (C07).

## Checklist de hecho

- [ ] **R09 (a):** etapa 1 (`existe` en secciones, `vista` en `observaciones`) y etapa 2 (juez frase a frase); sin cita o sin parseo = fallo.
- [ ] **R09 (a):** jueces validados (30–40 pares; ~20 para `correcta`): κ, matriz, FP y sin parsear en `resultados/tablas/validacion_juez.md`.
- [ ] **R09 (b):** la misma `cifra_ok` que R05; tolerancia escrita en el informe (USD 0,5 % relativa, BPA 0,005 absoluta) y sensibilidad.
- [ ] **R09 (c):** recall de herramientas + argumentos de `get_xbrl_fact`, sin deduplicar; la cifra leída de la prosa sale como fallo (test).
- [ ] **R14:** abstención correcta en `final_huecos` e indebida en las 20, en el resumen.
- [ ] **R10:** `evaluar(ruta)` corre en un clon limpio sin editar nada (2 preguntas de humo + 10 "ciegas simuladas" con solo los campos oficiales).
- [ ] **R11:** `resumen.json` con aciertos k/n por familia, micro y macro, recall@5, USD/pregunta, latencia media y mediana y llamadas/pregunta.
- [ ] **R12:** `puntuar(etiqueta)` regenera `puntuaciones.jsonl` y `resumen.json` sin llamar al agente (y, con la caché, sin llamar al juez).
- [ ] Tests de §10 en verde sin red. Revisar tras el 17 cómo plantea el profesor sus `uso_la_tool_correcta` y `cita_correcta`
  [notebook S1 · celda 28; miax_s1.py · formatear_fragmentos()].

## Fuentes

- [enunciado · §1, §4.3, §4.5, §5, §7] (`00_enunciado.md`); [01_requisitos_y_contratos.md](01_requisitos_y_contratos.md) R09–R12, R14 y §5.
- Notebook S1, celdas 28–29 (`pretty_trace` y el assert de trayectoria) y 32 (`validar()`); `golden_set_ejemplo.jsonl` (ej-002, ancla de los tests).
- [transcripcion_10sep · 02:29] (evaluadores como "minifunciones" y falsos "ninguna").
- [16_repo_transformers_labs.md](16_repo_transformers_labs.md) §3.1–3.4 y §3.6; [17_repo_generative_ai.md](17_repo_generative_ai.md) §3.1
  (`metricas_trayectoria`, enrutado, BYOD), §3.2 (juez frase a frase, validación, `rate_batch`) y §3.9 (`metricas_abstencion`);
  [15_repo_genai_labs.md](15_repo_genai_labs.md) §3.5 (juez de tres etiquetas).
- generative-ai · `ET/evaluate_groundedness_with_custom_parsing.ipynb` (celdas 22, 24), `ET/evaluate_agent_final_answer_with_custom_parsing.ipynb`
  (celda 24), `ET/evaluate_autorater.ipynb` (celdas 21, 25), `ET/evaluating_langgraph_agent.ipynb` (celdas 44, 71–73).
- [api_stack · create_agent, structured_output.ToolStrategy, langchain.messages.ToolMessage]; `get_usage_metadata_callback` (langchain-core 1.6.1, venv).
- Docs hermanos: [02](02_datos_corpus_y_xbrl.md) §5, [06](06_teoria_evaluacion_llms.md), [08](08_skill_agente_salida_estructurada.md) §7 y §12,
  [09](09_skill_guardrails_middleware_xbrl.md) §4, [10](10_skill_golden_set.md) §4–6, [11](11_skill_mejora_retrieval.md),
  [13](13_skill_medicion_informe_presentacion.md).
- Notas de trabajo (no versionadas): `C2_evaluacion_llms.md`, `D3_evaluacion_agentes.md`, `D12_retrieval_rag_grounding.md`, `A5_slides_rag.md`
  y el mapa de cobertura (D05, D06, D08, D11–D20; C06, C07, C10, C14, C17, C26).
