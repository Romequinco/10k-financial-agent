# Teoría: RAG y retrieval

> Requisitos: R08, R09 (y R07, R11, R14) · Lee antes: [10_teoria_tokenizacion_embeddings.md](10_teoria_tokenizacion_embeddings.md),
> [02_datos_corpus_y_xbrl.md](02_datos_corpus_y_xbrl.md) §3 y §6 · Después: [24_skill_mejora_retrieval.md](24_skill_mejora_retrieval.md),
> [13_teoria_evaluacion_llms.md](13_teoria_evaluacion_llms.md) §4, [12_teoria_agentes_react_tools.md](12_teoria_agentes_react_tools.md)

> Fuentes: slides de RAG del módulo NLP (vía nota A5 y [30 §7](30_clase_pistas_del_profesor.md)); [enunciado · §1, §3, §4.3, §4.4];
> [transcripcion_10sep · 00:05, 00:44, 02:26] y [transcripcion_05sep · 00:49–00:51] (vía [30](30_clase_pistas_del_profesor.md)); `miax_s1.py`
> (`buscar()`, `formatear_fragmentos()`); generative-ai `embeddings/`, `search/` y `gemini/` (vía [33 §3.7](33_repo_generative_ai.md) y nota D12);
> [perfil_dataset · chunks.jsonl, LEEME]; decisiones D07–D09 y D13 del mapa de cobertura; cálculos sobre `data/corpus/`.

**v1.0 · 12-sep-2026.** La teoría de RAG que hay detrás de R08 y de la tesis "el retrieval es una herramienta más". La receta (escalera,
código y checklist) está en [24](24_skill_mejora_retrieval.md). Citas de las slides: `p.` = página del PDF y `diap.` = número impreso.
Abreviaturas: `hybrid-search`, `task-type` = `generative-ai · embeddings/*.ipynb`; `clearbox` = `generative-ai · search/custom-ranking/clearbox.ipynb`;
`rag-engine` = `generative-ai · gemini/rag-engine/rag_engine_evaluation.ipynb`. Marcas como en [10](10_teoria_tokenizacion_embeddings.md).
**Revisar** cuando haya transcripción de la clase de RAG (12-sep) y después de la sesión del 17, que abre `search_filings`
[30 §6](30_clase_pistas_del_profesor.md).

## 1. RAG clásico frente a retrieval como herramienta

- **Factuality frente a grounding.** Factuality es que la respuesta se base en hechos reales; grounding es poder explicar cómo la respaldan
  los documentos, comprobando que **cada afirmación** se deduce de ellos [slides RAG · p.3, diap. 6]. Es la definición del evaluador (a).
- **Memoria paramétrica frente a no paramétrica.** Los pesos del LLM se quedan desactualizados y no dicen de dónde sale un dato; un corpus
  externo sí [slides RAG · p.6, diap. 13]. Aquí la memoria no paramétrica son XBRL y los chunks, y la paramétrica no debe aportar cifras
  (R05, R14).
- **El pipeline.** La ingestión es offline (extraer → trocear → embeber → indexar) y la consulta, síncrona (embeber la consulta → top-k →
  generar) [slides RAG · p.8–9, diap. 22–23]. En la práctica la ingestión viene hecha: índice y metadatos se entregan construidos
  [enunciado · §3].
- **Por qué falla el RAG ingenuo.** Low precision (chunks mal alineados con la pregunta), low recall (no llegan todos los relevantes) y
  alucinación al generar [slides RAG · p.10, diap. 26]. En un 10-K, el profesor añade dos: los datos en tablas y las respuestas repartidas
  en varios puntos [transcripcion_10sep · 00:05].
- **Paradigmas.** Naive, advanced (pre-retrieval, indexado, retrieval y post-retrieval), modular, graph y agentic RAG
  [slides RAG · p.9–12, diap. 24–30]. En el **agentic RAG** el agente interpreta la intención, extrae las restricciones como filtros, llama a
  la búsqueda adecuada con los parámetros adecuados, itera y sintetiza [slides RAG · p.14–15, diap. 36–37]. No busca una vez y dice "no lo
  sé": investiga en otras secciones hasta encontrar el dato [transcripcion_10sep · 00:44].
- **La tesis de la práctica.** "El retrieval no es la arquitectura, sino una herramienta más", y acertar por el camino equivocado cuenta
  como fallo [enunciado · §1].

| | RAG clásico | Nuestro agente |
| --- | --- | --- |
| Quién escribe la consulta | El pipeline, con la pregunta tal cual | El modelo, en los argumentos de `search_filings` (D09) |
| Filtros | Fijos o ninguno | Los extrae el modelo: `ticker`, `fiscal_year`, `item` |
| Búsquedas por pregunta | Una | Las necesarias, con tope (D04) |
| Fuentes | Un índice | XBRL (`get_xbrl_fact`), chunks (`search_filings`) y la sección entera (`read_section`) |
| Fallo típico | El top-k no trae la respuesta | Herramienta equivocada, filtros mal puestos, bucles |
| Cómo se evalúa | Recall y respuesta | Recall aislado y dentro del agente, más la trayectoria (c) |

## 2. Chunking

- **Por qué importa.** Sale un vector por trozo, y una página queda mejor representada que seis: "este es el dilema de los sistemas RAG"
  [transcripcion_05sep · 00:49–00:51]. Antes de trocear hay que conocer los documentos (tablas, jerarquía, listas), el límite de tokens del
  modelo de embeddings y la forma de las consultas, y añadir metadatos. "Experiment with chunk size!" [slides RAG · p.31, diap. 72].

| Estrategia | Idea | Precio | Fuente |
| --- | --- | --- | --- |
| Tamaño fijo con solape | Barato. Chunk pequeño = embedding preciso; grande = embedding general que pierde detalle | Parte frases | [slides RAG · p.31, diap. 73] |
| Por frase, párrafo, recursivo o por cabeceras; tablas aparte | Respeta la estructura | Trozos de tamaño irregular | [slides RAG · p.32, diap. 74–75] |
| *Small-to-big*: sentence window, parent document | Se busca con el trozo pequeño y se devuelve el grande | Más tokens por llamada | [slides RAG · p.33–34, diap. 76–78] |
| Metadatos o cabecera en el chunk (`{"org": "Alphabet", "year": "2022"}`) | El chunk "sabe" de quién y de cuándo es | Reembeber todo | [slides RAG · p.34, diap. 79] |

- **Nuestro troceado** [02 §3](02_datos_corpus_y_xbrl.md): 1.749 chunks de media 401,8 tokens (máximo 547). El "solape de 80" solo se da
  cuando el corte cae dentro de un párrafo: el 60 % de los pares consecutivos no se solapa, y el 49 % de los chunks que no cierran su
  sección acaba a mitad de frase (datos). Por eso el ancla es texto y no `chunk_id`, que cambia al re-trocear [enunciado · §4.3], y por eso
  el profesor avisa de que "vais a cambiar el troceado" [30 §6](30_clase_pistas_del_profesor.md). Al trocear, mejor cortar "por los
  puntos" [transcripcion_05sep · 04:22].
- **No copiéis el código de las slides.** Sus `chunk_size` (100–128) son **caracteres** (`length_function=len`) y solo ilustran
  [slides RAG · p.32, diap. 74]. El código es de LangChain 0.x o de LlamaIndex antiguo: `langchain.text_splitter`
  [slides RAG · p.31–32, diap. 73–75] y `ServiceContext` [slides RAG · p.49, diap. 119]. Ni `langchain-text-splitters` ni
  `langchain-classic` están en el stack fijado (nota A5).

## 3. Denso, disperso e híbrido

- **Denso** (bi-encoder, [10 §3](10_teoria_tokenizacion_embeddings.md)): capta semántica y paráfrasis, pero falla con identificadores sin
  asociación semántica, como SKU, marcas, códigos o nombres nuevos [slides RAG · p.22, diap. 52; hybrid-search · celda 5].
- **Disperso** (TF-IDF, BM25, SPLADE; [10 §2](10_teoria_tokenizacion_embeddings.md)): coincidencia exacta de términos; falla con
  paráfrasis y con otro idioma. En nuestro corpus, una pregunta en español solo casa por nombres propios, cifras y préstamos (datos).
- **Híbrido** = dos listas y una fusión. Las puntuaciones no son comparables (BM25 no está acotado; el coseno va de −1 a 1): "viven en
  espacios distintos" [hybrid-search · celda 59]. Por eso se fusionan **rangos**, con Reciprocal Rank Fusion [slides RAG · p.42, diap. 96,
  que cita a Cormack et al., SIGIR 2009]:

```text
RRF(d) = Σ_{listas l}  w_l / (k + rango_l(d))        rango desde 1; si d no está en la lista l, no suma nada
```

  Admite un peso por lista [slides RAG · p.28, diap. 65]. En Vertex, `rrf_ranking_alpha` = 1 es solo denso, 0 solo disperso y 0,5 el mismo
  peso [hybrid-search · celda 59].
- **La constante `k` cambia el resultado** (C18). Las slides no le dan valor, el notebook de hybrid-search suma 1/rango sin constante
  [hybrid-search · celda 59] y ClearBox usa 40 [clearbox · celda 35]. Ejemplo (cálculo propio):

| Documento | Denso | BM25 | RRF con k = 60 | Σ 1/rango (sin constante) |
| --- | --- | --- | --- | --- |
| A | 1.º | — | 1/61 = 0,016 | 1,000 |
| B | 3.º | 3.º | 2/63 = 0,032 | 0,667 |

  Con k = 60 gana el consenso (B); sin constante, el primer puesto de una sola lista (A). **Decisión:** k = 60, pesos iguales y `n_cand = 20`
  por lista, fijados antes de medir y sin cambiar entre filas de la escalera (D09). k = 60 es el valor habitual asociado al paper que citan
  las slides (⚠️ no leído); lo que importa es fijarlo.
- **RRF solo reordena lo que traen las listas**: el techo del híbrido es la unión de los dos top-20. Hay que reportar también "solo BM25",
  que es el baseline por señal [clearbox · celdas 32–33].
- **"Híbrido" tiene dos sentidos** (C20): denso + disperso (hybrid-search) o vector + `WHERE` sobre metadatos, como en GenWealth
  [generative-ai · gemini/sample-apps/genwealth/README.md · «Gen AI Integrations»]. En el informe, "filtro" e "híbrido" son dos arreglos
  distintos de R08.

## 4. Filtros por metadatos: pre frente a post

- Cada chunk lleva metadatos y se filtra al consultar [slides RAG · p.34, diap. 79]; en el agentic RAG, las restricciones de la pregunta se
  convierten en filtros [slides RAG · p.15, diap. 37]. Las slides lo colocan en dos sitios: junto con la consulta [diap. 79] y en el
  post-retrieval, al lado del reranking (por score, recencia, metadatos o permisos) [slides RAG · p.41, diap. 94].
- **Pre-filtro**: se restringe el conjunto de candidatos y se ordena dentro. **Post-filtro**: se ordena, se corta y luego se descarta. Dan lo
  mismo si el ranking es exhaustivo y el corte llega después del filtro. El post-filtro pierde recall en cuanto se corta un top-N antes de
  filtrar: ANN, el `n_cand` del híbrido o un rerank.
- **Nuestro caso.** `buscar()` pide los 1.749 vectores (`indice.search(q, ntotal)`) y filtra después, así que su post-filtro no pierde nada
  [01 §5, trampa 7](01_requisitos_y_contratos.md). El arreglo "filtro" mide, por tanto, dos cosas (D09): en modo aislado y con filtros
  oráculo, el **techo**; dentro del agente, si el modelo **pasa** bien los filtros (porcentaje de llamadas con `ticker`, `fiscal_year` e
  `item` correctos, [24 §5](24_skill_mejora_retrieval.md)). En el híbrido y en el rerank, el pre-filtro es obligatorio.
- **Tamaño del candidato** [perfil_dataset · chunks.jsonl]: ticker + FY deja entre 89 y 214 chunks; con item, entre 1 y 90 (1A 30–85,
  7 10–36, 7A 1–5, 8 43–90). Con filtro, el acierto aleatorio es min(1, k/|candidatos|): en el 7A, recall@5 es trivial (D08).
- **Un filtro equivocado deja el recall a 0**: el año de presentación en lugar del fiscal (el FY2025 de GOOGL se presentó en 2026) o
  `item="15"` para los estados financieros de NVIDIA, que el corpus sirve como `"8"` [02 §1–2](02_datos_corpus_y_xbrl.md).
  `formatear_fragmentos()` ya sugiere quitar filtros cuando no hay resultados [miax_s1.py · formatear_fragmentos()], que es la idea de la
  consulta *self-correcting* [slides RAG · p.36, diap. 82].

## 5. Transformar la consulta

- Pequeños cambios en la redacción cambian mucho lo que se recupera, y la consulta de búsqueda no tiene por qué ser la pregunta que se
  responde [slides RAG · p.36, diap. 82].

| Técnica | Qué hace | En nuestro caso | Fuente |
| --- | --- | --- | --- |
| Reescritura y traducción | Extraer keywords o entidades, acortar, pasar al idioma y al vocabulario del corpus | Pregunta en español → consulta en inglés con términos de 10-K (*net revenue*, *risk factors*) | [slides RAG · p.36, diap. 82]; [10 §3](10_teoria_tokenizacion_embeddings.md) |
| Descomposición | *Single-step* (revenue de Uber y de Lyft → dos subpreguntas) o *multi-step* (encadenadas) | Comparativas: una subconsulta por FY | [slides RAG · p.36, diap. 82] |
| Multi-query | N consultas desde perspectivas distintas; unión deduplicada | 1–3 consultas fusionadas con RRF | [slides RAG · p.37, diap. 84] |
| Self-correcting | Evaluar el resultado y reintentar | Reintentar sin `item` si no hay resultados | [slides RAG · p.36, diap. 82] |
| HyDE | Embeber una respuesta hipotética que escribe el LLM | Fuera de la escalera; opcional | ⚠️ no está en las slides; [task-type · celda 5] |

- **Plan-and-Solve**: plantilla con rol, sinónimos, pasos de razonamiento y ejemplos *few-shot* con salida JSON [slides RAG · p.36, diap. 83].
  Es el origen de nuestro esquema `Busqueda` con salida estructurada.
- **HyDE y la expansión con LLM** cuestan segundos y dinero por consulta [task-type · celda 5]. En un 10-K la respuesta hipotética inventa
  cifras y puede atraer chunks con números parecidos (hipótesis): por eso no entra en la escalera.
- **Decisión** (D09, paso 3): `reescribir(pregunta) → Busqueda{1–3 consultas en inglés, filtros}`, cacheada, con multi-query y una
  subconsulta por FY; es la medida en modo aislado. **Dentro del agente** reescribe el propio modelo en los argumentos de `search_filings`,
  guiado por un docstring con las mismas instrucciones, porque la tool no ve la pregunta original (C21). En la demo del profesor, la `query`
  era "literalmente la pregunta que podría hacer un usuario" [transcripcion_10sep · 00:44]: ese es el paso 0.
- **Coste**: en modo aislado, una llamada más al LLM por pregunta; en el agente, tokens del propio bucle. El callback de D16 captura las dos.

## 6. Reranking y cuánto contexto ver

- **Sistema multietapa**: recuperar deprisa y ordenar con precisión los candidatos [hybrid-search · celda 55].

| | Bi-encoder (bge) | Cross-encoder |
| --- | --- | --- |
| Entrada | Consulta y pasaje por separado | `consulta [SEP] pasaje`, juntos |
| Documentos precalculables | Sí | No: una pasada del transformer por cada par |
| Salida | Un vector; se compara por coseno | Un score de relevancia (0–1) |
| Uso | Recuperar entre los 1.749 | Reordenar el top-20 |

  [slides RAG · p.4, diap. 8; p.42, diap. 97; slides NLP_S2 · p.24, p.26]. El cross-encoder se puede afinar con datos propios
  [slides RAG · p.42, diap. 97].
- **Rerank con LLM** (puntuar de 1 a 10, o por pares con PRP): alucina, cuesta y es lento [slides RAG · p.41, diap. 95]. La compresión
  contextual con LLM también es cara [slides RAG · p.38–39, diap. 88–89].
- **El rerank no recupera, reordena**: su techo es el hit@20 previo. El profesor lo nombró como extra ("los warrers", ⚠️ ASR, probablemente
  *rerankers*) [transcripcion_10sep · 02:26]. ⚠️ `CrossEncoder` no está comprobado en sentence-transformers 6.0.1; el modelo se descarga en el
  clon limpio (R10) y su latencia va a R11 ([24 §11](24_skill_mejora_retrieval.md)).
- **Lost in the middle.** Con un top-k estático, añadir chunks puede empeorar la respuesta; con más de 10, los mejores van al principio y al
  final [slides RAG · p.37–38, diap. 85, 87]. FiD mejora con más pasajes, pero está entrenado para ello [slides RAG · p.7, diap. 15–16]. Si
  se sube `k`, hay que medir también el acierto extremo a extremo.
- **Contexto largo frente a retrieval.** `read_section` es el caso de contexto largo: hasta 34.751 tokens, ≈ 0,026 USD de entrada por
  vuelta que se vuelven a pagar en cada vuelta siguiente, frente a unos 2.010 de `search_filings` con k=5, unas 17 veces menos
  [02 §4](02_datos_corpus_y_xbrl.md). Además, el dato puede quedar en medio. Es el último recurso, salvo en el 7A (409–1.877 tokens), que
  cuesta como una búsqueda. Resumir la sección (map-reduce, refine) multiplica las llamadas y rompe la cita literal
  [generative-ai · gemini/use-cases/document-processing/summarization_large_documents_langchain.ipynb · celdas 45, 58, vía nota D12].

## 7. Evaluar el retrieval

- **Retrieval frente a extremo a extremo** [slides RAG · p.46, diap. 113]: un buen recall no garantiza una buena respuesta, así que se miden
  por separado. Las slides nombran precision, recall, hit-rate, MRR y NDCG, sin fórmulas [slides RAG · p.47, diap. 114].
- **Con una sola relevancia por pregunta** (el ancla, D08):

| Métrica | Definición | Decisión |
| --- | --- | --- |
| acierto@k | `normalizar(ancla)` es substring de algún chunk del top-k | La unidad de medida (D07, D08) |
| recall@k = hit-rate@k | Fracción de preguntas con acierto@k | **Principal, @5** (el `k` del contrato); @1, @3 y @10 recortando un único top-20 |
| MRR@10 | Media de 1/rango del primer chunk con el ancla (0 si no está en el top-10) | Secundaria: dice si un arreglo sube el ancla de puesto |
| precision@k | Con una sola relevancia, como mucho 1/k | No se reporta |
| nDCG@k | 1/log₂(1 + rango): otra transformación del rango, más plana que MRR | Fuera (C09) |
| Context precision / recall (Ragas) | Señal/ruido del contexto; si llega todo lo necesario [slides RAG · p.49, diap. 119] | Context recall = nuestro recall@k; Ragas no está en el stack |

- **Detalles de D08** (desarrollados en [13 §4](13_teoria_evaluacion_llms.md); el código, en [24 §4](24_skill_mejora_retrieval.md)):
  - se mide sobre las preguntas con `ancla_texto` (extractivas y comparativas; en las comparativas solo cuenta `ancla_texto`);
  - acierto **estricto** por substring normalizado; la cobertura de 4-gramas ≥ 0,8 solo diagnostica (C07);
  - antes de medir, `anclas_no_indexables` = 0: los offsets son de carácter sobre la sección y el 60 % de los cortes no se solapa, así que
    hay que comprobar que cada ancla cabe entera en algún chunk (V5, V6);
  - siempre en k/n, estratificado por item y, con filtros, junto al acierto aleatorio;
  - **modo aislado** para la tabla R11 y `recall_agente` (el ancla en la unión de lo que devolvió `search_filings` en la trayectoria) como
    diagnóstico **dentro del agente**.
- **Duplicados.** Con solape, el ancla puede estar en dos chunks: los relevantes son todos los que la contienen y cuenta la primera
  aparición. RAG Engine asigna la relevancia a cada chunk y su nDCG llega a superar 1 [rag-engine · celda 44].
- **Sobreajuste.** Con unas 14 anclas, cada una mueve ~7 pp; ClearBox valida con validación cruzada y su mejora (~0,04 en recall@1) no llega
  a una pregunta [clearbox · celdas 31, 41]. Los hiperparámetros se fijan antes de medir (D09).
- **Latencia.** Objetivo de retrieval por debajo de 300 ms y extremo a extremo de 2–3 s [slides RAG · p.45, diap. 103]. Con varias llamadas
  al LLM el extremo a extremo no llegará; los ms del retrieval se miden aparte, en la escalera aislada (D17).

## 8. Trampas con tablas y números

- El **41 %** de los chunks lleva tabla, con las celdas separadas por `\t` y las filas por `\n` [perfil_dataset · LEEME]: hay que normalizar
  espacios antes de buscar un ancla (D07). Una tabla cortada entre dos chunks deja filas sin cabecera (hipótesis; el 49 % de los chunks
  acaba a mitad de frase).
- El denso no distingue cifras cercanas (hipótesis, [10 §3](10_teoria_tokenizacion_embeddings.md)) y el tokenizer `[a-z0-9]+` parte
  `60,922` en `60` y `922`: los números apenas ayudan a BM25, salvo con la variante que los conserva (C19).
- **Leer una cifra de una tabla es camino equivocado**, aunque acierte [enunciado · §1]: la cifra sale de `get_xbrl_fact`, y el retrieval
  busca la **frase** que la explica (el ancla del Item 7 en las comparativas, D10).
- **Escala y unidades.** "$60.9 billion" son 60.922 millones y "billones" en español es 10¹² (D06). El BPA de NVIDIA pasa de 12,05 a 2,97
  por el split 10:1: no cayó un 75 % [01 §5](01_requisitos_y_contratos.md).
- **Trampas del corpus que parecen de retrieval**: `fiscal_year` no es el año de presentación, el Item 15 de NVIDIA se sirve como `"8"` y en
  pandas hay que escribir `fila["item"]`, no `fila.item` [01 §5](01_requisitos_y_contratos.md).
- **Tablas en preguntas de prosa**: excluirlas o penalizarlas es un opcional que se mide (hipótesis) [24 §11](24_skill_mejora_retrieval.md).

## 9. Qué implica para la práctica

| Concepto de este doc | Decisión | Dónde se construye |
| --- | --- | --- |
| RAG agéntico (§1) | El modelo escribe `query` y filtros; XBRL para cifras; `read_section` como último recurso | D09, D22 · [20](20_skill_herramientas_docstrings.md), [12](12_teoria_agentes_react_tools.md) |
| Pre frente a post (§4) | Techo con filtros oráculo + % de filtros bien pasados; pre-filtro antes de cualquier corte | D09 · [24 §5](24_skill_mejora_retrieval.md) |
| Híbrido (§3) | `BM25Okapi` con IDF global + RRF k = 60, pesos iguales, `n_cand = 20` | D09 · [24 §6](24_skill_mejora_retrieval.md) |
| Reescritura (§5) | `reescribir()` → `Busqueda`, cacheada; subconsulta por FY; en el agente, el docstring | D09 · [24 §7](24_skill_mejora_retrieval.md) |
| Métricas (§7) | recall@5 en k/n, MRR@10, estricto, `anclas_no_indexables` = 0, aislado y dentro del agente | D08 · [24 §4](24_skill_mejora_retrieval.md), [13 §4](13_teoria_evaluacion_llms.md) |
| Grounding (§1) | (a) = existe ∧ vista ∧ respalda | D13 · [25 §5–6](25_skill_evaluadores.md) |
| Opcionales (§2, §6) | Rerank, re-troceado, cabecera, prefijo sí/no, otro modelo de embeddings | D09 · [24 §11](24_skill_mejora_retrieval.md) |

1. **R08 · La escalera mide conceptos distintos.** Paso 0, denso tal cual (= `buscar()`); paso 1, techo del filtro; paso 2, aporte del léxico;
   paso 3, traducción y descomposición con los filtros del LLM, que es la cifra de la tabla (D09).
2. **R08 · Hipótesis que la escalera confirma o tumba** (y que alimentan "qué no funcionó", R15): BM25 no mueve nada hasta que la consulta
   va en inglés; el filtro aporta poco donde el techo ya era alto; la reescritura empeora alguna pregunta.
3. **R09a · Un buen retrieval no basta.** La cita tiene que existir, haberse visto en un `ToolMessage` y respaldar lo afirmado (D13).
4. **R11 · El retrieval también cuesta**: la reescritura suma una llamada, el rerank suma ms y `read_section` multiplica los tokens.
5. **R14 · Una puntuación máxima baja es una señal de hueco, no una prueba** (`puntuacion` es un coseno real
   [miax_s1.py · buscar()], y un umbral habría que calibrarlo con preguntas que no sean del golden, nota A5); la honestidad la dan `get_xbrl_fact` ("no
   reportó") y `fuente="ninguna"` (D11, D22).

## 10. Contradicciones resueltas

| # | Tema | Una fuente | Otra | Resolución |
| --- | --- | --- | --- | --- |
| C18 | Constante de RRF | Sin constante [hybrid-search · celda 59] | 60 (nota A5) · 40 [clearbox · celda 35]; las slides no dan valor | k = 60, pesos iguales, fijados antes de medir (D09) |
| C20 | Qué es "filtro" y qué es "híbrido" | Filtro después de recuperar [slides RAG · p.41, diap. 94] | Filtro junto con la consulta [slides RAG · p.34, diap. 79]; "hybrid" = vector + `WHERE` (GenWealth) | Con búsqueda exhaustiva, pre = post; el filtro se mide como techo y como % de filtros bien pasados; pre-filtro obligatorio antes de cortar un top-N (D09) |
| — | Código de las slides | LangChain 0.x / LlamaIndex (`ServiceContext`) | Stack fijado [01 §4](01_requisitos_y_contratos.md) | No se copia; el híbrido y la reescritura se escriben a mano en ~20 líneas ([24](24_skill_mejora_retrieval.md)) |
| — | `chunk_size` | 100–128 en las slides | ~500 tokens en el corpus | Las slides cuentan caracteres (`length_function=len`) |
| — | Clase del 12-sep | Solo slides | Sin transcripción | Este doc se revisa cuando llegue |

## Fuentes

- Slides de RAG: p.3–15 (diap. 6–37), p.20–22 (diap. 48–52), p.28 (diap. 65), p.31–39 (diap. 72–89), p.41–42 (diap. 94–97), p.44–49
  (diap. 101–119), vía nota A5 y [30 §7](30_clase_pistas_del_profesor.md); [slides NLP_S2 · p.24, p.26].
- [enunciado · §1, §3, §4.3, §4.4]; [transcripcion_10sep · 00:05, 00:44, 02:26]; [transcripcion_05sep · 00:49–00:51, 04:22], vía
  [30 §3, §6 y §7](30_clase_pistas_del_profesor.md).
- `miax_s1.py` (`buscar()`, `formatear_fragmentos()`) y [01 §4–5](01_requisitos_y_contratos.md).
- generative-ai: hybrid-search · celdas 5, 55, 59; task-type · celda 5; clearbox · celdas 31–35, 41; rag-engine · celda 44;
  genwealth README; summarization_large_documents_langchain · celdas 45, 58; vía nota D12 y [33 §3.7](33_repo_generative_ai.md).
- [02 §1–4](02_datos_corpus_y_xbrl.md) y [perfil_dataset · chunks.jsonl, LEEME] (tamaños, solape, tablas y candidatos por filtro).
- Docs hermanos: [10](10_teoria_tokenizacion_embeddings.md), [13 §4](13_teoria_evaluacion_llms.md), [24](24_skill_mejora_retrieval.md),
  [25](25_skill_evaluadores.md), [32](32_repo_transformers_labs.md). Decisiones D07–D10, D13, D17, D22 y C07, C09, C18–C21 del mapa de cobertura.
