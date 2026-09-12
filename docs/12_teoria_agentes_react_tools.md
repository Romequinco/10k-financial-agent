# Teoría: agentes, ReAct y herramientas

> Requisitos: R01–R05 (y R11, R14, R15) · Lee antes: [01_requisitos_y_contratos.md](01_requisitos_y_contratos.md) §3–§5,
> [30_clase_pistas_del_profesor.md](30_clase_pistas_del_profesor.md) §3 · Después: [20_skill_herramientas_docstrings.md](20_skill_herramientas_docstrings.md),
> [21_skill_agente_salida_estructurada.md](21_skill_agente_salida_estructurada.md), [22_skill_guardrails_middleware_xbrl.md](22_skill_guardrails_middleware_xbrl.md)

> Fuentes: [notebook S1 · celdas 0, 9–11, 16–29]; [transcripcion_10sep · 00:05–02:24] vía [30](30_clase_pistas_del_profesor.md); genai-labs
> `01-3-react.ipynb` vía [31 §3–§4](31_repo_genai_labs.md) y nota B1; generative-ai `fc/`, `adp/` y `controlled-generation/` vía
> [33 §3.3–§3.6, §4–§5](33_repo_generative_ai.md) y nota D4; [slides RAG · p.9, p.14–15, p.36–40] vía nota A5; [api_stack · create_agent, middleware,
> structured_output, ToolMessage, InMemorySaver, Deprecados]; verificaciones V1–V4 del mapa de cobertura (nota interna).

**v1.0 · 12-sep-2026.** Cómo funciona un agente con herramientas en nuestro stack (langchain 1.3.18, langchain-core 1.6.1, langgraph 1.2.11) y por
qué el docstring es la interfaz. Sin recetas: el código está en 20–22. Marcas: **(probado)** = ejecutado en el venv del stack con
`GenericFakeChatModel`, sin red (confirma la API y el flujo, no cómo se comporta Gemini); **(venv)** = introspección del código instalado; ⚠️ = sin
verificar. **Revisar tras el 18-sep (ReAct con el paper) y el 19-sep (MCP, ADK y A2A).**

## 1. Del RAG al agente: el retrieval es una herramienta

Un **2-Step RAG** recupera una vez, con `k` fija, y genera. Se queda corto cuando la respuesta está en dos sitios, cuando el dato vive en una tabla
estructurada (XBRL) o cuando la entidad no existe [notebook S1 · celda 0; transcripcion_10sep · 00:05]. En el **Agentic RAG** el modelo decide qué
herramienta usar, cuántas veces y con qué consulta, y si no encuentra algo reformula o cambia de sección [transcripcion_10sep · 00:44;
slides RAG · p.14–15]. De ahí la tesis de la práctica: "el retrieval no es la arquitectura, sino una herramienta más" [enunciado · §1].

| Camino hacia un dato | Tokens de entrada | ¿Cifra exacta? | Auditable por | Uso en la práctica |
| --- | ---: | --- | --- | --- |
| Contexto largo: el 10-K de MSFT FY2025 entero / el corpus | 48.212 / 649.119 | No: sale de prosa o de tablas partidas | — | Nunca para evaluar |
| Búsqueda (`search_filings`, k=5) | ≈ 2.010 | No | `chunk_id` y cita literal | Preguntas cualitativas |
| Consulta exacta (`get_xbrl_fact`) | ≈ 40 | Sí | concepto y FY | Toda cifra |

Datos de [notebook S1 · celda 9] y [02 §4](02_datos_corpus_y_xbrl.md): en entrada, el camino caro sale unas 1.200 veces más caro, y por pregunta
completa unas 30 [notebook S1 · celda 10]. Aunque el corpus quepa en la ventana de Gemini, la cifra no saldría de `get_xbrl_fact` y el camino
contaría como fallo [33 §3.6; enunciado · §1]; además, el dato puede quedar en medio del contexto (*lost in the middle*) [slides RAG · p.37–38].
El valor del agente está en **elegir**: por eso los docstrings son parte de la tarea y "cómo enruta" es un punto de la presentación (R02, R15).

## 2. Tool calling: qué ve el modelo y quién ejecuta

### 2.1 La herramienta, vista desde el modelo

Una *tool* es una función más el esquema que la describe; `@tool` lo genera a partir de la firma y el docstring, y ese esquema viaja en cada
petición [notebook S1 · celda 11]:

| El modelo ve | El modelo no ve |
| --- | --- |
| El nombre, los parámetros con sus tipos, el docstring y lo que devuelve cuando la llama | El cuerpo, los comentarios, lo rápida o cara que es |

"El modelo decide si os llama leyendo el docstring" [notebook S1 · celda 11]; es "literalmente lo que va a leer la IA" [transcripcion_10sep · 01:47].
Con `@tool(parse_docstring=True)` la descripción son los bloques anteriores a `Args:` y cada línea de `Args:` pasa a la descripción del parámetro;
lo que va detrás de `Args:` se pierde (venv; plantilla y pruebas en [20 §3](20_skill_herramientas_docstrings.md)). Lo que llega al proveedor
(`convert_to_openai_tool`, venv), abreviado:

```json
{"type": "function",
 "function": {"name": "get_xbrl_fact",
              "description": "Devuelve el valor EXACTO de una magnitud financiera… Cuándo NO: riesgos… Conceptos (nombre exacto): …",
              "parameters": {"type": "object", "required": ["ticker", "fiscal_year", "concept"],
                             "properties": {"ticker": {"type": "string", "description": "NVDA, MSFT, AAPL, GOOGL, META o AMZN."},
                                            "fiscal_year": {"type": "integer", "description": "Ejercicio fiscal, 2024 o 2025."},
                                            "concept": {"type": "string", "description": "Nombre exacto del concepto us-gaap…"}}}}}
```

### 2.2 Los cinco pasos

Un modelo no ejecuta nada: produce texto o una petición estructurada [notebook S1 · celda 19].

1. Se le mandan los mensajes **y los esquemas** (`modelo.bind_tools(tools)`).
2. Responde con un `AIMessage` de texto vacío o casi y `tool_calls = [{"name", "args", "id"}]` [notebook S1 · celda 20].
3. **Nuestro código** ejecuta la función.
4. Devuelve el resultado como `ToolMessage(content=str, tool_call_id=<id>, name=…)` [api_stack · ToolMessage].
5. Vuelta a empezar hasta que responda sin pedir herramientas.

El `id` empareja cada resultado con su petición cuando hay varias a la vez [notebook S1 · celda 20]; el profesor lo dejó para "cosas bastante más
avanzadas" [transcripcion_10sep · 02:01], pero es obligatorio: sin él, el proveedor no sabe a qué llamada responde cada `ToolMessage`.

### 2.3 Llamadas en paralelo y modos de llamada

- **Paralelas.** Un solo `AIMessage` puede traer varias `tool_calls`; `create_agent` las ejecuta y añade un `ToolMessage` por `id` (probado). En una
  comparativa, los dos `get_xbrl_fact` en el mismo turno ahorran una vuelta de modelo sin ampliar la firma [33 §3.3; generative-ai ·
  fc/parallel_function_calling.ipynb · celdas 3, 27]. `ChatOpenRouter.bind_tools(…, parallel_tool_calls=False)` las desactiva (venv). ⚠️ Falta ver
  si Gemini vía OpenRouter las emite (prueba de humo, [21 §10](21_skill_agente_salida_estructurada.md)).
- **AUTO / ANY / NONE.** En AUTO el modelo decide y puede contestar en prosa sin llamar; ANY obliga a llamar; con NONE contesta con lo aprendido
  en el entrenamiento, el "revenue de memoria" que la trayectoria cuenta como fallo [generative-ai · fc/forced_function_calling.ipynb · celdas 21,
  27, 30, 43, vía 33 §3.3]. En `ChatOpenRouter.bind_tools(tool_choice=…)`: `"auto"`, `"none"`, `"any"` (se traduce a `"required"`), el nombre de una
  tool, o `True` si solo hay una (venv). Dentro de `create_agent` se cambia con un `wrap_model_call` y `request.override(tool_choice=…)`, solo en la
  primera llamada (probado, [33 §3.3]). ⚠️ Sin verificar que OpenRouter y Gemini lo respeten: es un experimento, no el defecto
  ([21 §11](21_skill_agente_salida_estructurada.md)).

### 2.4 Errores como datos

| Qué falla | Qué hace `create_agent` (probado) |
| --- | --- |
| Tipo inválido (`fiscal_year="FY2025"`) | Valida con pydantic antes del cuerpo y devuelve `ToolMessage(status="error")` "Error invoking tool … Input should be a valid integer"; el bucle sigue |
| Tool inexistente | `ToolMessage` de error "… is not a valid tool, try one of […]"; el bucle sigue |
| Excepción dentro del cuerpo | **Se propaga y aborta la invocación**: el manejador por defecto solo convierte los errores de invocación (venv, `_default_handle_tool_errors`) |
| La tool devuelve un texto que explica el problema | El modelo lo lee y corrige, p. ej. "no reportó … conceptos disponibles" [notebook S1 · celda 12] |

Consecuencia: las tools capturan sus errores y devuelven texto [notebook S1 · celda 21, TODO punto 5; transcripcion_10sep · 00:33–00:36], y ese
texto es *prompt*: dice qué hacer después [33 §3.3]. `ToolErrorMiddleware(on_error=…)` convierte excepciones en `ToolMessage` solo si se configura
(*opt-in*) [api_stack · ToolErrorMiddleware].

## 3. ReAct: razonar, actuar, observar

**ReAct** (*Reasoning + Acting*, 2022) alterna *Thought* (razonar), *Action* (llamar a algo externo) y *Observation* (su resultado) hasta terminar
[genai-labs · 01-prompting/01-3-react.ipynb · celda 5, vía 31; notebook S1 · celda 24]. El bucle de la celda 21 es exactamente eso, y el paper se ve
el 18-sep. En el paper y en genai-labs la acción viaja **como texto** (`Answer[…]`, `<STOP>`, `splitlines()`), que se rompe si el modelo responde en
una línea o la consulta lleva ":"; con *tool calling* nativo la acción es `tool_calls`, la observación un `ToolMessage` y la parada, un mensaje sin
`tool_calls` [31 §3.3]. El *Thought* queda dentro del modelo (texto o razonamiento interno ⚠️); lo que se ve y se evalúa es la trayectoria de
acciones.

```python
from langchain.messages import ToolMessage

def bucle_react(modelo_con_tools, por_nombre: dict, mensajes: list, max_vueltas: int = 8):
    """Esqueleto del bucle de la celda 21. Versión probada, con captura de errores: 31 §3.3 y 21 §8."""
    for _ in range(max_vueltas):
        r = modelo_con_tools.invoke(mensajes)             # Thought + Action
        mensajes.append(r)                                # el AIMessage entero, no solo su texto
        if not r.tool_calls:                              # sin Action: respuesta final
            return r
        for tc in r.tool_calls:                           # Observation, emparejada por id
            salida = por_nombre[tc["name"]].invoke(tc["args"])
            mensajes.append(ToolMessage(content=str(salida), tool_call_id=tc["id"], name=tc["name"]))
    raise RuntimeError("Límite de vueltas agotado")       # genai-labs devolvía None en silencio [31 §3.1]
```

**Por qué hay bucles.** El modelo puede volver a predecir acciones anteriores [genai-labs · 01-prompting/01-3-react.ipynb · celda 26]. La celda 23
lo provoca: AMZN no reporta `GrossProfit` y el modelo reintenta con variantes del concepto [notebook S1 · celda 23]. La causa raíz es que la
herramienta no deje claro que el dato no existe; el límite es la red de seguridad [33 §3.5].

**Por qué el coste crece con las vueltas.** Cada llamada al modelo reenvía el historial completo: system prompt, esquemas de las tools, pregunta y
todo lo observado antes [notebook S1 · celda 21; genai-labs · 01-3-react.ipynb · celda 7; 33 §3.6]. Si el agente hace 5 llamadas al modelo y
lee el Item 1A de META FY2025 (34.751 tokens) después de la primera, esa sección entra en las 4 siguientes: ≈ 139.000 tokens de entrada, unos
0,10 $ a 0,75 $/M, frente a los "10, 20 céntimos" por pregunta o sesión que propone el profesor [transcripcion_10sep · 00:28]. Un `get_xbrl_fact`
son unos 40 tokens. Los esquemas de las cuatro tools finales, unos 2.000 tokens (⚠️ estimación), se pagan en **todas** las llamadas
([20 §3](20_skill_herramientas_docstrings.md)). La latencia también crece con el contexto [transcripcion_10sep · 00:28]. Por eso el enrutado barato
(R02), el límite de llamadas (R04) y medir tokens por pregunta (R11) van juntos.

## 4. `create_agent`: el bucle ya hecho

`create_agent` es el bucle de la sección anterior en unas líneas: `tools=` sustituye a `bind_tools` y al diccionario `POR_NOMBRE`,
`response_format=` valida la salida y `checkpointer=` da memoria [notebook S1 · celda 26]. "The process repeats until no more `tool_calls` are
present in the response" [api_stack · create_agent].

- **Modelo: instancia, no cadena.** `model` admite `str | BaseChatModel`; con una cadena, `create_agent` hace `init_chat_model(model)` y se pierde
  `temperature=0` (venv; [01 §5, fallo 9](01_requisitos_y_contratos.md)). Se le pasa la instancia (D01).
- **El grafo** (probado). Sin middleware: `__start__ → model → tools → model → … → __end__`. Con middleware, cada *hook* es un nodo propio
  (`ModelCallLimitMiddleware.before_model`, `VerificadorXBRL.after_model`…). Los `before_model` corren en el orden de la lista y los `after_model`
  en el **inverso**: con `middleware=[A, B]` la secuencia es `A.before → B.before → model → B.after → A.after`. En la pila de D04 el `VerificadorXBRL`,
  último de la lista, es el primero que ve la respuesta del modelo.
- **Estado frente a ventana de contexto.** El estado es el log completo: mensajes, cada tool call y su resultado, `structured_response` y los
  contadores del middleware; "por favor, miraos esto… lo vais a necesitar" [transcripcion_10sep · 02:17, 02:24]. El LLM no ve el estado, solo una
  versión simplificada de los mensajes, sin metadatos [transcripcion_10sep · 02:22–02:23]. Se consulta con `agente.get_state(config)`, que devuelve un
  `StateSnapshot` (venv) [30 §3].
- **Memoria: `checkpointer` + `thread_id`.** Sin checkpointer no hay memoria; sin `thread_id` el checkpointer no sabe a qué conversación va cada
  invocación [notebook S1 · celda 27]. `InMemorySaver` es para depurar y probar [api_stack · InMemorySaver], y nos basta. Para evaluar, **un hilo
  nuevo por pregunta** (D05): con el mismo hilo, `messages` acumula los turnos anteriores, mezcla trayectorias e infla el coste [notebook S1 ·
  celdas 27–28].
- **`recursion_limit`.** Cuenta *supersteps* del grafo, no llamadas. El valor por defecto de langgraph 1.2.11 es **10007** (variable de entorno
  `LANGGRAPH_DEFAULT_RECURSION_LIMIT`); el 25 que circula es el `DEFAULT_RECURSION_LIMIT` de `langchain_core.runnables.config`, no el de langgraph
  (venv). Sin middleware son unos 2 *supersteps* por llamada al modelo; con la pila de D04, unos 6–7, así que 50 cortaría antes que
  `ModelCallLimitMiddleware` y el arnés usa 100 (V2, [22 §2](22_skill_guardrails_middleware_xbrl.md)).

## 5. Salida estructurada: Provider, Tool y Auto

| Estrategia | Firma [api_stack · structured_output] | Cómo funciona |
| --- | --- | --- |
| `ProviderStrategy(schema, *, strict=None)` | Nativa del proveedor | El proveedor fuerza el formato; depende de lo que acepten OpenRouter y Gemini ⚠️ |
| `ToolStrategy(schema, *, tool_message_content=None, handle_errors=True)` | Herramienta sintética | El esquema es una tool más; el modelo la "llama" para responder |
| `AutoStrategy(schema)` | Automática | Elige según las capacidades del modelo |

- **Qué pasa con un esquema suelto** (`response_format=RespuestaFinanciera`, celda 26): "Raw schemas will be wrapped in an appropriate strategy
  based on model capabilities" [api_stack · create_agent]. Con gemini-3.8-flash vía `ChatOpenRouter`, `profile` es `None` y el nombre no está en la
  lista de modelos con salida nativa, así que acaba en **`ToolStrategy`** (V1, venv, código de `langchain.agents.factory`). La celda 26 avisa de que el
  esquema suelto "falla" sin salida nativa [notebook S1 · celda 26]; con este stack no falla, se envuelve (C03). Decisión: `ToolStrategy` explícito
  (D02), con el mismo comportamiento y sin depender del perfil del modelo.
- **Rastro en la trayectoria** (probado, [21 §4](21_skill_agente_salida_estructurada.md)): un `AIMessage` con la tool call `RespuestaFinanciera` y un
  `ToolMessage` "Returning structured response: …". Tres consecuencias: la tool sintética se excluye de la trayectoria con una lista blanca (D12);
  cuenta contra `ToolCallLimitMiddleware` [22 §2]; y `structured_response` **puede ser `None`** si un límite corta antes, así que siempre hay *fallback*.
- **Autocorrección de formato.** Con `handle_errors=True`, un `ValueError` del validador vuelve al modelo como "Error: Failed to parse structured output
  for tool 'RespuestaFinanciera': …" y el modelo reintenta (probado, [33 §3.4]). Sirve para exigir `cita` cuando `fuente` es texto: el esquema del
  contrato no obliga a citar [notebook S1 · celda 25; 30 §5], y los campos opcionales se rellenan "de memoria" si nada lo impide
  [generative-ai · controlled-generation/intro_controlled_generation.ipynb · celda 20, vía 33 §3.4].
- **Opcional u obligatoria** (C02). Para LangChain `response_format` "realmente es opcional" [transcripcion_10sep · 02:14]; para la práctica es
  obligatoria [enunciado · §4.2, §7], porque es lo que permite evaluar leyendo campos.
- `with_structured_output` existe, pero el notebook lo marca como obsoleto y sería una llamada fuera del bucle [notebook S1 · celda 3]; juez y
  reescritor usan `create_agent(model, tools=[], response_format=ToolStrategy(…))`, un solo nodo de modelo [api_stack · create_agent].

## 6. Middleware: hooks y límites

| Hook [api_stack] | Cuándo corre | Devuelve | Uso en la práctica |
| --- | --- | --- | --- |
| `before_agent` / `after_agent` | Una vez por invocación | Actualizaciones de estado | Registro al final (opcional) |
| `before_model` | Antes de cada llamada al modelo | Estado, `jump_to` | `ModelCallLimitMiddleware` corta aquí |
| `wrap_model_call` | Envuelve cada llamada; recibe `ModelRequest` y `handler` | `ModelResponse` | Forzar `tool_choice` en la primera llamada (experimento) |
| `after_model` | Tras cada respuesta del modelo | Estado, `jump_to` | `VerificadorXBRL` (R05); `ToolCallLimitMiddleware` |
| `wrap_tool_call` | Envuelve cada ejecución; recibe `request.tool_call` y `request.state` | `ToolMessage` o `Command` | `sin_repetir` (opcional, [22 §3](22_skill_guardrails_middleware_xbrl.md)) |
| `dynamic_prompt` | Construye el system prompt en cada llamada | `str` | No hace falta: prompt estático |

- **Saltos.** `@hook_config(can_jump_to=["tools", "model", "end"])` en `before_model`/`after_model` [api_stack · hook_config]. Un `after_model` que
  devuelve `{"messages": [HumanMessage(…)], "jump_to": "model"}` hace responder otra vez al modelo; en la segunda pasada puede sustituir
  `structured_response` (V3, probado): es el mecanismo de R05 ([22 §5](22_skill_guardrails_middleware_xbrl.md)).
- **Límites de serie** [api_stack · ToolCallLimitMiddleware, ModelCallLimitMiddleware]: `ToolCallLimitMiddleware(*, tool_name=None, thread_limit=None,
  run_limit=None, exit_behavior="continue")`, con `"continue"`, `"end"` o `"error"`, y `ModelCallLimitMiddleware(*, thread_limit=None,
  run_limit=None, exit_behavior="end")`. `run_limit` cuenta por invocación y `thread_limit` acumula en el hilo. Con `"continue"` la llamada que
  excede recibe "Tool call limit exceeded…" pero, si el modelo insiste, **nada lo para**; `ModelCallLimit` es el corte duro, con
  `structured_response=None` (probado, [33 §3.5]). De ahí la pila de D04: `ToolCallLimit(8)`, `ToolCallLimit(read_section, 2)`, `ModelCallLimit(12,
  "end")` y `VerificadorXBRL`, más `recursion_limit=100` en el arnés.
- **De serie, pero fuera de lo evaluado:** `ModelFallbackMiddleware` cambia el modelo evaluado y reintenta con los otros en cada fallo, sin
  recordar nada [30 §3]; `ModelRetryMiddleware` duplicaría el `max_retries=2` de `ChatOpenRouter` [22 §8]; `SummarizationMiddleware` sustituye el
  historial por un resumen y perdería el texto literal de las citas [33 §3.6]; `LLMToolSelectorMiddleware` es otra llamada al LLM para elegir entre
  solo cuatro tools; `HumanInTheLoopMiddleware` necesita personas, y `evaluar()` corre solo [api_stack].

## 7. Patrones

**Router exacta / difusa.** En nuestro diseño el router es el propio modelo leyendo docstrings y `SYSTEM`: cifra → `get_xbrl_fact`; cualitativa →
`search_filings`; duda sobre el universo → `list_available`; `read_section`, último recurso. Eso es lo que se enseña en "cómo enruta" y se mide con
P/R/F1 por herramienta y la matriz familia × herramienta ([20 §9](20_skill_herramientas_docstrings.md), [25 §4](25_skill_evaluadores.md)). Un router
explícito previo (razonar antes de clasificar y un destino "Unsupported") [generative-ai · adp/semantic-router.ipynb · celdas 18, 21, vía 33 §3.3]
o el *query routing* de las slides [slides RAG · p.39] cuestan una llamada más; "fuera del corpus" lleva a `fuente="ninguna"`, no a bloquear. Solo
como experimentos medidos.

**Planner para comparativas.** Descomposición en un paso: una subpregunta por ejercicio [slides RAG · p.36]. La trayectoria de `demo_traza` lo
hace: dos `search_filings` con la misma consulta y filtros, una por FY, y dos `get_xbrl_fact` con el mismo concepto [demo_traza · pasos 1–4, vía
nota A1]. Basta con el plan en el prompt ([21 §5](21_skill_agente_salida_estructurada.md)) y llamadas en paralelo; un planner multiagente es mucho
más lento [generative-ai · adp/README.md · l. 88, vía 33 §5], y un agente por documento serían 48 [slides RAG · p.40]. Trampa: el split 10:1 de NVDA;
se comparan valores reportados y se dice [01 §5, trampa 5].

**Autocorrección (*self-correction*).** Tres lazos, siempre con contador: el texto de error de la tool (el modelo repite con otros argumentos); los
errores de validación de `ToolStrategy`; y R05, que devuelve el desajuste con `jump_to="model"`, un reintento como máximo y, si persiste, abstención
(V3, D15). El anti-patrón es el crítico→editor sin contador [33 §3.5]. En retrieval: reintentar sin `item` si no hay resultados [slides RAG · p.36],
medido aparte [24 §5](24_skill_mejora_retrieval.md).

**Guardrails.** "Una herramienta no es una garantía, es una opción que el modelo puede tomar" [notebook S1 · celda 16]; los guardrails convierten
opciones en garantías. Mejor deterministas y en código, con tests, que en el prompt o con un LLM crítico: en zero-trust el límite del reembolso solo
estaba en el prompt y la función no lo comprobaba [33 §3.5]. Capas: entrada (fuera de corpus: no se bloquea, lo resuelven tools y prompt,
[22 §8](22_skill_guardrails_middleware_xbrl.md)); herramienta (validación y errores como texto); salida (esquema, validador y R05); bucle (límites).

**Principios de diseño de tools** (detalle en [20 §2](20_skill_herramientas_docstrings.md)): devuelven texto, "o algo asimilable como texto"
[transcripcion_10sep · 00:31]; son idempotentes y normalizan sus entradas [transcripcion_10sep · 01:24]; no revientan; no vuelcan datos masivos
[transcripcion_10sep · 02:12]; dicen "no está" con claridad y nunca con un 0 [33 §3.3]; declaran su coste; y no esconden llamadas a otras tools del
contrato, que la trayectoria no vería [30 §3].

## 8. API obsoleta frente a la actual

Los asistentes de IA proponen API desfasada de LangChain incluso con la documentación delante [transcripcion_10sep · 01:42]: la referencia es
`api_stack_langchain.md`. Estado en el venv del stack (probado):

| Obsoleto | Estado en el venv | Hoy |
| --- | --- | --- |
| `langgraph.prebuilt.create_react_agent(…, prompt=…)` | Importa; al llamarlo avisa de que "has been moved to `langchain.agents`" | `langchain.agents.create_agent(…, system_prompt=…)` |
| `MemorySaver` | Es un alias de `InMemorySaver` | `InMemorySaver` |
| `modelo.with_structured_output(…)` | Existe | `response_format=ToolStrategy(…)` dentro del agente |
| `RunnableWithMessageHistory` | Importa (`langchain_core.runnables.history`) | `checkpointer` + `thread_id` |
| `initialize_agent`, `AgentExecutor`, `AgentType` | `ImportError` | `create_agent` + `@tool` |
| `LLMChain`, `ConversationChain`, `langchain.memory` | `ModuleNotFoundError` | `prompt \| modelo`; `checkpointer` |
| `MessageGraph` | Deprecado en v1.0, se quita en v2.0 [33 §4] | `create_agent` |
| ReAct por texto (`Answer[`, `<STOP>`) | — | `tool_calls` + `ToolMessage` |
| `create_agent(model="openrouter:…")` | Funciona, pero sin `temperature=0` | `create_agent(model=init_chat_model(…, temperature=0))` |
| `openrouter:auto`, `ModelFallbackMiddleware` | Funcionan | Modelo fijo en todo lo evaluado [notebook S1 · celda 6] |

`create_react_agent`, `MemorySaver`, `with_structured_output` y `RunnableWithMessageHistory` son los cuatro que el notebook marca como obsoletos
[notebook S1 · celda 3]; el resto sale de [31 §4](31_repo_genai_labs.md) y [33 §4](33_repo_generative_ai.md).

## 9. MCP, A2A y ADK: solo una mención

Se ven el 19-sep, con un notebook extra [01 §1]. En pocas palabras (definición general, ⚠️ a completar tras la clase): **MCP** es un protocolo para
exponer herramientas y recursos desde un servidor a cualquier agente; **A2A**, un protocolo para que agentes hablen entre sí; **ADK**, el
framework de agentes de Google con el que se dan las sesiones V y VI del módulo de NLP [slides agenda · p.8–9, vía nota A6]. Para la práctica no
cambian nada: el stack fijado es LangChain/LangGraph, las cuatro tools corren en el mismo proceso y el evaluador de trayectoria busca sus nombres
[enunciado · §7]. Un servidor MCP añadiría latencia y un punto de fallo más en el clon limpio (R10).

## 10. Qué implica para la práctica

- **R01/R02:** el docstring es la interfaz que ve el modelo; vocabulario cerrado, "cuándo NO" y coste, sin nada detrás de `Args:`
  ([20](20_skill_herramientas_docstrings.md)).
- **R01/R14:** las tools no lanzan y sus mensajes de error dicen qué hacer; "no reportó" y `list_available` son la base de la honestidad.
- **R03:** `ToolStrategy(schema=RespuestaFinanciera)` explícito, *fallback* cuando `structured_response` es `None`, validador para exigir la cita
  ([21 §3–§4](21_skill_agente_salida_estructurada.md)).
- **R04:** `continue` no basta; `ModelCallLimit` corta y `recursion_limit=100` protege también al baseline ([22 §2](22_skill_guardrails_middleware_xbrl.md)).
- **R05:** un `after_model` con `jump_to="model"`, determinista y con un reintento ([22 §5](22_skill_guardrails_middleware_xbrl.md)).
- **R09c/R11:** la trayectoria es la lista de `tool_calls` de la invocación, con lista blanca y sin deduplicar; un hilo por pregunta; el coste crece
  con las vueltas porque el historial se reenvía.
- **R15:** material para contar: la asimetría de coste de los tres caminos, el experimento de docstrings y cómo enruta el agente.

## Fuentes

- [enunciado · §1, §4.2, §5, §7]; [01 §1, §3–§5](01_requisitos_y_contratos.md).
- [notebook S1 · celdas 0, 3, 6, 9–11, 16, 18–29]: RAG frente a agente, coste de los tres caminos, qué ve el modelo, cinco pasos, bucle y TODO 3,
  celda 23, ReAct, `RespuestaFinanciera`, `create_agent`, memoria y trayectoria.
- [transcripcion_10sep · 00:05, 00:28, 00:31–00:49, 01:24, 01:42–01:47, 02:01, 02:12–02:24], vía [30 §2–§3](30_clase_pistas_del_profesor.md).
- genai-labs `01-prompting/01-3-react.ipynb` (celdas 5, 7, 26–27) vía [31 §3.1–§3.3, §4](31_repo_genai_labs.md) y nota B1.
- generative-ai `fc/forced_function_calling.ipynb`, `fc/parallel_function_calling.ipynb`, `adp/semantic-router.ipynb`, `adp/README.md` y
  `controlled-generation/` vía [33 §3.3–§3.6, §4–§5](33_repo_generative_ai.md) y nota D4.
- [slides RAG · p.9, p.14–15, p.36–40] vía nota A5; [slides agenda · p.8–9] vía nota A6; `demo_traza.json` vía nota A1.
- [api_stack · create_agent, ToolCallLimitMiddleware, ModelCallLimitMiddleware, AgentMiddleware y hooks, hook_config, ToolErrorMiddleware,
  structured_output.*, ToolMessage, InMemorySaver, Deprecados]; venv: `ChatOpenRouter.bind_tools`, `DEFAULT_RECURSION_LIMIT`,
  `_default_handle_tool_errors`, grafo de `create_agent` y orden de los hooks.
- Docs hermanos: [20](20_skill_herramientas_docstrings.md), [21](21_skill_agente_salida_estructurada.md), [22](22_skill_guardrails_middleware_xbrl.md),
  [24 §5](24_skill_mejora_retrieval.md), [25 §4](25_skill_evaluadores.md), [02 §4](02_datos_corpus_y_xbrl.md).
