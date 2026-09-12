# Teoría: evaluar LLMs y agentes

> Requisitos: R09, R11, R15 (y R08, R12, R14) · Lee antes: [01_requisitos_y_contratos.md](01_requisitos_y_contratos.md) §2,
> [11_teoria_rag_retrieval.md](11_teoria_rag_retrieval.md), [12_teoria_agentes_react_tools.md](12_teoria_agentes_react_tools.md)
> · Después: [25_skill_evaluadores.md](25_skill_evaluadores.md), [26_skill_medicion_informe_presentacion.md](26_skill_medicion_informe_presentacion.md)

> Fuentes: [enunciado · Datos básicos, §1, §4.5, §5, §7]; slides de RAG (p.40–50) y de Tuning (p.50–57); [transcripcion_04sep · 00:52];
> [transcripcion_10sep · 02:26–02:29]; transformers-labs `05-llm/` (vía [32](32_repo_transformers_labs.md) §3 y §5); generative-ai
> `gemini/evaluation/` y `hc/` (vía [33](33_repo_generative_ai.md) §3.1, §3.2, §3.7 y §3.9); decisiones D06–D19 del mapa de cobertura.

**v1.0 · 12-sep-2026.** Conceptos para diseñar los evaluadores y leer la tabla baseline frente a final. El código está en
[25](25_skill_evaluadores.md) y la tabla y el informe, en [26](26_skill_medicion_informe_presentacion.md). Abreviaturas de las citas:
`ev/` = `gemini/evaluation/`, `ET/` = `gemini/evaluation/evaltask_approach/`, `hc/` = `gemini/sample-apps/gemini-hallcheck/` (repo
generative-ai); `[05-N · celda M]` = `transformers-labs · 05-llm/05-N-*.ipynb`. Marcas: **(probado)** = ejecutado en el venv del stack;
**(cálculo propio)** = aritmética hecha para este doc; ⚠️ = sin verificar.

## 1. Qué se evalúa y contra qué

- **Benchmarks frente a golden propio.** Los benchmarks públicos son "lo menos malo": hay que probar el modelo en tu caso de uso
  [transcripcion_04sep · 00:52]. Nuestro caso de uso es el golden propio de 20 preguntas (R06), más 10 ciegas que no ha visto nadie
  [enunciado · Datos básicos]. Los notebooks de Vertex recomiendan unos 100 ejemplos para las métricas agregadas
  [generative-ai · ET/bring_your_own_computation_based_metric.ipynb · celda 20]: con 20 hay que leer con cuidado (§9).
- **Retrieval frente a extremo a extremo** [slides RAG · p.46]. El retrieval se mide aislado, con recall@k contra el ancla (R08). El
  extremo a extremo mide la respuesta del agente (R11). Separarlos permite atribuir el fallo: un ancla que no está en el top-k es un fallo de
  búsqueda y una cita inventada con el ancla delante es un fallo de generación.
- **Con referencia frente a sin referencia** [slides RAG · p.48; generative-ai · ET/evaluate_rag_gen_ai_evaluation_service_sdk.ipynb · celdas 20, 47].
  Con referencia se compara con una verdad del golden (cifra, ancla, respuesta esperada, herramientas). Sin referencia se juzga la
  respuesta contra su propio contexto: faithfulness o groundedness, es decir, si lo que dice se deduce de lo que citó.
- **Cálculo frente a modelo.** Unas métricas las calcula una función Python; otras, un LLM que hace de juez. Las dos conviven en la misma
  tabla [generative-ai · ET/bring_your_own_computation_based_metric.ipynb · celda 22].

| Evaluador (R09 y D14) | Referencia | Quién decide |
| --- | --- | --- |
| (a) la cita existe, se vio y respalda | Sin referencia (respuesta frente a cita) + corpus | Código (etapa 1) + juez (etapa 2) |
| (b) la cifra coincide con XBRL | `xbrl_facts.parquet` | Código, con tolerancia |
| (c) trayectoria | `herramienta_esperada` + argumentos | Código |
| `correcta` | `respuesta_esperada` (+ ancla) | Juez de un solo criterio |
| (d) abstención | ¿hay dato en el corpus? | Código |

## 2. Métricas deterministas sobre texto y por qué no bastan

- **Exact match (EM):** 1 si las cadenas son idénticas. Sin normalizar, una mayúscula o una comilla `’` convierten un acierto en fallo
  [05-8 · celda 3]. Con `normalizar()` (NFKC, comillas y guiones a ASCII, minúsculas, espacios colapsados; D07) es la prueba de que una
  cita es literal. El caso sin respuesta, `""` frente a `"No answer found."`, da EM = 0 [05-8 · celdas 8–9]: la abstención se evalúa por
  estructura (`fuente == "ninguna"`, `cifra is None`), no comparando cadenas.
- **F1 de tokens** (estilo SQuAD): TP = tokens compartidos, FP = sobrantes, FN = que faltan; F1 = TP / (TP + (FP+FN)/2) [05-5 · celda 14].
  Tolera el orden y las paráfrasis cortas, pero no ve los números: "revenue was $60.9 billion" frente a "revenue was $6.09 billion" da F1 = 0,75
  separando por espacios (cálculo propio).
- **ROUGE-L:** F sobre la subsecuencia común más larga (LCS), que **no es contigua** [05-6 · celda 5]. Palabras sueltas de un párrafo
  puntúan alto aunque la frase no exista, y el mismo par con error ×10 da ROUGE-L = 0,75 (probado, [32 §3.2](32_repo_transformers_labs.md)).
  El notebook usa β = P/R y su LCS recursiva revienta con textos de 1.200 palabras [32 §5](32_repo_transformers_labs.md).
- **BLEU:** brevity penalty × media geométrica de las precisiones de 1 a 4-gramas con *clipping* [05-7 · celdas 4, 12, 18]. La
  implementación del repo da **1,0 a basura** porque descarta las precisiones nulas antes del logaritmo (probado,
  [32 §5](32_repo_transformers_labs.md)). Bien implementado, sigue premiando el solape léxico: castiga una paráfrasis correcta en español
  frente a un corpus en inglés y no distingue 60,9 de 6,09.
- **Cobertura de 4-gramas contiguos:** la precisión de n-gramas de [05-7 · celda 13] con n = 4 y sin *clipping*
  ([32 §3.2](32_repo_transformers_labs.md)). Cambiar una palabra en una frase de 25 la deja en ≈ 0,82 (cálculo propio). Sirve para separar
  "casi literal" (fallo de normalización) de "inventada".

**Resolución:** BLEU, ROUGE y F1 de tokens, **solo como diagnóstico**. Las citas se aprueban por substring normalizado (D07, D13), las
cifras se comparan como números y nunca como cadenas (D06) y el respaldo semántico lo decide un juez validado (§6).

## 3. Clasificación: TP/FP/FN, P/R/F1, micro y macro

- TP, FP y FN se cuentan respecto a una clase positiva [05-5 · celda 4]; precision = TP/(TP+FP), recall = TP/(TP+FN), F1 = media armónica
  [05-5 · celdas 7–15].
- **Micro** suma antes de dividir; **macro** promedia por clase y da el mismo peso a una clase con pocos casos [05-5 · celdas 25, 36]. En
  la tabla R11: micro = aciertos/preguntas y macro = media de las tres familias. Si el golden tiene 8 numéricas, 6 extractivas y 6
  comparativas, micro pesa más las numéricas; macro no. Una familia sin preguntas (posible en las ciegas) es "—", nunca 0: 05-5 esquiva el
  0/0 fijando a mano `n_class = 5` para seis etiquetas [05-5 · celdas 19–20].
- **Enrutado por herramienta (R15):** por cada tool, TP = se esperaba y se usó, FP = se usó sin esperarse, FN = se esperaba y no se usó
  [generative-ai · ev/evaluate_with_your_python_code.ipynb · celda 20]. Separado por familia, es la diapositiva de "enrutado exacto frente a
  difuso": XBRL para cifras, texto para lo cualitativo.

## 4. Métricas de retrieval

Las slides nombran precision, recall, hit-rate, MRR y nDCG, sin fórmulas [slides RAG · p.47]. Con **una sola relevancia por pregunta**
(el ancla, D08):

| Métrica | Definición con un ancla | Uso |
| --- | --- | --- |
| recall@k = hit-rate@k | fracción de preguntas con el ancla (normalizada) dentro de algún chunk del top-k | **Principal, @5** (el `k` del contrato); @1, @3 y @10 como curva |
| MRR@10 | media de 1/rango del primer chunk con el ancla (0 si no está en el top-10) | Secundaria: dice si un arreglo **sube** el ancla de puesto |
| nDCG@k | con una relevancia, 1/log₂(1+rango): 1; 0,63; 0,5… | **Fuera** (C09) |

- nDCG solo aporta con relevancias graduadas o múltiples. Con una sola, es otra transformación del rango, más plana que MRR (cálculo propio),
  y la documentación de Vertex la considera problemática [generative-ai · search/ranking-api/ranking_api_beir_evaluation.ipynb · celda 3].
  La de RAG Engine incluso supera 1 [generative-ai · gemini/rag-engine/rag_engine_evaluation.ipynb · celda 44].
- **Estricto frente a laxo (C07):** acierto = substring normalizado. La cobertura de 4-gramas ≥ 0,8 infla el recall y va aparte, como
  diagnóstico. Antes de medir se comprueba que cada ancla cabe entera en algún chunk del índice en uso (`anclas_no_indexables`): el 60 % de
  los cortes no se solapa [02 §3](02_datos_corpus_y_xbrl.md).
- **Techo y azar.** Con filtros oráculo se mide un techo; con filtros, el acierto aleatorio es `min(1, k/|candidatos|)` y el 7A tiene de 1 a
  5 chunks. Un recall@5 alto en el 7A no demuestra nada (D08).
- **Modo aislado frente a dentro del agente.** La tabla R11 lleva el aislado (la función de búsqueda con la pregunta); `recall_agente` (el
  ancla en la unión de lo que devolvió `search_filings` en la trayectoria) diagnostica si el agente busca bien. Detalle en
  [11](11_teoria_rag_retrieval.md) y [24](24_skill_mejora_retrieval.md).

## 5. Evaluar la trayectoria de un agente

"Acertar por el camino equivocado cuenta como fallo, y hay un evaluador escrito para detectarlo" [enunciado · §1]. Las métricas de Vertex
[generative-ai · ET/evaluating_langgraph_agent.ipynb · celda 44], sobre nombres de herramienta:

| Métrica | Pasa si… | Ejemplo: ref = [xbrl, search]; pred = [search, xbrl(FY25), xbrl(FY24)] |
| --- | --- | --- |
| exact | misma secuencia, mismo orden | 0 |
| in_order | las de referencia aparecen en orden; se permiten extras | 0 |
| any_order | aparecen todas, sin importar orden ni extras | 1 |
| precision | fracción de llamadas que estaban en la referencia (multiconjunto) | 0,67 |
| recall | fracción de la referencia que se llamó | 1 |
| redundantes / eficiencia | llamadas repetidas con los mismos args / `min(1, óptimo/reales)` | 0 / 0,67 |

(Ejemplo calculado con `metricas_trayectoria` de [33 §3.1](33_repo_generative_ai.md), probado.)

- **Argumentos.** Las métricas de parámetros de Vertex solo miran `tool_calls[0]` y dividen por la unión de claves
  [generative-ai · ev/evaluate_with_your_python_code.ipynb · celdas 14, 16]. Lo que importa aquí es otra cosa: que alguna `get_xbrl_fact` lleve
  ticker, FY y concepto correctos. Es lo único que caza la confusión de concepto que la tolerancia deja pasar (META FY2024: caja y R&D al
  0,04 % [32 §3.3](32_repo_transformers_labs.md)) y la confusión de año.
- **No deduplicar.** El parser del tutorial de ADK añade una llamada solo si no estaba [generative-ai · ev/evaluating_adk_agent.ipynb · celda 14]:
  esconde los bucles y rebaja las llamadas por pregunta (C26). Redundancia = mismo (nombre, args) repetido
  [generative-ai · ev/multi_turn_agent_evaluation_with_user_simulation_metric_registration_auto_loss_analysis.ipynb · celda 24];
  eficiencia [generative-ai · ev/agent_as_a_judge_eval.ipynb · celda 16].
- **Verificar el estado, no el texto.** Un juez que solo lee lo que dice el agente "se cree" la alucinación; el que consulta la fuente de verdad
  la caza [generative-ai · ev/multi_agent_state_verification_eval.ipynb · celda 21]. Por eso (b) y R05 buscan la verdad en el parquet con los
  argumentos de cada llamada y no parsean el `ToolMessage` (D12, D15).
- **Qué elegimos.** No se sabe cómo puntuará el evaluador del día 24 más allá de los nombres [enunciado · §7]. (c) = recall 1 ∧ argumentos
  ok (D12); exact, in_order, precision, redundancia y eficiencia van como diagnóstico.

## 6. LLM-as-a-judge

Un LLM puntúa contra una rúbrica, en modo directo (*pointwise*) o por pares (*pairwise*) [slides RAG · p.48;
generative-ai · ET/customize_model_based_metrics.ipynb · celdas 21–25]. La plantilla tiene criterio, rúbrica, pasos y variables de entrada.

**Reglas de diseño**
- **Un criterio por juez** [slides Tuning · p.50]: un juez de respaldo para (a) y otro de corrección (`correcta`), nunca uno "global".
- **Binario con razonamiento primero**, en lugar de la escala 1–5 de la slide [slides RAG · p.48]. El campo `razonamiento` va antes que la
  etiqueta en el esquema, para que el modelo razone antes de decidir.
- **Groundedness frase a frase** (estilo FACTS): cada frase de la respuesta es `supported`, `unsupported`, `contradictory` o `no_rad` (no
  requiere atribución), sin conocimiento del mundo [generative-ai · ET/evaluate_groundedness_with_custom_parsing.ipynb · celda 24]. Así, una
  comparativa con una mitad respaldada y otra no suspende. El parser original deja `no_rad` en el denominador [celda 22]: lo sacamos (D13).
  Resuelve C10 frente al SUPPORTS/REFUTES/NOT_ENOUGH_INFO de [31 §3.5](31_repo_genai_labs.md), que da una etiqueta por respuesta.
- **Corrección contra la referencia:** formato flexible, unidades estrictas ("100 millas" no es "100 km") y un "no tengo el dato" es inválido si
  la referencia lo tiene [generative-ai · ET/evaluate_agent_final_answer_with_custom_parsing.ipynb · celda 24].
- **Primero lo determinista.** El juez solo corre si la cita existe literal y el agente la vio (etapa 1, D13): es gratis, reproducible y
  quita al juez los casos en que "se cree" una cita inventada.

**Sesgos**
- **Longitud:** "long answers are not best answers" [slides Tuning · p.50]. La rúbrica pide ignorarla.
- **Posición** (en pairwise): se aleatoriza el orden [generative-ai · ET/evaluate_autorater.ipynb · celda 23]. Aquí no se usa pairwise.
- **Auto-preferencia:** el juez por defecto es el mismo modelo que el agente (D01). Ninguna fuente lo trata ⚠️: se controla validando al juez y,
  si el kappa sale bajo, probando otro modelo como juez.
- **Exceso de confianza fuera de distribución:** el reward model es "overconfident" fuera de su distribución [slides Tuning · p.54]. Un juez
  validado con citas cortas puede fallar con tablas.

**Validar al juez (meta-evaluación)** [generative-ai · ET/evaluate_autorater.ipynb · celda 25]: 30–40 pares etiquetados a mano con negativos
construidos (cifra alterada, cita de otra pregunta, cita que menciona el tema pero no la cifra, escala ×1.000); acuerdo, **kappa de Cohen** y
matriz de confusión. κ = (p_o − p_e) / (1 − p_e), donde p_o es el acuerdo observado y p_e el esperado por azar con las proporciones de cada
anotador. El acuerdo solo engaña: con 32 positivos de 40, un juez que siempre dice "supported" acierta el 80 % y tiene κ = 0; uno con 2 FN y
3 FP acierta el 87,5 % y tiene κ = 0,59 (cálculo propio). Los **falsos positivos** del juez (aprueba lo que el humano suspende) son el error
caro. `rate_batch` descarta en silencio los veredictos que no parsean [celda 21]: hay que contarlos. La self-consistency (N llamadas y
consenso [celda 21]) apenas aporta a `temperature=0`. Umbral de aceptación: propuesta propia en [25](25_skill_evaluadores.md).

## 7. Cifras: tolerancia absoluta frente a relativa

`math.isclose(a, b, rel_tol, abs_tol)` [05-5 · celda 16]: la relativa escala con la magnitud y la absoluta no. La tolerancia tiene que ser
**mayor** que el redondeo legítimo y **menor** que la diferencia más pequeña que importa (D06, datos de [02 §5](02_datos_corpus_y_xbrl.md)):

| Unidad | Redondeo legítimo | Diferencia que no se puede tragar | Tolerancia |
| --- | --- | --- | --- |
| USD (miles de millones) | "$391 billion" (3 cifras significativas) | menor cambio interanual: 1,57 % | relativa 0,5 % |
| USD/shares (BPA) | ninguno: se reporta al céntimo | básico frente a diluido: 0,03 | absoluta 0,005 |

- Con un 0,5 % relativo en el BPA, el diluido 6,08 pasaría por el básico 6,11 (0,49 %) [32 §3.3](32_repo_transformers_labs.md): por eso el BPA
  va en absoluto (C06). La tolerancia se escribe en el informe (R09) y se enseña su **sensibilidad** (0 %, 0,1 %, 0,5 %, 1 %), re-puntuando sin
  volver a ejecutar.
- **Escala.** Se reescala por palabras de la unidad ("millones", "billion"); si el valor cuadra a ×10^±3/6/9, se etiqueta `error_escala`, que
  sigue siendo fallo. "Billones" (10¹²) se deja fuera a propósito: "60,9 billones" es un error de ×1.000 [22 §4](22_skill_guardrails_middleware_xbrl.md).
- Ninguna tolerancia distingue conceptos con valores parecidos: eso es trabajo de (c) (§5).

## 8. Abstención y alucinación

- hallcheck puntúa +1 si acierta, −t/(1−t) si falla y 0 si se abstiene, y mide cobertura (respondidas/total), acierto condicionado y tasa de
  alucinación entre las respondidas [generative-ai · hc/src/gemhall/metrics.py · l. 19–47], más la curva riesgo-cobertura [hc/README.md · l. 7].
  Con t = 0,75, un fallo resta 3.
- Falta la mitad que pide el profesor: detectar cuándo "te ha dicho que no había respuesta cuando sí que había"
  [transcripcion_10sep · 02:29]. **Abstención correcta** = `ninguna` en un hueco; **abstención indebida** = `ninguna` con dato (falso
  "ninguna"). Sin la segunda, un agente que siempre dice "no está" parece honesto [33 §3.9](33_repo_generative_ai.md).
- Los huecos no caben en el golden de 20 porque `validar()` exige cifra o ancla (D11): van en un fichero aparte y se miden con el mismo `evaluar()`.
- Baseline y final son dos puntos de la curva riesgo-cobertura: un final que responde más y alucina menos domina; uno que "mejora" a base de
  abstenerse, no.

## 9. Muestras pequeñas: ruido y significación

- **Granularidad.** Con 20 preguntas, cada una vale 5 pp; en las ciegas, 10 pp; en recall@k, con unas 14 anclas, ≈ 7 pp. Siempre k/n junto al %.
- **Ruido.** `temperature=0` hace la decodificación casi voraz, pero no garantiza el mismo resultado entre llamadas: ⚠️ no se ha comprobado
  que sea determinista en OpenRouter y `seed` no está verificado (D01). Ejecutar el baseline dos veces sin cambiar nada da el ruido de fondo
  [32 §3.6](32_repo_transformers_labs.md). Las repeticiones sirven para estimar el ruido, no para promediar la tabla.
- **Ganadas y perdidas.** La comparación es pareada (mismas preguntas): se cuentan las preguntas que el final gana y pierde frente al
  baseline, no solo los totales. +2 netas pueden ser 2 ganadas y 0 perdidas, o 6 y 4.
- **Test pareado (propuesta propia, ninguna fuente lo trae):** test de signo o McNemar exacto sobre las discordantes. Con 5 ganadas y 1
  perdida (+20 pp), p ≈ 0,22 bilateral (cálculo propio): con n = 20, casi ninguna mejora es "significativa". Se informa la dirección y los
  conteos, sin reclamar significación.

## 10. Sobreajuste, reward hacking y hold-out

- Iterar solo contra las 20 propias es optimizar un reward construido con muy pocos datos: la política puede "hackear" la métrica sin cumplir
  el objetivo [slides Tuning · p.55–56]. Analogía propia, útil en la presentación.
- Síntomas de memoria del golden: docstrings o prompt con casos concretos del golden, reglas "si preguntan X, usa Y" para una pregunta, la
  lista de huecos en el prompt (D22), preguntas escritas con el vocabulario del chunk (inflan BM25 [33 §3.8](33_repo_generative_ai.md)) e
  hiperparámetros ajustados contra el golden (D09). ClearBox valida con 5 semillas × 3 folds y su mejora final, ~0,04 en recall@1, es menos que
  una pregunta de 20 [generative-ai · search/custom-ranking/clearbox.ipynb · celdas 31, 41].
- **Hold-out.** Las 10 ciegas son el test fuera de distribución; llmevalkit recomienda probar al ganador "on a blind case"
  [generative-ai · tools/llmevalkit/README.md · «Tutorial» paso 5]. Si el acierto baja, hay que explicar qué parte era general y qué parte
  memoria del conjunto: "eso es un hallazgo, no un suspenso" [enunciado · §5].
- **Ejecutar ≠ puntuar.** Se guardan las predicciones y se puntúa desde los ficheros (patrón BYOD
  [generative-ai · ET/evaluating_langgraph_agent.ipynb · celdas 71–73]). Así el baseline congelado se re-puntúa con el evaluador nuevo sin
  volver a ejecutarlo (R12), y los cambios de tolerancia o de juez no cuestan llamadas.

## 11. Coste y latencia como métricas

- Son **observabilidad**, junto con tokens, prompts y trazas [slides RAG · p.50]; Vertex separa *monitoring* (herramientas, trayectoria,
  respuesta) de *observability* (latencia, tasa de fallo) [generative-ai · ET/evaluating_langgraph_agent.ipynb · celda 31]. R11 los exige
  **como columnas**.
- **Coste:** tokens × precio de una tabla fechada, con el callback de uso, que también cuenta la reescritura y los reintentos de R05 (D16). El
  juez va aparte: no es coste del agente. "Coste por acierto" ayuda a leer el trade-off (propuesta de [32 §3.6](32_repo_transformers_labs.md)).
- **Latencia:** `perf_counter` alrededor de la invocación, tras calentar el índice (la primera búsqueda carga ~130 MB), preguntas en secuencia,
  media y mediana (D17). Las slides dan como objetivo retrieval < 300 ms y extremo a extremo 2–3 s [slides RAG · p.45]; con varias llamadas al
  LLM, lo segundo no es realista: se reporta lo que salga.
- **Llamadas por pregunta** y tasa de fallo: menos llamadas solo es mejor con aciertos parecidos (D18).
- El trade-off coste/latencia/precisión [slides RAG · p.40] es la pregunta que se hará a todos los grupos [enunciado · §5].

## 12. Qué implica para la práctica

1. **Un evaluador por criterio, determinista primero.** (a) etapa 1 (existe y vista) en código y etapa 2 con juez frase a frase; (b) con
   `cifra_ok` (D06), la misma que usa R05; (c) con recall de herramientas y argumentos (D12). `correcta`, con un juez aparte (D14).
2. **Nada de BLEU ni ROUGE para decidir.** Como mucho, cobertura de 4-gramas para diagnosticar citas casi literales.
3. **Validar a los jueces antes de usar sus números**: 30–40 pares, kappa, matriz de confusión y fallos de parseo contados (D13). Veredictos
   cacheados para que re-puntuar sea reproducible y gratis.
4. **recall@5 estricto contra el ancla** como cifra de retrieval, con MRR@10 y la curva @1/3/10 de un único top-20 (D08). Sin nDCG.
5. **Abstención medida en las dos direcciones** (correcta e indebida) con el fichero de huecos (D11).
6. **Micro y macro, siempre k/n**, familias vacías como "—", ganadas y perdidas, y el baseline repetido para ver el ruido.
7. **Ejecutar ≠ puntuar**: predicciones en JSONL y todo lo demás regenerado desde ahí (D19), con el baseline congelado en `baseline-v1`.
8. **Coste y latencia como columnas**, con el juez fuera del coste medio.
9. **Las ciegas son el hold-out**: no se itera contra ellas y el delta se explica como memoria frente a generalización.

## Fuentes

- [enunciado · §1, §4.5, §5, §7] (`00_enunciado.md`) y [01_requisitos_y_contratos.md](01_requisitos_y_contratos.md) §2–3.
- Slides de RAG (módulo NLP): p.40, p.45–50 (evaluación, LLM-as-a-judge, observabilidad). Slides de Tuning: p.50, p.54–57 (normas de
  etiquetado, reward model, reward hacking).
- [transcripcion_04sep · 00:52] ("benchmarks: lo menos malo"); [transcripcion_10sep · 02:26–02:29] (evaluadores como "minifunciones",
  falsos "ninguna").
- transformers-labs · `05-llm/05-5-eval-classification.ipynb`, `05-6-eval-summarization.ipynb`, `05-7-eval-textgeneration.ipynb`,
  `05-8-eval-qna.ipynb`, consolidados en [32_repo_transformers_labs.md](32_repo_transformers_labs.md) §3.1–3.4, §3.6 y §5.
- generative-ai · `ET/evaluating_langgraph_agent.ipynb`, `ev/evaluate_with_your_python_code.ipynb`, `ET/evaluate_groundedness_with_custom_parsing.ipynb`,
  `ET/evaluate_agent_final_answer_with_custom_parsing.ipynb`, `ET/evaluate_autorater.ipynb`, `ET/customize_model_based_metrics.ipynb`,
  `ev/multi_agent_state_verification_eval.ipynb`, `hc/src/gemhall/metrics.py`, `search/custom-ranking/clearbox.ipynb`,
  `tools/llmevalkit/README.md`, consolidados en [33_repo_generative_ai.md](33_repo_generative_ai.md) §3.1, §3.2, §3.7–3.9.
- [31_repo_genai_labs.md](31_repo_genai_labs.md) §3.5 (juez de tres etiquetas); [02_datos_corpus_y_xbrl.md](02_datos_corpus_y_xbrl.md) §3 y §5;
  [22_skill_guardrails_middleware_xbrl.md](22_skill_guardrails_middleware_xbrl.md) §4.
- Notas de trabajo (no versionadas): `C2_evaluacion_llms.md`, `D3_evaluacion_agentes.md`, `D12_retrieval_rag_grounding.md`,
  `A5_slides_rag.md`, `A6_tuning_agenda.md`, `A34_nlp_teoria.md` y el mapa de cobertura (decisiones D06–D19, contradicciones C06, C07, C09, C10, C26).
