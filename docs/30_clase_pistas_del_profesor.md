# Pistas de clase para la práctica

> Fuentes: transcripciones del 4, 5 y 10 de septiembre, notebook de la sesión 1 y slides del módulo NLP (material no versionado, en docs/raw/).

**v1.0 · 12-sep-2026.** Consolida las notas de trabajo A1 (notebook S1), A2 (transcripción del 10-sep), A34 (teoría NLP),
A5 (slides de RAG) y A6 (Tuning y agenda). Cada afirmación crítica se ha contrastado con la fuente original y, las de API,
con el stack instalado. Solo recoge lo que **no está, o no está claro,** en el [enunciado](00_enunciado.md) y en
[01_requisitos_y_contratos.md](01_requisitos_y_contratos.md), cuyos IDs `Rxx` se usan aquí.

Citas: `[transcripcion_10sep · hh:mm]` = marca de la transcripción (ASR corregido por contexto); `[notebook S1 · celda N]`
(celdas desde 0); `[slides X · p.N]` = página del PDF; `[api_stack · sección]` = `docs/raw/_texto/api_stack_langchain.md`;
**(venv)** = comprobado por introspección en el venv con el stack fijado; **(probado)** = ejecutado en ese venv con un modelo
falso, sin red (confirma la API, no el comportamiento de Gemini). Profesores: Guillermo Fajardo (práctica) y Rafael Sánchez
(módulo NLP) [transcripcion_10sep · 00:00; slides RAG · p.1].

## 1. Qué hicimos en la sesión 1 y qué hay que tener para el 17

La sesión (2 h 34 min) recorrió en directo el notebook S1:

1. **Tesis.** Un RAG "por sí solo se queda… un poquito corto": falla con datos en tablas y con respuestas repartidas en
   varios puntos. El retrieval pasa a ser una herramienta de un agente que itera y cambia de sección
   [transcripcion_10sep · 00:00, 00:05, 00:44; notebook S1 · celda 0].
2. **Coste del corpus y latencia** [transcripcion_10sep · 00:26–00:28; notebook S1 · celdas 9–10].
3. **Las cuatro tools.** `get_xbrl_fact` y `search_filings` venían hechas; `read_section` es la vía cara; `list_available`
   se programó en directo (ejercicio 1) [transcripcion_10sep · 00:31–01:47; notebook S1 · celdas 12–15].
4. **Ejercicio 2** (mismo código, docstring vago): no se resolvió. La solución llegará "justo antes de la siguiente clase"
   [transcripcion_10sep · 01:56–01:58; notebook S1 · celda 17].
5. **Del modelo al agente.** `bind_tools` → bucle manual (ReAct) → `create_agent` con `RespuestaFinanciera` → estado y
   trayectoria → coste con los metadatos de uso [transcripcion_10sep · 01:58–02:24; notebook S1 · celdas 19–29].
6. **La práctica**, contada en los últimos diez minutos [transcripcion_10sep · 02:24–02:31]. Hubo varios fallos en vivo (§5).

**Para el jueves 17** [notebook S1 · celda 33]. En clase no se detallaron los deberes: mandan la celda 33 y el enunciado (§2).

- [ ] **Baseline corriendo**: el notebook ejecutado de arriba abajo *en vuestro repositorio*, con `responder()` y `evaluar()`.
  El 17 empieza ejecutando cada agente contra **cinco preguntas duras**; sin agente, "la primera hora se convierte en
  soporte técnico".
- [ ] **20 preguntas propias** que pasen `validar()`, con al menos 6 comparativas.
- [ ] Recomendado:
  - los 3 TODO comprobados **ejecutando**, no solo con los asserts (§5);
  - el baseline congelado con etiqueta git;
  - un `thread_id` nuevo por pregunta;
  - un tope de pasos en el arnés (§5, fallo 1).
- Hay un notebook de rescate, pero "quien lo use empieza la sesión sin conocer su propio código" [notebook S1 · celda 33].

## 2. Aclaraciones del profesor sobre el enunciado

| Tema | Qué dijo | Cita | Implicación para nosotros |
| --- | --- | --- | --- |
| **Fecha de entrega** | "las prácticas que vais a tener que entregar el 24"; "se entrega el 24". El notebook titula un apartado "Qué se entrega el 24" | [transcripcion_10sep · 00:00, 00:08; notebook S1 · celda 0] | El enunciado fija el **23-sep a las 23:59**: "justo antes de la sesión 3", y el 24 son las ciegas y la presentación [enunciado · Datos básicos, §2]. Límite: el 23. Confirmarlo (§8) |
| **Formato** | "que sea un notebook… No, perdón, que sea un GitHub": así el código "se queda como fijo" y él puede verlo. Además, "lo vais a tener que presentar, aunque sea brevemente" | [transcripcion_10sep · 02:31] | Repo con funciones importables; el notebook, como mucho, de demo. Preparar un recorrido corto del código para la presentación |
| **Embeddings** | "vais a tener que seleccionar un modelo para hacer embeddings"; son ligeros y cargan en Colab, y también los hay en OpenRouter. "Vais a tener que hacer embeddings por vuestra cuenta" y guardarlos, o se regeneran en cada ejecución | [transcripcion_10sep · 02:26, 02:31] | El enunciado entrega el índice FAISS de bge-small ya construido [enunciado · §3]. Cambiar de modelo obliga a reindexar (§7) y no sustituye a los tres arreglos de R08. Si se hace, el índice nuevo va persistido en el repo con su manifiesto. ⚠️ Confirmar si es obligatorio (§8) |
| **Contra qué se mide** | "os vais a medir… con estos set de 20 preguntas con la versión básica y elemental que he hecho yo, con la que hagáis vosotros" | [transcripcion_10sep · 02:26] | El baseline es su agente: las tools y el `create_agent` del notebook. No aclara si las 20 son las oficiales o las propias; el notebook habla de 20 oficiales + 20 propias [notebook S1 · celda 30] y la tabla va sobre el golden propio [enunciado · §5] |
| **De dónde sale la mejora** | "sobre todo" de la parte RAG: "cómo he dividido los trozos del texto, cómo he buscado los ítems". Su versión es "bastante sencilla" y "luego los warrers" (⚠️ probablemente *rerankers*) | [transcripcion_10sep · 02:26] | Los tres arreglos de R08 son el mínimo. El troceado y el reranking son extras que también hay que medir; el 17 "vais a cambiar el troceado" (§6) |
| **`response_format`** | La celda Pydantic es "bastante importante y la vais a tener que utilizar", pero "lo del response format realmente es opcional. Te lo podría dar en texto" | [transcripcion_10sep · 02:14] | Es opcional para LangChain y **obligatorio** para la práctica (R03) |
| **`list_available`** | Si en el prompt le dices qué empresas y años tiene, "esta función ya no tiene sentido"; la tool tiene sentido con un corpus dinámico | [transcripcion_10sep · 01:23] | Es contrato [enunciado · §7]: se mantiene. Poner además el universo en el `SYSTEM` es compatible. ⚠️ Cómo lo trata el evaluador de trayectoria (§8) |
| **Evaluadores** | "minifunciones" que te digan "si lo ha hecho bien, si lo ha hecho mal, si se ha inventado algo, si te ha dicho que no había respuesta cuando sí que había" | [transcripcion_10sep · 02:29] | Además de cita, cifra y trayectoria (R09), medir los **falsos "ninguna"** (R14): preguntas con dato en el corpus respondidas con `fuente="ninguna"` |
| **Setup** | Se configura "exactamente igual que se ha seteado hoy en clase"; "no tenéis que descargar nada de EDGAR" | [transcripcion_10sep · 02:26] | Coincide con [enunciado · §3]. El clon limpio necesita los ZIP del corpus sin pasos manuales |
| **Golden set** | "Golden data de 20 preguntas con respuesta… que vosotros sepáis". Sobre las preguntas y las respuestas: "eso sí me lo vais a tener que entregar igualmente" | [transcripcion_10sep · 02:26, 02:31] | No dijo nada de comparativas, anclas ni validador: mandan [notebook S1 · celdas 30–32] |
| **Elección de modelo** | Un "metamodelo" que pase de un modelo gratuito a uno de pago, el modelo "mixto" de OpenRouter, y comparar varios gratuitos con uno de pago como experimento | [transcripcion_10sep · 00:18–00:20, 00:28] | Solo en desarrollo. Lo que se evalúa va con modelo fijo y `temperature=0`, sin `openrouter:auto` [notebook S1 · celda 6]. La comparación de modelos cabe en "qué se probó" (R15) |
| **`id` de la tool call** | Se usa "para cosas bastante más avanzadas que ahora mismo no son muy relevantes" | [transcripcion_10sep · 02:01] | Empareja cada resultado con su petición y hay un assert sobre `tool_call_id` [notebook S1 · celdas 20–22]: propagarlo siempre |
| **Consulta de búsqueda** | En la demo, la `query` era "literalmente la pregunta que podría hacer un usuario" | [transcripcion_10sep · 00:44] | El corpus está en inglés y la consulta debe ir en inglés [notebook S1 · celdas 13, 21]. Es el primer caso de la reescritura de R08 |
| **Dificultad** | "Es una práctica sencillita": hacer lo mismo que en clase "un poquito mejor", metiéndose "en las tripas de cómo funcionan las funciones" | [transcripcion_10sep · 02:29] | Prioridad: tools y retrieval medidos, no una arquitectura nueva |

## 3. Consejos y avisos del profesor

**Herramientas y docstrings**
- Una tool es una función de Python con "una capa por encima" que explica qué hace, qué devuelve y cómo son sus
  parámetros. Debe devolver texto, "o algo asimilable como texto", por ejemplo un JSON. El LLM nunca ve el código
  [transcripcion_10sep · 00:31].
- El parámetro débil de `get_xbrl_fact` es `concept`: con el ticker y el año hay poco riesgo, pero en US-GAAP "puede haber
  diferentes nombres para el mismo concepto" [transcripcion_10sep · 00:33]. → El docstring debe enumerar los conceptos y
  la regla del revenue (R02; [01_requisitos §5](01_requisitos_y_contratos.md), trampa 2).
- Que no revienten: si falta el dato, la tool devuelve un texto que explique el caso. Si peta, "te va a petar el
  programa completamente" [transcripcion_10sep · 00:33–00:36].
- `@tool` es "la manera más simple… no es la mejor": con muchas variables hay que definirlas una a una. El docstring es
  "literalmente lo que va a leer la IA" para decidir. "Úsala siempre antes de responder que un dato no existe" vale "no
  solo al principio, sino cuando creas que no lo tienes" [transcripcion_10sep · 01:47].
- Ante un caso raro de enrutado, el cuerpo pide ir alargando la descripción; lo correcto es "una mejor redacción"
  [transcripcion_10sep · 01:58].
- `list_available`, lo más concisa posible: nombre de la empresa, ejercicios e items (el título puede ser mejor que el
  código del item). Sobran el texto, el número de tokens y la URL [transcripcion_10sep · 01:19].
- Nada de volcar datos masivos por una tool. Devolver en texto el OHLC diario de NVIDIA de muchos años es un "suspenso"
  [transcripcion_10sep · 02:12].
- Una tool puede llamar a otra, e incluso a otro agente. El caso típico: "esta tool intenta hacer esto y, si ve que no es
  capaz, al menos te devuelve lo que te daría otra tool" [transcripcion_10sep · 00:46–00:49]. ⚠️ Inferencia nuestra: esa
  llamada interna no aparece en la trayectoria, y el evaluador busca los nombres de las cuatro tools [enunciado · §7]. No
  hay que esconder un `get_xbrl_fact` dentro de `search_filings`.
- Los datos se normalizan en su capa, no en el agente: "cada unidad tiene que ser completamente independiente,
  funcional e idempotente" [transcripcion_10sep · 01:24].
- "Este tipo de funciones son las que vais a tener que modificar, recrear o ampliar en la práctica"
  [transcripcion_10sep · 00:52].

**Enrutado**
- Que el agente tenga "un pelín de contexto" para llamar bien a `search_filings` "depende un poco de vosotros"
  [transcripcion_10sep · 00:36]. En la demo eligió el Item 1A porque la pregunta hablaba de riesgos
  [transcripcion_10sep · 00:44].
- `list_available` evita búsquedas absurdas. Si preguntan por el beneficio del Banco Santander en 2005, "lo lógico sería
  que ni llegara a intentarlo" [transcripcion_10sep · 01:09].
- `read_section` es la herramienta "a saco". Leer 34.000 tokens de META 1A en cada pregunta "no tiene demasiado sentido";
  solo si no hay otra salida [transcripcion_10sep · 00:44, 00:49].

**RAG frente a agente**
- El RAG trocea, calcula embeddings y recupera los k fragmentos más relevantes. Falla con datos en tablas y con
  respuestas que están en varios puntos [transcripcion_10sep · 00:05].
- La diferencia es que el agente no busca una vez y dice "no lo sé": reflexiona e investiga, yendo a otras secciones
  hasta encontrar la información [transcripcion_10sep · 00:44].

**Estado, trayectoria y evaluación**
- El estado es el log: mensajes, cada tool call y lo que devolvió. "Por favor, miraos esto… lo vais a necesitar para la
  práctica" [transcripcion_10sep · 02:17, 02:24]. El LLM **no** ve el estado, solo "una versión simplificada" de los
  mensajes [transcripcion_10sep · 02:22].
- El `config` (`thread_id`) identifica cada conversación para no mezclarlas [transcripcion_10sep · 02:19]. Leyó el
  estado con `get_state` [transcripcion_10sep · 02:19–02:23]; en el stack es `agente.get_state(config)` y devuelve un
  `StateSnapshot` **(venv)**. En `evaluar()`, un `thread_id` nuevo por pregunta: con el mismo hilo, `messages` acumula
  los turnos anteriores [notebook S1 · celda 27].

**Coste y latencia**
- Las APIs cobran la entrada más barata que la salida. Con Gemini 3.8 Flash (0,75 $/M de entrada), leer los ~650.000
  tokens del corpus cuesta menos de 0,75 $ [transcripcion_10sep · 00:26].
- La idea es minimizar lo que lee el LLM. Una pregunta, o una sesión de preguntas, debería salir por "10, 20 céntimos"
  [transcripcion_10sep · 00:28].
- El tiempo de respuesta "cambia drásticamente" con 200.000 tokens en contexto frente a ninguno [transcripcion_10sep ·
  00:28]. → La columna de latencia (R11) penaliza `read_section`.
- Hay que medir: sumar los metadatos de uso de cada mensaje (tokens y, si la API lo da, coste). Así se defiende una
  mejora con datos, como "hemos gastado un 30 % menos de tokens" con preguntas de longitud parecida. Si no se mide, el
  coste "se va muy rápido de madre" [transcripcion_10sep · 02:24].
- En el stack:
  - `AIMessage.usage_metadata` trae `input_tokens`, `output_tokens` y `total_tokens` [api_stack · AIMessage].
  - `ChatOpenRouter` 0.2.8 rellena `usage_metadata` y, si OpenRouter devuelve `cost`, lo copia a
    `response_metadata["cost"]` **(venv, código fuente)**. ⚠️ Falta comprobar con una llamada real si `cost` llega sin
    pedirlo.
  - `get_num_tokens()` no sirve: `ChatOpenRouter` no lo redefine y se usa el tokenizador GPT-2 por defecto de
    langchain-core **(venv)**.

**Modelo y proveedor**
- Gemini 3.8 Flash cuesta "céntimos": mejor ponerle un presupuesto pequeño que depender del tier gratuito de Gemini,
  que "suele acabarse bastante pronto" [transcripcion_10sep · 00:16].
- La cuenta de OpenRouter es gratuita. Se puede cargar, por ejemplo, 10 € sin recarga automática. Cree que el precio
  es el mismo que con el proveedor directo ("creo") [transcripcion_10sep · 00:23].
- El comportamiento con tools depende del modelo. La demo SIN/CON `list_available` no salió, y lo atribuyó a que "a lo
  mejor he puesto un modelo más tonto" [transcripcion_10sep · 01:54].
- Su "metamodelo" gratis → pago (una variable que recuerde que se agotó la cuota [transcripcion_10sep · 00:20]) ya existe
  en el stack como `ModelFallbackMiddleware(first_model, *additional_models)`. Ojo: reintenta con los otros modelos **en
  cada** llamada que falla, sin recordar nada **(venv)**. Solo vale en desarrollo, porque cambia el modelo evaluado.

**Librerías y asistentes de programación**
- Los asistentes de IA proponen API desfasada de LangChain, incluso con el enlace a la documentación delante
  [transcripcion_10sep · 01:42]. LangChain mete muchos *breaking changes* [transcripcion_10sep · 02:19].
- Recomienda:
  - Context7 como *skill*, y pedir en el `CLAUDE.md` que se use la documentación actualizada o, en proyectos con
    versiones fijadas, la de esa versión leyendo los requirements [transcripcion_10sep · 01:51];
  - Perplexity para consultar documentación [transcripcion_10sep · 01:42].
  → Nuestra referencia es `api_stack_langchain.md`.
- Usar la IA "como una palanca con la que aprender" y no para que lo haga todo: con poco contexto "se va de madre"
  [transcripcion_10sep · 00:23].

**Datos y claves**
- "Daos un paseíto por el dataset": mirar los DataFrames afina muchísimo la intuición y es clave para mejorar un RAG
  sobre datos financieros [transcripcion_10sep · 02:29].
- Las claves van siempre en un almacén de secretos: una clave publicada por error ha llegado a generar "facturas de
  cientos de miles de dólares" (R13) [transcripcion_04sep · 00:36].

## 4. Preguntas de alumnos y respuestas

Anonimizadas. Todas son del 10-sep salvo la última.

| Pregunta | Respuesta | Cita |
| --- | --- | --- |
| ¿Algún modelo gratuito con límites altos para probar? | OpenRouter tiene varios (menciona Nemotron, de NVIDIA). El tier gratuito de Gemini se acaba pronto, y Gemini 3.8 Flash cuesta céntimos | [transcripcion_10sep · 00:16–00:18] |
| ¿Se pueden encadenar modelos cuando se acaban los tokens? | Sí: capturando el error concreto de cuota. Lo escribió en pseudocódigo y se corrigió: hace falta una variable para no reintentar el gratuito en cada llamada | [transcripcion_10sep · 00:17–00:20] |
| ¿Conviene darse de alta en OpenRouter? | Sí. La documentación de Google está "por 50 sitios diferentes" y su tier gratuito es más corto de lo anunciado | [transcripcion_10sep · 00:23] |
| (Pregunta del profesor) ¿Qué problema tendría el LLM con `get_xbrl_fact`? | Un alumno: pasarle los valores correctos. El profesor: sobre todo el `concept` | [transcripcion_10sep · 00:31–00:33] |
| ¿Puede una tool usar otra? | Sí, e incluso llamar a otro agente especialista | [transcripcion_10sep · 00:46–00:49] |
| ¿El agente llama a `list_available` cuando lo necesita? | Depende. Con un dataset conocido basta con ponerlo en el prompt; con un corpus dinámico, hace falta la tool | [transcripcion_10sep · 01:23] |
| ¿Y si cambia la estructura de los datos? | El proveedor o el scraper deben mantener una estructura coherente; lidiar con eso no es trabajo del agente | [transcripcion_10sep · 01:24] |
| ¿Hay alguna skill para consultar documentación al día? | Context7 | [transcripcion_10sep · 01:45–01:51] |
| ¿El agente decide por las descripciones de las tools? | Sí: ve el system prompt y las tools, y la descripción es lo que lee para elegir | [transcripcion_10sep · 01:47] |
| ¿Queda un log de las tools y de las respuestas intermedias? | Sí, es el estado | [transcripcion_10sep · 02:17] |
| ¿La ventana de contexto es todo el estado? | No. El LLM ve una versión simplificada de los mensajes, sin la metadata | [transcripcion_10sep · 02:22–02:23] |
| ¿El coste se calcula multiplicando tokens por precio? | No hace falta: muchas APIs devuelven el coste en cada mensaje, o al menos los tokens en los metadatos de uso | [transcripcion_10sep · 02:24] |
| ¿El entregable va en notebook o por terminal con parámetros? | En GitHub, con los embeddings guardados. No precisó la interfaz | [transcripcion_10sep · 02:31] |
| En Colab sale "no se ha podido preparar el corpus" | Los ZIP estaban mal colocados: lo de "clase 1" va fuera y lo del dataset, dentro de su carpeta. Además, en `CANDIDATOS_CORPUS` de `miax_s1.py` hay que dejar solo las primeras rutas | [transcripcion_10sep · 00:55–00:59] |
| Una pregunta sobre Apple falla con errores 400/401 | Un alumno apuntó a que algunas IPs de Google (Colab) podían estar bloqueadas, y el profesor lo vio posible | [transcripcion_10sep · 02:10–02:12] |
| (04-sep) ¿Los tokenizadores modernos cubren todos los idiomas? | Sí, son multilingües. Gemma tiene 256.000 tokens de vocabulario | [transcripcion_04sep · 03:05] |

## 5. El notebook S1: TODO, asserts y fallos conocidos

| Pieza | Qué comprueba | ¿Es una prueba real? |
| --- | --- | --- |
| TODO 1, `list_available` (celda 15) | §3 (celda 17): que su salida contenga `"NVDA"` | Sí. Sin hacer, la tool devuelve `None` y §3 falla |
| TODO 2, docstring vago (celda 17) | Nada | No hay assert. Solución prometida antes del 17 [transcripcion_10sep · 01:58] |
| TODO 3, cuerpo del bucle (celda 21) | §5 (celda 22): `ToolMessage` y `tool_call_id` en `inspect.getsource` | **No**: pasa sin implementar ([01_requisitos §5](01_requisitos_y_contratos.md), fallo 10). La prueba real es ejecutar la celda 22 y mirar la trayectoria |
| §1 (celda 6) | Que existan `chunks.jsonl` y `corpus.faiss` | Solo existencia. Los asserts de hash de la celda 5 van dentro de un `try/except` y únicamente imprimen "No se pudo preparar el corpus", el error que vio un alumno [transcripcion_10sep · 00:55] |
| §2 (celda 9) | 48 secciones; informe > fragmentos > consulta XBRL | Sí |
| §6 (celda 29) | `structured_response` es una `RespuestaFinanciera`, `fuente` es válida y la trayectoria pasó por `get_xbrl_fact` | Sí. Es el patrón del evaluador de trayectoria |
| §7 (celda 32) | La plantilla pasa `validar()` y con `TSLA` falla | Solo prueba el validador |

**Fallos ya recogidos** en [01_requisitos §5](01_requisitos_y_contratos.md), sin repetirlos aquí:
- 8, BPA redondeado a entero;
- 9, `create_agent` recibe la cadena del modelo. **Confirmado en el código**: con una cadena, `create_agent` hace
  `model = init_chat_model(model)` y no pasa `temperature` **(venv)**;
- 10, asserts de §5;
- 11, `CANDIDATOS_CORPUS`. En clase el profesor pidió dejar solo las primeras rutas [transcripcion_10sep · 00:08, 00:57];
- 12, `KeyError` de `demo_traza.json`.

**Fallos y matices que 01 no detalla** (el resumen de los 1–3 y el 9 ya está en 01 §3, §4 y §6)
1. **El baseline no tiene tope de vueltas.** `agente_manual` tiene `max_vueltas`, pero el `create_agent` de la celda 26
   no lleva middleware, y el `recursion_limit` por defecto de langgraph 1.2.11 es **10007** pasos **(venv)**. La pregunta
   de la celda 23 contra el baseline puede quemar el presupuesto. En `evaluar()` conviene pasar
   `config={..., "recursion_limit": N}` y capturar `GraphRecursionError` (`langgraph.errors`) **(venv)**. Es parte del
   arnés, no una mejora del agente.
2. **`ToolCallLimitMiddleware(run_limit=8)`**, anunciado para el 17 [notebook S1 · celdas 14, 23]:
   - se importa de `langchain.agents.middleware` y se pasa con `create_agent(..., middleware=[...])`
     [api_stack · create_agent, exportaciones de middleware];
   - `run_limit` cuenta por invocación y `thread_limit` acumula en todo el hilo [api_stack · ToolCallLimitMiddleware];
   - con `exit_behavior="continue"` (el valor por defecto), la tool que pasa del límite se bloquea con un aviso y **el
     modelo sigue**. Si el modelo insiste en pedir tools, el bucle solo para en el `recursion_limit` **(probado)**;
   - con `exit_behavior="end"` corta, pero deja `structured_response = None` **(probado)**, así que `evaluar()` tiene
     que tolerarlo;
   - para acotar también las llamadas al modelo existe `ModelCallLimitMiddleware(run_limit=…)`
     [api_stack · ModelCallLimitMiddleware].
   ```python
   from langchain.agents.middleware import ToolCallLimitMiddleware
   agente = create_agent(model=modelo, tools=HERRAMIENTAS, system_prompt=SYSTEM,   # modelo = instancia con temperature=0
                         response_format=RespuestaFinanciera, checkpointer=InMemorySaver(),
                         middleware=[ToolCallLimitMiddleware(run_limit=8, exit_behavior="end")])
   ```
   Decisión D04 ([22 §2](22_skill_guardrails_middleware_xbrl.md)): `ToolCallLimitMiddleware(run_limit=8)` con `"continue"` +
   `ToolCallLimitMiddleware(tool_name="read_section", run_limit=2)` + `ModelCallLimitMiddleware(run_limit=12, exit_behavior="end")` +
   `VerificadorXBRL`, y `recursion_limit=100` en el arnés; `"end"` en el límite global es la trampa 1 de
   [22 §11](22_skill_guardrails_middleware_xbrl.md).
3. **`ToolStrategy`** se importa de `langchain.agents.structured_output`, como dice la celda 26 **(venv)**. Según el
   docstring de `create_agent`, un esquema Pydantic suelto se envuelve en la estrategia adecuada según las capacidades
   del modelo (*raw schemas will be wrapped…*) [api_stack · create_agent]. Resuelto (V1, venv): con gemini-3.8-flash vía `ChatOpenRouter` el esquema
   suelto se envuelve en `AutoStrategy` y acaba en `ToolStrategy` ([12 §5](12_teoria_agentes_react_tools.md)).
4. **El esquema no obliga a citar.** `cita` y `chunk_id` tienen `default=None`; solo `respuesta` y `fuente` son
   obligatorios. La celda 25 dice lo contrario: "el modelo no puede devolver una respuesta sin decir de dónde sale"
   [notebook S1 · celda 25]. La cita hay que exigirla en el evaluador (a) o en un middleware.
5. **El docstring de `get_xbrl_fact` pone `'Revenues'` de ejemplo**, y ese concepto no existe para AAPL, MSFT, META ni
   AMZN [notebook S1 · celda 12; enunciado · §3].
6. **Los filtros son de igualdad exacta y `k` no tiene tope** en las tres tools: `"nvda"` o `"Item 1A"` no casan con
   nada [notebook S1 · celdas 12–14]. Hay que normalizar las entradas y capar `k` dentro del cuerpo.
7. **`validar()` tiene huecos** [notebook S1 · celda 32]:
   - con `fiscal_year: null`, `int(None)` revienta;
   - un ancla que no sea `str` rompe `.split()`;
   - no comprueba que la cifra coincida con XBRL ni que el ancla exista literal en el corpus;
   - en las comparativas, los mensajes de error siguen diciendo "extractiva…" o "numérica…";
   - los campos extra se toleran.
8. **`pretty_trace` confunde**: rotula `cita:` pero imprime el `chunk_id`, y cuenta las llamadas de todo el hilo, no
   solo las de la última pregunta [notebook S1 · celdas 27–28].
9. **Comparativas "por cada ejercicio".** La tabla de familias dice que la comparativa rellena los campos "por cada
   ejercicio" [notebook S1 · celda 30], pero la plantilla y `validar()` solo admiten un `fiscal_year` y una
   `cifra_esperada` [notebook S1 · celda 32]. Ver §8.
10. **Referencias descuadradas** [notebook S1 · celdas 0, 26, 33]:
    - la celda 26 llama al bucle "las treinta líneas de la celda 23", y es la 21;
    - la celda 33 remite `responder()`/`evaluar()` al "§6 del enunciado", cuando están en §4.5 y §5;
    - el notebook fecha la entrega el 24.
11. **"No hashable" con `@tool`.** En clase, la versión de `list_available` que usaba `secciones` funcionaba como
    función y fallaba como tool. No se resolvió ("este lo miraré yo") y, para la demo de `create_agent`, la quitó
    [transcripcion_10sep · 01:40, 02:17]. El patrón que sí funciona en el notebook es leer el DataFrame global dentro del
    cuerpo, como hace `read_section` [notebook S1 · celda 14].

## 6. Qué llega en las próximas sesiones

Fechas de entrega y presentación: [01_requisitos §1](01_requisitos_y_contratos.md).

| Fecha | Sesión | Qué se espera y qué preparar | Fuente |
| --- | --- | --- | --- |
| **12 sep (sáb, hoy)** | RAG, módulo NLP (Rafael Sánchez) | Chunking, retrieval híbrido, reescritura, reranking y evaluación. Atender a lo que toque R08: filtros por metadatos, RRF y recall@k. Aún sin transcripción: revisar esta guía después de la clase | [notebook S1 · celda 0; slides agenda · p.7] |
| **17 sep (jue)** | Sesión 2 de la práctica | **Arranca** con los baselines contra cinco preguntas duras. Se abre `search_filings` "a degüello": troceado, embeddings, `IndexFlatIP`, top-k y los tres arreglos medidos con recall@k. "Vais a cambiar el troceado" (por eso el ancla es texto y no `chunk_id`). Pre-filtro frente a post-filtro, "una de las conversaciones del día 17". El prefijo BGE como ejemplo de fallo silencioso. Guardrails ("que el agente no se invente cifras") y `ToolCallLimitMiddleware`. Evaluación con el golden set y el evaluador `uso_la_tool_correcta`; estado y comparativas; interrupciones con un humano en medio. Antes de la clase, la solución del ejercicio 2 | [notebook S1 · celdas 13, 14, 16, 23, 26, 28, 30, 33; miax_s1.py · docstring, buscar(); transcripcion_10sep · 00:38, 01:58, 02:26, 02:29; enunciado · §2] |
| **18 sep (vie)** | ReAct, con el paper | Pone nombre y teoría al bucle que ya escribimos | [notebook S1 · celdas 24, 33] |
| **19 sep (sáb)** | MCP, ADK y A2A | Con un notebook de bonus. ADK es otro framework: las últimas clases del módulo son de agentes con ADK, "no LangChain". Sirven como ideas (sobre todo de evaluación de agentes), no como código. La agenda NLP no da fechas para sus sesiones V y VI (ADK, sesiones y memoria; agentes FSI, despliegue y evaluación) | [notebook S1 · celda 33; transcripcion_04sep · 00:15; slides agenda · p.8–9] |

## 7. Ideas de las clases teóricas útiles para la práctica

**Tokenización (04-sep)**
- "Si te falla un modelo, lo primero que tienes que mirar no es el algoritmo, es tu tokenizador". → Si el recall es bajo, mirar cómo trocea bge-small una pregunta en español (R08) [transcripcion_04sep · 01:05].
- Cada modelo se entrena con su tokenizador, "con lo cual va a ser distinto". → Contar tokens con el `usage_metadata` del proveedor, no con un tokenizador ajeno (R11) [transcripcion_04sep · 01:37].
- Lo ideal es tokenizar los números dígito a dígito, y muchos tokenizadores no lo hacen: GPT-2 no, StarCoder sí. → Las cifras salen de XBRL y se comparan como número normalizado, nunca como cadena (R05, R09b) [transcripcion_04sep · 01:37, 02:16–02:19].
- El proceso es estandarizar → tokenizar → vectorizar. El stemming y la lematización ya no se hacen porque pierden información. → Tokenizador de BM25 con minúsculas y sin puntuación suelta, sin stemming salvo que se mida (R08) [transcripcion_04sep · 03:05–03:08; slides NLP_S1 · p.14].
- Cada librería retoca las fórmulas (lo vimos con TF-IDF), así que hay que mirar su documentación. → Documentar `k1`, `b` y `epsilon` de `BM25Okapi`, por defecto 1.5, 0.75 y 0.25 [api_stack · rank_bm25.BM25Okapi] (R08, R15) [transcripcion_04sep · 02:00].

**Embeddings (04 y 05-sep)**
- Lo primero de la ficha de un modelo de embeddings es si es multilingüe ("house" ≈ "casa"). → bge-small-**en**-v1.5 es, por su nombre, un modelo inglés (⚠️ por confirmar): hay que reescribir la consulta en inglés y medir el recall con la pregunta tal cual y con la reescrita (R08) [transcripcion_04sep · 04:00].
- Los embeddings asimétricos (`task_type` RETRIEVAL_QUERY frente a RETRIEVAL_DOCUMENT) y MTEB para comparar modelos. → El prefijo BGE, que va solo en la consulta, es el mismo mecanismo (R08) [slides NLP_S1 · p.35].
- Sale un vector por entrada, sea una frase o seis páginas, y una página queda mejor representada que seis: "este es el dilema de los sistemas RAG". → El troceado es palanca de R08 y condiciona las anclas de R07 [transcripcion_05sep · 00:49–00:51].
- Un modelo de embeddings nuevo, o una versión nueva, no es compatible con el anterior: hay que reindexar (R08, R12) [transcripcion_05sep · 00:57; slides RAG · p.44].
- Comparar embeddings "eso está resuelto. El problema es la escala". → Con 1.749 vectores basta la búsqueda exacta (`IndexFlatIP`); ANN solo podría bajar el recall (R08) [transcripcion_05sep · 00:44].

**BERT, pre-training y fine-tuning (05-sep)**
- Al preparar el texto, partir "por los puntos" cuando se pueda, para no cortar frases. → Trocear respetando frases para que ninguna ancla quede partida (R07, R08) [transcripcion_05sep · 04:22].
- "Yo no recomiendo tocar los pesos": lo mejoras para tus datos y lo empeoras en lo demás. → La mejora va por retrieval, prompt y tools, con el modelo fijo (R12) [transcripcion_05sep · 04:11].
- Los benchmarks son "lo menos malo"; hay que probar el modelo con tu caso de uso. → Para eso está el golden set propio (R06) [transcripcion_04sep · 00:52].

**RAG (slides de la clase del 12-sep)**
- Grounding: explicar cómo respaldan los documentos cada respuesta. → Es la definición del evaluador (a) (R09) [slides RAG · p.3].
- Metadatos en cada chunk (`{"org": "Alphabet", "year": "2022"}`) y filtros por metadatos al consultar (R08) [slides RAG · p.34].
- Búsqueda híbrida: densa + sparse (BM25) fusionadas con RRF (R08) [slides RAG · p.22, p.42].
- Descomposición en un paso ("Compare… Uber and Lyft revenues" → una subpregunta por empresa). → Es el patrón de las comparativas por FY (R06, R08) [slides RAG · p.36].
- Multi-query y *lost in the middle*: más chunks no siempre dan mejor respuesta (R08) [slides RAG · p.37].
- Reranking con cross-encoder como paso opcional (R08) [slides RAG · p.42].
- Métricas de retrieval: hit-rate y MRR (R08, R11) [slides RAG · p.47].
- LLM-as-a-judge, con las limitaciones que avisa la propia slide (R09a) [slides RAG · p.48].
- Objetivo de latencia del retrieval: por debajo de 300 ms (R11) [slides RAG · p.45].

**Tuning y agenda**
- El tuning recomienda 100–500 ejemplos, "the more the better". → Con 20 preguntas no hay nada que afinar y no se entrena (R12) [slides Tuning · p.3].
- Los etiquetadores evalúan "one single criteria" y "long answers are not best answers"; la plantilla RLAIF termina en "Preferred Response=". → Un juez por criterio, que no premie la longitud (R09a) [slides Tuning · p.50, p.57].
- Reward hacking. → Iterar solo contra el golden propio sobreajusta; las 10 ciegas lo destapan (R15) [slides Tuning · p.55].
- "Práctica: entregables autoejecutables en Colab. Sólo se evaluará un 'Run all' exitoso" está en la agenda del módulo NLP, no en el enunciado (R10; §8) [slides agenda · p.12].
- La sesión de Tuning (11-sep) no tiene transcripción en `docs/raw` [transcripcion_04sep · 00:23].

## 8. Dudas abiertas para preguntar al profesor

**Para el 17-sep**
1. **Entrega**: ¿el 23 a las 23:59, como dice el enunciado, o el 24, como se dijo en clase y pone el notebook?
2. **Embeddings propios**: ¿es obligatorio elegir y generar nuestro modelo de embeddings [transcripcion_10sep · 02:26,
   02:31] o basta con el índice de bge-small entregado? Si se cambia, ¿el baseline se queda con el índice original?
3. **"Os vais a medir con estos 20"**: ¿la tabla baseline/final va sobre las 20 oficiales, sobre las propias o sobre
   ambas? ¿Cuándo llega `golden_set.jsonl` [notebook S1 · celda 31]?
4. **Comparativas**: ¿cómo se representa el segundo ejercicio? La celda 30 dice "por cada ejercicio" y el validador
   admite uno. ¿`cifra_esperada` es el nivel del FY reciente o la variación?
5. **Preguntas de hueco** ("no está en el corpus"): ¿cómo se codifican, si `validar()` exige cifra en las numéricas y
   ancla en las extractivas?
6. **`herramienta_esperada`**: ¿el evaluador del 24 exige todas, alguna o en orden? ¿Penaliza llamadas de más, como
   `list_available` si el universo ya está en el prompt?
7. **Evaluadores**: ¿los falsos "ninguna" van como cuarto evaluador o dentro de los tres? ¿Hay una tolerancia de
   referencia para las cifras?
8. **Filtro por metadatos**: `buscar()` ordena todo el índice y filtra después, así que filtrar antes no cambia el top-k.
   ¿Qué cuenta como arreglo: que el LLM pase los filtros, un pre-filtro antes de cortar el top-N del híbrido, o una
   extracción determinista?
9. **Ciegas**: ¿en qué formato llegan (¿JSONL con el esquema del golden?), en qué entorno y quién lanza `evaluar()`?
   ¿Traen ancla para medir recall?
10. **"Run all"** de Colab [slides agenda · p.12]: ¿aplica a esta práctica?
11. **Límite de llamadas**: ¿qué `exit_behavior` espera (`"continue"` por defecto o `"end"`)? ¿Cuentan todas las tools?
12. Qué había que añadir "en la primera celda y en `miax_s1.py`" para Colab [transcripcion_10sep · 00:36, 00:55]. ¿Los
    "warrers" son *rerankers* [transcripcion_10sep · 02:26]?

**Qué había que corregir o completar en 01_requisitos_y_contratos.md** (aplicado en 01 §3–§6 en la revisión de cierre del
12-sep; se deja como traza)
- **§4, límite de bucle.** `ToolCallLimitMiddleware(run_limit=8)` es correcto pero incompleto:
  - con el `exit_behavior="continue"` por defecto no corta si el modelo insiste;
  - el baseline sin middleware tiene `recursion_limit` 10007;
  - `thread_limit` acumula en el hilo;
  - el import es `langchain.agents.middleware` y se pasa con `middleware=` (§5, fallos 1–2).
- **§6, comparativas.** Falta la pista de la celda 30 ("por cada ejercicio").
- **§6, fecha.** Sumar [transcripcion_10sep · 00:00], [notebook S1 · celda 0] y "justo antes de la sesión 3"
  [enunciado · §2]. La conclusión (vale el 23) no cambia.
- **§2/§6.** No recoge dos cosas del profesor:
  - que pide elegir y persistir embeddings propios [transcripcion_10sep · 02:26, 02:31];
  - que los evaluadores detecten los falsos "ninguna" [transcripcion_10sep · 02:29].
- **§3.** Añadir la ruta `langchain.agents.structured_output` de `ToolStrategy` y el matiz del envoltorio automático
  (§5, fallo 3).
- **§5, fallo 9.** Se puede citar como confirmado en el código: `model = init_chat_model(model)` **(venv)**.
