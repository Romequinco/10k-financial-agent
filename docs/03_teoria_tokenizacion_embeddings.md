# Teoría: tokenización y embeddings

> Requisitos: R08, R11 (y R02, R05, R07, R09b) · Lee antes: [01_requisitos_y_contratos.md](01_requisitos_y_contratos.md) §4–5,
> [02_datos_corpus_y_xbrl.md](02_datos_corpus_y_xbrl.md) §3 · Después: [04_teoria_rag_retrieval.md](04_teoria_rag_retrieval.md),
> [11_skill_mejora_retrieval.md](11_skill_mejora_retrieval.md), [13_skill_medicion_informe_presentacion.md](13_skill_medicion_informe_presentacion.md)

> Fuentes: [transcripcion_04sep], [transcripcion_05sep], [slides NLP_S1] y [slides NLP_S2] (vía nota A34 y [14 §7](14_clase_pistas_del_profesor.md));
> [slides RAG · p.4, p.20, p.22, p.27–28, p.44]; transformers-labs `01-embeddings-tokenizers/` (vía [16 §3.5 y §3.7](16_repo_transformers_labs.md));
> generative-ai `embeddings/` (vía [17 §3.7](17_repo_generative_ai.md)); [api_stack · rank_bm25.BM25Okapi, AIMessage];
> [perfil_dataset · indice/MANIFEST, chunks.jsonl]; código de rank_bm25 0.2.2 y langchain-core 1.6.1 (venv); cálculos sobre `data/corpus/`.

**v1.0 · 12-sep-2026.** Lo mínimo de tokenización, BM25 y embeddings para entender por qué la consulta va en inglés, por qué BM25
complementa al denso y por qué el coste lo cuenta el proveedor. La receta está en [11](11_skill_mejora_retrieval.md) y la medición del
coste en [13](13_skill_medicion_informe_presentacion.md). Abreviaturas: `01-N` = `transformers-labs · 01-embeddings-tokenizers/01-N-*.ipynb`;
`task-type` = `generative-ai · embeddings/task-type-embedding.ipynb`. Marcas: **(datos)** = calculado sobre `data/corpus/`; **(probado)** =
ejecutado en el venv del stack; **(venv)** = introspección del stack instalado; **(cálculo propio)**; ⚠️ = sin verificar.

## 1. Tokens y tokenizers

- **Qué es un token.** Un modelo de lenguaje estima el siguiente token [transcripcion_04sep · 00:49]. El tokenizer es un software
  **determinista** que parte el texto en unidades de un vocabulario fijo; no se entrena por backprop, se "genera" contando frecuencias
  [slides NLP_S1 · p.10; transcripcion_04sep · 01:18–01:21].
- **Granularidad.** Por carácter (vocabulario pequeño, secuencias largas), por palabra (vocabulario enorme y muchas palabras fuera de
  vocabulario) o por subpalabra, el término medio que se usa hoy [slides NLP_S1 · p.10–11]. El tamaño del vocabulario es un
  hiperparámetro: más vocabulario, más cómputo en el softmax y en la matriz de embeddings; los multilingües rondan los 256K (Gemma)
  [slides NLP_S1 · p.13].

| Algoritmo | Cómo construye el vocabulario | Quién lo usa | Detalle útil |
| --- | --- | --- | --- |
| **BPE** | Fusiona una y otra vez el par más frecuente (`aaabdaaabac` → `XdXac`) | GPT-2, RoBERTa; `tiktoken` (OpenAI) | `tiktoken` solo aproxima la factura de Gemini [16 §3.7](16_repo_transformers_labs.md) |
| **WordPiece** | Parecido; `##` marca continuación de palabra (`token ##ization`) | BERT y derivados (bge ⚠️) | La versión *uncased* pasa a minúsculas y no reconstruye mayúsculas, `ñ` ni espacios [transcripcion_04sep · 02:13] |
| **SentencePiece** | Trabaja sobre Unicode, con BPE o Unigram y el vocabulario fijado antes | Gemini, Gemma, PaLM, T5 | Opciones `split_digits` y `byte_fallback` (bytes UTF-8 en vez de `<unk>`) |

[slides NLP_S1 · p.11–12; transcripcion_04sep · 01:15–01:24, 02:52–03:00]

- **"Una palabra no es un token"** [transcripcion_04sep · 03:55]. En nuestro corpus, `n_tokens` da **1,38 tokens por palabra** separada
  por espacios: 1,21 en los chunks de prosa y 1,71 en los que llevan tabla (datos; ⚠️ no se sabe con qué tokenizer se contó `n_tokens`).
  Un chunk de "unos 500 tokens" son unas 360 palabras.
- **Números.** Lo correcto sería trocearlos dígito a dígito y muchos tokenizers no lo hacen: GPT-2 guarda "600" entero y StarCoder lo
  separa [transcripcion_04sep · 01:37, 02:16–02:19]. La causa histórica de los fallos aritméticos de los LLM era el tokenizer
  [slides NLP_S1 · p.9]. Las tablas, llenas de cifras, cuestan más tokens por palabra (dato anterior).
- **Idioma.** Los tokenizers se entrenaron sobre todo con inglés; fuera del inglés salen más tokens por palabra y el modelo rinde peor
  [transcripcion_04sep · 01:05; slides NLP_S1 · p.9]. ⚠️ No está medido con el tokenizer de Gemini, pero en la práctica pesa poco: una
  pregunta son decenas de tokens y una `search_filings` con k=5, unos 2.010 [02 §4](02_datos_corpus_y_xbrl.md).
- **Cada modelo trae su tokenizer**, "con lo cual va a ser distinto" [transcripcion_04sep · 01:37]: el mismo texto da recuentos distintos
  en bge (WordPiece), Gemini (SentencePiece) y GPT-4 (`tiktoken`) [01-2 · celda 9]. La factura la cuenta el proveedor en el
  `usage_metadata` de cada `AIMessage` (`input_tokens`, `output_tokens`, `total_tokens`) [api_stack · AIMessage], que se acumula con
  `get_usage_metadata_callback()` (D16). `ChatOpenRouter` no sobrescribe `get_num_tokens` ni `get_token_ids`, así que caen al tokenizer
  de GPT-2 (venv): no sirven para el coste (D16).
- **Ventana de contexto.** Se mide en tokens del modelo. `read_section` llega a 34.751 tokens (1A de META FY2025) y se vuelve a pagar en
  cada vuelta del bucle, porque cada llamada reenvía el historial [02 §4](02_datos_corpus_y_xbrl.md). ⚠️ La ventana de gemini-3.8-flash
  por OpenRouter no está verificada; el tope de dos `read_section` por pregunta (D04) acota el caso peor.
- **Depurar.** "Si te falla un modelo, lo primero que tienes que mirar […] es tu tokenizador" [transcripcion_04sep · 01:05].

## 2. De la bolsa de palabras a BM25

- **Estandarizar → tokenizar → vectorizar** son los tres pasos habituales. El stemming y la lematización "ya no se hacen" porque pierden
  información [slides NLP_S1 · p.14; transcripcion_04sep · 03:05–03:08].
- **One-hot**: un 1 y el resto ceros; todas las distancias salen √2, así que no hay semántica [slides NLP_S1 · p.6–7]. **Bag of Words**:
  conteo por documento. **TF-IDF**: `tf = count/len` e `idf = log(N/df)`; en el ejemplo de la clase, "hipoteca" da 0,2 × 2 = 0,4
  [slides NLP_S1 · p.7–8]. No capta relaciones semánticas [slides NLP_S1 · p.19], y cada librería retoca la fórmula (por ejemplo, +1 en
  el log), así que hay que mirar su documentación [transcripcion_04sep · 02:00].
- **BM25** es TF-IDF con dos correcciones. Así lo implementa `rank_bm25` 0.2.2 (`_calc_idf` y `get_scores`, venv):

```text
score(D, Q) = Σ_{q ∈ Q}  IDF(q) · f(q,D)·(k1+1) / ( f(q,D) + k1·(1 − b + b·|D|/avgdl) )
IDF(q)      = ln( (N − n(q) + 0,5) / (n(q) + 0,5) )    y, si sale negativo (n(q) > N/2):  IDF(q) = ε · IDF_medio
```

  - `k1` (1,5 por defecto) **satura** la frecuencia: con longitud media, f = 1, 2, 5 y 10 aportan 1,00, 1,43, 1,92 y 2,17, con tope
    k1+1 = 2,5 (cálculo propio). Repetir un término diez veces no multiplica su peso por diez.
  - `b` (0,75) **normaliza por longitud**: una aparición vale 0,69 en un chunk del doble de la media y 1,29 en uno de la mitad
    (cálculo propio).
  - `ε` (0,25) pone un **suelo** al IDF de los términos que aparecen en más de la mitad de los documentos.
  - La consulta no se deduplica: `get_scores` recorre la lista, así que un término repetido suma dos veces (venv). Importa si se concatenan
    varias consultas en una.
- **En nuestro corpus** (datos; `BM25Okapi` sobre los 1.749 chunks con el tokenizer `[a-z0-9]+` de D09): longitud media de 296 tokens,
  7.175 términos, IDF medio 5,04 y suelo 1,26. Quedan en el suelo 22 términos (*the, and, of, to, in, our, we*…). El efecto no es el que
  se suele contar: *the* pesa 1,26, **más** que *revenue* (en 468 chunks, 1,01), *2025* (572, 0,72) o *2024* (860, 0,03). Lo que
  discrimina son los nombres propios y los términos raros: *blackwell* 5,59 (6 chunks), *margin* 3,35, *center* 2,85 y *nvidia* 2,61.
  Consecuencias: el año apenas discrimina y va al **filtro**, no a la consulta; las palabras vacías de una consulta redactada como frase
  meten ruido, así que conviene escribir consultas cortas de términos, sin empresa ni año, que es lo que pide `Busqueda`
  ([11 §7](11_skill_mejora_retrieval.md)). Una lista de stopwords es una variante que se mide (C19).
- **El tokenizer es decisión nuestra.** `BM25Okapi(corpus, tokenizer=None, k1=1.5, b=0.75, epsilon=0.25)` recibe el corpus ya tokenizado
  [api_stack · rank_bm25.BM25Okapi], y hay que usar la **misma** función para el corpus y para la consulta. `[a-z0-9]+` (D09) parte
  `60,922` en `60` y `922`, `10-K` en `10` y `k`, y `R&D` en `r` y `d`; con el español acentuado, "¿Cuáles" da `cu` y `les` (datos). La
  variante que conserva cifras (`[a-z0-9]+(?:[.,][0-9]+)*`, nota A34) es un experimento medido (C19).
- **Fallos silenciosos** (probado; el tercero, en el venv según la nota A34):

```python
import re
from rank_bm25 import BM25Okapi

def tokenizar(t: str) -> list[str]:            # D09: minúsculas + [a-z0-9]+, la misma en corpus y consulta
    return re.findall(r"[a-z0-9]+", t.lower())

docs = ["Revenue grew in the data center segment.",
        "The risk factors of the company.",
        "Net revenue of the company.",
        "The U.S. export controls on the company.",
        "The gross margin of the company."]
bm25 = BM25Okapi([tokenizar(d) for d in docs])   # corpus YA tokenizado; nada de tokenizer=lambda (Windows)
print(bm25.get_scores(tokenizar("data center revenue")).round(2))  # [2.43 0. 0.37 0. 0.]  bien
print(bm25.get_scores("revenue").round(2))     # [0. 0. 0. 0.99 0.]  str: itera letras; la 'u' de 'U.S.' gana
print(bm25.get_scores(["Revenue"]).round(2))   # [0. 0. 0. 0. 0.]  mayúscula: no casa con 'revenue'
```

  1. **Una consulta `str`** se recorre letra a letra. En el corpus real hay letras sueltas en el vocabulario (la `u`, sobre todo de
     "U.S.", aparece en 423 chunks), así que devuelve un ranking **basura distinto de cero**, sin error (datos). Solo da "todo ceros" si
     ninguna letra es token.
  2. **Mayúsculas**: `["Revenue"]` no casa con `revenue` y puntúa 0.
  3. **`tokenizer=lambda …`** tokeniza con `multiprocessing.Pool` y en Windows lanza `PicklingError`: tokenizad vosotros el corpus.
  4. **Sin coincidencias**, `argsort` ordena por posición: hay que quitar los score 0 del ranking (D09).
  5. **IDF local**: construir BM25 solo con los candidatos cambia los IDF; se construye una vez (IDF global) y se puntúa con
     `get_batch_scores(tokens, ids)` (D09, [11 §6](11_skill_mejora_retrieval.md)).

## 3. Embeddings

- **Qué es.** Un vector denso aprendido; la capa es una lookup table de vocabulario × dimensión. Una dimensión suelta no significa nada:
  importa la relación entre vectores [slides NLP_S1 · p.19–20; transcripcion_04sep · 03:57; transcripcion_05sep · 00:15–00:18].
- **Estáticos frente a contextuales.** word2vec, GloVe o Swivel dan un solo vector por palabra ("banco" siempre igual); en BERT el vector
  depende de la frase [slides NLP_S1 · p.34].
- **BERT** es encoder-only y bidireccional, preentrenado con MLM (15 %) y NSP, con los tokens especiales [CLS], [SEP] y [MASK]. Su entrada
  suma token, segment y position embeddings. BERT-base: 12 capas, 768 dimensiones, 110M parámetros; large: 24, 1.024 y 340M
  [slides NLP_S2 · p.5, p.24–25].
- **Embeddings de frase, "dos torres" o bi-encoder**: Sentence-BERT (2019) [slides NLP_S1 · p.34]. Consulta y documento se codifican por
  separado, así que los documentos se precalculan [slides RAG · p.4]. Los vectores por token se reducen a uno por texto con un *pooling*
  (la salida de [CLS] o la media). Sale **un** vector por entrada, sea una frase o seis páginas de PDF [transcripcion_05sep · 00:46–00:51]:
  es el dilema del chunking ([04 §2](04_teoria_rag_retrieval.md)).
- **Nuestro modelo**: `BAAI/bge-small-en-v1.5`, 384 dimensiones, índice `IndexFlatIP` sobre vectores normalizados
  [perfil_dataset · indice/MANIFEST]. Según su ficha es un BERT pequeño con pooling [CLS], el WordPiece *uncased* de 30.522 y 512 tokens de
  entrada: ⚠️ nada de eso está comprobado en el stack (el venv no tiene sentence-transformers).
- **Similitud.** L2, coseno o producto interno: "cualquiera de las tres te da un número" [transcripcion_05sep · 01:02]. Con vectores
  normalizados (‖u‖ = ‖v‖ = 1), u·v = cos(u, v) y ‖u − v‖² = 2 − 2·cos(u, v), así que las tres ordenan igual (cálculo propio). Hay que
  normalizar también la consulta: 01-6 no lo hace, y entonces la puntuación deja de ser un coseno; el orden no cambia, pero un umbral
  pierde el sentido [16 §3.5](16_repo_transformers_labs.md).
- **Asimetría consulta/documento.** "La pregunta no es la respuesta": con un embedding simétrico, la consulta queda más cerca de frases
  que se parecen a la pregunta que de la respuesta [task-type · celdas 5, 18–19]. El remedio es codificar distinto consulta y documento:
  `task_type` `RETRIEVAL_QUERY` o `QUESTION_ANSWERING` frente a `RETRIEVAL_DOCUMENT` [slides NLP_S1 · p.35; slides RAG · p.27–28]; en
  BGE, el prefijo `"Represent this sentence for searching relevant passages: "` **solo en la consulta** [01 §4](01_requisitos_y_contratos.md).
  Con task types, el MRR sube de ~0,3 a ~0,4 en 1.000 pares de NQ-Open [task-type · celdas 46, 54], con una muestra sin semilla
  [task-type · celda 29]; ⚠️ no se traslada ni a BGE ni a un 10-K. Omitir el prefijo "no da error, solo recupera peor" [01 §4]: es un fallo
  silencioso, como el chat template equivocado [transcripcion_05sep · 01:59]. Ponerlo en los pasajes al reindexar también lo es.
- **Multilingüe frente a solo inglés.** Lo primero de la ficha de un modelo es la dimensión, si es multilingüe ("house" ≈ "casa"), si es
  multimodal y si se puede afinar [slides NLP_S1 · p.25; transcripcion_04sep · 04:00]; para comparar modelos está MTEB
  [slides NLP_S1 · p.35]. bge-small-**en** es inglés por su nombre. ¿Estrictamente monolingüe? ⚠️ Su tokenizer trocea el español en
  subpalabras (no necesariamente en `[UNK]`), pero nada garantiza que acerque "ingresos" a "revenue". Se resuelve midiendo: el paso 0 de la
  escalera usa la pregunta en español y el paso 3, la reescrita en inglés [11 §2](11_skill_mejora_retrieval.md). Un modelo multilingüe (el
  `distiluse-base-multilingual-cased-v1` de 512 d de 01-6 [16 §3.5](16_repo_transformers_labs.md)) obliga a reindexar y puede recuperar
  peor en inglés (hipótesis).
- **Cambiar de modelo, o de versión, obliga a reindexar**: los espacios no son compatibles [transcripcion_05sep · 00:54–00:57;
  slides RAG · p.44]. Índice, `chunks_meta.parquet` y manifiesto (modelo, prefijo y SHA-256 de los chunks) se regeneran juntos
  [02 §3](02_datos_corpus_y_xbrl.md).
- **Límite de entrada y truncado** ⚠️. Todo modelo de embeddings tiene un máximo de tokens de entrada: 2.048 en text-embedding-005 y en
  gemini-embedding-001 [slides NLP_S1 · p.35]; 512 en bge-small según su ficha (⚠️). `n_tokens` da 6 chunks por encima de 512 (entre 513
  y 547) (datos), pero no se sabe con qué tokenizer se contó (hueco 4 del mapa). Si bge trunca, la cola de esos chunks no entra en el
  vector y un ancla situada al final solo se alcanza por BM25. La comprobación (`AutoTokenizer` de bge frente a `max_seq_length`) está en
  [16 §3.7](16_repo_transformers_labs.md); hay que correrla en un entorno con sentence-transformers antes de fiarse del paso 0.
- **Cifras.** Un embedding representa el "uso" de las palabras [slides NLP_S1 · p.20]: no esperéis que separe `60,922` de `61,000`
  (hipótesis medible). La cifra sale de `get_xbrl_fact`, y la frase que la explica se busca con BM25 + denso.

## 4. Búsqueda exacta frente a ANN

- La fuerza bruta cuesta O(dimensiones × elementos) [slides NLP_S1 · p.45]. "El problema no es comparar embeddings, es la escala"
  [transcripcion_05sep · 00:44]. Los índices ANN (IVF; ScaNN, con árbol, cuantización anisotrópica y *reorder*) cambian exactitud por
  velocidad y se recomiendan a partir de cientos de millones de vectores [slides RAG · p.20; slides NLP_S1 · p.45–47].
- Aquí hay 1.749 vectores de 384 dimensiones en float32, unos 2,7 MB, y `buscar()` ordena el índice entero en cada consulta
  [02 §3](02_datos_corpus_y_xbrl.md). Un ANN solo podría **bajar** el recall@k. Además, la búsqueda exacta da el vector completo de
  puntuaciones alineado por posición, que es lo que necesita la fusión con BM25 [16 §3.5](16_repo_transformers_labs.md). `IndexFlatIP` se
  queda.

## 5. Qué implica para la práctica

1. **R08 · La consulta, en inglés y con vocabulario de 10-K.** El corpus y bge-small-en están en inglés, y BM25 solo puntúa tokens que
   aparecen en el chunk. Una pregunta en español solo casa por nombres propios, cifras y préstamos, y sus palabras vacías (*los*, *de*, *en*)
   aparecen en 2–4 chunks del corpus ("Los Angeles County", "rehearing en banc") y reciben un IDF de ~6, el más alto de la consulta (datos).
   La reescritura (paso 3 de D09) traduce, y dentro del agente lo hace el modelo siguiendo el docstring
   ([07](07_skill_herramientas_docstrings.md)).
2. **R08 · Empresa, ejercicio e item van a los filtros, no a la consulta.** En BM25, *2024* y *2025* pesan 0,03 y 0,72 (datos). Con la
   pregunta en español o en inglés sobre el Data Center de NVIDIA en FY2025, el primer resultado de BM25 es un chunk del Item 7 de **FY2024**
   (datos): sin filtro de `fiscal_year`, el año no se respeta.
3. **R08 · BM25 tal como fija D09**: tokenizer `[a-z0-9]+`, `k1=1.5, b=0.75, ε=0.25` documentados en el informe, IDF global, consulta como
   lista de tokens y sin los score 0. Las variantes (conservar cifras, stopwords, stemming) son filas medidas de la escalera, nunca ajustes
   a ojo ([11 §11](11_skill_mejora_retrieval.md)).
4. **R08 · Prefijo BGE solo en la consulta.** Medir con y sin prefijo es un experimento gratis que enseña un fallo silencioso en la
   presentación (el heatmap `np.inner(E, E)` de [16 §3.5](16_repo_transformers_labs.md)).
5. **R07/R08 · Antes de medir, comprobad el truncado y las anclas.** Si alguna ancla cae en la cola de uno de los 6 chunks largos, el
   denso no puede verla; y `anclas_no_indexables` debe ser 0 (D08, [11 §2](11_skill_mejora_retrieval.md)).
6. **R08/R12 · Un solo modelo de embeddings en el baseline y en el final.** Cambiarlo es un opcional con índice y manifiesto nuevos, en otra
   carpeta, y nunca se mezclan modelos entre consulta e índice.
7. **R11 · El coste, del proveedor**: `get_usage_metadata_callback()` alrededor de cada `invoke` (D16); nunca `get_num_tokens` ni
   `tiktoken`. Lo que pesa son los resultados de las herramientas (`read_section`), no el idioma de la pregunta.
8. **R05/R09b · Las cifras nunca se comparan como cadena ni como tokens**: se parsean a número con su escala y se aplica la tolerancia de
   D06. Márgenes y variaciones se calculan en Python, no "de cabeza" en el LLM (nota A34).
9. **R07/R09a · Se compara texto normalizado, no tokens.** `normalizar()` (D07) a los dos lados; el tokenizer de un modelo *uncased* pierde
   mayúsculas, `ñ` y espacios [transcripcion_04sep · 02:13].

## 6. Erratas y dudas

| Tema | Una fuente dice | Otra dice | Qué usamos |
| --- | --- | --- | --- |
| Dimensión de BERT | "Embeddings de 512" [transcripcion_04sep · 03:57] | 768 en base y 1.024 en large [slides NLP_S2 · p.5] | **768**. 512 es la longitud máxima de entrada de BERT (posiciones), probable origen de la confusión (⚠️ no está en las slides) |
| Año de BERT | 2017 [slides NLP_S1 · p.34] | 2018 [slides NLP_S2 · p.22; transcripcion_05sep · 03:38] | **2018** (2017 es el año del Transformer, ⚠️) |
| ¿bge-small-en es monolingüe? | "en" en el nombre | Sin prueba con preguntas en español | ⚠️ Se mide: paso 0 frente a paso 3 |
| Tokenizer de `n_tokens` | "~500 tokens" [perfil_dataset · LEEME] | No dice cuál | ⚠️ Hueco 4 del mapa; 6 chunks > 512 |
| BM25 con una consulta `str` | "Todo ceros sin error" [17 §3.7](17_repo_generative_ai.md) (corpus de juguete; ya matizado) y, antes de corregirlo, [11 §12](11_skill_mejora_retrieval.md) | Con el corpus real, ranking basura distinto de cero (datos) | Nunca pasar un `str` |
| Suelo del IDF | Los términos de más de la mitad de los chunks "casi no pesan" (nota A34) | *the* 1,26 > *revenue* 1,01 (datos) | Consultas cortas de términos; stopwords como variante medida |

## Fuentes

- Clase: [transcripcion_04sep · 00:49, 01:05–01:24, 01:37, 02:00, 02:13–03:08, 03:55–04:00]; [transcripcion_05sep · 00:15–01:02, 01:59,
  03:38]; [slides NLP_S1 · p.6–14, p.19–20, p.25, p.34–35, p.45–47]; [slides NLP_S2 · p.5, p.22–25], vía nota A34 y
  [14 §7](14_clase_pistas_del_profesor.md).
- [slides RAG · p.4, p.20, p.27–28, p.44], vía nota A5.
- transformers-labs: 01-2 · celda 9; 01-6 · celdas 4, 6, 8, 10, vía nota C1 y [16 §3.5 y §3.7](16_repo_transformers_labs.md).
- generative-ai: `task-type` · celdas 5, 18–19, 29, 46, 54, vía nota D12 y [17 §3.7](17_repo_generative_ai.md).
- [01 §4–5](01_requisitos_y_contratos.md), [02 §3–4](02_datos_corpus_y_xbrl.md), [perfil_dataset · indice/MANIFEST, chunks.jsonl, LEEME].
- [api_stack · rank_bm25.BM25Okapi, AIMessage]; código de `BM25Okapi._calc_idf` y `get_scores` (rank_bm25 0.2.2) y
  `ChatOpenRouter.get_num_tokens` (langchain-openrouter 0.2.8 sobre langchain-core 1.6.1), leídos en el venv del stack.
- Datos propios sobre `data/corpus/chunks.jsonl`: tokens por palabra, estadísticas de `BM25Okapi` (IDF, suelo, términos en el suelo) y
  rankings de una pregunta en español y en inglés. Decisiones D06–D09, D16 y C19 del mapa de cobertura.
