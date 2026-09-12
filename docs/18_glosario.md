# Glosario

> Requisitos: transversal · Índice: [README.md](README.md) · Contratos: [01_requisitos_y_contratos.md](01_requisitos_y_contratos.md)

> Fuentes: los docs de esta carpeta (cada entrada enlaza el suyo, que es donde están las citas originales); [enunciado · §1, §3, §4];
> vocabulario común de la decisión D00 del mapa de cobertura (resumida en el [README](README.md)).

**v1.0 · 12-sep-2026.** Una o dos líneas por término y el enlace al doc donde se trata a fondo. Los términos técnicos van en inglés cuando
es lo estándar, con la forma española que usan los docs entre paréntesis. El vocabulario propio de la práctica (ancla, hueco, escalera,
techo, acierto…) está en la última sección. Números del corpus: (datos) de [02](02_datos_corpus_y_xbrl.md).

## 1. Finanzas, 10-K y XBRL

- **10-K.** Informe anual que toda cotizada en EE. UU. presenta ante la SEC, con los mismos epígrafes (*items*) y en el mismo orden todos los
  años. El corpus: 6 empresas × 2 ejercicios × 4 items = 48 secciones. → [02 §1](02_datos_corpus_y_xbrl.md)
- **Accession number.** Identificador de cada presentación en EDGAR; de él sale el año de presentación (`…-25-…`). → [02 §2](02_datos_corpus_y_xbrl.md)
- **BPA (EPS, beneficio por acción).** `EarningsPerShareBasic` y `EarningsPerShareDiluted`, en `USD/shares` con dos decimales. Básico y
  diluido distan ≥ 0,03, por eso su tolerancia es absoluta. → [02 §5](02_datos_corpus_y_xbrl.md), [09 §4](09_skill_guardrails_middleware_xbrl.md)
- **CIK.** Código de la empresa en la SEC; se guarda como texto con ceros a la izquierda, que pandas pierde si lo convierte a entero.
  → [02 §3, §6](02_datos_corpus_y_xbrl.md)
- **Concepto (XBRL concept).** Nombre del elemento de la taxonomía que etiqueta una cifra (`Revenues`, `NetIncomeLoss`…). El corpus tiene
  13, y el revenue no tiene uno único por empresa. Es el parámetro `concept` de `get_xbrl_fact`. → [02 §5–§6](02_datos_corpus_y_xbrl.md)
- **EDGAR.** Sistema de la SEC donde se publican las presentaciones. Admite 10 peticiones por segundo, así que el corpus se entrega ya hecho.
  → [02 §8](02_datos_corpus_y_xbrl.md)
- **Fiscal year (FY, ejercicio fiscal).** Año contable según la fecha de cierre de cada empresa (NVDA, enero; MSFT, junio; AAPL, septiembre; el
  resto, diciembre). `fiscal_year` no es el año de presentación ni el natural. → [02 §2](02_datos_corpus_y_xbrl.md)
- **Ground truth (verdad de referencia).** Contra lo que se evalúa: `xbrl_facts.parquet` para las cifras y el ancla para el texto.
  → [02 §3](02_datos_corpus_y_xbrl.md), [06 §1](06_teoria_evaluacion_llms.md)
- **Hecho XBRL (fact).** Una fila (ticker, FY, concepto, valor, unidad, `period_end`) del parquet: hay 135 de 156 celdas posibles.
  → [02 §3, §5](02_datos_corpus_y_xbrl.md)
- **Item.** Epígrafe numerado del 10-K. El corpus tiene el 1A (Risk Factors), el 7 (MD&A), el 7A (Market Risk) y el 8 (Financial
  Statements); las herramientas lo reciben como texto: `"1A"`, `"7"`, `"7A"`, `"8"`. → [02 §1](02_datos_corpus_y_xbrl.md)
- **`item_origen`.** Item real del 10-K. NVIDIA pone sus estados financieros en el Item 15 y el corpus los sirve bajo `"8"`.
  → [02 §1](02_datos_corpus_y_xbrl.md)
- **MD&A (Item 7).** *Management's Discussion and Analysis*: la dirección explica por qué suben o bajan sus magnitudes. Buen sitio para el
  ancla de una comparativa. → [02 §1](02_datos_corpus_y_xbrl.md), [10 §4](10_skill_golden_set.md)
- **`period_end`.** Fecha de cierre del ejercicio al que se refiere un hecho XBRL. → [02 §2](02_datos_corpus_y_xbrl.md)
- **SEC.** *Securities and Exchange Commission*, el regulador del mercado de valores de EE. UU. → [00 §3](00_enunciado.md)
- **Split (desdoblamiento).** El 10:1 de NVIDIA en 2024 hace que el BPA reportado baje de 12,05 a 2,97; una comparativa ingenua concluiría
  que cayó un 75 %. → [02 §6](02_datos_corpus_y_xbrl.md), [10 §4](10_skill_golden_set.md)
- **Unidad.** `"USD"` o `"USD/shares"`, literal de XBRL. `cifra` va sin escalar, en esa unidad. → [02 §5](02_datos_corpus_y_xbrl.md),
  [08 §3](08_skill_agente_salida_estructurada.md)
- **XBRL / us-gaap.** XBRL (*eXtensible Business Reporting Language*) etiqueta las cifras de los estados financieros para que las lea una
  máquina; us-gaap es la taxonomía de conceptos de los principios contables de EE. UU. Es la fuente autorizada de cualquier cifra y la
  vía exacta y barata del agente (`get_xbrl_fact`, ≈ 40 tokens). → [02 §5](02_datos_corpus_y_xbrl.md), [01 §3](01_requisitos_y_contratos.md)

## 2. Corpus

- **Chunk (fragmento).** Trozo de una sección: 1.749 en total, de media ~402 tokens y máximo 547, con `chunk_id` y offsets de carácter
  `inicio_car`/`fin_car`. Es lo que devuelve `search_filings`. → [02 §3](02_datos_corpus_y_xbrl.md)
- **`chunk_id`.** `TICKER-FY-ITEM-NNNN` (p. ej. `NVDA-2024-1A-0000`). Cambia al re-trocear: por eso el golden ancla a texto (R07).
  → [02 §3](02_datos_corpus_y_xbrl.md), [10 §2](10_skill_golden_set.md)
- **Chunking (troceado).** Cómo se corta el texto antes de embeberlo (tamaño fijo con solape, por frase o párrafo, *small-to-big*…). El
  "solape de 80" solo se da si el corte cae dentro de un párrafo: el 60 % de los pares no se solapa. → [04 §2](04_teoria_rag_retrieval.md)
- **Corpus.** `data/corpus/`: `secciones.jsonl`, `chunks.jsonl`, `xbrl_facts.parquet` e `indice/`. Se versiona en el repo,
  byte a byte ([data/README.md](../data/README.md)).
  → [02 §3](02_datos_corpus_y_xbrl.md), [README](README.md)
- **JSONL.** Un objeto JSON por línea: formato del corpus, del golden y de los ficheros de resultados. → [10 §2](10_skill_golden_set.md)
- **Manifiesto y SHA-256.** Los manifiestos citan el hash de `chunks.jsonl`: si no coincide, índice y metadatos están desalineados y el
  retrieval devuelve texto equivocado sin avisar. → [02 §3, §8](02_datos_corpus_y_xbrl.md)
- **Sección.** Texto íntegro de un (ticker, FY, item): 48, entre 409 y 34.751 tokens (META FY2025 1A). Es lo que devuelve `read_section`, la
  vía cara. → [02 §3–§4](02_datos_corpus_y_xbrl.md)

## 3. Tokens, embeddings y retrieval

- **ANN (búsqueda aproximada).** Índices como IVF, HNSW o ScaNN, que cambian exactitud por velocidad. Con 1.749 vectores no hace falta: el
  índice entregado es exacto y un ANN solo podría bajar el recall. → [03 §4](03_teoria_tokenizacion_embeddings.md)
- **bge-small-en-v1.5.** Modelo de embeddings del índice (`BAAI/`, 384 dimensiones). La consulta lleva el prefijo
  `"Represent this sentence for searching relevant passages: "`; los chunks no. Omitirlo no da error, solo recupera peor.
  → [03 §3](03_teoria_tokenizacion_embeddings.md), [02 §3](02_datos_corpus_y_xbrl.md)
- **Bi-encoder.** Codifica consulta y documento por separado ("dos torres") y compara sus vectores; permite precalcular el índice. Es el
  retrieval denso. → [03 §3](03_teoria_tokenizacion_embeddings.md), [04 §6](04_teoria_rag_retrieval.md)
- **BM25.** Ranking disperso: TF-IDF con saturación de la frecuencia (`k1`) y normalización por longitud (`b`). Usamos `BM25Okapi` de
  rank-bm25 con IDF global, `k1=1.5, b=0.75, ε=0.25` y tokenizer `[a-z0-9]+`. → [03 §2](03_teoria_tokenizacion_embeddings.md),
  [11 §6](11_skill_mejora_retrieval.md)
- **Cross-encoder.** Lee consulta y documento juntos y da una puntuación de relevancia: más preciso y más caro que el bi-encoder. Se usa para
  reranking. → [04 §6](04_teoria_rag_retrieval.md)
- **Denso, disperso e híbrido.** Denso = embeddings (semántica, paráfrasis); disperso = coincidencia de términos (BM25; cifras, nombres
  propios); híbrido = las dos listas fusionadas. → [04 §3](04_teoria_rag_retrieval.md)
- **Embedding.** Vector que representa el significado de un texto; textos parecidos quedan cerca (coseno).
  → [03 §3](03_teoria_tokenizacion_embeddings.md)
- **FAISS / `IndexFlatIP`.** Librería de búsqueda de vectores; `IndexFlatIP` es búsqueda exacta por producto interno, que sobre vectores
  normalizados es el coseno. → [03 §4](03_teoria_tokenizacion_embeddings.md), [02 §3](02_datos_corpus_y_xbrl.md)
- **Filtro por metadatos (pre y post-filtro).** Restringir por `ticker`, `fiscal_year` o `item`. Pre-filtro: antes de ordenar; post-filtro:
  después. Con la búsqueda exacta de `miax_s1.buscar()` no cambia el recall; importa cuando se corta un top-N (híbrido, rerank).
  → [04 §4](04_teoria_rag_retrieval.md), [11 §5](11_skill_mejora_retrieval.md)
- **Grounding y factuality.** Factuality: que la respuesta se base en hechos reales. Grounding: poder explicar cómo la respaldan los
  documentos, frase a frase. Es la idea del evaluador (a). → [04 §1](04_teoria_rag_retrieval.md)
- **HyDE.** Embeber una respuesta hipotética escrita por el LLM en lugar de la pregunta. Fuera de la escalera: opcional.
  → [04 §5](04_teoria_rag_retrieval.md)
- **Multi-query.** Varias consultas (1–3 en la escalera) fusionadas con RRF; en las comparativas, una por ejercicio.
  → [04 §5](04_teoria_rag_retrieval.md), [11 §7](11_skill_mejora_retrieval.md)
- **RAG (Retrieval-Augmented Generation).** Recuperar fragmentos y dárselos al LLM para que responda con ellos. En la práctica el retrieval es
  una herramienta más del agente (*agentic RAG*), no la arquitectura. → [04 §1](04_teoria_rag_retrieval.md)
- **Reescritura de la consulta (query rewriting).** El LLM reformula la pregunta como consulta en inglés y extrae los filtros. En el agente
  la hace el propio modelo al rellenar los argumentos de `search_filings`; se mide aislada con `reescribir()`.
  → [04 §5](04_teoria_rag_retrieval.md), [11 §7](11_skill_mejora_retrieval.md)
- **Reranking.** Reordenar el top-N con un modelo más caro (cross-encoder). Opcional y siempre después de los tres arreglos obligatorios.
  → [04 §6](04_teoria_rag_retrieval.md), [11 §11](11_skill_mejora_retrieval.md)
- **RRF (Reciprocal Rank Fusion).** Fusiona rankings por posición: `RRF(d) = Σ w / (k + rango(d))`. Fijado en k = 60 y pesos iguales,
  antes de medir. → [04 §3](04_teoria_rag_retrieval.md), [11 §6](11_skill_mejora_retrieval.md)
- **TF-IDF.** Peso de un término = frecuencia en el documento × rareza en la colección (`idf = log(N/df)`). BM25 lo corrige.
  → [03 §2](03_teoria_tokenizacion_embeddings.md)
- **Token y tokenizer.** Unidad en que un modelo trocea el texto (BPE, WordPiece, SentencePiece). Cada modelo tiene el suyo: los conteos no
  son intercambiables y la factura la cuenta el proveedor, no `get_num_tokens()`. → [03 §1](03_teoria_tokenizacion_embeddings.md)

## 4. Agentes y LangChain

- **Agente.** Un LLM que en cada vuelta decide si llama a una herramienta, lee el resultado y sigue, hasta responder.
  → [05 §1](05_teoria_agentes_react_tools.md)
- **API obsoleta.** `create_react_agent`, `MemorySaver`, `with_structured_output` y `RunnableWithMessageHistory`; hoy, `create_agent`,
  `InMemorySaver` y `response_format`. → [05 §8](05_teoria_agentes_react_tools.md), [01 §4](01_requisitos_y_contratos.md)
- **Checkpointer, `thread_id` e `InMemorySaver`.** El checkpointer guarda el estado por hilo (`thread_id`); `InMemorySaver` lo guarda en
  memoria. Para evaluar, un hilo nuevo por pregunta. → [05 §4](05_teoria_agentes_react_tools.md), [08 §7](08_skill_agente_salida_estructurada.md)
- **`create_agent`.** El bucle ReAct ya hecho de langchain 1.x sobre langgraph: `model`, `tools`, `system_prompt`, `response_format`,
  `middleware`, `checkpointer`. Se le pasa el modelo como instancia, no como cadena. → [05 §4](05_teoria_agentes_react_tools.md)
- **Docstring de enrutado.** Descripción de la herramienta que lee el modelo: cuándo usarla, cuándo NO y el vocabulario válido.
  `@tool(parse_docstring=True)` saca además la descripción de cada parámetro de la sección `Args:`. → [07 §2–§3](07_skill_herramientas_docstrings.md)
- **Enrutado (routing).** Elegir entre la vía exacta (`get_xbrl_fact`) y la difusa (`search_filings`, `read_section`). Se mide con
  precisión, recall y F1 por herramienta. → [07 §9](07_skill_herramientas_docstrings.md), [06 §5](06_teoria_evaluacion_llms.md)
- **Fallback.** Respuesta de sustitución cuando falta `structured_response` (límite, recursión o error):
  `RespuestaFinanciera(respuesta="No se pudo completar la respuesta.", fuente="ninguna")`. → [08 §7](08_skill_agente_salida_estructurada.md)
- **Guardrail.** Control que impide un comportamiento no deseado: bucles, cifras sin verificar, inventar un dato que no existe.
  → [09 §1](09_skill_guardrails_middleware_xbrl.md)
- **Herramienta (tool, `@tool`).** Función Python expuesta al modelo, que solo ve su nombre, sus parámetros, el docstring y el resultado.
  Las cuatro del contrato devuelven `str`. → [05 §2](05_teoria_agentes_react_tools.md), [07 §1](07_skill_herramientas_docstrings.md)
- **Hook.** Punto del bucle donde se engancha un middleware: `before_model`, `after_model`, `wrap_model_call`, `wrap_tool_call`… Con
  `jump_to` puede devolver el control al modelo. → [05 §6](05_teoria_agentes_react_tools.md)
- **`init_chat_model` y OpenRouter.** `init_chat_model("openrouter:google/gemini-3.8-flash", temperature=0)` crea el modelo; OpenRouter es
  la pasarela que da acceso a varios proveedores con una sola clave. → [08 §2](08_skill_agente_salida_estructurada.md), [01 §4](01_requisitos_y_contratos.md)
- **MCP, A2A y ADK.** Protocolo de herramientas, protocolo entre agentes y kit de agentes de Google (clase del 19-sep). Ideas, no código de
  la práctica. → [05 §9](05_teoria_agentes_react_tools.md)
- **Middleware.** Pieza que se engancha al bucle de `create_agent` para limitar, verificar o modificar lo que pasa. Aquí: los límites y el
  `VerificadorXBRL`. → [05 §6](05_teoria_agentes_react_tools.md), [09 §2](09_skill_guardrails_middleware_xbrl.md)
- **Modelo falso (`GenericFakeChatModel`).** Modelo de langchain-core que devuelve respuestas predefinidas. Con él se marca **(probado)**:
  confirma API y flujo, no el comportamiento de Gemini. → [README](README.md), [08 §12](08_skill_agente_salida_estructurada.md)
- **`model_validator`.** Validador de Pydantic entre campos. En el final, tres reglas: `xbrl`/`ambas` ⇒ `cifra`; `ninguna` ⇒ sin `cifra`;
  `texto`/`ambas` ⇒ `cita`. → [08 §3](08_skill_agente_salida_estructurada.md)
- **ReAct.** *Reasoning + Acting* (2022): alternar *Thought*, *Action* y *Observation* hasta terminar. Con tool calling nativo, la acción es un
  `tool_call` y la observación, un `ToolMessage`. → [05 §3](05_teoria_agentes_react_tools.md)
- **`recursion_limit` y superstep.** langgraph corta al superar un número de *supersteps* del grafo (no de llamadas) y lanza
  `GraphRecursionError`. El arnés usa 100. → [05 §4](05_teoria_agentes_react_tools.md), [09 §2](09_skill_guardrails_middleware_xbrl.md)
- **`RespuestaFinanciera`.** Esquema de salida del contrato: `respuesta, cifra, unidad, ticker, ejercicio, fuente, cita, chunk_id`, con
  `fuente ∈ {xbrl, texto, ambas, ninguna}`. Se pueden añadir campos, no quitarlos. → [01 §3](01_requisitos_y_contratos.md),
  [08 §3](08_skill_agente_salida_estructurada.md)
- **Structured output (salida estructurada).** El agente devuelve un objeto que valida un esquema en vez de prosa; en `create_agent`, con
  `response_format`, y se lee en `resultado["structured_response"]`. → [05 §5](05_teoria_agentes_react_tools.md), [08 §4](08_skill_agente_salida_estructurada.md)
- **System prompt.** Instrucciones fijas del agente: universo del corpus, reglas, significado de `fuente` y obligación de citar literal.
  → [08 §5](08_skill_agente_salida_estructurada.md)
- **`temperature`.** Aleatoriedad del muestreo. A 0 en todo lo que se evalúa, para que baseline y final sean comparables.
  → [08 §2](08_skill_agente_salida_estructurada.md)
- **Tool calling (function calling).** El modelo no ejecuta nada: devuelve `tool_calls` (nombre y argumentos); el código las ejecuta y le
  devuelve un `ToolMessage` con el mismo `tool_call_id`. → [05 §2](05_teoria_agentes_react_tools.md)
- **`tool_choice`.** Obliga o prohíbe llamar herramientas en una llamada al modelo; forzarla en la primera es un experimento opcional.
  → [05 §2.3](05_teoria_agentes_react_tools.md), [08 §11](08_skill_agente_salida_estructurada.md)
- **`ToolCallLimitMiddleware` y `ModelCallLimitMiddleware`.** Límites por invocación (`run_limit`). Con `"continue"` la llamada que se pasa
  recibe un aviso y el modelo sigue; con `"end"` el agente termina sin `structured_response`. → [05 §6](05_teoria_agentes_react_tools.md),
  [09 §2](09_skill_guardrails_middleware_xbrl.md)
- **`ToolStrategy`, `ProviderStrategy` y `AutoStrategy`.** Cómo obtiene `create_agent` la salida estructurada: como una herramienta
  sintética que el modelo "llama" para responder, con el formato nativo del proveedor, o eligiendo solo. Usamos `ToolStrategy`.
  → [05 §5](05_teoria_agentes_react_tools.md), [08 §4](08_skill_agente_salida_estructurada.md)
- **`usage_metadata`.** Tokens de entrada y salida de cada `AIMessage`; `get_usage_metadata_callback()` los suma para todas las llamadas de
  una pregunta, también las de fuera del bucle. → [13 §2](13_skill_medicion_informe_presentacion.md)
- **`VerificadorXBRL`.** Nuestro middleware de R05: tras la respuesta, contrasta sus cifras con el parquet y, si no cuadran, devuelve el
  desajuste al modelo (un reintento) o degrada a abstención. → [09 §5](09_skill_guardrails_middleware_xbrl.md)

## 5. Evaluación

- **Abstención y alucinación.** Abstenerse = responder `fuente="ninguna"` sin cifra. Alucinar = dar un dato que no está. La abstención
  indebida (decir "no está" cuando sí está) también es fallo. → [06 §8](06_teoria_evaluacion_llms.md), [12 §7](12_skill_evaluadores.md)
- **Caché de prompt (`cache_read`).** Tokens de entrada que el proveedor sirve desde caché. Se registran, pero sin descontarlos el coste
  medido es una cota superior. → [13 §2](13_skill_medicion_informe_presentacion.md)
- **Coste, latencia y llamadas por pregunta.** Las tres columnas de eficiencia de la tabla R11: USD con precios fechados, segundos (media y
  mediana) y `tool_calls`. → [06 §11](06_teoria_evaluacion_llms.md), [13 §2](13_skill_medicion_informe_presentacion.md)
- **Evaluadores (a), (b), (c) y (d).** (a) la cita existe y respalda lo afirmado; (b) la cifra coincide con XBRL con tolerancia; (c) la
  trayectoria pasó por la herramienta que tocaba; (d) abstención (propio). → [12 §1](12_skill_evaluadores.md), [06 §1](06_teoria_evaluacion_llms.md)
- **Exact match, n-gramas, BLEU y ROUGE.** Métricas deterministas sobre texto. Aquí la cita se aprueba por substring normalizado; la
  cobertura de 4-gramas, BLEU y ROUGE solo sirven de diagnóstico. → [06 §2](06_teoria_evaluacion_llms.md)
- **Familia.** Tipo de pregunta del golden: `numerica` (mide el guardrail XBRL), `extractiva` (retrieval y trazabilidad) y `comparativa`
  (dos ejercicios). → [01 §3](01_requisitos_y_contratos.md), [10 §2](10_skill_golden_set.md)
- **Golden set.** Conjunto de preguntas con respuesta conocida, en JSONL: 20 propias, ≥ 6 comparativas, que pasan `validar()`. Se congela
  antes del baseline. → [10](10_skill_golden_set.md)
- **Groundedness (faithfulness).** Si lo que dice la respuesta se deduce del contexto que cita. Estilo FACTS: una etiqueta por frase
  (`supported`, `unsupported`, `contradictory`, `no_rad`). → [06 §1, §6](06_teoria_evaluacion_llms.md), [12 §6](12_skill_evaluadores.md)
- **Hold-out.** Datos que no se usan para iterar y miden la generalización. Aquí, las 10 preguntas ciegas del 24: su delta frente al golden
  propio separa la mejora general de la memoria. → [06 §10](06_teoria_evaluacion_llms.md), [13 §8](13_skill_medicion_informe_presentacion.md)
- **Kappa de Cohen.** Acuerdo entre dos etiquetadores (juez y humano) corregido por el azar; se calcula en Python puro para validar al
  juez. → [06 §6](06_teoria_evaluacion_llms.md), [12 §9](12_skill_evaluadores.md)
- **LLM-as-a-judge (juez).** Un LLM que puntúa según un criterio. Uno por criterio, razonamiento antes de la etiqueta, a `temperature=0`,
  con caché y validado antes de fiarse. → [06 §6](06_teoria_evaluacion_llms.md), [12 §6](12_skill_evaluadores.md)
- **Micro y macro.** Micro = aciertos / preguntas; macro = media de las familias. Una familia sin preguntas es "—", nunca 0.
  → [06 §3](06_teoria_evaluacion_llms.md), [12 §7](12_skill_evaluadores.md)
- **MRR@10.** Media de 1/rango del primer chunk que contiene el ancla (0 si no está en el top-10). Métrica secundaria del retrieval; nDCG no
  aporta con una sola relevancia por pregunta. → [06 §4](06_teoria_evaluacion_llms.md), [11 §4](11_skill_mejora_retrieval.md)
- **Precisión, recall y F1 (TP/FP/FN).** Clasificación de conjuntos: en la trayectoria, herramientas esperadas frente a llamadas; en el
  enrutado, por herramienta. → [06 §3](06_teoria_evaluacion_llms.md)
- **recall@k.** Fracción de las preguntas con ancla en las que algún chunk del top-k contiene el ancla normalizada (= hit-rate@k).
  Principal: @5, el `k` por defecto del contrato; siempre con k/n. → [06 §4](06_teoria_evaluacion_llms.md), [11 §4](11_skill_mejora_retrieval.md)
- **Reward hacking y sobreajuste.** Optimizar la métrica en lugar del objetivo, por ejemplo iterar contra el golden hasta aprenderlo.
  → [06 §10](06_teoria_evaluacion_llms.md)
- **Significación con n pequeño.** Con 20 preguntas, cada una vale 5 pp: se cuentan ganadas y perdidas; un test de signo o McNemar
  exacto es propuesta propia. → [06 §9](06_teoria_evaluacion_llms.md)
- **Tolerancia documentada.** Margen para dar por buena una cifra: relativa del 0,5 % en USD, absoluta de 0,005 en BPA, con una sola
  `cifra_ok()` para R05 y (b). → [06 §7](06_teoria_evaluacion_llms.md), [09 §4](09_skill_guardrails_middleware_xbrl.md), [12 §3](12_skill_evaluadores.md)
- **Trayectoria.** Secuencia de `tool_calls` del agente en una invocación, filtrada con la lista blanca y sin deduplicar. El evaluador (c)
  exige que estén las esperadas y que los argumentos de `get_xbrl_fact` sean los correctos. → [06 §5](06_teoria_evaluacion_llms.md),
  [12 §4](12_skill_evaluadores.md)
- **Trayectoria exact, in_order y any_order.** Coincidencia exacta con la referencia, en orden con extras permitidos, o en cualquier orden.
  Diagnósticos; (c) usa su propia semántica. → [06 §5](06_teoria_evaluacion_llms.md)
- **`validar()` y `validar_estricto()`.** El validador oficial del golden (celda 32, se usa tal cual) y el nuestro, que mira lo que el
  oficial no: cifra igual al parquet, ancla literal con sus offsets y entera en un chunk, campos extra de comparativas y huecos, y formato
  de `id` y `autor`. → [10 §8](10_skill_golden_set.md)

## 6. Vocabulario propio de la práctica

- **Acierto.** Por familia: numérica (b)∧(c); extractiva (a)∧(c)∧`correcta`; comparativa (a)∧(b)∧(c)∧`correcta`; hueco,
  `ninguna` ∧ sin cifra ∧ (c). Acertar por el camino equivocado es fallo. → [12 §7](12_skill_evaluadores.md)
- **Ancla (`ancla_texto`).** Frase literal del 10-K, de ≤ 40 palabras, que prueba la respuesta; `ancla_inicio`/`ancla_fin` son offsets de
  carácter sobre el texto de la sección. → [10 §2, §6](10_skill_golden_set.md)
- **`anclas_no_indexables`.** Anclas que no caben enteras en ningún chunk del índice en uso: falsos negativos del golden, no del
  retrieval. Tiene que ser 0 antes de medir. → [11 §2](11_skill_mejora_retrieval.md), [10 §6](10_skill_golden_set.md)
- **Arnés (`ejecutar()`).** Envoltorio común de baseline y final: hilo nuevo, `recursion_limit=100`, captura de errores, *fallback*, coste
  y latencia. → [08 §7](08_skill_agente_salida_estructurada.md)
- **Baseline y final.** Baseline = la versión del profesor con el modelo a `temperature=0` y el arnés (D21), congelada con la etiqueta git
  `baseline-v1`. Final = el sistema mejorado (`final-v1`). → [13 §3–§4](13_skill_medicion_informe_presentacion.md)
- **Ciegas.** Las 10 preguntas que se entregan al empezar la clase del 24 y se ejecutan contra el repo ya entregado. → [13 §8](13_skill_medicion_informe_presentacion.md),
  [12 §11](12_skill_evaluadores.md)
- **Cita "vista".** La cita aparece en el contenido de algún `ToolMessage` de `search_filings` o `read_section` de la trayectoria: el agente
  la leyó, no la recordó. → [12 §5](12_skill_evaluadores.md)
- **Clon limpio.** Copia recién clonada del repo en la que `responder()` y `evaluar()` tienen que funcionar sin editar nada (R10); se ensaya
  antes del 22-sep. → [02 §8](02_datos_corpus_y_xbrl.md), [13 §10](13_skill_medicion_informe_presentacion.md)
- **`correcta`.** Juez de un solo criterio: si la respuesta dice lo mismo que `respuesta_esperada`, con la misma unidad y escala.
  → [12 §6](12_skill_evaluadores.md)
- **Ejecutar ≠ puntuar.** `evaluar()` ejecuta y guarda `predicciones.jsonl`; `puntuar()` recalcula las métricas desde ese fichero sin volver a
  llamar al agente. → [12 §8](12_skill_evaluadores.md)
- **Escalera.** Secuencia de pasos del retrieval (0 denso → 1 + filtro → 2 + BM25/RRF → 3 + reescritura) en la que solo cambia un arreglo
  entre filas y se mide recall@k tras cada uno. → [11 §2](11_skill_mejora_retrieval.md)
- **Etapa 1 y etapa 2 (evaluador de cita).** Etapa 1, determinista: la cita existe en la sección y fue vista. Etapa 2, solo si pasa la 1: el
  juez comprueba que respalda la respuesta. → [12 §5–§6](12_skill_evaluadores.md)
- **Hueco.** Dato que la empresa no reporta (10 reales, como el `GrossProfit` de AMZN, META y GOOGL) o que está fuera del corpus. La
  respuesta correcta es `fuente="ninguna"`; se evalúan aparte, fuera de los 20. → [10 §5](10_skill_golden_set.md), [02 §9](02_datos_corpus_y_xbrl.md)
- **Lista blanca.** Las herramientas reales (las cuatro del contrato y las añadidas). Filtra la trayectoria y deja fuera la tool sintética
  `RespuestaFinanciera` de `ToolStrategy`. → [12 §4](12_skill_evaluadores.md)
- **Modo aislado y dentro del agente.** Aislado: se llama directamente a la función de búsqueda (la cifra de recall de la tabla). Dentro del
  agente: el ancla está entre los chunks que devolvieron sus `search_filings` (diagnóstico). → [11 §2](11_skill_mejora_retrieval.md)
- **Oráculo (filtros oráculo).** Filtros sacados del golden y no del modelo: dan el techo de un paso de la escalera, no la cifra realista.
  → [11 §5](11_skill_mejora_retrieval.md)
- **Paseíto por el dataset.** Recorrido inicial por los datos antes de escribir preguntas o código. → [02 §7](02_datos_corpus_y_xbrl.md)
- **Prueba de humo.** Ejecución mínima con la API real (céntimos) para ver cómo se comporta Gemini de verdad, antes del 17.
  → [08 §10](08_skill_agente_salida_estructurada.md)
- **Registro de experimentos.** Lista de lo probado, con su efecto y coste, incluido lo que no movió la métrica (R15).
  → [13 §7](13_skill_medicion_informe_presentacion.md)
- **Techo.** El mejor recall que permite un paso: filtros oráculo, o hit@20 de la unión de listas en el híbrido (RRF solo reordena).
  → [11 §5–§6, §10](11_skill_mejora_retrieval.md)
