# Repo genai-labs: qué nos sirve para la práctica

> Origen: https://github.com/rafaelsf80/genai-labs (repo del profesor del módulo NLP). Copia local no versionada en docs/raw/repos/genai-labs-master/.

**v1.0 · 12-sep-2026.** Consolida las notas de trabajo B1 (`01-prompting/`) y B2 (resto del repo), contrastadas con los ficheros
originales y con el stack instalado. Los IDs `Rxx` remiten a [01_requisitos_y_contratos.md](01_requisitos_y_contratos.md).

Citas: `[genai-labs · <ruta> · celda N]` (celdas desde 0) o `· l. N`; `[api_stack · <sección>]` = `docs/raw/_texto/api_stack_langchain.md`;
`[enunciado · §N]` = `00_enunciado.md`; `[perfil_dataset · …]` = `docs/raw/_texto/perfil_dataset.md`. **(probado)** = ejecutado en
un venv con el stack de §4 y un modelo falso (`GenericFakeChatModel`, sin red): confirma API y flujo, no cómo se comporta Gemini.

## 1. Qué es y qué parte hemos revisado

Labs de IA generativa en cinco bloques: 01 prompting, 02 tuning, 03 infraestructura, 04 multimodal y 05 RAG [genai-labs · README.md · l. 11-81].
Varios requieren Vertex AI, traen `TODO` sin solución y el README marca como OBSOLETE los labs de LangChain y de "Ask Database" [genai-labs · README.md · l. 4, 6, 19-20].
**Revisado a fondo:** los seis notebooks de `01-prompting/`, `langchain/*.py`, `ask-database/*`, `05-rag/*.md` y `03-ai-infra/03-4-kvcache.ipynb`.
**Triaje:** `02-tuning/`, el resto de `03-ai-infra/` y `04-multimodal/`.
Ningún notebook revisado guarda outputs (0 celdas de código con salida en los seis de 01 ni en 03-4): no hay resultados que citar.
**Veredicto:** nos sirven las *lecciones* de 01-1/01-2/01-3 (grounding, ReAct, límite de pasos, verificador) y sus anti-ejemplos.
El código no se reutiliza: sus imports de LangChain antiguo fallan en nuestro stack (§4) y `05-rag/` no tiene código (§5).

## 2. Mapa de utilidad

Rutas desde la raíz del repo; `langchain/` y `ask-database/` cuelgan de `01-prompting/` (también en §4).

| Notebook / fichero | Qué enseña | Relevancia | Requisitos | Cómo reutilizarlo |
| --- | --- | --- | --- | --- |
| `01-prompting/01-3-react.ipynb` | ReAct Thought/Action/Observation a mano y automatizado (`wiki_react_chain`, `max_steps=7`); aviso de bucle infinito; variante de fact-checking SUPPORTS/REFUTES [celdas 5-9, 26-27, 32] | **Alta** (conceptual) | R04, R05, R09a, R14 | §3.1-3.5 |
| `01-prompting/01-2-external-tools.ipynb` | Tool use en dos llamadas: el LLM escribe la búsqueda, se ejecuta `wiki_tool` y el artículo se reinyecta [celdas 10-25] | Media | R08, R02 | Reescritura de la consulta (§3.7) |
| `01-prompting/01-1-cot.ipynb` | CoT few-shot; encaje exemplar-tarea; tablas; razonar y dejar el JSON al final; mide cada llamada con `perf_counter` [celdas 11, 18-36] | Media | R02, R03, R11, R14 | System prompt (§3.8), registro (§3.6) |
| `01-prompting/01-5-langgraph-react-agents.ipynb` | `create_react_agent` prebuilt con Wikipedia; entrada/salida `{"messages": [...]}` [celdas 5, 7] | Media | R01, R10, R13 | Antecesor de `create_agent`; claves (§3.9) |
| `01-prompting/langchain/agent-react.py` | Action space del paper ReAct (`Search`, `Lookup`) con descripciones vagas [l. 1-3, 13-24] | Media (anti-ejemplo) | R01, R02 | `Search`/`Lookup` ≈ `search_filings`/`read_section` (`get_xbrl_fact` es la vía exacta que el paper no tenía); qué NO poner en un docstring (§3.8) |
| `ask-database/ask-bigquery-sqlalchemy-gradio.py` | Text-to-SQL con reglas "solo columnas visibles", `LIMIT` y `return_intermediate_steps` [l. 55-93] | Media-baja | R02, R05 | Vocabulario cerrado; exponer pasos intermedios |
| `ask-database/ask-bigquery-gcplibrary-gradio.py` | DDL en el prompt, `temperature=0`, ejecuta la SQL del LLM sin validar [l. 24-80] | Baja | R02 | Anti-ejemplo: no ejecutar lo que genera el LLM |
| `langchain/chain-google-search.py` | `serpapi` + `llm-math` con la clave escrita en el código [l. 12-21] | Baja (anti-ejemplo) | R13 | §3.9 |
| `03-ai-infra/03-4-kvcache.ipynb` | GPT-2 con `use_cache=True/False`, 10 generaciones, media ± std [celda 3] | Baja | R11 | Patrón de medición de ruido (§3.6) |
| `01-prompting/01-4-langchain.ipynb`, `01-6-pandasai.ipynb` | Esqueletos casi todo en `TODO` (LCEL, memoria, loaders/FAISS; PandasAI) [01-4 · celdas 4-26; 01-6 · celdas 5-11] | Baja | — | Solo `prompt \| model` (§4) |
| `langchain/{model,chain,prompt-template,chain-with-reasoning,memory,agent}.py` | VertexAI text-bison, `LLMChain`, `ConversationChain`, Document AI | Baja | — | Solo tabla de equivalencias (§4) |
| `05-rag/*.md` | Tres enlaces externos, sin código [l. 1-3] | Nula en local | (R08: nada) | — |
| `02-tuning/`, resto de `03-ai-infra/`, `04-multimodal/` | Fine-tuning, cuantización, TPU/JAX/Ray, VAE/difusión/vídeo | Nula | — | — |

## 3. Patrones reutilizables traducidos a nuestro stack

### 3.1 Límite de pasos: de `max_steps` a middleware (R04)
Original: `wiki_react_chain(..., max_steps=7)` corta tras `max_steps` llamadas al LLM y devuelve `None` en silencio ("Would be
better to raise an exception") [genai-labs · 01-prompting/01-3-react.ipynb · celda 27]. El motivo: el LLM puede re-predecir
acciones anteriores y entrar en un bucle infinito [genai-labs · 01-prompting/01-3-react.ipynb · celda 26].

```python
from langchain.agents import create_agent
from langchain.agents.middleware import ToolCallLimitMiddleware
from langchain.chat_models import init_chat_model
from langgraph.checkpoint.memory import InMemorySaver
modelo = init_chat_model("openrouter:google/gemini-3.8-flash", temperature=0)
TOOLS = [list_available, get_xbrl_fact, search_filings, read_section]      # orden fijo
agente = create_agent(
    model=modelo,                          # la instancia, no la cadena [01_requisitos · §5, fallo 9]
    tools=TOOLS,
    system_prompt=SYSTEM,                  # vuestro prompt (§3.8)
    response_format=RespuestaFinanciera,   # o ToolStrategy(schema=RespuestaFinanciera)
    middleware=[ToolCallLimitMiddleware(run_limit=8),                             # global
                ToolCallLimitMiddleware(tool_name="read_section", run_limit=2)],  # opcional
    checkpointer=InMemorySaver(),
)
```
- Firma: `ToolCallLimitMiddleware(*, tool_name=None, thread_limit=None, run_limit=None, exit_behavior='continue')`; `run_limit`
  cuenta por invocación, `thread_limit` persiste en el hilo; `middleware=` es parámetro de `create_agent`
  [api_stack · ToolCallLimitMiddleware; create_agent]. `ToolStrategy` se importa de `langchain.agents.structured_output` (probado).
- `exit_behavior="continue"` (defecto): la llamada que excede no se ejecuta, el modelo recibe el `ToolMessage` "Tool call limit
  exceeded. Do not make additional tool calls." y sigue; `structured_response` se rellena. Con `"end"` termina con un `AIMessage`
  "Tool call limit reached: …" y **sin** `structured_response`: hace falta el fallback de §3.6 (probado ambos). `"error"` lanza
  `ToolCallLimitExceededError` [api_stack · ToolCallLimitMiddleware]. El límite global y el de `read_section` conviven (probado).
- `max_steps` cuenta llamadas **al LLM**: su equivalente literal es `ModelCallLimitMiddleware(run_limit=…)`
  [api_stack · ModelCallLimitMiddleware]. En clase se prevé `ToolCallLimitMiddleware(run_limit=8)` [01_requisitos · §4].

### 3.2 Detectar el bucle y recuperarse (R04, R14)
Original: el snippet solo corta, y el autor pide que el código de producción "catch the loop and attempt to recover"
[genai-labs · 01-prompting/01-3-react.ipynb · celda 26]. En `create_agent` va en un middleware `wrap_tool_call`, que recibe
`request.tool_call` y `request.state` [api_stack · decorador wrap_tool_call; ToolCallRequest].

```python
from langchain.agents.middleware import wrap_tool_call
from langchain.messages import ToolMessage

@wrap_tool_call
def sin_repetir(request, handler):
    tc = request.tool_call
    previas = [t for m in request.state["messages"]
               for t in (getattr(m, "tool_calls", None) or []) if t["id"] != tc["id"]]
    if any(t["name"] == tc["name"] and t["args"] == tc["args"] for t in previas):
        return ToolMessage(content="Llamada repetida: ya tienes ese resultado. Si el dato no existe, "
                                   "responde con fuente='ninguna'.", tool_call_id=tc["id"], name=tc["name"])
    return handler(request)
# middleware=[ToolCallLimitMiddleware(run_limit=8), sin_repetir]
```
- Probado: la repetición no se ejecuta y el modelo recibe el aviso. Sigue apareciendo en los `tool_calls` de la trayectoria,
  así que cuenta en "llamadas/pregunta" (R11). Es el caso del margen bruto de AMZN, sin `GrossProfit` [01_requisitos · §5, trampa 3].

### 3.3 El mismo bucle a mano, con tool calling nativo (R04)
Traducción pieza a pieza de `wiki_react_chain` [genai-labs · 01-prompting/01-3-react.ipynb · celda 27]; sirve para el bucle
`TODO` de la sesión 1, cuyos asserts pasan sin implementarlo [01_requisitos · §5, fallo 10].

```python
POR_NOMBRE = {t.name: t for t in TOOLS}
modelo_tools = modelo.bind_tools(TOOLS)

def bucle_manual(pregunta: str, max_vueltas: int = 8):  # max_steps; añadid la clave de §3.2
    msgs = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": pregunta}]
    for _ in range(max_vueltas):
        r = modelo_tools.invoke(msgs)                     # Thought + Action
        msgs.append(r)
        if not r.tool_calls:                              # sustituye a buscar "Answer["
            return r.text, msgs
        for tc in r.tool_calls:                           # Action -> Observation
            try:
                salida = str(POR_NOMBRE[tc["name"]].invoke(tc["args"]))
            except Exception as e:                        # el error vuelve al modelo
                salida = f"ERROR en {tc['name']}: {e}"
            msgs.append(ToolMessage(content=salida, tool_call_id=tc["id"], name=tc["name"]))
    raise RuntimeError("Límite de vueltas agotado")       # 01-3 devolvía None
```
Desaparece el parsing por texto (`splitlines()[1]`, `split("Answer[")`, `split(":")`, `<STOP>`), que falla si el modelo responde
en una sola línea (`IndexError`) o si la consulta lleva ":". Ojo al copiar de esa celda: su `call_llm` ignora `model` y usa
siempre `MODEL_GEMMA` [genai-labs · 01-prompting/01-3-react.ipynb · celda 27], y `max_output_tokens` nunca llega a
`GenerateContentConfig` [genai-labs · 01-prompting/01-3-react.ipynb · celdas 2-3]. (probado)

### 3.4 Verificador determinista contra XBRL (R05)
Patrón: afirmación → evidencia → SUPPORTS/REFUTES [genai-labs · 01-prompting/01-3-react.ipynb · celda 32], más exponer los pasos
intermedios (`return_intermediate_steps=True`; la función devuelve `intermediate_steps[1]`, la SQL generada)
[genai-labs · 01-prompting/ask-database/ask-bigquery-sqlalchemy-gradio.py · l. 55, 93]. Aquí la evidencia es el parquet, la
comparación no usa LLM y la trayectoria dice qué `get_xbrl_fact` comprobar.

```python
import pandas as pd
from langchain.agents.middleware import AgentMiddleware, hook_config
from langchain.messages import HumanMessage
xbrl = pd.read_parquet(RUTA_XBRL)       # columnas: ticker, fiscal_year, concept, value, unit…
def valor_xbrl(ticker, fy, concept):
    f = xbrl[(xbrl["ticker"] == ticker) & (xbrl["fiscal_year"] == fy) & (xbrl["concept"] == concept)]
    return None if f.empty else float(f["value"].iloc[0])
MARCA = "[VERIFICADOR XBRL]"
class VerificadorXBRL(AgentMiddleware):
    def __init__(self, valor_xbrl, tol_rel=0.005):
        super().__init__()
        self.valor_xbrl, self.tol = valor_xbrl, tol_rel

    @hook_config(can_jump_to=["model"])
    def after_model(self, state, runtime):
        resp = state.get("structured_response")
        if resp is None or resp.cifra is None or resp.fuente == "ninguna":
            return None
        if any(MARCA in str(m.content) for m in state["messages"] if isinstance(m, HumanMessage)):
            return None                                  # un solo reintento por pregunta
        consultas = [tc["args"] for m in state["messages"]
                     for tc in (getattr(m, "tool_calls", None) or []) if tc["name"] == "get_xbrl_fact"]
        for a in consultas:
            v = self.valor_xbrl(a["ticker"], int(a["fiscal_year"]), a["concept"])
            if v is not None and abs(v - resp.cifra) <= self.tol * abs(v):
                return None                              # cuadra con un hecho consultado
        return {"messages": [HumanMessage(f"{MARCA} La cifra {resp.cifra} no coincide con ningún hecho "
                                          f"XBRL consultado ({consultas}). Llama a get_xbrl_fact o corrígela.")],
                "jump_to": "model"}
# middleware=[..., VerificadorXBRL(valor_xbrl)]
```
- `valor_xbrl` aquí es la versión con `float`, sustituida por la de [09 §4](09_skill_guardrails_middleware_xbrl.md) (`(valor, unidad)` o `None`,
  contrato único en `agente10k/datos.py`, SUGERENCIA).
- API: `after_model(self, state, runtime)` devuelve actualizaciones de estado; `hook_config(can_jump_to=[...])` admite `'tools'`,
  `'model'`, `'end'` [api_stack · AgentMiddleware.after_model; decorador hook_config]. Columnas: [perfil_dataset · xbrl_facts.parquet].
  Probado con `ToolStrategy` y un lookup de diccionario: el hook ve `structured_response`, el salto hace responder otra vez al
  modelo y la marca corta en un reintento. ⚠️ Por verificar con gemini-3.8-flash y con la estrategia que elija `response_format` sin envoltorio.
- No cubre cifras derivadas (variaciones, márgenes, %) ni la escala (`unidad`). La tolerancia se decide y se documenta (R09b):
  el 0,5 % de 60.922 M USD son unos 305 M (probado: una respuesta de 61.000 M pasa).

### 3.5 Juez de cita con tres etiquetas (R09a)
Original: el context "You are verifying claims as true or false" pide decidir si la observación SUPPORTS o REFUTES; su único
exemplar enseña SUPPORTS y no existe la salida "no hay información" [genai-labs · 01-prompting/01-3-react.ipynb · celda 32].

```python
from typing import Literal
from pydantic import BaseModel

class Veredicto(BaseModel):
    etiqueta: Literal["SUPPORTS", "REFUTES", "NOT_ENOUGH_INFO"]
    motivo: str
JUEZ = ("Verificas afirmaciones. Recibes una AFIRMACIÓN y una CITA literal de un 10-K. Usa solo la cita: "
        "SUPPORTS si la respalda, REFUTES si la contradice, NOT_ENOUGH_INFO si no dice nada al respecto.")
juez = create_agent(model=modelo, tools=[], system_prompt=JUEZ, response_format=Veredicto)
v = juez.invoke({"messages": [{"role": "user", "content":
      f"AFIRMACIÓN: {resp.respuesta}\nCITA: {resp.cita}"}]})["structured_response"]
```
- `tools=[]` es válido: "the agent will consist of a model node without a tool calling loop" [api_stack · create_agent] (probado).
- Antes del juez, lo determinista: que la cita exista literal (normalizando espacios) en el `chunk_id` o la sección citados.

### 3.6 `responder()`: hilo nuevo, latencia, llamadas y coste (R10, R11, R14)
Original: `call_llm` mide cada llamada con `time.perf_counter()` y guarda modelo, parámetros, prompt y respuesta en una tabla
[genai-labs · 01-prompting/01-1-cot.ipynb · celda 11]; 03-4 repite 10 generaciones e imprime media ± std
[genai-labs · 03-ai-infra/03-4-kvcache.ipynb · celda 3].

```python
import time, uuid
NOMBRES = {t.name for t in TOOLS}
PRECIO_IN, PRECIO_OUT = 0.75e-6, 3.75e-6          # gemini-3.8-flash, USD/token; revisar la víspera
def responder(pregunta: str):
    cfg = {"configurable": {"thread_id": f"q-{uuid.uuid4()}"}}      # sin fuga entre preguntas
    t0 = time.perf_counter()
    res = agente.invoke({"messages": [{"role": "user", "content": pregunta}]}, config=cfg)
    lat = time.perf_counter() - t0
    tray = [tc["name"] for m in res["messages"] for tc in (getattr(m, "tool_calls", None) or [])
            if tc["name"] in NOMBRES]                 # fuera la tool del esquema (ToolStrategy)
    um = [getattr(m, "usage_metadata", None) or {} for m in res["messages"]]
    usd = sum(u.get("input_tokens", 0) for u in um) * PRECIO_IN + sum(u.get("output_tokens", 0) for u in um) * PRECIO_OUT
    salida = res.get("structured_response") or RespuestaFinanciera(
        respuesta="No se pudo completar la respuesta.", fuente="ninguna")    # límite con "end"
    return salida, {"latencia_s": lat, "llamadas": len(tray), "trayectoria": tray, "usd": usd}
```
- `thread_id` nuevo por pregunta: el checkpointer persiste el estado de cada hilo [api_stack · create_agent (checkpointer)] y
  reutilizarlo arrastra las preguntas anteriores. El fallback solo necesita `respuesta` y `fuente` [enunciado · §7] (probado).
- `usage_metadata`: `input_tokens`, `output_tokens`, `total_tokens`, `input_token_details` [api_stack · AIMessage]; este último con
  `audio`, `cache_creation`, `cache_read` en langchain-core 1.6.1 (probado). ⚠️ Por verificar si langchain-openrouter rellena
  `cache_read` y a qué precio cobra OpenRouter lo cacheado: sin eso, el coste es una cota superior. Precios: [01_requisitos · §4].
  No repitáis cada pregunta N veces para la tabla: la media ± std de 03-4 sirve solo para estimar el ruido.
- **Decisión posterior:** la versión final es `ejecutar()`/`responder()` de [08 §7](08_skill_agente_salida_estructurada.md): `responder()` devuelve
  solo un `RespuestaFinanciera` (D20), el coste sale de `get_usage_metadata_callback` (D16) y el arnés pasa `recursion_limit=100` (D04).

### 3.7 Reescritura de la consulta (R08)
Original: en el paso 1 de 01-2 el LLM recibe context + exemplar + pregunta y escribe la búsqueda; `get_wiki_query` se queda la
primera línea y corta en `<STOP>` [genai-labs · 01-prompting/01-2-external-tools.ipynb · celdas 15-19]. Es el único "recuperar y
leer" con código del repo: 01-4 deja FAISS en `TODO` [genai-labs · 01-prompting/01-4-langchain.ipynb · celdas 18-26] y 05-rag solo enlaza.

```python
REESCRIBE = ("Reescribe la pregunta como una consulta de búsqueda breve EN INGLÉS para un 10-K, "
             "con el vocabulario del propio informe. Devuelve SOLO la consulta, en una línea.")
def reescribir(pregunta: str, cache: dict) -> str:
    if pregunta not in cache:                          # cache en JSON -> regenerable (R12)
        r = modelo.invoke([{"role": "system", "content": REESCRIBE}, {"role": "user", "content": pregunta}])
        cache[pregunta] = r.text.strip().splitlines()[0]   # como get_wiki_query: primera línea
    return cache[pregunta]
```
- En modo aislado es una llamada más al LLM por búsqueda: su coste va a la escalera ([11 §7](11_skill_mejora_retrieval.md)); dentro del
  agente no hay llamada extra, porque reescribe el propio modelo al rellenar `query` (D09). Solo cuenta como mejora si sube el
  recall@k contra el ancla [01_requisitos · R08]. (probado)

### 3.8 System prompt y docstrings (R02, R03, R14)
- **Grounding por instrucción:** "All questions must be supported by facts in the table" [genai-labs · 01-prompting/01-1-cot.ipynb · celda 25];
  "Only use information in the observations to answer the question." [genai-labs · 01-prompting/01-3-react.ipynb · celda 9].
  Añadid la salida explícita `fuente="ninguna"` que al verificador de 01-3 le falta [celda 32] (R14).
- **El modelo imita el exemplar:** con la pregunta de las fábricas falla si el exemplar no arrastra el estado de un día al
  siguiente y acierta si lo hace [genai-labs · 01-prompting/01-1-cot.ipynb · celdas 18-21]. En comparativas, el "estado" es el
  otro FY: un dato por ejercicio, mismo concepto y unidad, y ojo al split de NVDA [01_requisitos · §5, trampa 5].
- **Revisad los exemplars:** los de 01-1 traen errores: "17, 9, 3, 19…" donde la tabla dice 4 [genai-labs · 01-prompting/01-1-cot.ipynb · celda 27];
  "2023 minus 16 is 7, so the age is 8" con `"age" : 9` [celda 36]. Incluid uno del caso "no está" y no uséis preguntas del golden set.
- **Formato:** "The last text output should be the JSON" [genai-labs · 01-prompting/01-1-cot.ipynb · celda 32] y `Answer[...]`
  [genai-labs · 01-prompting/01-3-react.ipynb · celda 9] son convenciones de texto; `response_format` las convierte en contrato validado (R03).
- **Docstrings:** anti-ejemplo `"useful for when you need to ask with search"` / `"...with lookup"`
  [genai-labs · 01-prompting/langchain/agent-react.py · l. 17, 22]: ni cuándo no usarla ni vocabulario. El principio bueno es
  "Pay attention to use only the column names you can see" [genai-labs · 01-prompting/ask-database/ask-bigquery-sqlalchemy-gradio.py · l. 61]:
  el docstring enumera el vocabulario cerrado (items `'1A'`, `'7'`, `'7A'`, `'8'`; conceptos de revenue por ticker; sin la lista de huecos
  (C16, D22): los descubre `get_xbrl_fact` con "no reportó", [07 §10](07_skill_herramientas_docstrings.md) trampa 5) [01_requisitos · R02; §5, trampas 2-3].

### 3.9 Claves (R13)
Bien: variable de entorno y `getpass` solo si falta [genai-labs · 01-prompting/01-5-langgraph-react-agents.ipynb · celda 7].
Mal: `os.environ["SERPAPI_API_KEY"] = "XXXX"` en el código, y sin `import os` [genai-labs · 01-prompting/langchain/chain-google-search.py · l. 12];
`PROJECT_ID`/`PROCESSOR_ID` escritos en el fichero [genai-labs · 01-prompting/langchain/agent.py · l. 16-18].

```python
import os, getpass
if not os.environ.get("OPENROUTER_API_KEY"):   # la variable que lee langchain-openrouter 0.2.8 (probado)
    os.environ["OPENROUTER_API_KEY"] = getpass.getpass("OpenRouter API key: ")
```

## 4. APIs obsoletas o específicas de GCP y su equivalente

"Estado" = resultado de importarlo en el venv del stack fijado (probado). `01-N` = `01-prompting/01-N-*.ipynb`.

| Original (dónde) | Estado | Equivalente en nuestro stack | Marca |
| --- | --- | --- | --- |
| `from langchain.llms import VertexAI` (text-bison@001) [langchain/model.py · l. 6-19; chain.py · l. 5; memory.py · l. 5; agent-react.py · l. 7] | `ModuleNotFoundError` | `init_chat_model("openrouter:google/gemini-3.8-flash", temperature=0)` | ⚠️ API obsoleta · ⚠️ específico de GCP |
| `from langchain import PromptTemplate, LLMChain`; `.run()` [langchain/chain.py · l. 6-17] | `ImportError` | `ChatPromptTemplate` de `langchain_core.prompts` + `prompt \| modelo` + `.invoke({...})` [01-4 · celdas 6, 16] | ⚠️ API obsoleta |
| `ConversationChain` [langchain/memory.py · l. 4-10] | `ImportError` | `checkpointer=InMemorySaver()` + `thread_id` | ⚠️ API obsoleta |
| `initialize_agent`, `AgentType`, `load_tools`, `Tool(...)` [agent-react.py · l. 8-36; chain-google-search.py · l. 5-21; 01-4 · celda 13] | `ImportError` | `create_agent(...)` + `@tool` con firma tipada y docstring | ⚠️ API obsoleta |
| `from langgraph.prebuilt import create_react_agent`, `prompt=` [01-5 · celdas 5, 7] | Importa, pero deprecado [api_stack · Deprecados] | `from langchain.agents import create_agent`, `system_prompt=` | ⚠️ API obsoleta |
| `WikipediaQueryRun` desde `langchain.tools`, `WikipediaAPIWrapper` [01-5 · celda 5] | `ImportError` | No hace falta: no hay web en el contrato | ⚠️ API obsoleta |
| `langchain.document_loaders`, `.text_splitter`, `.embeddings`, `.vectorstores` [01-4 · celdas 18-26; langchain/agent.py · l. 66] | `ModuleNotFoundError` | Corpus ya troceado; `faiss-cpu` y `sentence-transformers` directos [01_requisitos · §4] | ⚠️ API obsoleta |
| `SQLDatabaseChain.from_llm(...)` [ask-bigquery-sqlalchemy-gradio.py · l. 55] | No probado | `get_xbrl_fact`, consulta determinista | ⚠️ API obsoleta |
| `genai.Client(...).models.generate_content(..., config=GenerateContentConfig(...))` [01-1 · celda 11; 01-2 · celda 2; 01-3 · celdas 3, 27] | Fuera del stack | `init_chat_model(...)`: un proveedor y un modelo fijos para baseline y final | ⚠️ específico del SDK de Google |
| `OpenAI().responses.create`, `ChatOpenAI`, `ChatGoogleGenerativeAI` [01-1 · celda 11; 01-5 · celdas 5, 7] | Fuera del stack | Igual que la fila anterior | Proveedor directo |
| `TextGenerationModel.from_pretrained("text-bison@001")`, `bigquery.Client` [gcplibrary · l. 24-41]; Document AI [langchain/agent.py · l. 6-35] | Fuera del stack | No aplica | ⚠️ específico de GCP |
| Tool use por texto: `<STOP>`, `splitlines()`, `Answer[` [01-2 · celda 17; 01-3 · celda 27] | — | `bind_tools` → `tool_calls` → `ToolMessage`; fin = sin `tool_calls`; `response_format` (§3.3) | Patrón superado |
| `LANGCHAIN_WANDB_TRACING`, `wandb.Table` [01-5 · celda 3; 01-1 · celda 4] | Fuera del stack | Registro propio por pregunta (§3.6) | Fuera del stack |

## 5. Qué no aplica y por qué

- **`05-rag/`:** tres ficheros de 1-3 líneas con enlaces externos (un post de Medium, el repo
  `rafaelsf80/genai-vertex-documents-synchronous` y un README `langchain_observability_snippet`) [genai-labs · 05-rag/*.md · l. 1-3].
  Ni el filtro por metadatos ni BM25 + denso aparecen en el repo, y la reescritura solo en su versión Wikipedia (§3.7): las
  técnicas de R08 hay que sacarlas de la clase de RAG.
- **`02-tuning/`, `03-ai-infra/`, `04-multimodal/`:** el modelo va por API y debe ser el mismo en baseline y final [01_requisitos · §4];
  no entrenamos ni servimos modelos, y el corpus es texto con las cifras en XBRL [01_requisitos · §2]. De 03-4 solo vale el patrón
  de medición: el KV cache se controla en un modelo local, y su paralelo en el prompt caching del proveedor es ⚠️ por verificar.
- **Wikipedia, `serpapi` y `llm-math` como herramientas:** el contrato fija cuatro sobre el corpus [01_requisitos · §3]. Añadir una
  calculadora para comparativas sería una herramienta nueva (permitido [01_requisitos · R01]); decisión del grupo.
- **ReAct por texto con `<STOP>`:** lo sustituye el tool calling nativo; léelo solo para entender el paper (sesión del 18-sep).
- **PandasAI y text-to-SQL para cifras:** el LLM escribe la consulta (no determinista), gcplibrary la ejecuta sin validar
  [genai-labs · 01-prompting/ask-database/ask-bigquery-gcplibrary-gradio.py · l. 79-80] y el evaluador de trayectoria busca
  `get_xbrl_fact` [01_requisitos · §3]. Para la verdad del golden set (R06) basta pandas.
- **Carga de PDFs:** `agent.py` deja comentada la carga del 10-K de Alphabet con `PyPDFLoader` [genai-labs · 01-prompting/langchain/agent.py · l. 66-75];
  nuestro corpus ya viene seccionado y troceado [enunciado · §3].
- **Gradio** (la entrega es `evaluar()`, R10), **cuatro modelos por llamada a `temperature=1.0`** [genai-labs · 01-prompting/01-1-cot.ipynb · celdas 4, 9, 11]
  y **Gemma 3 1B** para ReAct ("You may not get great results" [genai-labs · 01-prompting/01-3-react.ipynb · celdas 2, 30]): evaluamos un modelo fijo a temperatura 0 [01_requisitos · §4].

## 6. Orden de lectura recomendado

1. `01-prompting/01-3-react.ipynb`, celdas 5-9, 26-27 y 32: ReAct, límite de pasos y verificador (§3.1-3.5).
2. `01-prompting/01-2-external-tools.ipynb`, celdas 10-19: tool use en dos pasos y reescritura de la consulta (§3.7).
3. `01-prompting/01-1-cot.ipynb`, celdas 11, 18-21, 25-27 y 31-33: exemplars, grounding, JSON al final y medición (§3.6, §3.8).
4. `01-prompting/01-5-langgraph-react-agents.ipynb`, celdas 5 y 7: el antecesor de `create_agent` y el patrón de claves (5 minutos).
5. `01-prompting/langchain/agent-react.py`: el action space del paper y cómo NO escribir una descripción de herramienta.
6. (Opcional) `01-prompting/ask-database/ask-bigquery-sqlalchemy-gradio.py`, l. 55-93: vocabulario cerrado y pasos intermedios.
