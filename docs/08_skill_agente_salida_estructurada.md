# Skill: montar el agente, `responder()` y la salida estructurada

> Requisitos: R03, R04 (montaje), R10, R13 · Lee antes: [05_teoria_agentes_react_tools.md](05_teoria_agentes_react_tools.md),
> [07_skill_herramientas_docstrings.md](07_skill_herramientas_docstrings.md), [15_repo_genai_labs.md](15_repo_genai_labs.md) §3.1, §3.3, §3.6 y §3.9

> Fuentes: `00_enunciado.md`, `01_requisitos_y_contratos.md`, notebook S1 (celdas 4, 6 y 19–29), transcripción del 10-sep, docs 14–17,
> `api_stack_langchain.md` y las decisiones comunes D01–D05, D16–D22 y D25 del mapa de cobertura (nota interna).

**v1.0 · 12-sep-2026.** El agente que se evalúa: modelo, esquema, prompt, pila de middleware, `responder()` y prueba con la API real. Límites
y R05 en [09](09_skill_guardrails_middleware_xbrl.md); herramientas en [07](07_skill_herramientas_docstrings.md); `evaluar()` y tablas en
[13](13_skill_medicion_informe_presentacion.md). Marcas: **(probado)** = ejecutado en el venv del stack con `GenericFakeChatModel`, sin red
(API y flujo, no el comportamiento de Gemini); **(venv)** = introspección; ⚠️ = sin verificar. Módulos `agente10k/…`: **SUGERENCIA**.

## 1. Qué se construye

| Pieza | Baseline (el del profesor, D21) | Final | Dónde (sugerencia) |
| --- | --- | --- | --- |
| Modelo | instancia `init_chat_model(MODELO_ID, temperature=0)` | la misma | `config.py` |
| Esquema | `RespuestaFinanciera` de la celda 25, tal cual | + 3 campos opcionales + `model_validator` (§3) | `esquemas.py` |
| `response_format` | esquema suelto (≡ `ToolStrategy`, §4) | `ToolStrategy(schema=…)` explícito | `agente.py` |
| Prompt | `SYSTEM` de la celda 21 | §5 | `agente.py` |
| Middleware | ninguno | límites + `VerificadorXBRL` ([09](09_skill_guardrails_middleware_xbrl.md)) | `middleware.py` |
| Arnés | `ejecutar()` de §7: hilo nuevo, `recursion_limit=100`, *fallback*, coste y latencia | el mismo | `api.py` |

El baseline solo cambia dos cosas respecto al notebook, porque son requisitos de evaluación y no mejoras: el modelo como instancia a
`temperature=0` y el arnés. Todo lo demás (arreglo del BPA incluido) es mejora medida (D21).

## 2. Paso 1: clave y modelo (R13, D01, D25)

```python
# agente10k/config.py (SUGERENCIA)
import getpass
import os

from langchain.chat_models import init_chat_model

MODELO_ID = os.environ.get("AGENTE10K_MODELO", "openrouter:google/gemini-3.8-flash")  # fijo al evaluar


def asegurar_clave(nombre: str = "OPENROUTER_API_KEY") -> None:
    """Entorno -> Secrets de Colab (opcional) -> getpass. Nunca en el código ni en un notebook."""
    if os.environ.get(nombre):
        return
    try:
        from google.colab import userdata          # solo existe en Colab
        os.environ[nombre] = userdata.get(nombre)
    except Exception:
        os.environ[nombre] = getpass.getpass(f"{nombre}: ").strip()


def crear_modelo():
    asegurar_clave()
    return init_chat_model(MODELO_ID, temperature=0)   # a create_agent se le pasa ESTA instancia
```

- **La instancia, nunca la cadena.** Con una cadena, `create_agent` hace `init_chat_model(model)` sin `temperature` [01 §5, fallo 9] (venv).
  La instancia es un `ChatOpenRouter` con `temperature=0.0`, `max_retries=2` (reintentos de red, se dejan), `seed=None` (no se confía en él) y
  `profile=None` (venv). Sirve también al reescritor de [11](11_skill_mejora_retrieval.md) y, por defecto, al juez de [12](12_skill_evaluadores.md).
- Nada de `openrouter:auto` ni `ModelFallbackMiddleware` en lo evaluado: si el modelo cambia, baseline frente a final no significa nada
  [notebook S1 · celda 6; 14 §3]. `AGENTE10K_MODELO` solo para experimentos; `ejecutar()` guarda el id en cada fila.
- `OPENROUTER_API_KEY` es la variable que lee langchain-openrouter 0.2.8 [15 §3.9](15_repo_genai_labs.md) (probado). Antes de cada push,
  `git grep -nE "sk-or-v1-|API_KEY\s*=\s*['\"]"` tiene que salir vacío: una clave publicada puede salir carísima [transcripcion_04sep · 00:36].

## 3. Paso 2: el esquema de salida (R03, D03)

```python
# agente10k/esquemas.py (SUGERENCIA)
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class RespuestaFinanciera(BaseModel):
    """Respuesta trazable a una pregunta sobre informes 10-K."""

    # --- los 8 campos del contrato [enunciado · §7]: mismos nombres y tipos ---
    respuesta: str = Field(description="Respuesta breve y directa, en español.")
    cifra: float | None = Field(default=None, description=(
        "Valor SIN escalar en la unidad de XBRL (USD enteros; BPA en USD por acción), copiado de "
        "get_xbrl_fact. null si no está verificado o no aplica."))
    unidad: str | None = Field(default=None, description="'USD' o 'USD/shares', literal de XBRL.")
    ticker: str | None = Field(default=None, description="NVDA, MSFT, AAPL, GOOGL, META o AMZN.")
    ejercicio: int | None = Field(default=None, description="FY de 'cifra'; en comparativas, el más reciente.")
    fuente: Literal["xbrl", "texto", "ambas", "ninguna"] = Field(description=(
        "xbrl: cifra de get_xbrl_fact; texto: fragmentos leídos; ambas: las dos; ninguna: no está en el corpus."))
    cita: str | None = Field(default=None, description=(
        "Frase LITERAL copiada de un fragmento devuelto por search_filings o read_section. "
        "Obligatoria si fuente es 'texto' o 'ambas'."))
    chunk_id: str | None = Field(default=None, description="chunk_id del fragmento de la cita.")
    # --- añadidos (D03): opcionales, el contrato permite añadir campos ---
    concept_xbrl: str | None = Field(default=None, description="Concepto us-gaap que respalda 'cifra'.")
    ejercicio_base: int | None = Field(default=None, description="Solo comparativas: el ejercicio anterior.")
    cifra_base: float | None = Field(default=None, description=(
        "Solo comparativas: valor XBRL de ejercicio_base, mismo concepto y unidad que 'cifra'."))

    @model_validator(mode="after")
    def _coherencia(self):                                      # solo en el sistema final
        if self.fuente in ("xbrl", "ambas") and self.cifra is None:
            raise ValueError("fuente 'xbrl'/'ambas' exige 'cifra', copiada de get_xbrl_fact.")
        if self.fuente == "ninguna" and self.cifra is not None:
            raise ValueError("fuente 'ninguna' exige cifra=null: no estimes.")
        if self.fuente in ("texto", "ambas") and not self.cita:
            raise ValueError("fuente 'texto'/'ambas' exige 'cita': frase literal de un fragmento leído.")
        return self
```

- **Por qué el validador:** en el contrato solo `respuesta` y `fuente` son obligatorios, así que el esquema **no obliga a citar**, aunque la
  celda 25 diga lo contrario [14 §5, matiz 4]. Con `ToolStrategy` el `ValueError` vuelve al modelo como `ToolMessage` "Error: Failed to parse
  structured output for tool 'RespuestaFinanciera': …" y el modelo reintenta (probado); el tope lo pone `ModelCallLimitMiddleware`. Que la cita
  exista lo mira el evaluador (a) de [12](12_skill_evaluadores.md).
- Las `description` son prompt: fijan la escala de `cifra`, la unidad literal y la cita literal. El *fallback* (§7) pasa el validador. Sin campo
  `razonamiento`: cuesta tokens de salida y ningún evaluador lo pide (como mucho, experimento).

## 4. Paso 3: la estrategia de `response_format` (R03, D02)

| Opción | Qué hace [api_stack] | Con nuestro modelo |
| --- | --- | --- |
| Esquema Pydantic suelto (celda 26) | "Raw schemas will be wrapped in an appropriate strategy based on model capabilities" [api_stack · create_agent] | Se envuelve en `AutoStrategy`; como `ChatOpenRouter.profile` es `None` y el modelo no está en la lista de *fallback* de salida nativa, acaba en `ToolStrategy` (venv, código de `langchain.agents.factory`) |
| `ProviderStrategy(schema, *, strict=None)` | Salida estructurada nativa del proveedor [api_stack · structured_output.ProviderStrategy] | ⚠️ Depende de lo que OpenRouter y Gemini acepten; la firma no tiene `handle_errors` |
| `ToolStrategy(schema, *, tool_message_content=None, handle_errors=True)` | El esquema como herramienta sintética [api_stack · structured_output.ToolStrategy] | **Elegida (D02)** |

Por qué `ToolStrategy` explícito: es lo que el envoltorio automático ya elige con este modelo (no cambia el comportamiento), no depende del
perfil del modelo ni de versiones futuras, `handle_errors=True` devuelve al modelo los errores del validador y fija el nombre de la tool
sintética (`"RespuestaFinanciera"`), que la lista blanca de la trayectoria deja fuera (§7). Se importa de `langchain.agents.structured_output`
(probado); el aviso de la celda 26 de que el esquema suelto "falla" no aplica con este stack [14 §5, matiz 3]. Juez y reescritor:
`create_agent(model=modelo, tools=[], system_prompt=…, response_format=ToolStrategy(schema=…))`, un solo nodo de modelo
[api_stack · create_agent] (probado). Nunca `with_structured_output`, obsoleto [01 §4].

`resultado["structured_response"]` **puede ser `None`** (límite con `"end"`, recursión, excepción): siempre hay *fallback* (§7). Rastro en
`messages` (probado): un `AIMessage` con la tool call `RespuestaFinanciera` y un `ToolMessage` "Returning structured response: …". Si el modelo
la emite **en el mismo `AIMessage`** que una herramienta real, la respuesta se acepta y la herramienta también se ejecuta (probado).

## 5. Paso 4: el system prompt (R02, R14, D22)

```python
SYSTEM = """Eres un analista financiero que responde preguntas sobre los informes 10-K de NVDA, MSFT, AAPL, GOOGL,
META y AMZN, ejercicios fiscales 2024 y 2025, usando ÚNICAMENTE las herramientas.

Universo
- El ejercicio fiscal (FY) no es el año de presentación: NVDA cierra en enero, MSFT en junio, AAPL en septiembre,
  y GOOGL, META y AMZN en diciembre.
- Items: '1A' factores de riesgo; '7' MD&A (análisis de la dirección); '7A' riesgo de mercado; '8' estados financieros.

Enrutado
- Toda CIFRA sale de get_xbrl_fact, una llamada por compañía y ejercicio. Nunca tomes como cifra un número de un fragmento
  (única excepción, en Campos).
- Riesgos, estrategia o explicaciones de la dirección: search_filings, con la consulta en INGLÉS y el vocabulario de
  un 10-K, pasando ticker, fiscal_year e item siempre que los sepas.
- read_section solo si search_filings no encuentra el pasaje: es muy cara.
- Si dudas de si una compañía o un ejercicio están en el corpus, usa list_available.

Si el dato no está
- Si get_xbrl_fact dice que la compañía no reportó el concepto, o la compañía o el ejercicio no están en el corpus:
  fuente="ninguna", cifra=null, y dilo en la respuesta.
- No estimes, no calcules magnitudes que la compañía no reporta y no reintentes con conceptos inventados.

Comparativas entre ejercicios
- Llama a get_xbrl_fact para los dos ejercicios con el MISMO concepto (puedes pedir las dos llamadas a la vez) y busca
  con search_filings la frase que explique el cambio: una llamada por ejercicio con la misma query (ticker y fiscal_year
  de cada uno). Cita la del ejercicio más reciente, normalmente del Item 7 (o del item que trate el tema: 1A riesgos,
  8 notas como el split).
- cifra y ejercicio = el ejercicio más reciente; cifra_base y ejercicio_base = el anterior. La variación, solo en la respuesta.
- Compara los valores reportados, sin ajustarlos. Si el BPA cambia de forma brusca, comprueba en el texto si hubo un
  split y dilo.

Campos
- fuente: "xbrl" (cifra de get_xbrl_fact), "texto" (fragmentos), "ambas" o "ninguna".
- cifra: el valor exacto de get_xbrl_fact, sin escalar; unidad "USD" o "USD/shares"; concept_xbrl: el concepto usado.
- Si la cifra pedida no es uno de los conceptos XBRL (p. ej. un segmento), puedes darla con fuente="texto" solo si
  aparece literal en la cita; nunca para los 13 conceptos de get_xbrl_fact.
- cita: una frase copiada LITERALMENTE de un fragmento que hayas leído, con su chunk_id. No la parafrasees ni la traduzcas.
- respuesta: breve y en español. Cualquier importe que menciones tiene que coincidir con get_xbrl_fact o estar
  literal en la cita.
"""
```

- Parte del `SYSTEM` de la celda 21 y añade el universo, el significado de `fuente` y la cita literal (D22). **No lista los huecos**: con la lista
  delante el agente contesta "ninguna" sin llamar a `get_xbrl_fact` y suspende (c); los huecos los descubre la herramienta ("no reportó",
  [07](07_skill_herramientas_docstrings.md)). Listarlos es un experimento aparte.
- Los 13 conceptos, la regla del revenue y el coste de cada tool van en los docstrings ([07](07_skill_herramientas_docstrings.md)). Nada de
  ejemplos del golden set ni de cifras sin verificar [15 §3.8](15_repo_genai_labs.md). Prompt estático: favorece la caché de prefijo ⚠️
  [17 §3.6](17_repo_generative_ai.md).

## 6. Paso 5: montar el agente (R03, R04, D04)

```python
# agente10k/agente.py (SUGERENCIA)
from langchain.agents import create_agent
from langchain.agents.structured_output import ToolStrategy
from langgraph.checkpoint.memory import InMemorySaver

# from agente10k.esquemas import RespuestaFinanciera                    -> §3
# from agente10k.middleware import VerificadorXBRL, pila_middleware     -> 22


def construir_agente(modelo, tools, system_prompt, valor_xbrl=None, hechos=None):
    """Sistema final. `modelo` es la INSTANCIA de crear_modelo()."""
    verificador = VerificadorXBRL(valor_xbrl, hechos) if valor_xbrl else None
    return create_agent(
        model=modelo,
        tools=tools,
        system_prompt=system_prompt,
        response_format=ToolStrategy(schema=RespuestaFinanciera),  # handle_errors=True
        middleware=pila_middleware(verificador),                   # límites + R05 (09)
        checkpointer=InMemorySaver(),
    )


def construir_baseline(modelo, tools_notebook, system_notebook, esquema_notebook):
    """Celda 26 tal cual, salvo el modelo (instancia a temperature=0). Sin middleware (D21)."""
    return create_agent(model=modelo, tools=tools_notebook, system_prompt=system_notebook,
                        response_format=esquema_notebook, checkpointer=InMemorySaver())
```

- **Middleware**, en este orden: `ToolCallLimitMiddleware(run_limit=8)`, `ToolCallLimitMiddleware(tool_name="read_section", run_limit=2)`,
  `ModelCallLimitMiddleware(run_limit=12, exit_behavior="end")` y `VerificadorXBRL` (parámetros y tests en
  [09](09_skill_guardrails_middleware_xbrl.md)). El baseline va sin middleware: es el "antes" de R04.
- **Checkpointer + `thread_id`:** un hilo nuevo por pregunta (D05); con el mismo hilo `messages` acumula los turnos, contamina la trayectoria
  e infla el coste [notebook S1 · celda 27]. El checkpointer permite recuperar la trayectoria de una ejecución cortada con
  `agente.get_state(config)` (probado tras `GraphRecursionError`). `InMemorySaver` está pensado para depuración y pruebas
  [api_stack · InMemorySaver]: nos basta.

## 7. Paso 6: `ejecutar()` y `responder()` (R10, R11, D04, D05, D16–D20)

`responder(pregunta)` devuelve **una `RespuestaFinanciera` válida siempre** (D20); `ejecutar()` devuelve además todo lo que necesitan los
evaluadores y la tabla R11, y es lo que llama `evaluar()` [13](13_skill_medicion_informe_presentacion.md).

```python
# agente10k/api.py (SUGERENCIA)
import time
import uuid
from functools import lru_cache

from langchain.messages import AIMessage, ToolMessage
from langchain_core.callbacks import get_usage_metadata_callback
from langgraph.errors import GraphRecursionError

# from agente10k.config import MODELO_ID, PRECIOS, crear_modelo        -> §2 y precios.json (D24)
# from agente10k.herramientas import TOOLS                              -> 20 (orden fijo)
# from agente10k.datos import valor_xbrl, hechos                        -> 09 §4
FALLBACK = {"respuesta": "No se pudo completar la respuesta.", "fuente": "ninguna"}
NOMBRES_TOOLS = {"list_available", "get_xbrl_fact", "search_filings", "read_section"}  # + las que añadáis


def trayectoria(mensajes, nombres=NOMBRES_TOOLS) -> list[dict]:
    """tool_calls de la invocación, con lista blanca (fuera 'RespuestaFinanciera') y sin deduplicar."""
    return [{"name": tc["name"], "args": tc["args"], "id": tc["id"]}
            for m in mensajes if isinstance(m, AIMessage)
            for tc in (m.tool_calls or []) if tc["name"] in nombres]


def uso_en_mensajes(mensajes) -> dict:
    us = [getattr(m, "usage_metadata", None) or {} for m in mensajes]
    tot = {k: sum(u.get(k, 0) for u in us) for k in ("input_tokens", "output_tokens", "total_tokens")}
    return tot | {"cache_read": sum((u.get("input_token_details") or {}).get("cache_read", 0) or 0 for u in us)}


def usd(uso_por_modelo: dict, precios: dict) -> float:
    """precios = {"google/gemini-3.8-flash": (0.75, 3.75), ...} en USD/M, de resultados/precios.json."""
    total = 0.0
    for nombre, u in uso_por_modelo.items():               # clave = response_metadata["model_name"]
        clave = next((k for k in precios if nombre.startswith(k)), MODELO_ID.split(":", 1)[-1])
        p_in, p_out = precios[clave]
        total += (u.get("input_tokens", 0) * p_in + u.get("output_tokens", 0) * p_out) / 1e6
    return total


def ejecutar(agente, pregunta: str, thread_id: str | None = None, esquema=None) -> dict:
    """Una pregunta, un hilo nuevo. Nunca lanza: la causa de un fallo va en `error`."""
    esquema = esquema or RespuestaFinanciera
    cfg = {"configurable": {"thread_id": thread_id or f"q-{uuid.uuid4()}"}, "recursion_limit": 100}
    res, error = {}, None
    with get_usage_metadata_callback() as cb:              # también las llamadas fuera del bucle
        t0 = time.perf_counter()
        try:
            res = agente.invoke({"messages": [{"role": "user", "content": pregunta}]}, config=cfg)
        except GraphRecursionError as e:
            error = f"GraphRecursionError: {e}"
        except Exception as e:                             # 400/401, red, una tool que revienta…
            error = f"{type(e).__name__}: {e}"
        latencia = time.perf_counter() - t0
    if error:                                              # lo que llegó a guardarse del hilo
        try:
            res = agente.get_state(cfg).values or {}
        except Exception:
            res = {}
    mensajes = res.get("messages", [])
    salida = res.get("structured_response")
    if salida is None:
        error = error or "sin structured_response (límite con 'end')"
        salida = esquema(**FALLBACK)
    uso = {m: dict(u) for m, u in cb.usage_metadata.items()}
    en_msgs = uso_en_mensajes(mensajes)
    costes = [m.response_metadata.get("cost") for m in mensajes if isinstance(m, AIMessage)]
    tray = trayectoria(mensajes)
    return {
        "respuesta": salida, "error": error, "thread_id": cfg["configurable"]["thread_id"],
        "tool_calls": tray, "n_llamadas": len(tray),
        "llamadas_modelo": sum(isinstance(m, AIMessage) for m in mensajes),
        "uso": uso, "uso_mensajes": en_msgs, "usd": usd(uso, PRECIOS),
        "tokens_fuera_del_bucle": sum(u.get("total_tokens", 0) for u in uso.values()) - en_msgs["total_tokens"],
        "usd_openrouter": sum(c for c in costes if c) or None,
        "latencia_s": latencia, "modelo": MODELO_ID, "r05": res.get("r05"),
        "errores_esquema": sum(isinstance(m, ToolMessage) and "Failed to parse structured output"
                               in str(m.content) for m in mensajes),
        "observaciones": [{"name": m.name, "tool_call_id": m.tool_call_id, "content": str(m.content)}
                          for m in mensajes if isinstance(m, ToolMessage)
                          and m.name in ("search_filings", "read_section")],   # "vista" de (a)
    }


@lru_cache(maxsize=1)
def agente_final():
    return construir_agente(crear_modelo(), TOOLS, SYSTEM, valor_xbrl, hechos)


def responder(pregunta: str) -> RespuestaFinanciera:
    """R10: siempre devuelve una RespuestaFinanciera válida."""
    return ejecutar(agente_final(), pregunta)["respuesta"]
```

| Campo | Para qué | Nota |
| --- | --- | --- |
| `tool_calls`, `n_llamadas` | (c) y "llamadas/pregunta" (D12, D18) | Lista blanca: fuera la tool sintética. Las llamadas bloqueadas por un límite siguen contando [15 §3.2](15_repo_genai_labs.md) |
| `observaciones` | "vista" del evaluador (a) (D13) | Contenido de los `ToolMessage` de `search_filings` y `read_section` |
| `uso`, `usd` | Coste R11 (D16) | Callback por `model_name`: incluye reescritura y reintentos de R05. Con un modelo sin `model_name` no cuenta nada [16 §3.6](16_repo_transformers_labs.md) |
| `uso_mensajes`, `tokens_fuera_del_bucle` | Contraste | Suma de `usage_metadata` de `messages` [15 §3.6](15_repo_genai_labs.md) |
| `usd_openrouter`, `cache_read` | Contraste del precio | ⚠️ Solo si OpenRouter envía `cost` y `cache_read` |
| `latencia_s` | R11 (D17) | Tras calentar FAISS, bge y BM25 sin llamar al LLM; eso lo hace `evaluar()` |
| `error`, `errores_esquema`, `r05` | Diagnóstico | `llamadas_modelo` incluye el `AIMessage` de aviso de `ModelCallLimit` |

`get_num_tokens()` no se usa: `ChatOpenRouter` no lo redefine y cuenta con el tokenizador de GPT-2 [14 §3] (venv).

## 8. Paso 7: depurar (bucle manual y traza)

**TODO 3 del notebook.** Sus asserts (celda 22) pasan **sin implementar nada**: `inspect.getsource` encuentra `ToolMessage` y `tool_call_id`
en los propios comentarios del TODO [01 §5, fallo 10]. La prueba real es ejecutar `PREGUNTA_DOBLE` y ver la trayectoria. El cuerpo que falta
(dentro de `for tc in respuesta.tool_calls:` de la celda 21):

```python
if verboso:
    print(f"[{vuelta}] {tc['name']}({tc['args']})")
try:
    salida = str(POR_NOMBRE[tc["name"]].invoke(tc["args"]))
except Exception as e:                                   # el error vuelve al modelo, no rompe el bucle
    salida = f"ERROR en {tc['name']}: {type(e).__name__}: {e}"
mensajes.append(ToolMessage(content=salida, tool_call_id=tc["id"], name=tc["name"]))
```

Versión autónoma, con tool calling nativo: [15 §3.3](15_repo_genai_labs.md) (probado). Al historial va el `AIMessage` entero, no su texto
(⚠️ Gemini 3 puede necesitar sus metadatos de razonamiento para encadenar vueltas). **Con `create_agent`:**
`agente.stream(entrada, config=cfg, stream_mode="updates")` da un update por nodo (probado); también `debug=True` [api_stack · create_agent] y
`agente.get_state(cfg).values["messages"]`. Ojo: `pretty_trace` (celda 28) rotula `cita:` pero imprime el `chunk_id` [14 §5, matiz 8].

## 9. Paso 8: casos de comportamiento que hay que ver

**Celda 23: "Compara el margen bruto de Amazon en FY2024 y FY2025…"** AMZN no reporta `GrossProfit` [01 §5, trampa 3].

| | Baseline (sin middleware) | Final |
| --- | --- | --- |
| Si el modelo insiste en reintentar | Lo corta el `recursion_limit=100` del arnés: `GraphRecursionError` tras 50 llamadas a tools (probado); el *fallback* y la causa en `error` | `ToolCallLimit` bloquea desde la 9.ª tool call y `ModelCallLimit` corta en la 12.ª llamada al modelo: 12 tool calls, `structured_response=None`, *fallback* (probado) |
| Si obedece a la herramienta | — | Dos `get_xbrl_fact` en paralelo ("no reportó") y respuesta con `fuente="ninguna"`, `cifra=None` |
| Criterio | R04: termina solo, sin pararlo a mano | R04 y R14: termina solo y declara el hueco. Un margen calculado a partir de otras magnitudes es fallo (D11) |

Sin el arnés, el baseline tendría el `recursion_limit` por defecto de langgraph 1.2.11, 10007 pasos [14 §5, matiz 1] (venv).

**Comparativa de revenue** ("¿Cuánto creció el revenue de Microsoft entre FY2024 y FY2025 y a qué lo atribuye la dirección?"). Trayectoria
esperada, como la de `demo_traza` [demo_traza · pasos 1–4]: `get_xbrl_fact("MSFT", 2024, "RevenueFromContractWithCustomerExcludingAssessedTax")` y el de
2025 en el mismo `AIMessage` (paralelas; no hace falta ampliar la firma [17 §3.3](17_repo_generative_ai.md)), luego `search_filings(<consulta en
inglés>, ticker="MSFT", fiscal_year=2025, item="7", k=5)` y `search_filings(<misma consulta>, ticker="MSFT", fiscal_year=2024, item="7", k=5)`,
una por ejercicio ([07 §5](07_skill_herramientas_docstrings.md)). Respuesta: `fuente="ambas"`, `cifra=281724000000`, `ejercicio=2025`,
`cifra_base=245122000000`, `ejercicio_base=2024`, `unidad="USD"`, cita literal del Item 7 y la variación (+14,9 %) solo en la prosa
[perfil_dataset · xbrl_facts.parquet]. El formato del golden para esto está en [10](10_skill_golden_set.md) (D10).

**Split de NVDA.** El BPA básico reportado baja de 12,05 (FY2024) a 2,97 (FY2025) por el split 10:1 de 2024 [01 §5, trampa 5]. Se comparan los
valores **reportados**, sin ajustar, y la respuesta tiene que decir que no son comparables por el split; concluir que "cayó un 75 %" es fallo.
⚠️ Falta localizar en el texto de NVDA FY2025 una frase sobre el split que sirva de ancla y de cita.

## 10. Paso 9: prueba de humo con la API real (antes del 17)

Todo lo "probado" usa un modelo falso. Esto cuesta céntimos y responde a lo que falta por saber de gemini-3.8-flash por OpenRouter
(hueco 1 del mapa). Guardad la salida en el repo.

```python
def prueba_humo(modelo, agente, tools):
    r = modelo.invoke("Responde solo con la palabra: listo")
    print("1 model_name:", r.response_metadata.get("model_name"), "| cost:", r.response_metadata.get("cost"))
    print("  usage_metadata:", r.usage_metadata)          # ¿cache_read? ¿output_token_details.reasoning?
    r = modelo.bind_tools(tools).invoke("¿Revenue de Microsoft en FY2024 y en FY2025?")
    print("2 tool calls en un solo AIMessage:", [(t["name"], t["args"]) for t in r.tool_calls])
    preg = "¿Cuál fue el revenue de NVIDIA en FY2024?"
    a, b = ejecutar(agente, preg), ejecutar(agente, preg)
    print("3 respuesta:", a["respuesta"], "| error:", a["error"], "| errores_esquema:", a["errores_esquema"])
    print("  uso:", a["uso"], "| usd:", a["usd"], "| usd_openrouter:", a["usd_openrouter"])
    firma = lambda f: [(t["name"], t["args"]) for t in f["tool_calls"]]
    print("4 ¿determinista?", firma(a) == firma(b), a["respuesta"] == b["respuesta"])
    c = ejecutar(agente, "Compara el margen bruto de Amazon en FY2024 y FY2025 y explica a qué se debe el cambio.")
    print("5 celda 23:", c["respuesta"].fuente, c["n_llamadas"], c["error"], c["r05"])
```

| Comprobación | Si falla |
| --- | --- |
| 1: `model_name` casa por prefijo con la tabla de precios | Ajustar las claves de `precios.json`; si no llega `model_name`, el callback no cuenta nada y hay que sumar `uso_mensajes` |
| 1: llega `cost` / `cache_read` / tokens de razonamiento | Si no llega `cost`, el coste es la fórmula; sin `cache_read`, es una cota superior (D16) |
| 2: dos tool calls en un mensaje | Si las pide en serie, la comparativa cuesta una vuelta más: anotarlo en R11 |
| 3: `structured_response` válida, `get_xbrl_fact` en la trayectoria | Mirar `errores_esquema` y los `ToolMessage` de error del esquema |
| 4: misma trayectoria y respuesta dos veces | Si no, `temperature=0` no basta: ejecutar el baseline dos veces y reportar el ruido (D21) |
| 5: termina solo, `fuente="ninguna"` | Revisar el mensaje "no reportó" de la tool y el prompt; mirar `r05` |

Además, en la primera ejecución del golden: cómo reacciona Gemini al mensaje `[VERIFICADOR XBRL]` ([09](09_skill_guardrails_middleware_xbrl.md)).

## 11. Experimento opcional: forzar la herramienta en la primera llamada

`ChatOpenRouter.bind_tools` acepta `tool_choice`, `strict` y `parallel_tool_calls` (venv), y un `wrap_model_call` puede cambiar `tool_choice` solo en
la primera llamada al modelo: el código probado está en [17 §3.3](17_repo_generative_ai.md). Solo para preguntas clasificadas como numéricas,
y midiendo (c), llamadas y coste con y sin él. ⚠️ Falta ver si OpenRouter y Gemini respetan `tool_choice`. No entra en el sistema final si no
mejora la trayectoria.

## 12. Tests sin red

Con un modelo falso: `GenericFakeChatModel` con `bind_tools` que devuelve `self` (patrón de [15 §3](15_repo_genai_labs.md)).

```python
# tests/test_agente.py (SUGERENCIA) · pytest, sin LLM ni red
from langchain.messages import AIMessage
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel


class Falso(GenericFakeChatModel):          # modelo falso: responde lo que le demos, en orden
    def bind_tools(self, tools, **kw):
        return self


TC = {"name": "get_xbrl_fact", "id": "c1", "args": {"ticker": "NVDA", "fiscal_year": 2024, "concept": "Revenues"}}
FIN = AIMessage(content="", tool_calls=[{"name": "RespuestaFinanciera", "id": "s1", "args": {
    "respuesta": "60.922 millones de dólares", "fuente": "xbrl", "cifra": 60_922_000_000,
    "unidad": "USD", "ticker": "NVDA", "ejercicio": 2024, "concept_xbrl": "Revenues"}}])


def test_ejecutar_hilos_nuevos_y_lista_blanca():
    ag = construir_agente(Falso(messages=iter([AIMessage(content="", tool_calls=[TC]), FIN] * 2)),
                          TOOLS, SYSTEM, valor_xbrl, hechos)
    r1, r2 = ejecutar(ag, "¿Revenue de NVIDIA en FY2024?"), ejecutar(ag, "otra")
    assert r1["error"] is None and r1["respuesta"].cifra == 60_922_000_000
    assert [t["name"] for t in r1["tool_calls"]] == ["get_xbrl_fact"]    # sin 'RespuestaFinanciera'
    assert r2["n_llamadas"] == 1 and r1["thread_id"] != r2["thread_id"]  # el hilo no se acumula
```

Probado así (con dos tools de juguete y el `VerificadorXBRL` de [09](09_skill_guardrails_middleware_xbrl.md)): el test anterior; el *fallback*
por `ModelCallLimit` y por `GraphRecursionError` con un modelo que siempre pide tools; y el bucle manual, que empareja cada `ToolMessage`
con su `tool_call_id`. Prueba de extremo a extremo: `evaluar()` con 2 preguntas en un clon limpio [13](13_skill_medicion_informe_presentacion.md).

## 13. Trampas

1. `create_agent(model="openrouter:…")` pierde `temperature=0` sin avisar (venv).
2. Reutilizar `thread_id` entre preguntas: la trayectoria y el coste de la segunda incluyen los de la primera.
3. Leer `resultado["structured_response"]` sin *fallback*: `KeyError`/`None` con `"end"`, recursión o una excepción.
4. Contar como llamada la tool sintética `RespuestaFinanciera`, o deduplicar la trayectoria: esconde bucles (D12).
5. Poner los huecos en el prompt o en `list_available`: el agente acierta "ninguna" sin pasar por `get_xbrl_fact` y suspende (c).
6. Una cifra escalada: `cifra=60922` con `unidad="USD"` es un error ×10⁶ (`error_escala`); lo vigila R05 ([09](09_skill_guardrails_middleware_xbrl.md)).
7. Una clave en un notebook con salidas guardadas: `git grep` antes de cada push.

## Checklist de hecho

- [ ] **R03** · El agente final usa `ToolStrategy(schema=RespuestaFinanciera)`; los 8 campos del contrato están intactos, los añadidos son
      opcionales y el validador rechaza `xbrl` sin cifra, `ninguna` con cifra y `texto` sin cita.
- [ ] **R03** · `ejecutar()` lee `structured_response` y nunca devuelve `None`: el *fallback* está probado con `ModelCallLimit` y con `GraphRecursionError`.
- [ ] **R04** (montaje) · Pila de middleware de D04 en el final, arnés `recursion_limit=100` en los dos sistemas; la celda 23 termina sola
      contra el baseline y contra el final.
- [ ] **R10** · `responder("…")` devuelve una `RespuestaFinanciera` en un clon limpio, con la clave solo en el entorno.
- [ ] **R10/R11** · Cada ejecución guarda trayectoria (lista blanca, sin deduplicar), tokens, USD, latencia, modelo y error.
- [ ] **R13** · Ninguna clave en código, notebooks ni historial (`git grep` vacío); `OPENROUTER_API_KEY` por entorno o `getpass`.
- [ ] Prueba de humo de §10 ejecutada y guardada; dudas anotadas para el 17.
- [ ] Baseline construido con la celda 26 + instancia a `temperature=0` + el mismo arnés, y etiquetado antes de mejorar nada (D19, D21).

## Fuentes

- [enunciado · §4.2, §4.5, §5, §7]: salida estructurada obligatoria, `responder()`/`evaluar()`, contrato.
- [01 §3, §4, §5](01_requisitos_y_contratos.md): contratos, stack fijado, fallos 8–12.
- [notebook S1 · celdas 4, 6, 20–29]: `pedir_clave`, modelo, bucle y TODO 3, celda 23, esquema, `create_agent`, memoria, `pretty_trace`, §6.
- [transcripcion_10sep · 02:14, 02:17–02:24] y [transcripcion_04sep · 00:36], vía [14](14_clase_pistas_del_profesor.md) §2, §3 y §5.
- [15 §3.1, §3.3, §3.6, §3.8, §3.9](15_repo_genai_labs.md); [16 §3.6](16_repo_transformers_labs.md); [17 §3.3, §3.4, §3.6](17_repo_generative_ai.md).
- [api_stack · create_agent, structured_output.ToolStrategy/ProviderStrategy/AutoStrategy, InMemorySaver, AIMessage, ToolMessage].
- [perfil_dataset · xbrl_facts.parquet]: valores de MSFT y NVDA.
- Pruebas propias en el venv del stack (modelo falso): `ToolStrategy` con validador, respuesta y tool en el mismo mensaje, *fallback* por
  límite y por recursión, `get_state` tras el corte, hilos independientes, bucle manual. Decisiones comunes D01–D05, D16–D22, D25.
