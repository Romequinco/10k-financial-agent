# Repo generative-ai (Google Cloud): qué nos sirve para la práctica

> Origen: https://github.com/GoogleCloudPlatform/generative-ai (repo oficial de ejemplos de IA generativa de Google Cloud; URL tomada de su README, l. 3). Copia local no versionada en docs/raw/repos/generative-ai-main/. Tiene unos 2.800 ficheros (2.840 en la copia): aquí solo va lo útil para la práctica.

**v1.0 · 12-sep-2026.** Consolida las notas de trabajo D3 (evaluación de agentes), D4 (tools, salida estructurada, guardrails y coste) y D12 (retrieval y evaluación de
RAG), contrastadas con los ficheros originales y con el stack instalado. Los IDs `Rxx` remiten a [01_requisitos_y_contratos.md](01_requisitos_y_contratos.md). No repite
lo que ya resuelven [15](15_repo_genai_labs.md) (límite de llamadas, verificador XBRL, juez de tres etiquetas, `responder()`) y [16](16_repo_transformers_labs.md)
(recall@k contra el ancla, cita literal, tolerancia, trayectoria, BM25, harness): los enlaza y los completa.

Citas: `[generative-ai · <ruta> · celda N]` (celdas desde 0, según la conversión de `docs/raw/_texto/notebooks/`) o `· l. N`; `[celda N]` suelto = último fichero citado.
Abreviaturas: `ev/` = `gemini/evaluation/`, `ET/` = `gemini/evaluation/evaltask_approach/`, `adp/` = `gemini/agents/genai-experience-concierge/agent-design-patterns/`,
`fc/` = `gemini/function-calling/`, `zt/` = `agents/adk/zero-trust-agents/demo/`, `hc/` = `gemini/sample-apps/gemini-hallcheck/`. `[api_stack · …]` = `docs/raw/_texto/api_stack_langchain.md`;
`[enunciado · §N]` = `00_enunciado.md`. **(probado)** = ejecutado en un venv con el stack de §4 y un modelo falso (`GenericFakeChatModel`, sin red): confirma API y flujo,
no cómo se comporta Gemini. **(venv)** = comprobado por introspección en ese venv.

## 1. Qué es y qué parte hemos revisado

Notebooks, sample apps y herramientas oficiales de Google Cloud para Gemini y Vertex AI; casi todo usa `google-genai`/`vertexai` y servicios de GCP (Gen AI Evaluation
Service, Vertex AI Search, RAG Engine, Agent Engine). **Revisado a fondo:** `gemini/evaluation/`, `fc/`, `gemini/controlled-generation/`, `adp/`, `gemini/orchestration/`,
`gemini/token-counting/`, `gemini/context-caching/`, `embeddings/`, `search/` (Ranking API, ClearBox, auto-rag-eval), `gemini/rag-engine/`, `gemini/grounding/` y las apps
`gemini-hallcheck`, `entity-extraction` y `zero-trust-agents`. **Ojeado:** el resto de `gemini/evaluation/`, las apps financieras (GenWealth, finance-advisor-spanner,
swot-agent) y el resumen de documentos largos. **Fuera:** visión, audio, vídeo, traducción, tuning, open-models y despliegue. **Veredicto:** la mejor fuente para **evaluar
agentes** (R09-R12, R15) y **diseñar herramientas y salida estructurada** (R01-R05, R14). Se toma el patrón: el código no corre sin traducirlo (§4) y trae fallos (§5).

## 2. Mapa de utilidad

| Notebook / fichero | Qué enseña | Relevancia | Requisitos | Cómo reutilizarlo |
| --- | --- | --- | --- | --- |
| `ET/evaluating_langgraph_agent.ipynb`, `ev/evaluate_with_your_python_code.ipynb` | Harness dataset → runnable → métricas; cinco métricas de trayectoria; BYOD [celdas 27, 31, 44, 71]; métricas de tool use y TP/FP/FN en Python [celdas 14, 16, 20] | **Alta** | R09c, R10-R12, R15 | §3.1 |
| `ET/evaluate_groundedness_with_custom_parsing.ipynb`, `ET/evaluate_agent_final_answer_with_custom_parsing.ipynb`, `ET/evaluate_autorater.ipynb`, `gemini/grounding/intro-grounding-gemini.ipynb` | Juez FACTS frase a frase [celdas 22, 24]; juez valid/invalid con unidades estrictas [celda 24]; meta-evaluación del juez con kappa y matriz de confusión [celdas 21, 25]; fuentes devueltas con la respuesta [celda 15] | **Alta** | R09a, R14, R15 | §3.2 |
| `ev/agent_as_a_judge_eval.ipynb`, `ev/multi_turn_…_auto_loss_analysis.ipynb`, `ev/multi_agent_state_verification_eval.ipynb` | Step efficiency [celda 16]; llamadas redundantes [celda 24]; verificar contra la fuente de verdad [celda 21] | Media | R04, R05, R11 | §3.1, §3.2 |
| `adp/function-calling.ipynb` | Tools parametrizadas frente a NL2SQL; errores como datos; recorte de `max_results`; `max_recursion_depth` silencioso [celdas 4, 20, 28, 38] | **Alta** | R01, R02, R04, R14 | §3.3, §3.5 |
| `fc/forced_function_calling.ipynb`, `fc/parallel_function_calling.ipynb` | Modos AUTO/ANY/NONE y forzar solo la primera llamada [celdas 21-43]; llamadas paralelas [celdas 3, 27] | **Alta** | R01, R02, R09c | §3.3 |
| `adp/semantic-router.ipynb`, `adp/guardrail-classifier.ipynb` | Razonamiento antes que la clase, destino "Unsupported", fail-closed [celdas 18, 21] | Media | R02, R15 | §3.3 (bugs en §5) |
| `gemini/controlled-generation/intro_controlled_generation.ipynb` | Esquema de respuesta; opcionales rellenados "de memoria"; `if/then` [celdas 15, 20, 23] | **Alta** | R03, R14 | §3.4 |
| `gemini/orchestration/langgraph_multi-agent-rag-and-self-correction.ipynb`, `zt/` | Crítico→editor sin contador [celdas 16, 18]; guarda solo en el prompt frente a guardas con tests [agent.py · l. 85-146; gateway_guard.py · l. 73-150] | **Alta** (patrón) | R04, R05, R13 | [15 §3.4] + §3.5 |
| `gemini/token-counting/local_token_counting.ipynb`, `gemini/context-caching/intro_context_caching.ipynb` | Tokens ocultos; `usage_metadata` como verdad; caché de prefijo [celdas 44, 48; 18, 22, 26] | **Alta** | R11 | §3.6 |
| `embeddings/hybrid-search.ipynb`, `embeddings/task-type-embedding.ipynb` | RRF y `rrf_ranking_alpha` [celdas 5, 52, 59]; asimetría consulta/documento, MRR ~0,3 → ~0,4 [celdas 29, 46, 54] | **Alta** | R08 | §3.7 |
| `gemini/rag-engine/rag_engine_evaluation.ipynb`, `search/ranking-api/ranking_api_beir_evaluation.ipynb`, `search/custom-ranking/clearbox.ipynb` | recall/nDCG@k con bugs [celdas 44-47; 3, 17]; baselines por señal y validación cruzada [celdas 31-33, 41] | Media-alta | R08, R12, R15 | §3.7 |
| `search/auto-rag-eval/` (README, `main.py`) | Generar pares pregunta-respuesta desde el corpus con crítico LLM y revisión humana | **Alta** (corregido) | R06, R07, R12 | §3.8 |
| `hc/` (README, `src/gemhall/metrics.py`), `gemini/use-cases/entity-extraction/` | Cobertura, acierto condicionado, alucinación; ítems sin respuesta; centinela "missing" | **Alta** | R14, R15 | §3.9 |

## 3. Patrones reutilizables traducidos a nuestro stack

### 3.1 Trayectoria y enrutado: las métricas de Vertex en Python (R09c, R11, R15)
Original: `trajectory_exact_match` (mismas acciones y orden), `in_order_match` (las de referencia en orden, con extras), `any_order_match` (todas, sin importar orden ni
extras), `precision` y `recall` [generative-ai · ET/evaluating_langgraph_agent.ipynb · celda 44]. Las de tool use solo miran `tool_calls[0]` y las de parámetros dividen
por la unión de claves [generative-ai · ev/evaluate_with_your_python_code.ipynb · celdas 14, 16]; el agregado cuenta TP/FP/FN de "llamar o no" [celda 20]. [16 §3.4] ya aprueba por
recall = 1 más argumentos; esto añade columnas, porque no sabemos cómo puntuará el evaluador del día 24 [01_requisitos · §3].

```python
import json
from collections import Counter

def metricas_trayectoria(pred: list[dict], ref: list[str]) -> dict:   # pred: tool_calls ya filtrados [16 §3.4]
    p = [t["name"] for t in pred]
    comunes, it = sum((Counter(p) & Counter(ref)).values()), iter(p)
    claves = [(t["name"], json.dumps(t["args"], sort_keys=True, default=str)) for t in pred]
    return {"exact": float(p == list(ref)), "in_order": float(all(r in it for r in ref)),
            "any_order": float(not Counter(ref) - Counter(p)),
            "precision": comunes / len(p) if p else float(not ref), "recall": comunes / len(ref) if ref else 1.0,
            "redundantes": len(claves) - len(set(claves)), "eficiencia": min(1.0, len(ref) / max(1, len(p)))}
```
- **No deduplicar:** el parser del tutorial de ADK solo añade una llamada si no estaba ya [generative-ai · ev/evaluating_adk_agent.ipynb · celda 14] y oculta bucles.
  `redundantes` usa la clave (nombre, args ordenados) de [generative-ai · ev/multi_turn_agent_evaluation_with_user_simulation_metric_registration_auto_loss_analysis.ipynb · celda 24];
  `eficiencia` = `min(1, óptimo / max(1, reales))` [generative-ai · ev/agent_as_a_judge_eval.ipynb · celda 16], con óptimo = `len(herramienta_esperada)` (R04, R11).
- **Enrutado (R15):** por herramienta, TP = se esperaba y se usó, FP = se usó sin esperarse, FN = se esperaba y no se usó → precision, recall y F1, como el agregado de
  [ev/evaluate_with_your_python_code · celda 20]; separado por familia es la diapositiva de enrutado exacta/difusa. Multiconjunto y lista vacía son decisión nuestra:
  Vertex no dice si compara `tool_input` ni cómo trata duplicados [ET/evaluating_langgraph_agent · celda 44] ⚠️.
- BYOD (puntuar sin reejecutar [celda 71]) es el "ejecutar ≠ puntuar" de [16 §3.6]; registrad la tasa de fallo, que el notebook cuenta como *observability* [celda 31].

### 3.2 Evaluador (a): juez frase a frase, su validación y la "cita vista" (R09a)
Original: el prompt estilo FACTS etiqueta cada frase como `supported` (con extracto), `unsupported`, `contradictory` (con extracto) o `no_rad`; sin evidencia indiscutible
en el contexto, `unsupported`, y nada de conocimiento del mundo salvo lo trivial [generative-ai · ET/evaluate_groundedness_with_custom_parsing.ipynb · celda 24]. Su parser
calcula `successful / len(verdicts)` con `no_rad` en el denominador y deja 0 si el JSON no parsea [celda 22]. El grounding de Gemini devuelve con la respuesta el texto de
las fuentes (`grounding_chunks`) y qué segmento respalda cada una (`grounding_supports`) [generative-ai · gemini/grounding/intro-grounding-gemini.ipynb · celda 15]: nuestro
análogo es el `artifact`.

```python
from typing import Literal
from pydantic import BaseModel
from langchain.agents import create_agent
from langchain.messages import ToolMessage

class Veredicto(BaseModel):                                          # una etiqueta por frase de la respuesta
    etiquetas: list[Literal["supported", "unsupported", "contradictory", "no_rad"]]

JUEZ = ("Divide la RESPUESTA en frases y etiqueta cada una frente al CONTEXTO (cita literal de un 10-K): supported (lo implica por completo), "
        "unsupported, contradictory o no_rad (no requiere atribución). Sé muy estricto, sin conocimiento del mundo; unidad y escala deben coincidir.")
juez = create_agent(model=modelo, tools=[], system_prompt=JUEZ, response_format=Veredicto)

def respaldo(cita: str, respuesta: str) -> bool | None:
    v = juez.invoke({"messages": [{"role": "user", "content": f"CONTEXTO: {cita}\nRESPUESTA: {respuesta}"}]}).get("structured_response")
    if v is None:
        return None                                                  # fallo de parseo: contarlo aparte
    etq = [e for e in v.etiquetas if e != "no_rad"]                  # no_rad fuera del denominador
    return bool(etq) and all(e == "supported" for e in etq)

# search_filings con @tool(response_format="content_and_artifact") devuelve (texto_para_el_modelo,
#   {"query": query, "chunks": {chunk_id: texto}}); el dict queda en ToolMessage.artifact
def cita_vista(resultado: dict, resp) -> bool:                       # ¿el agente vio ese chunk en ESTA trayectoria?
    vistos = {cid: tx for m in resultado["messages"] if isinstance(m, ToolMessage) and isinstance(m.artifact, dict)
              for cid, tx in m.artifact.get("chunks", {}).items()}
    return bool(resp.cita) and normalizar(resp.cita) in normalizar(vistos.get(resp.chunk_id or "", ""))
```
- Al trocear en frases, una comparativa con dos afirmaciones no aprueba si solo una está respaldada (complementa [15 §3.5]). `cita_vista` se suma a "la cita existe" de
  [16 §3.2]: un `chunk_id` que el agente no vio es inventado o memorizado. **Probado:** con `content_and_artifact`, `search_filings.invoke({...})` sigue devolviendo `str`
  (asserts intactos) y en el agente el dict va a `.artifact`, que no llega al modelo [api_stack · langchain.messages.ToolMessage]; cambia la anotación de retorno (⚠️ ¿se comprueba?).
- **Decisión posterior: descartado (C17, D13).** Las tools mantienen `-> str` ([07 §2](07_skill_herramientas_docstrings.md), regla 1) y la cita vista se comprueba en el
  contenido de los `ToolMessage`, sin cambiar la anotación ([12 §5](12_skill_evaluadores.md)). `cita_vista` de arriba queda como alternativa no usada.
- **Validad al juez** (propuesta): 30-40 pares etiquetados a mano con negativos construidos (cifra alterada, cita de otra pregunta); acuerdo, kappa de Cohen (a mano: sklearn no
  está en el venv) y matriz de confusión, como [generative-ai · ET/evaluate_autorater.ipynb · celda 25]. Su `rate_batch` descarta los `None` sin avisar [celda 21]: contadlos.
- Juez contra la respuesta dorada (columna aparte): formatos distintos valen, "100 millas" frente a "100 km" no, y el modelo no puede decir que no tiene el dato si la referencia
  lo encuentra [generative-ai · ET/evaluate_agent_final_answer_with_custom_parsing.ipynb · celda 24]. Un juez que solo lee texto se cree la alucinación [generative-ai · ev/multi_agent_state_verification_eval.ipynb · celda 21].

### 3.3 Herramientas: errores como datos, docstring parseado y primera llamada forzada (R01, R02, R04, R14)
Original: el ejecutor del concierge captura la excepción y devuelve `{"error": str(e)}` al modelo [generative-ai · adp/function-calling.ipynb · celda 20]; `find_inventory`
dice en su descripción que hay que conocer los IDs antes de llamarla y devuelve un error explícito si no hay resultados [celda 38]; los opcionales se piden solo si ya se
conocen y `max_results` se recorta [celda 28]. Anti-ejemplo: `query_order_limit` devuelve `0.0` si no encuentra el pedido [generative-ai · zt/agent.py · l. 85].

```python
from langchain.tools import tool
from langchain.agents.middleware import wrap_model_call
from langchain.messages import AIMessage

TICKERS = ("NVDA", "MSFT", "AAPL", "GOOGL", "META", "AMZN")

@tool(parse_docstring=True)
def get_xbrl_fact(ticker: str, fiscal_year: int, concept: str) -> str:
    """Cifra EXACTA reportada en XBRL: úsala para CUALQUIER cifra, una llamada por ejercicio.
    NO leas cifras de search_filings ni de read_section. Si no está reportada, fuente="ninguna".

    Args:
        ticker: NVDA, MSFT, AAPL, GOOGL, META o AMZN.
        fiscal_year: Ejercicio fiscal (2024 o 2025), no el año de presentación.
        concept: Concepto us-gaap exacto (revenue de NVDA: 'Revenues').
    """
    t = ticker.strip().upper()
    if t not in TICKERS:
        return f"ERROR: ticker '{ticker}' fuera del corpus. Válidos: {', '.join(TICKERS)}."
    v, unidad = buscar_hecho(t, int(fiscal_year), concept)          # vuestro lookup en xbrl_facts
    if v is None:                                                    # nunca un 0 por defecto
        return f"{t} no reportó {concept} en FY{fiscal_year}. No lo estimes ni lo calcules."
    cifra = f"{v:,.2f}" if unidad == "USD/shares" else f"{v:,.0f}"  # BPA sin redondear a entero
    return f"{t} FY{fiscal_year} {concept} = {cifra} {unidad}"

@wrap_model_call
def forzar_xbrl_primera(request, handler):
    if not any(isinstance(m, AIMessage) for m in request.messages) and es_numerica(request.messages[-1].content):
        request = request.override(tool_choice="get_xbrl_fact")     # solo en la primera llamada al modelo
    return handler(request)
```
- `parse_docstring=True` lleva cada línea de `Args:` a la descripción del parámetro, y un `Args:` mal formado falla al decorar [api_stack · langchain.tools.tool]. El formato
  conserva los textos de los asserts (`60,922,000,000`, `no reportó`) y el BPA con decimales [01_requisitos · §5, fallo 8] (probado ambos).
- **Forzar solo la primera llamada:** en `AUTO` el modelo contestó en prosa sin llamar a la herramienta [generative-ai · fc/forced_function_calling.ipynb · celdas 26-27];
  `ANY` obliga [celda 30] y luego se vuelve a `tool_config=None` para que pueda contestar [celda 38]; con `NONE` responde con lo aprendido en el entrenamiento [celda 43], el
  "revenue de memoria" que la trayectoria cuenta como fallo [01_requisitos · §2]. Probado: `tool_choice` llega a `bind_tools` solo en la primera llamada [api_stack · ModelRequest];
  `ChatOpenRouter.bind_tools` acepta `tool_choice` y `parallel_tool_calls` (venv). ⚠️ Falta ver si OpenRouter/Gemini lo respeta.
- Comparativas: dos `get_xbrl_fact` en la misma respuesta (llamadas paralelas [generative-ai · fc/parallel_function_calling.ipynb · celdas 3, 27]), sin ampliar la firma (R01).
  Router opcional: razonamiento antes que la clase y destino "Unsupported" [generative-ai · adp/semantic-router.ipynb · celdas 18, 21], pero "fuera de corpus" lleva a
  `fuente="ninguna"`, no a bloquear (las ciegas son legítimas), y a `temperature=0` (el del repo usa 0.2 [celda 21]).

### 3.4 Salida estructurada con reglas condicionales (R03, R14)
Original: con esquema de respuesta la salida lo sigue [generative-ai · gemini/controlled-generation/intro_controlled_generation.ipynb · celda 15], pero los campos son
opcionales por defecto y, sin contexto suficiente, el modelo rellena con lo aprendido en el entrenamiento [celda 20]; las reglas condicionales van con `if/then` [celda 23].

```python
from pydantic import model_validator

class RespuestaFinanciera(BaseModel):
    ...  # los 8 campos del contrato, sin renombrar [enunciado · §7]; se pueden añadir campos
    @model_validator(mode="after")
    def _coherencia(self):
        if self.fuente in ("xbrl", "ambas") and self.cifra is None:
            raise ValueError("fuente xbrl/ambas exige cifra")
        if self.fuente == "ninguna" and self.cifra is not None:
            raise ValueError("fuente='ninguna' no admite cifra: no la estimes")
        if self.fuente in ("texto", "ambas") and not self.cita:
            raise ValueError("fuente texto/ambas exige una cita literal")
        return self
```
- Con `ToolStrategy(schema=RespuestaFinanciera)` (`handle_errors=True` por defecto [api_stack · structured_output.ToolStrategy]) el `ValueError` vuelve al modelo como
  `ToolMessage` "Error: Failed to parse structured output for tool 'RespuestaFinanciera': …" y el modelo reintenta (probado). Lleva el nombre del esquema: la lista blanca de
  [16 §3.4] lo deja fuera de la trayectoria. Sin tope visible de reintentos: lo pone §3.5. Sin envoltorio, la estrategia depende del modelo [api_stack · create_agent] (⚠️ no probado).
- `description` de `cifra` y `cita`: "`null` si no está verificado", más la convención de unidades. Campos añadidos útiles: `concept_xbrl`, `ejercicio_base` y `cifra_base`
  (**decisión posterior**: nombres fijados en D03 y C12, [08 §3](08_skill_agente_salida_estructurada.md)) [01_requisitos · §6].

### 3.5 Límites que cortan de verdad y guardas con tests (R04, R05)
Original: `max_recursion_depth=3` corta con un `print` y un `return`, sin respuesta final [generative-ai · adp/function-calling.ipynb · celda 20]; el `reviewer_router` devuelve
al Editor sin contador [generative-ai · gemini/orchestration/langgraph_multi-agent-rag-and-self-correction.ipynb · celda 18]. En zero-trust el límite del reembolso solo está
en el prompt [generative-ai · zt/agent.py · l. 145-146] y `issue_refund_transaction` no lo comprueba [l. 89-132], mientras que las políticas del gateway tienen tests
deterministas pensados para CI [generative-ai · zt/gateway_guard.py · l. 73-150; zt/run_demo.sh · l. 155-166].

```python
from langchain.agents.middleware import ModelCallLimitMiddleware, ToolCallLimitMiddleware

middleware = [ToolCallLimitMiddleware(run_limit=8), ToolCallLimitMiddleware(tool_name="read_section", run_limit=2),  # C05, D04 (09 §2)
              ModelCallLimitMiddleware(run_limit=12, exit_behavior="end"),   # corte duro (12: propuesta)
              VerificadorXBRL(valor_xbrl)]                                    # [15 §3.4]

def test_verificador():                                         # pytest, sin LLM ni red; cifra_ok de [16 §3.3]
    for t, fy, c, v, ok in [("NVDA", 2024, "Revenues", 60_922_000_000.0, True),     # [enunciado · §7]
                            ("NVDA", 2024, "Revenues", 60_922.0, False),             # millones en vez de unidades
                            ("AMZN", 2025, "GrossProfit", 1.0, False)]:              # hueco real [01_requisitos · §5]
        assert cifra_ok(v, "USD", valor_xbrl(t, fy, c), "USD")["ok"] is ok
```
- `valor_xbrl` es la de [15 §3.4](15_repo_genai_labs.md): versión con `float`, sustituida por la de [09 §4](09_skill_guardrails_middleware_xbrl.md)
  (`(valor, unidad)` o `None`); con ella, el test pasa `(valor_xbrl(t, fy, c) or (None,))[0]`.
- **Probado:** con `exit_behavior="continue"` (defecto) la llamada que excede recibe un `ToolMessage` de error y el grafo sigue; si el modelo **ignora** el aviso, nada lo
  para: un modelo falso que siempre pide `get_xbrl_fact` agotó 100 llamadas al modelo con `ToolCallLimitMiddleware(run_limit=8)`. `ModelCallLimitMiddleware(run_limit=12)`
  [api_stack · ModelCallLimitMiddleware] lo cortó tras 12 llamadas con un `AIMessage` de aviso y sin `structured_response`: fallback de [15 §3.6]. [15 §3.1] cubre el caso en
  que el modelo obedece. La causa raíz del bucle de la celda 23 es que la herramienta no diga claro que el dato no existe (§3.3); el límite es la red.
- El verificador R05 es un crítico **determinista**: el nodo en el que un LLM revisa si las cifras son correctas [generative-ai · gemini/orchestration/intro_langgraph_gemini.ipynb · celda 21] no es reproducible.

### 3.6 Coste por llamada: qué se paga y cuánto (R11)
Original: cada llamada paga system prompt, thinking, declaraciones, llamadas y respuestas de herramientas, esquema de respuesta y el historial completo, que se reenvía en
cada turno [generative-ai · gemini/token-counting/local_token_counting.ipynb · celda 44]; `usage_metadata` es la verdad de facturación y contar en local solo estima [celda 48];
la latencia hasta el primer token crece más o menos con los tokens de entrada [celda 26]. Cálculo propio a 0,75 USD/M de entrada (gemini-3.8-flash [01_requisitos · §4]):

| Qué entra en el contexto | Tokens | USD de entrada por cada llamada al modelo que lo lleve |
| --- | ---: | ---: |
| Resultado de `get_xbrl_fact` / `search_filings` (k=5) | ≈ 40 / ≈ 2.000 [01_requisitos · §3] | ≈ 0,00003 / ≈ 0,0015 |
| `read_section` (META FY2025 1A) | 34.751 [01_requisitos · §3] | ≈ 0,026 |
| Corpus completo (contexto largo) | ≈ 650.000 [enunciado · §3] | ≈ 0,49 |

- Un `read_section` sigue en el historial y se paga otra vez en cada llamada posterior (⚠️ salvo caché del proveedor): primero `search_filings` con `item`. Gemini 3 Flash
  admite 1M tokens [generative-ai · gemini/long-context/intro_long_context.ipynb · celda 3]: el corpus cabría, pero la cifra no saldría de `get_xbrl_fact` [01_requisitos · §2].
- Caché de prefijo: lo grande y común al principio y peticiones con el mismo prefijo seguidas [generative-ai · gemini/context-caching/intro_context_caching.ipynb · celda 22];
  mínimo de 2.048 tokens y ahorro implícito solo en Gemini 2.5, según el notebook [celda 18]: prompt y docstrings estáticos, y ⚠️ verificar `cache_read` en OpenRouter ([15 §3.6]).
- Router, reintentos del verificador y juez son llamadas extra con columna propia. `SummarizationMiddleware` sustituye el historial por un resumen (su prompt por defecto, venv)
  y perdería el texto literal de la cita: fuera de las ejecuciones evaluadas (propuesta).

### 3.7 Retrieval: RRF con `alpha` y cómo medir sin engañarse (R08)
Original: las distancias densa y dispersa viven en espacios distintos, así que se fusionan rangos con RRF, que suma 1/rango de cada lista sin constante
[generative-ai · embeddings/hybrid-search.ipynb · celda 59]; `rrf_ranking_alpha` = 1 (o sin especificar) es solo denso, 0 solo disperso y 0,5 mismo peso [celda 59], y el
ejemplo usa 0,5 [celda 52]. La búsqueda densa falla con datos *out of domain* (códigos, nombres nuevos) [celda 5].

```python
import numpy as np

def rrf(listas: list, pesos: list[float], k: int = 60) -> list[int]:
    punt = {}
    for lista, w in zip(listas, pesos):
        for r, i in enumerate(lista if w > 0 else [], start=1):
            punt[int(i)] = punt.get(int(i), 0.0) + w / (k + r)
    return sorted(punt, key=punt.get, reverse=True)

def rank_bm25(consulta: str, cand: np.ndarray, n: int = 20) -> np.ndarray:
    s = np.asarray(bm25.get_batch_scores(tokenizar(consulta), cand.tolist()))   # bm25 con IDF global [16 §3.5]
    orden = np.argsort(-s, kind="stable")
    return cand[orden[s[orden] > 0][:n]]                                # sin coincidencias no hay señal

def hibrido(consulta: str, cand: np.ndarray, alpha: float = 0.5, n: int = 20, k: int = 60) -> list[int]:
    """alpha=1: solo denso; 0: solo BM25. Fijad alpha y k ANTES de medir."""
    denso = cand[np.argsort(-puntuacion_densa(consulta)[cand], kind="stable")[:n]]   # [16 §3.5]
    return rrf([denso, rank_bm25(consulta, cand, n)], [alpha, 1 - alpha], k)
```
- **Probado:** `bm25.get_scores("revenue percent")` con un `str`, o `["Revenue"]` con mayúscula, da todo ceros sin error (con el corpus real, el `str` no da ceros sino un ranking basura: ver [03 §6](03_teoria_tokenizacion_embeddings.md)); `get_batch_scores(tokens, ids)` = `get_scores(tokens)[ids]`.
- `k` es decisión nuestra (⚠️ el notebook usa 1/rango, sin constante) y no se cambia entre baseline y final. No ajustéis `alpha` ni `k` contra el golden: ClearBox valida con
  5 semillas × 3 folds [generative-ai · search/custom-ranking/clearbox.ipynb · celda 31] y su mejora final, ~0,04 en recall@1 [celda 41], es menos que una pregunta de 20
  (0,05). Reportad "solo BM25" junto a "denso" e "híbrido" (baselines por señal [celdas 32-33]) y el techo: RRF solo reordena lo que traen las dos listas.
- Asimetría: con *task types* distintos para consulta y documento el MRR sube de ~0,3 a ~0,4 en 1.000 pares de NQ-Open [generative-ai · embeddings/task-type-embedding.ipynb · celdas 46, 54],
  con muestra sin semilla [celda 29]. No se traslada a BGE ni a 10-K (⚠️ hipótesis), pero justifica medir recall@k con y sin el prefijo BGE [01_requisitos · §4].
- Recuperad una vez el top-20 por pregunta y cortad por k (R12): RAG Engine repite la recuperación por cada k (648 consultas, 44:47 min solo para k=5) [generative-ai · gemini/rag-engine/rag_engine_evaluation.ipynb · celda 46].
  nDCG no es la métrica principal: con una sola relevancia por consulta es problemático [generative-ai · search/ranking-api/ranking_api_beir_evaluation.ipynb · celda 3], y el
  `ndcg_at_k` de RAG Engine da a cada chunk la relevancia de su documento y puede superar 1 [rag_engine_evaluation · celda 44]. Principal: recall@k y MRR de [16 §3.1].

### 3.8 Golden set asistido: auto-rag-eval corregido (R06, R07, R12)
Original: documentos → chunks → pistas → recuperación y destilado de contexto → perfiles → pares pregunta-respuesta → revisión
[generative-ai · search/auto-rag-eval/README.md · l. 248-290]. El README promete varios críticos con consenso [l. 294], pero el código usa uno ("Analyst") [main.py · l. 100-103];
guarda contexto, perfil y par, pero no el chunk de origen [l. 105-112]; muestrea con `random.SystemRandom()`, no reproducible [l. 205]; y el README pide que expertos del
dominio verifiquen los pares [README.md · l. 412-421]. Adaptación (propuesta):
1. Muestreo estratificado por `(ticker, fiscal_year, item)` con `random.Random(semilla)` (R12); el LLM propone, a partir de **un** chunk, pregunta autocontenida (empresa
   y ejercicio explícitos), `ancla_texto` literal y `respuesta_esperada` con `create_agent(model, tools=[], response_format=Candidata)`.
2. Filtro determinista antes del crítico (ancla normalizada dentro del chunk y ≤ 40 palabras, R07, [16 §3.2]); crítico LLM APPROVED/REJECTED; **curación humana** que
   reescribe en español natural, sin el vocabulario del chunk, que infla BM25 y el recall.
3. Guardar `chunk_id_esperado` y un campo extra `origen` [01_requisitos · §3] (⚠️ decidir en grupo si una pregunta generada y curada cuenta como "propia", R06). La cifra sale
   de `xbrl_facts.parquet`, no del LLM; los huecos reales (AMZN y META sin `GrossProfit` [01_requisitos · §5]) van a un set de robustez aparte, como `--idk-frac` de
   hallcheck [generative-ai · hc/README.md · l. 8, 115], si el validador exige `cifra_esperada` en `numerica`.

### 3.9 Abstención y alucinación al estilo hallcheck (R14, R15)
Original: +1 si acierta, −t/(1−t) si falla y 0 si se abstiene; cobertura = respondidas / total, y acierto condicionado y tasa de alucinación entre las respondidas
[generative-ai · hc/src/gemhall/metrics.py · l. 19-47]; curva riesgo-cobertura por umbral [hc/README.md · l. 7].

```python
def metricas_abstencion(filas: list[dict], t: float = 0.75) -> dict:
    """filas: {'abstiene': fuente == 'ninguna', 'hay_dato': verdad is not None, 'acierto': bool}"""
    media = lambda xs: sum(xs) / len(xs) if xs else None
    resp = [f for f in filas if not f["abstiene"]]
    return {"cobertura": len(resp) / len(filas), "acierto_condicionado": media([f["acierto"] for f in resp]),
            "tasa_alucinacion": media([not f["acierto"] for f in resp]),
            "abstencion_correcta": media([f["abstiene"] for f in filas if not f["hay_dato"]]),
            "abstencion_indebida": media([f["abstiene"] for f in filas if f["hay_dato"]]),
            f"score_t{t}": sum(1.0 if f["acierto"] else -t / (1 - t) for f in resp) / len(filas)}
```
- Las dos abstenciones no están en el `aggregate` original: sin la indebida, un agente que siempre dice "no está" parecería honesto. Baseline y final son dos puntos de la
  curva riesgo-cobertura (R15); con t = 0,75, un fallo resta 3.
- Centinela de ausencia: el prompt de extracción pide escribir "missing" si falta el dato [generative-ai · gemini/use-cases/entity-extraction/README.md · l. 259], nuestro
  `fuente="ninguna"`. Su `evaluate.py` solo mide `exact_match` [evaluate.py · l. 180-191] y, si el JSON no parsea, devuelve la cadena cruda como clase [evaluate.py · l. 121-126].

## 4. APIs obsoletas o específicas de GCP y su equivalente

| Original (dónde) | Estado en el venv | Equivalente en nuestro stack | Marca |
| --- | --- | --- | --- |
| `genai.Client(vertexai=True, …)`, `ChatVertexAI` + `bind_tools` [ET/evaluating_langgraph_agent · celda 27]; `FunctionDeclaration`, `Part.from_function_response` y bucle manual [fc/intro_function_calling · celdas 20, 30] | Fuera del stack | `init_chat_model("openrouter:google/gemini-3.8-flash", temperature=0)` [01_requisitos · §4] + `@tool` + `create_agent`, que ejecuta las tools y añade los `ToolMessage` [api_stack · create_agent] | ⚠️ específico de GCP |
| `FunctionCallingConfig(mode=ANY, allowed_function_names)` [fc/forced_function_calling · celda 30]; `AutomaticFunctionCallingConfig` + `max_recursion_depth` [adp/function-calling · celdas 20, 42] | Fuera del stack | `wrap_model_call` + `request.override(tool_choice=…)` (§3.3); `ToolCallLimitMiddleware` + `ModelCallLimitMiddleware` (§3.5) | ⚠️ específico de GCP |
| `response_schema`, `response.parsed`, `text/x.enum`, JSON Schema `if/then` [controlled_generation · celdas 15, 19, 23, 24] | Fuera del stack | `response_format` o `ToolStrategy` → `["structured_response"]`; `Literal`; `model_validator` (§3.4) | ⚠️ específico de GCP |
| `llm.with_structured_output(...)` [orchestration/langgraph_multi-agent-rag-and-self-correction · celda 16]; `MemorySaver()` [adp/function-calling · celda 46] | Existen | `response_format` en `create_agent`; `InMemorySaver()` | ⚠️ API obsoleta según el notebook de S1 [01_requisitos · §4] |
| `MessageGraph`, `from langchain.load import dump` [ET/evaluating_langgraph_agent · celdas 16, 27] | `MessageGraph` avisa: deprecado en v1.0, se quita en v2.0; `langchain.load` no existe (`dumpd` está en `langchain_core.load`) | `create_agent` y recorrer `resultado["messages"]` | ⚠️ API obsoleta |
| `langchain_classic` (`RetrievalQA`, `load_summarize_chain`, `ConversationBufferMemory`) [orchestration/intro_langchain_gemini · celda 14] | `ModuleNotFoundError` | `create_agent` + herramientas + `response_format` | ⚠️ API obsoleta |
| `EvalTask(...).evaluate(runnable=…)`, `CustomMetric`, `PointwiseMetric`, `vertexai.Client().evals` [ET/*; ev/evaluate_with_your_python_code · celda 14] | Fuera del stack | Funciones Python locales (§3.1, §3.2) y harness de [16 §3.6] | ⚠️ específico de GCP |
| `HybridQuery(…, rrf_ranking_alpha)` [hybrid-search · celda 52], `rag.retrieval_query` [rag_engine_evaluation · celda 44], `semantic-ranker-default-004` [ranking_api_beir_evaluation · celda 12], `EmbedContentConfig(task_type=…)` [task-type-embedding · celda 15] | Fuera del stack | FAISS exacto + `rank_bm25` + `rrf()` (§3.7); prefijo BGE solo en la consulta [01_requisitos · §4] | ⚠️ específico de GCP |
| `tenacity` con reintentos en 429/502/503/504 [adp/task-planner · celdas 16, 20] | Importa | `ModelRetryMiddleware(max_retries=…)` [api_stack · ModelRetryMiddleware] o el campo `max_retries` de `ChatOpenRouter` | ⚠️ específico de GCP |
| `pytrec_eval` [ranking_api_beir_evaluation · celdas 9-10], `sklearn`/`scipy` [evaluate_autorater · celda 25], `jsonschema`/`DeepDiff` [evaluate_gemini_structured_output] | `sklearn` y `scipy` no importan | Python puro (§3.2; métricas de [16 §3.1]) | Fuera del stack |

## 5. Qué no aplica y por qué

- **Métricas remotas y de estilo** del Gen AI Evaluation Service (`safety`, `coherence`, rúbricas generadas), **pairwise y self-consistency con temperatura > 0:** se
  corrige por exactitud contra XBRL y trazabilidad (R09), con métricas deterministas regenerables en un clon limpio (R10, R12) y a `temperature=0` [01_requisitos · §4].
- **Jueces de `multi_agent_state_verification_eval`:** Prompt Judge, G-Eval y Multi-Agent Judge no llaman a ningún LLM, ramifican por la cadena `trace_id`
  [generative-ai · ev/multi_agent_state_verification_eval.ipynb · celdas 18, 20, 22]; solo vale la idea de verificar el estado (§3.2).
- **Contexto largo, resumen map-reduce/refine y `RetrievalQA`:** rompen la trayectoria o la cita literal (R07, R09a). El notebook de resumen construye el DataFrame de refine a
  partir del de map-reduce [generative-ai · gemini/use-cases/document-processing/summarization_large_documents_langchain.ipynb · celda 55], y el de LangChain pregunta el net
  income de Alphabet al PDF de su 10-K [generative-ai · gemini/orchestration/intro_langchain_gemini.ipynb · celdas 84-90]: el camino que la trayectoria cuenta como fallo [01_requisitos · §2].
- **Infraestructura GCP** (Vector Search, RAG Engine, Agent Engine, AlloyDB, Spanner, BigQuery, KMS), **HITL** y **planner multiagente:** `evaluar()` corre sin personas en un
  clon limpio (R10), con 1.749 vectores basta la búsqueda exacta ([16 §3.5]) y el README avisa de que el planner es mucho más lento que un solo agente
  [generative-ai · adp/README.md · l. 88]. De zero-trust (firma HMAC, ledger, filtro por palabras clave) solo vale validar en código y testear (§3.5).
- **`gemini-embedding-001`, tuning de embeddings y señales de Vertex AI Search** (`jetstream_score`, `freshness_rank`): el modelo está fijado [01_requisitos · §4] y esas señales no existen aquí.
- **Bugs que no hay que copiar:** el enum `RouterTarget` define miembros en minúscula y el código usa `RouterTarget.CUSTOMER_SERVICE`, y `turns[:max_router_turn_history]` toma
  los primeros turnos, no los últimos [generative-ai · adp/semantic-router.ipynb · celdas 18, 21]; tras `del first[query_id]` falta un `continue` y la línea siguiente lee esa
  clave [generative-ai · search/ranking-api/ranking_api_beir_evaluation.ipynb · celda 17]; `no_rad` en el denominador (§3.2); `tool_calls[0]` (§3.1).

## 6. Orden de lectura recomendado

1. `gemini/evaluation/evaltask_approach/evaluating_langgraph_agent.ipynb`, celdas 27-44 y 71: harness y métricas de trayectoria (§3.1).
2. `gemini/evaluation/evaltask_approach/evaluate_groundedness_with_custom_parsing.ipynb` (celdas 22-24) y `evaluate_autorater.ipynb` (celdas 21-25): el juez y cómo validarlo (§3.2).
3. `gemini/agents/genai-experience-concierge/agent-design-patterns/function-calling.ipynb` (celdas 20-38) y `gemini/function-calling/forced_function_calling.ipynb` (celdas 21-43):
   herramientas, errores y modos de llamada (§3.3, §3.5).
4. `gemini/controlled-generation/intro_controlled_generation.ipynb`, celdas 15-25: salida estructurada y sus límites (§3.4).
5. `embeddings/hybrid-search.ipynb` (celda 59) y `gemini/rag-engine/rag_engine_evaluation.ipynb` (celdas 44-47): RRF y métricas de retrieval con sus trampas (§3.7).
6. `gemini/sample-apps/gemini-hallcheck/` (README y `src/gemhall/metrics.py`) y `search/auto-rag-eval/` (README y `main.py`): abstención y golden asistido (§3.8, §3.9).
