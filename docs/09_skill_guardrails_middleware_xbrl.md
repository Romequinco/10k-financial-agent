# Skill: guardrails, límite de llamadas y middleware de verificación XBRL

> Requisitos: R04, R05, R14 · Lee antes: [08_skill_agente_salida_estructurada.md](08_skill_agente_salida_estructurada.md),
> [05_teoria_agentes_react_tools.md](05_teoria_agentes_react_tools.md), [15_repo_genai_labs.md](15_repo_genai_labs.md) §3.1–3.4,
> [16_repo_transformers_labs.md](16_repo_transformers_labs.md) §3.2–3.3 y [17_repo_generative_ai.md](17_repo_generative_ai.md) §3.5

> Fuentes: `00_enunciado.md` §4.2, `01_requisitos_y_contratos.md`, notebook S1 (celdas 12, 21 y 23), docs 14–17, `api_stack_langchain.md`,
> `perfil_dataset.md` y las decisiones comunes D04, D06, D07, D11, D15 y D16 del mapa de cobertura (nota interna).

**v1.0 · 12-sep-2026.** Los guardrails del sistema final como piezas comprobables: límites (R04), verificador determinista de cifras contra
`xbrl_facts.parquet` (R05) y abstención ante huecos (R14), con tests sin LLM. El montaje está en [08](08_skill_agente_salida_estructurada.md).
Marcas: **(probado)** = ejecutado en el venv del stack con `GenericFakeChatModel`, sin red (API y flujo, no cómo reacciona Gemini);
**(venv)** = introspección; ⚠️ = sin verificar. Módulos `agente10k/…`: **SUGERENCIA**.

## 1. Qué protege cada guardrail

| Guardrail | Contra qué | Dónde actúa | Si salta |
| --- | --- | --- | --- |
| `ToolCallLimitMiddleware(run_limit=8)` | Bucle de herramientas (celda 23) | Tras cada llamada al modelo | Bloquea la llamada con un aviso y el modelo sigue |
| `ToolCallLimitMiddleware(tool_name="read_section", run_limit=2)` | Leer secciones enteras sin freno (hasta 34.751 tokens cada una) | Ídem, solo `read_section` | Ídem |
| `ModelCallLimitMiddleware(run_limit=12, exit_behavior="end")` | Un modelo que ignora el aviso | Antes de cada llamada al modelo | Termina sin `structured_response`: *fallback* del arnés |
| `recursion_limit=100` + `try/except` (arnés, también en el baseline) | Todo lo demás | `ejecutar()` de [08](08_skill_agente_salida_estructurada.md) | `GraphRecursionError` capturado, *fallback* y causa en `error` |
| `VerificadorXBRL` (R05) | Cifras mal copiadas, escaladas, de otro año o sacadas de la prosa | Tras la respuesta estructurada | 1 reintento con el desajuste; si sigue mal, abstención |
| Herramientas + prompt (R14) | Estimar un dato que no existe o que está fuera del corpus | `get_xbrl_fact` ("no reportó…") y `SYSTEM` | `fuente="ninguna"`, sin bloquear la pregunta |
| `max_retries=2` de `ChatOpenRouter` | Errores de red | Cliente HTTP | Si se agotan, excepción y *fallback* |

Todo es código determinista: el crítico LLM que "verifica la corrección de las cifras" no es reproducible
[generative-ai · gemini/orchestration/intro_langgraph_gemini.ipynb · celda 21] [17 §3.5](17_repo_generative_ai.md).

## 2. Paso 1: la pila de límites (R04, D04)

Firmas reales (venv): `ToolCallLimitMiddleware(*, tool_name=None, thread_limit=None, run_limit=None, exit_behavior='continue')` y
`ModelCallLimitMiddleware(*, thread_limit=None, run_limit=None, exit_behavior='end')` [api_stack · ToolCallLimitMiddleware; ModelCallLimitMiddleware].
`run_limit` cuenta por invocación y `thread_limit` acumula en el hilo; con un hilo por pregunta, `run_limit` es lo que importa.

| Configuración | Qué pasa (probado) | `structured_response` |
| --- | --- | --- |
| `ToolCallLimit` con `"continue"` | La llamada que excede recibe el `ToolMessage` "Tool call limit exceeded. Do not make additional tool calls." y el grafo sigue. Si el modelo insiste, **nada lo para** salvo otro límite | Se rellena si el modelo acaba respondiendo |
| `ToolCallLimit` con `"end"` | Termina con un `AIMessage` "Tool call limit reached: …" sin avisar antes al modelo | `None` si aún no había respondido |
| `ToolCallLimit` con `"error"` | Lanza `ToolCallLimitExceededError` [api_stack · ToolCallLimitMiddleware] | — |
| `ModelCallLimit(12, "end")` | Un modelo que siempre pide tools: 12 llamadas al modelo, 12 tool calls y un `AIMessage` de aviso | `None` → *fallback* |

- **Por qué así:** `continue` deja al modelo rendirse con `fuente="ninguna"`; `ModelCallLimit` es el corte duro si no lo hace
  [14 §5, matiz 2](14_clase_pistas_del_profesor.md) [17 §3.5](17_repo_generative_ai.md). `read_section=2` permite la misma sección de dos FY.
- **Pasos de grafo:** con los cuatro middleware cada vuelta cuesta unos 6–7 *supersteps*: `recursion_limit=50` cortaría en la 7.ª llamada,
  antes que `ModelCallLimit`; con 100 actúa `ModelCallLimit`. Sin middleware son unos 2 por vuelta: el baseline se corta tras 50 tool calls
  (probado). El valor por defecto de langgraph es 10007 (venv).
- **Qué cuenta:** cada tool call, también las paralelas (con `run_limit=1` y dos llamadas en un mensaje, se bloquea la segunda), y **también la
  tool sintética `RespuestaFinanciera`**: tras 8 llamadas reales la respuesta es la 9.ª y aparece un "limit exceeded" detrás de "Returning
  structured response", pero la respuesta se conserva con `"continue"` y con `"end"` (probado). Las llamadas bloqueadas siguen en `tool_calls`
  y cuentan (D18); la sintética no (lista blanca, [08 §7](08_skill_agente_salida_estructurada.md)).

```python
# agente10k/middleware.py (SUGERENCIA)
from typing import NotRequired

from langchain.agents.middleware import (AgentMiddleware, AgentState, ModelCallLimitMiddleware,
                                         ToolCallLimitMiddleware, hook_config, wrap_tool_call)
from langchain.messages import HumanMessage, ToolMessage

# from agente10k.normalizacion import cifra_ok, en_cita, normalizar_ticker, parse_cifras   -> §4


def pila_middleware(verificador=None, con_sin_repetir: bool = False) -> list:
    """D04: la misma pila en todas las ejecuciones evaluadas del sistema final."""
    pila = [ToolCallLimitMiddleware(run_limit=8),                          # R04 ("continue")
            ToolCallLimitMiddleware(tool_name="read_section", run_limit=2),
            ModelCallLimitMiddleware(run_limit=12, exit_behavior="end")]   # corte duro
    if con_sin_repetir:
        pila.append(sin_repetir)                                           # opcional, §3
    if verificador is not None:
        pila.append(verificador)                                           # R05, §5
    return pila
```

## 3. Paso 2: bucles y llamadas repetidas (opcional, mejora medida)

La causa raíz del bucle de la celda 23 es que la herramienta no deje claro que el dato no existe; el límite es la red de seguridad
[17 §3.5](17_repo_generative_ai.md). El mensaje "no reportó … No lo estimes ni lo calcules" es cosa de [07](07_skill_herramientas_docstrings.md).
Si aun así el modelo repite, `sin_repetir` intercepta la ejecución (`wrap_tool_call` recibe `request.tool_call` y `request.state`
[api_stack · ToolCallRequest]):

```python
def _firma(tc) -> tuple:
    a = dict(tc["args"])
    if "ticker" in a:
        a["ticker"] = normalizar_ticker(a["ticker"])
    try:
        a["fiscal_year"] = int(a["fiscal_year"])
    except (KeyError, TypeError, ValueError):
        pass
    return tc["name"], tuple(sorted((k, str(v)) for k, v in a.items()))


@wrap_tool_call
def sin_repetir(request, handler):
    """No reejecuta una llamada idéntica (args normalizados) a otra ya respondida."""
    tc, msgs = request.tool_call, request.state["messages"]
    respondidas = {m.tool_call_id for m in msgs if isinstance(m, ToolMessage)}
    previas = {_firma(t) for m in msgs for t in (getattr(m, "tool_calls", None) or [])
               if t["id"] in respondidas}
    if _firma(tc) in previas:
        return ToolMessage(content="Llamada repetida: ya tienes ese resultado más arriba. Si el "
                                   "dato no existe, responde con fuente='ninguna'.",
                           tool_call_id=tc["id"], name=tc["name"])
    return handler(request)
```

Mejora sobre el de [15 §3.2](15_repo_genai_labs.md): compara argumentos normalizados (`"nvda"` = `"NVDA"`, `"2024"` = `2024`) y solo contra
llamadas **ya respondidas**; con el original, dos llamadas idénticas en el mismo mensaje se bloquean la una a la otra y no se ejecuta ninguna
(probado ambos). Entra en el final solo si baja llamadas o coste sin tocar aciertos. Diagnóstico: `redundantes` en la trayectoria (D12).

## 4. Paso 3: extraer y comparar cifras (D06, D07)

`normalizar()` y `cifra_ok()` se copian **sin cambios** de [16 §3.2 y §3.3](16_repo_transformers_labs.md) (probados; el signo menos `"−"`, si se
añade, va en esa única `_TRAD`: no hay otra copia de `normalizar`, D07). Una sola `cifra_ok` para R05 y el evaluador (b) de [12](12_skill_evaluadores.md): USD al 0,5 % relativo, BPA a
0,005 absoluto, hueco si `cifra is None`, reescalado por palabras de escala ("billones" fuera) y `error_escala` a ×10^±3/6/9 (D06). Lo nuevo:

```python
# agente10k/normalizacion.py (SUGERENCIA; continúa tras normalizar() y cifra_ok() de 16 §3.2-3.3)
import math
import re

ALIAS = {"GOOG": "GOOGL", "ALPHABET": "GOOGL", "GOOGLE": "GOOGL", "FACEBOOK": "META",
         "NVIDIA": "NVDA", "MICROSOFT": "MSFT", "APPLE": "AAPL", "AMAZON": "AMZN"}


def normalizar_ticker(t) -> str:          # UNA definición, la misma que usan las tools (07)
    t = str(t or "").strip().upper()
    return ALIAS.get(t, t)


_NUM = re.compile(r"(?<![\w.,])(\d{1,3}(?:[.,]\d{3})+(?:[.,]\d+)?|\d+(?:[.,]\d+)?)")
_ESC = re.compile(r"\s*(miles de millones|mil millones|billones|billions?|millones|mill[oó]n"
                  r"|millions?|thousand|miles|bn\b|mm\b|m\b|b\b)")
_FACTOR = {"miles de millones": 1e9, "mil millones": 1e9, "billones": 1e12,  # 10^12: la trampa
           "billion": 1e9, "billions": 1e9, "bn": 1e9, "b": 1e9, "millones": 1e6, "millon": 1e6,
           "millón": 1e6, "million": 1e6, "millions": 1e6, "mm": 1e6, "m": 1e6,
           "thousand": 1e3, "miles": 1e3}
_PCT = re.compile(r"\s*(%|por ciento|percent|puntos porcentuales|pp\b)")
_MONEDA = re.compile(r"\$|usd|d[oó]lar")
_BPA = re.compile(r"por acci[oó]n|per share|/acci[oó]n|/share|\bbpa\b|\beps\b")
_ANO = re.compile(r"(19|20)\d\d")


def _a_float(s: str) -> float:
    if "," in s and "." in s:                                    # el último separador es el decimal
        dec = "," if s.rfind(",") > s.rfind(".") else "."
        return float(s.replace("." if dec == "," else ",", "").replace(dec, "."))
    for sep in ",.":
        if sep in s:
            partes = s.split(sep)
            if len(partes) > 2 or (len(partes[-1]) == 3 and partes[0] != "0"):
                return float(s.replace(sep, ""))                 # 60,922 · 60.922.000 -> miles
            return float(s.replace(sep, "."))                    # 2,97 · 2.97 · 14,9 -> decimal
    return float(s)


def parse_cifras(texto: str | None) -> list[dict]:
    """Importes en USD y BPA de la prosa (ES/EN). Los % salen con tipo '%' (solo diagnóstico)."""
    t, cifras = normalizar(texto), []
    for m in _NUM.finditer(t):
        num, antes, despues = m.group(1), t[max(0, m.start() - 25):m.start()], t[m.end():m.end() + 40]
        negativo = (antes.endswith("(") and despues.startswith(")")) or antes.endswith("-")
        despues = despues[1:] if despues.startswith(")") else despues   # (1.234) millones
        if _PCT.match(despues):
            cifras.append({"valor": _a_float(num), "tipo": "%", "texto": num})
            continue
        esc = _ESC.match(despues)
        cola = despues[esc.end():esc.end() + 15] if esc else despues[:8]
        moneda = bool(_MONEDA.search(antes[-8:] + " " + cola))
        bpa = bool(_BPA.search(antes + " " + despues[:25])) and not esc
        if not (moneda or esc or bpa) or despues.startswith((":", "-k")):
            continue                                             # "Item 7", "10:1", "10-K"...
        if _ANO.fullmatch(num) and not (moneda or esc):
            continue                                             # años, aunque haya "BPA" cerca
        valor = _a_float(num) * (_FACTOR[esc.group(1)] if esc else 1.0)
        cifras.append({"valor": -valor if negativo else valor,
                       "tipo": "USD/shares" if bpa else "USD", "texto": num})
    return cifras


def en_cita(valor: float, cita: str | None) -> bool:
    """¿Aparece `valor` como número en la cita (con su escala, o de tabla en miles/millones)?"""
    t = normalizar(cita)
    cands = [c["valor"] for c in parse_cifras(t) if c["tipo"] != "%"]
    cands += [_a_float(n) * f for n in _NUM.findall(t) for f in (1, 1e3, 1e6, 1e9)]
    return any(math.isclose(valor, c, rel_tol=0.005, abs_tol=0.005) for c in cands)
```

Qué extrae (probado): "60.922 millones de dólares" y "$60,922 million" → 60.922·10⁶; "$391 billion" → 391·10⁹; "391 billones de dólares" →
391·10¹² (`error_escala`); "2,97 USD por acción (12,05 en FY2024)" → dos BPA; "(1.234) millones" → negativo; "14,9 %" → tipo `%`; años, "Item 7",
"10:1" y "10-K" → nada. **Límites:** en "de 245.122 a 281.724 millones" solo sale la segunda; sin moneda, escala ni "por acción" no se extrae
nada; tres decimales tras una coma ("0,125" aparte) se leen como miles.

La verdad sale del parquet, con la misma búsqueda que usan `get_xbrl_fact` ([07](07_skill_herramientas_docstrings.md)) y el evaluador (b):

```python
# agente10k/datos.py (SUGERENCIA) · columnas: ticker, cik, fiscal_year, concept, value, unit, period_end, form
# cargar_corpus() -> 02 §7: ruta configurable, SHA-256 y alineación comprobados (D25)
_, _, _xbrl = cargar_corpus()
_IDX = {(r.ticker, int(r.fiscal_year), r.concept): (float(r.value), r.unit) for r in _xbrl.itertuples(index=False)}
valor_xbrl = lambda ticker, fy, concept: _IDX.get((ticker, fy, concept))           # (valor, unidad) | None
hechos = lambda ticker, fy: [(c, v, u) for (t, f, c), (v, u) in _IDX.items() if (t, f) == (ticker, fy)]
```

## 5. Paso 4: el `VerificadorXBRL` (R05, D15)

Evoluciona el de [15 §3.4](15_repo_genai_labs.md) (probado): cambia la tolerancia única del 0,5 % por `cifra_ok`, añade las cifras de la
prosa, `cifra_base`, la política de `fuente="texto"`, la degradación y un registro.

```python
MARCA = "[VERIFICADOR XBRL]"
TEXTO_DEGRADADA = ("No he podido verificar la cifra contra los datos XBRL del 10-K, "
                   "así que prefiero no darla.")
INSTRUCCION = (" Corrige: copia el valor exacto de get_xbrl_fact, sin escalar y con unidad 'USD' o "
               "'USD/shares' (en comparativas, cifra = ejercicio reciente y cifra_base = el anterior; "
               "la variación, solo en la prosa), o llama a get_xbrl_fact con el concepto correcto. "
               "Si el dato no existe: fuente='ninguna' y cifra=null. No estimes.")


class EstadoR05(AgentState):
    r05: NotRequired[dict]            # registro de la invocación; sale en resultado["r05"]


class VerificadorXBRL(AgentMiddleware):
    """R05: contrasta las cifras de la respuesta con xbrl_facts, sin LLM."""

    state_schema = EstadoR05

    def __init__(self, valor_xbrl, hechos, max_reintentos: int = 1):
        super().__init__()
        self.valor_xbrl = valor_xbrl  # (ticker, fy, concept) -> (valor, unidad) | None
        self.hechos = hechos          # (ticker, fy) -> [(concept, valor, unidad)]
        self.max_reintentos = max_reintentos

    def verdad(self, mensajes) -> list[tuple]:
        """V: el valor del parquet de cada get_xbrl_fact de la invocación, por sus args."""
        V = []
        for a in (t["args"] for m in mensajes for t in (getattr(m, "tool_calls", None) or [])
                  if t["name"] == "get_xbrl_fact"):
            try:
                clave = (normalizar_ticker(a["ticker"]), int(a["fiscal_year"]), str(a["concept"]).strip())
            except (KeyError, TypeError, ValueError):
                continue
            r = self.valor_xbrl(*clave)
            if r is not None and (*clave, *r) not in V:
                V.append((*clave, *r))                # (ticker, fy, concept, valor, unidad)
        return V

    def revisar(self, resp, mensajes) -> dict:
        V = self.verdad(mensajes)
        pares = [(a, b) for a in V for b in V if a[0] == b[0] and a[2] == b[2] and a[1] < b[1]]
        concepto = getattr(resp, "concept_xbrl", None)
        fy_base = getattr(resp, "ejercicio_base", None)
        items = [("cifra", resp.cifra, resp.unidad, resp.ejercicio),
                 ("cifra_base", getattr(resp, "cifra_base", None), resp.unidad, fy_base)]
        prosa = parse_cifras(resp.respuesta)
        items += [("respuesta", c["valor"], "USD", None) for c in prosa if c["tipo"] != "%"]
        problemas, citadas = [], []
        for campo, valor, unidad, fy in items:
            if valor is None:
                continue
            # si hay hechos del mismo FY (y concepto), solo esos: caza años cruzados y básico/diluido
            cand = [v for v in V if (fy is None or v[1] == fy)
                    and (campo == "respuesta" or not concepto or v[2] == concepto)] or V
            if any(cifra_ok(valor, unidad, v[3], v[4])["ok"] for v in cand):
                continue
            if campo == "respuesta" and any(cifra_ok(valor, "USD", abs(b[3] - a[3]), "USD")["ok"]
                                            for a, b in pares if a[4] == "USD"):
                continue                                  # variación entre dos hechos consultados
            sin_llamar = self._en_parquet(resp, valor, unidad, {resp.ejercicio, fy_base})
            if sin_llamar:
                problemas.append(f"{campo}={valor:,.2f} coincide con {sin_llamar}, pero no has "
                                 "llamado a get_xbrl_fact con ese concepto: llámalo y usa su valor.")
            elif resp.fuente in ("texto", "ambas") and en_cita(valor, resp.cita):
                citadas.append(valor)                     # no_verificable_xbrl_citada: pasa
            else:
                problemas.append(self._describir(campo, valor, unidad, cand))
        pct = [{"valor": c["valor"],
                "ok": any(abs(abs(c["valor"]) - abs((b[3] - a[3]) / a[3] * 100)) <= 0.05
                          for a, b in pares if a[3])}
               for c in prosa if c["tipo"] == "%"]        # % derivados: solo se anotan
        return {"problemas": problemas, "pct": pct, "no_verificable_xbrl_citada": citadas}

    def _en_parquet(self, resp, valor, unidad, fys):
        ticker = normalizar_ticker(resp.ticker) if resp.ticker else None
        for fy in sorted(f for f in fys if f) if ticker else []:
            for c, v, u in self.hechos(ticker, fy):
                if cifra_ok(valor, unidad, v, u)["ok"]:
                    return f"{ticker} FY{fy} {c}"
        return None

    @staticmethod
    def _describir(campo, valor, unidad, cand) -> str:
        if not cand:
            return (f"{campo}={valor:,.2f} no está respaldada: no has llamado a get_xbrl_fact "
                    "o no devolvió ningún valor.")
        pistas = []
        for t, fy, c, v, u in cand:
            motivo = cifra_ok(valor, unidad, v, u).get("motivo", "")
            pistas.append(f"{t} FY{fy} {c} = {v:,.2f} {u}"
                          + (f" (¿escala? {motivo})" if "escala" in motivo else ""))
        return (f"{campo}={valor:,.2f} ({unidad or 'sin unidad'}) no coincide con ningún hecho "
                "consultado: " + "; ".join(pistas) + ".")

    @hook_config(can_jump_to=["model"])
    def after_model(self, state, runtime):
        resp = state.get("structured_response")
        if resp is None:                  # el modelo pidió tools: aún no hay respuesta
            return None
        mensajes = state["messages"]
        registro = self.revisar(resp, mensajes)
        problemas = registro["problemas"]
        previos = sum(isinstance(m, HumanMessage) and MARCA in str(m.content) for m in mensajes)
        registro.update(reintentos=previos, degradada=False)
        if not problemas:
            return {"r05": registro}
        if previos < self.max_reintentos:             # 1 reintento: el desajuste vuelve al modelo
            registro["reintentos"] = previos + 1
            return {"messages": [HumanMessage(f"{MARCA} " + " ".join(problemas) + INSTRUCCION)],
                    "jump_to": "model", "r05": registro}
        registro["degradada"] = True                  # sigue mal: se degrada a abstención
        abstencion = type(resp)(respuesta=TEXTO_DEGRADADA, fuente="ninguna",
                                ticker=resp.ticker, ejercicio=resp.ejercicio)
        return {"structured_response": abstencion, "r05": registro}
```

- **API** (probado): `after_model(self, state, runtime)` devuelve actualizaciones del estado y `@hook_config(can_jump_to=["model"])` habilita
  `"jump_to"` [api_stack · AgentMiddleware.after_model; hook_config]. Con `ToolStrategy` el hook ve `structured_response` en la misma pasada
  en que el modelo responde; tras el salto, si el modelo pide una tool, llega como `None`. Devolver `{"structured_response": …}` sin salto
  sustituye la respuesta final (secuencia `AI → Tool → Human[MARCA] → AI → Tool`). La clave `r05` de `state_schema` sale en el resultado de
  `invoke` y `ejecutar()` la guarda.
- **V por los argumentos, no por el `ToolMessage`:** el texto de `get_xbrl_fact` cambia entre versiones [demo_traza · paso 3; notebook S1 ·
  celda 12], y el modelo puede responder en el mismo mensaje que la llamada, antes de que exista el `ToolMessage` (probado).
- **1 reintento y degradar** (D15): el tope evita el bucle crítico→editor sin contador
  [generative-ai · gemini/orchestration/langgraph_multi-agent-rag-and-self-correction.ipynb · celda 18]. La abstención conserva `ticker` y
  `ejercicio` y pasa el validador; en una numérica puntúa como fallo (mejor que una cifra inventada, pero no es acierto).
- **Solo en el final.** Cada reintento es otra llamada con todo el historial: entra en el coste (D16). Al informe van `r05.reintentos` y
  `r05.degradada` por pregunta.

## 6. Unidades, comparativas y qué hacer cuando no se puede verificar

| Caso | Qué hace el verificador (probado) |
| --- | --- |
| `cifra=60922` con `unidad="USD"` / con `unidad="millones de USD"` (verdad 60.922.000.000) | Desajuste con pista `error_escala 1e6` / pasa (reescala) |
| BPA `3.0` frente a 2,97 (NVDA FY2025); diluido 6,08 con solo el básico (6,11) consultado | Desajuste (0,03 > 0,005); es el fallo 8 del notebook [01 §5] |
| Básico y diluido consultados, `concept_xbrl` dice cuál | Solo cuenta ese concepto: 6,08 con `EarningsPerShareBasic` es desajuste |
| GOOGL FY2024: consulta `Revenues`, responde con el otro concepto de revenue | Pasa: mismo valor [perfil_dataset · xbrl_facts.parquet] |
| Comparativa: `cifra` (FY reciente) y `cifra_base` (FY base) | Cada una contra los hechos de su FY; años cruzados → desajuste |
| Variación en la prosa ("+36.602 millones") | Pasa si es la diferencia entre dos hechos consultados del mismo concepto |
| "14,9 %" en la prosa | Se recalcula con V y se anota en `r05.pct` (`ok` a ±0,05 pp); nunca bloquea |
| Hueco (AMZN `GrossProfit`) con `fuente="ninguna"` y sin cifras / con un importe inventado en la prosa | Pasa / desajuste → reintento → abstención |
| Cifra igual a un hecho del parquet que no se consultó (p. ej. `fuente="texto"` copiando el revenue de la prosa) | Desajuste: "llama a get_xbrl_fact con ese concepto" (acertar por el camino equivocado es fallo [01 §2]) |
| Importe que no es XBRL (p. ej. por segmento), con `fuente="texto"` y literal en la cita | Pasa como `no_verificable_xbrl_citada` |
| Sin `get_xbrl_fact` y sin cita que lo contenga | Desajuste: "no está respaldada" |

**Split de NVDA:** se verifican los valores reportados de cada FY (12,05 y 2,97); que la respuesta explique el split lo mira el juez de
corrección de [12](12_skill_evaluadores.md), no R05. **Margen bruto u otros % de un hueco:** R05 no los bloquea (solo anota los %); el juez de
corrección y la métrica de abstención de [12](12_skill_evaluadores.md) son los que lo penalizan (D11, D14).

## 7. Paso 5: tests sin LLM ni red

Con un extracto real del parquet en un diccionario y el modelo falso de [08 §12](08_skill_agente_salida_estructurada.md) (`Falso`,
`GenericFakeChatModel` con `bind_tools` que devuelve `self`). Todos pasan en el venv del stack (probado).

```python
# tests/test_verificador.py (SUGERENCIA) · pytest
from langchain.agents import create_agent
from langchain.agents.structured_output import ToolStrategy
from langchain.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver

# from agente10k.esquemas import RespuestaFinanciera; from agente10k.middleware import VerificadorXBRL, pila_middleware
# from agente10k.normalizacion import parse_cifras; from tests.test_agente import Falso  (+ una @tool get_xbrl_fact de juguete)
HECHOS = {("NVDA", 2024, "Revenues"): (60_922_000_000.0, "USD"),                  # [perfil_dataset]
          ("NVDA", 2025, "EarningsPerShareBasic"): (2.97, "USD/shares"),
          ("AAPL", 2024, "EarningsPerShareBasic"): (6.11, "USD/shares"), ("AAPL", 2024, "EarningsPerShareDiluted"): (6.08, "USD/shares"),
          ("GOOGL", 2024, "Revenues"): (350_018e6, "USD"),
          ("GOOGL", 2024, "RevenueFromContractWithCustomerExcludingAssessedTax"): (350_018e6, "USD")}
V05 = VerificadorXBRL(lambda t, f, c: HECHOS.get((t, f, c)),
                      lambda t, f: [(c, *v) for (a, b, c), v in HECHOS.items() if (a, b) == (t, f)])


def problemas(resp, *consultas):          # trayectoria mínima: un AIMessage con los get_xbrl_fact
    msgs = [AIMessage(content="", tool_calls=[{"name": "get_xbrl_fact", "id": f"c{i}", "args": dict(
        zip(("ticker", "fiscal_year", "concept"), q))} for i, q in enumerate(consultas)])]
    return V05.revisar(resp, msgs)["problemas"]


def R(**kw):
    return RespuestaFinanciera(**{"respuesta": "x", "fuente": "xbrl", **kw})


REV, BPA25 = ("NVDA", 2024, "Revenues"), ("NVDA", 2025, "EarningsPerShareBasic")
EPS = (("AAPL", 2024, "EarningsPerShareBasic"), ("AAPL", 2024, "EarningsPerShareDiluted"))


def test_casos_de_d15():
    assert problemas(R(cifra=60_922_000_000, unidad="USD"), REV) == []
    assert "escala" in problemas(R(cifra=60_922, unidad="USD"), REV)[0]           # millones vs unidades
    assert problemas(R(cifra=60_922, unidad="millones de USD"), REV) == []
    assert problemas(R(cifra=3.0, unidad="USD/shares"), BPA25)                     # 3 frente a 2,97
    assert problemas(R(cifra=6.08, unidad="USD/shares"), EPS[0])                   # diluido por básico
    assert problemas(R(cifra=6.08, unidad="USD/shares", ejercicio=2024,
                       concept_xbrl="EarningsPerShareBasic"), *EPS)
    assert problemas(R(cifra=350_018e6, unidad="USD", ticker="GOOGL", ejercicio=2024,
                       concept_xbrl="RevenueFromContractWithCustomerExcludingAssessedTax"),
                     ("GOOGL", 2024, "Revenues")) == []                            # concepto equivalente
    hueco = RespuestaFinanciera(respuesta="Amazon no reporta GrossProfit.", fuente="ninguna",
                                ticker="AMZN", ejercicio=2025)
    assert problemas(hueco, ("AMZN", 2025, "GrossProfit")) == []
    assert problemas(hueco.model_copy(update={"respuesta": "Unos 391 billones de dólares."}),
                     ("AMZN", 2025, "GrossProfit"))                               # importe inventado
    val = lambda s: [(round(c["valor"], 2), c["tipo"]) for c in parse_cifras(s)]
    assert val("El BPA fue de 2,97 USD por acción (12,05 en FY2024), tras el split 10:1.") == \
        [(2.97, "USD/shares"), (12.05, "USD/shares")]
    assert val("391 billones de dólares") == [(391e12, "USD")]                    # la trampa
    assert val("creció un 14,9 %") == [(14.9, "%")] and val("según el 10-K, Item 7") == []


def test_reintento_y_degradacion():                  # V3, con el agente y el modelo falso
    llamada = AIMessage(content="", tool_calls=[{"name": "get_xbrl_fact", "id": "c0",
                        "args": dict(zip(("ticker", "fiscal_year", "concept"), REV))}])
    final = lambda c, i: AIMessage(content="", tool_calls=[{"name": "RespuestaFinanciera", "id": f"s{i}",
        "args": {"respuesta": "x", "fuente": "xbrl", "cifra": c, "unidad": "USD", "ticker": "NVDA"}}])
    for segunda, degradada in [(60_922e6, False), (61_922e6, True)]:
        ag = create_agent(model=Falso(messages=iter([llamada, final(60_922, 1), final(segunda, 2)])),
                          tools=[get_xbrl_fact], response_format=ToolStrategy(schema=RespuestaFinanciera),
                          middleware=pila_middleware(V05), checkpointer=InMemorySaver())
        res = ag.invoke({"messages": [{"role": "user", "content": "q"}]},
                        config={"configurable": {"thread_id": "t"}, "recursion_limit": 100})
        assert res["r05"]["reintentos"] == 1 and res["r05"]["degradada"] is degradada
        assert (res["structured_response"].fuente == "ninguna") is degradada
```

Probados además: el corte por `ModelCallLimit`, `sin_repetir`, el reintento en que el modelo llama a `get_xbrl_fact` y luego acierta, y los
casos de §6 (comparativa con variación y %, años cruzados, segmento citado, revenue copiado de la prosa).

## 8. Entrada fuera del corpus, red y reintentos

- **Fuera del corpus** (TSLA, FY2023, el Santander de 2005 [transcripcion_10sep · 01:09]): no se bloquea, porque las ciegas son legítimas y un
  filtro por palabras falla con nombres de empresa. Lo cubren las herramientas (ticker o FY inválido → texto con los valores válidos,
  [07](07_skill_herramientas_docstrings.md)), `list_available` y el prompt ([08 §5](08_skill_agente_salida_estructurada.md)); se mide con la pregunta
  fuera de corpus de `golden_huecos.jsonl` ([10](10_skill_golden_set.md), D11). Un router LLM previo [17 §3.3](17_repo_generative_ai.md) es otra
  llamada por pregunta: solo como experimento.
- **Red:** `max_retries=2` de `ChatOpenRouter` (venv); `ModelRetryMiddleware(max_retries=2, …)` existe (venv) pero duplicaría reintentos. Nunca
  `ModelFallbackMiddleware`: cambia el modelo evaluado [14 §3](14_clase_pistas_del_profesor.md). Una excepción es un fallo de esa ejecución
  (*fallback* + `error`); si hubo errores de red, se repite la tanda entera, no solo las falladas. En clase hubo 400/401 desde Colab
  [transcripcion_10sep · 02:10–02:12]. Reintentos de R05 y avisos de límite reenvían el historial: entran en el coste (D16).

## 9. ⚠️ Por verificar con Gemini real

En la prueba de humo ([08 §10](08_skill_agente_salida_estructurada.md)) y en la primera ejecución del golden:

1. ¿Obedece el "Tool call limit exceeded" o sigue hasta `ModelCallLimit`? Contad los cortes.
2. ¿Corrige tras el `[VERIFICADOR XBRL]`? Reintentos que acaban bien frente a degradadas; leed esas trazas y, si no entiende qué corregir,
   mejorad `INSTRUCCION` en general, no pregunta a pregunta contra el golden.
3. ¿Falsos desajustes de `parse_cifras` con su forma real de escribir cifras? Revisad los `problemas` de las 20 primeras respuestas y pasad
   los casos nuevos a los tests.
4. ¿Responde en el mismo mensaje que una tool? El verificador lo soporta; anotadlo.

## 10. Cómo contarlo en la presentación ("qué guardrail os protege")

- **Antes/después de la celda 23:** baseline sin más tope que el arnés (hasta ~50 tool calls) frente a final que acaba con
  `fuente="ninguna"` en pocas llamadas o, en el peor caso, en el tope de 12 llamadas al modelo. Coste y latencia de las dos ejecuciones.
- **R05 con números:** respuestas corregidas, degradadas y un mensaje real (millones frente a unidades, o el "3" del BPA de NVDA).
- **Qué no cubre**, dicho claro: % y márgenes derivados, importes no XBRL sin cita, rangos en la prosa, y conceptos de valor casi igual (META
  FY2024: caja y R&D al 0,04 %) salvo con `concept_xbrl` o los argumentos que mira (c) [16 §3.3](16_repo_transformers_labs.md).
- **Abstención:** `abstencion_correcta` en los huecos y `abstencion_indebida` (falsos "ninguna") en las 20 [transcripcion_10sep · 02:29],
  incluido el efecto de las degradaciones de R05 ([12](12_skill_evaluadores.md), [13](13_skill_medicion_informe_presentacion.md)).

## 11. Trampas

1. `exit_behavior="end"` en el `ToolCallLimit` global: corta sin dejar que el modelo se rinda (sin respuesta si aún no había contestado).
2. `recursion_limit=50` con la pila completa corta antes que `ModelCallLimit`; sin arnés, el baseline tiene 10007 pasos.
3. Una tolerancia única del 0,5 %: 6,08 pasa por 6,11. Para el BPA, absoluta de 0,005 (D06).
4. Sacar la verdad del texto del `ToolMessage`: su formato cambia; se busca en el parquet por los `args`.
5. No arreglar antes el BPA redondeado de la tool: el modelo copiaría el "3" y R05 lo rechazaría [01 §5, fallo 8].
6. Reintentos sin tope, con otro modelo, o listar los huecos en `list_available` para "evitar el bucle" (arregla R04 a costa de (c), D22).
7. Dar por bueno el verificador sin tests: cada falso desajuste es un reintento pagado y, a veces, un acierto degradado.

## Checklist de hecho

- [ ] **R04** · El sistema final lleva la pila de D04; con el modelo falso que insiste, la ejecución termina por `ModelCallLimit` y el
      arnés devuelve el *fallback*; la celda 23 termina sola contra el baseline (por `recursion_limit=100`) y contra el final.
- [ ] **R04** · Las llamadas bloqueadas cuentan en llamadas/pregunta; la tool sintética no.
- [ ] **R05** · `VerificadorXBRL` extrae `cifra`, `cifra_base` y los importes de la prosa, los contrasta con el parquet mediante `cifra_ok`
      (la misma del evaluador b) y devuelve el desajuste al modelo con `jump_to="model"`; 1 reintento y luego abstención.
- [ ] **R05** · Tests de §7 en verde sin red: millones frente a unidades, 3 frente a 2,97, básico frente a diluido, hueco AMZN, GOOGL
      equivalente, "billones" y reintento/degradación con el agente.
- [ ] **R05** · Cada fila de resultados guarda `r05` (reintentos, degradada, problemas, %, citadas).
- [ ] **R14** · Un hueco termina con `fuente="ninguna"` y `cifra=None` sin estimar; la pregunta fuera de corpus también, sin bloqueo.
- [ ] Revisadas a mano las trazas con `r05.reintentos > 0` de la primera ejecución real (§9).

## Fuentes

- [enunciado · §4.2]: límite de llamadas y middleware que extrae las cifras y devuelve el desajuste al modelo.
- [01 §2, §4, §5](01_requisitos_y_contratos.md): R04, R05, R14; trampas 2, 3 y 5; fallo 8.
- [notebook S1 · celdas 12, 21, 23] y [transcripcion_10sep · 01:09, 02:10–02:12, 02:29], vía [14 §3 y §5](14_clase_pistas_del_profesor.md).
- [15 §3.1–3.4](15_repo_genai_labs.md); [16 §3.2–3.3](16_repo_transformers_labs.md); [17 §3.3, §3.5](17_repo_generative_ai.md);
  [generative-ai · gemini/orchestration/*] vía 33.
- [api_stack · ToolCallLimitMiddleware, ModelCallLimitMiddleware, AgentMiddleware.after_model, wrap_tool_call, hook_config, ToolCallRequest].
- [perfil_dataset · xbrl_facts.parquet]: valores de los tests y columnas del parquet.
- Pruebas propias en el venv del stack (modelo falso): límites y tool sintética, llamadas paralelas, `state_schema` en el resultado,
  `structured_response` tras el salto, reintento y degradación, `sin_repetir`, `parse_cifras` y los casos de §6. Decisiones comunes D04,
  D06, D07, D11, D15, D16 y D22.
