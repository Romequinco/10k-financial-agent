# Repo transformers-labs: qué nos sirve para la práctica

> Origen: https://github.com/rafaelsf80/transformers-labs (repo del profesor del módulo NLP). Copia local no versionada en docs/raw/repos/transformers-labs-master/.

**v1.0 · 12-sep-2026.** Consolida las notas de trabajo C1 (`01-*`, `03-6`, `03-7`, `04-6`) y C2 (`05-llm/`), contrastadas con los
ficheros originales, con el stack instalado y con los datos del perfil. Los IDs `Rxx` remiten a [01_requisitos_y_contratos.md](01_requisitos_y_contratos.md).

Citas: `[transformers-labs · <ruta> · celda N]` (celdas desde 0) o `· l. N`, abreviada `[05-5 · celda N]` en tablas y dentro de una misma
sección; `[api_stack · <sección>]` = `docs/raw/_texto/api_stack_langchain.md`;
`[perfil_dataset · …]` = `docs/raw/_texto/perfil_dataset.md`; `[miax_s1 · l. N]` = `docs/raw/clase/sesion1/miax_s1.py`; `[S1 · celda N]` =
notebook de la sesión 1; `[enunciado · §N]` = `00_enunciado.md`; `[15 §N]` = [15_repo_genai_labs.md](15_repo_genai_labs.md). **(probado)** =
ejecutado en un venv con el stack de §4 (Python 3.13.7, sin red, sin `sentence-transformers` ni `faiss`) con datos sintéticos o un modelo falso.

## 1. Qué es y qué parte hemos revisado

Labs del módulo NLP en cinco bloques: 01 tokenizers y embeddings, 02 RNN/LSTM, 03 atención y transformers, 04 BERT (pre-Chinchilla) y
05 LLM y evaluación, más `transformers-use-cases/` (15 carpetas, 8 de ellas `*-vertex`) [transformers-labs · README.md · l. 3-87, 126-247].
**Revisado a fondo:** todo `01-embeddings-tokenizers/`, 03-6, 03-7, 04-6, los cinco notebooks `05-4`…`05-8` y los tres `.py` de `05-llm/`.
**Triaje (títulos o listado):** 02-*, 03-1…5/8/9, 04-2…5/7/8 y `transformers-use-cases/`. `archive/` y `utils/`, sin revisar.
Ningún notebook revisado guarda outputs (0 celdas con salida, recuento propio) y muchos son esqueletos con `TODO`: solo hay código que citar.
**Veredicto:** no hay nada de agentes ni de RAG completo. Sirven (1) las métricas implementadas a mano en 05-5…05-8, que dan recall@k,
el evaluador de trayectoria y la tabla de R11; (2) el único retrieval denso de principio a fin (01-6, ScaNN), que se traduce a FAISS exacto;
y (3) la tokenización para BM25 y el conteo de tokens. El código de métricas trae fallos comprobados: se copian las ideas, no las funciones (§5).

## 2. Mapa de utilidad

| Notebook / fichero | Qué enseña | Relevancia | Requisitos | Cómo reutilizarlo |
| --- | --- | --- | --- | --- |
| `05-llm/05-5-eval-classification.ipynb` | TP/FP/FN respecto a una clase positiva; precision, recall y F1 con dos fórmulas; macro vs micro; `math.isclose` [celdas 4, 7-16, 19-41] | **Alta** | R08, R09b, R09c, R11 | recall@k (§3.1), tolerancia (§3.3), trayectoria (§3.4), tabla (§3.6) |
| `05-llm/05-8-eval-qna.ipynb` | Exact match como igualdad de cadenas, con respuesta y sin ella [celdas 2-9] | **Alta** (normalizando) | R07, R09a, R14 | Existencia de la cita (§3.2); abstención estructural |
| `05-llm/05-7-eval-textgeneration.ipynb` | BLEU por piezas: brevity penalty, precisión modificada con *clipping*, media geométrica [celdas 3-4, 12-13, 18-22] | Media (diagnóstico) | R09a | Cobertura de n-gramas de la cita (§3.2); su BLEU no (§5) |
| `05-llm/05-6-eval-summarization.ipynb` | LCS recursivo y memoizado; ROUGE-L con `β = P/R` [celdas 3, 5, 7-19] | Baja | R09a | Solo para entender por qué LCS no sirve para citas (§3.2) |
| `05-llm/05-4-comparison-llms.ipynb` | 5 LLMs × 6 prompts, `perf_counter` por llamada, `wandb.Table`, claves con `getpass` [celdas 3, 5-7, 9, 11-12, 16] | Media | R11, R13 | Arnés de medición (§3.6); su configuración es un anti-ejemplo (§5) |
| `01-embeddings-tokenizers/01-6-scann.ipynb` | sentence-transformers, normalización L2, índice ScaNN, latencia en ms y heatmap de similitud [celdas 4-10] | **Media-alta** | R08, R11 | FAISS exacto + fusión con BM25 (§3.5) |
| `01-embeddings-tokenizers/01-2-tokenizers-comparison.ipynb` | `show_tokens` con `tiktoken` (gpt-4) y `AutoTokenizer`; entrenar SentencePiece BPE [celdas 9-10, 13] | Media | R08, R11 | Estimar tokens y comprobar el truncado de bge (§3.7) |
| `01-embeddings-tokenizers/01-1-intro-tokenizers.ipynb`, `…/01-5-nlp-libraries.ipynb` | BoW, TF-IDF y tokenizers de NLTK (en `TODO`); `preprocess_text`: minúsculas, stopwords, `isalnum`, Porter [01-1 · celdas 4-15; 01-5 · celda 15] | Media | R08 | Tokenizador de BM25 (§3.5) |
| `04-pretraining-bert/04-6-classification-finbert.ipynb` | `ProsusAI/finbert`, 3 clases, fine-tuning con `Trainer` sobre `financial_phrasebank`, W&B; inferencia en `TODO` [celdas 0, 7, 9, 12] | Baja | (R01, opcional) | No recomendado (§5) |
| `03-attention-transformers/03-6-huggingface.ipynb`, `…/03-7-modelhub.ipynb` | `pipeline` y AutoClass (en `TODO`); `huggingface-cli login` + `hf_hub_download` [03-6 · celdas 3-8; 03-7 · celda 5] | Baja | R13 | bge no necesita token (§4) |
| `05-llm/05-{1,2,3}-*-gradio.py` | Demos de Gradio sobre el SDK `google-genai` | Nula | — | — (§4, §5) |
| 01-3, 01-4, 01-8, 02-*, 03-1…5/8/9, 04-2…5/7/8, `transformers-use-cases/` | Entrenar embeddings/RNN/BERT, TF, resumen, traducción, Vertex | Nula | — | §5 |

## 3. Patrones reutilizables traducidos a nuestro stack

Propuesta de "acierto" por familia (se apoya en lo que el validador exige a cada familia [01_requisitos · §3] y en que acertar por el
camino equivocado es fallo [01_requisitos · §2]): `numerica` = (b) ∧ (c); `extractiva` = (a) ∧ (c); `comparativa` = (a) ∧ (b) ∧ (c);
hueco (posible en las ciegas) = `fuente == "ninguna"` ∧ `cifra is None` ∧ (c). Las letras son los evaluadores de R09.
D14 añade `correcta` en extractivas y comparativas ([12 §7](12_skill_evaluadores.md)).

### 3.1 De TP/FP/FN a recall@k y MRR contra el ancla (R07, R08)
Original: `count_tp_fp_fn` cuenta respecto a una clase positiva y `recall = TP/(TP+FN)`
[transformers-labs · 05-llm/05-5-eval-classification.ipynb · celdas 4, 9-10]. Con una sola ancla por pregunta, recall@k es la fracción
de preguntas cuya ancla aparece en algún chunk del top-k (hit-rate@k). El MRR dice además si un arreglo sube el ancla de puesto.

```python
def recall_mrr(golden, buscar_fn, k=5, filtros=False, consulta_fn=lambda p: p["pregunta"]) -> dict:
    hits, rr = [], []
    for p in golden:
        if not p.get("ancla_texto"):
            continue                                        # solo las preguntas con ancla
        kw = ({"ticker": p["ticker"], "fiscal_year": p["fiscal_year"], "item": p["item_esperado"]}
              if filtros else {})
        docs = buscar_fn(consulta_fn(p), k=k, **kw)         # firma de miax_s1.buscar
        pos = next((i for i, d in enumerate(docs, 1)
                    if normalizar(p["ancla_texto"]) in normalizar(d["texto"])), None)   # §3.2
        hits.append(pos is not None)
        rr.append(1 / pos if pos else 0.0)
    n = len(hits)
    return {"k": k, "n": n, "recall": sum(hits) / n if n else None, "mrr": sum(rr) / n if n else None}
```
- Una fila por arreglo: denso → +filtro → +BM25 → +reescritura (`consulta_fn` = la `reescribir()` de [15 §3.7]), con k = 5 (el
  `k` por defecto del contrato [01_requisitos · §3]) y @1/@10 como curva. Con n preguntas con ancla, cada una mueve 100/n pp: dad k/n. (probado con un `buscar_fn` falso)
- **Decisión C07/D08:** acierto estricto (substring normalizado; la cobertura de §3.2, solo diagnóstico); @1/3/5/10 y MRR@10 de un único
  top-20; código final en [11 §4](11_skill_mejora_retrieval.md).
- `filtros=True` usa los metadatos del golden: es la **cota superior** del arreglo. `buscar()` pide el ranking completo
  (`indice.search(vector, indice.ntotal)`) y filtra después, lo que a esta escala "no cambia el resultado" [miax_s1 · l. 111-112, 124].
  La mejora real depende de que el agente **pase** `ticker`, `fiscal_year` e `item`, o sea, de los docstrings (R02).
- Comparad texto normalizado: en las tablas del corpus las celdas van unidas por `\t` y las filas por `\n` [perfil_dataset · LEEME].

### 3.2 La cita existe: EM normalizado y cobertura de n-gramas (R07, R09a)
Original: `exact_match` devuelve 1 solo si las cadenas son idénticas, sin normalizar nada [transformers-labs · 05-llm/05-8-eval-qna.ipynb · celda 3];
la precisión modificada cuenta n-gramas del candidato presentes en la referencia, con *clipping* [transformers-labs · 05-llm/05-7-eval-textgeneration.ipynb · celdas 12-13].
El contrato define `cita` como "Texto literal del informe" [enunciado · §7]: el aprobado es literal y lo difuso solo diagnostica.

```python
import re, unicodedata
_TRAD = str.maketrans({"’": "'", "‘": "'", "“": '"', "”": '"', "–": "-", "—": "-"})
def normalizar(t: str | None) -> str:
    t = unicodedata.normalize("NFKC", t or "").translate(_TRAD).lower()
    return re.sub(r"\s+", " ", t).strip()                   # colapsa \t y \n de las tablas
def _tokens(t):
    return re.findall(r"\w+|[^\w\s]", normalizar(t))        # la puntuación, token aparte
def cobertura(frag: str, fuente: str, n: int = 4) -> float:
    """Fracción de n-gramas CONTIGUOS de `frag` presentes en `fuente` (precisión de 05-7 sin clipping)."""
    f, s = _tokens(frag), _tokens(fuente)
    if len(f) < n:
        return float(bool(f) and " ".join(f) in " ".join(s))
    vistos = set(zip(*(s[i:] for i in range(n))))
    grams = list(zip(*(f[i:] for i in range(n))))
    return sum(g in vistos for g in grams) / len(grams)
def cita_existe(cita: str | None, textos: list[str]) -> dict:
    """Etapa 1 de R09a. `textos` = chunk citado + secciones del ticker/FY."""
    if not cita:
        return {"ok": None, "modo": "sin_cita"}
    fuente = " ".join(normalizar(t) for t in textos if t)
    piezas = [p for p in re.split(r"\s*(?:\.\.\.|…)\s*", cita) if p.strip()]   # elisiones: cada trozo, literal
    if all(normalizar(p) in fuente for p in piezas):
        return {"ok": True, "modo": "literal"}
    c = cobertura(cita, fuente)
    return {"ok": False, "modo": "casi_literal" if c >= 0.8 else "no_encontrada", "cobertura": round(c, 3)}
```
- Se busca también en las secciones porque el `chunk_id` cambia al re-trocear [enunciado · §4.3]; acertar el `chunk_id` se apunta
  aparte, como diagnóstico. `casi_literal` separa fallos de normalización de invenciones: umbral 0,8 ⚠️ por calibrar con 10-15 citas reales. (probado)
- **LCS/ROUGE-L no deciden**: la LCS no es contigua [transformers-labs · 05-llm/05-6-eval-summarization.ipynb · celda 5] (palabras sueltas
  de un párrafo puntúan alto sin que la frase exista) y no ve cifras: su `rouge_l` [celda 19] da **0,75** entre "revenue was $60.9
  billion" y "revenue was $6.09 billion" (probado). Las cifras van por §3.3; el respaldo semántico (etapa 2), por el juez de [15 §3.5].
- R14: en 05-8, la verdad `""` frente a `"No answer found."` da EM = 0 [transformers-labs · 05-llm/05-8-eval-qna.ipynb · celdas 8-9]:
  la abstención se evalúa por estructura (`fuente == "ninguna"` y `cifra is None`), no comparando cadenas.

### 3.3 La cifra con tolerancia documentada (R05, R09b)
Original: `math.isclose(f1_score_a, f1_score_b, abs_tol=...)` para comparar floats [transformers-labs · 05-llm/05-5-eval-classification.ipynb · celda 16].
Propuesta, justificada con los 135 hechos de `xbrl_facts` [perfil_dataset · xbrl_facts.parquet] (cálculos probados sobre esa tabla):

| Unidad XBRL | Tolerancia | Por qué |
| --- | --- | --- |
| `USD` (111 hechos, todos múltiplos de 10⁶, el menor 7.280 M) | relativa 0,5 % | Acepta "$391 billion" (3 cifras significativas). El menor cambio interanual es 1,57 % (AAPL `Assets` FY2025), así que confundir el FY falla |
| `USD/shares` (24 hechos) | **absoluta 0,005** | BPA básico y diluido distan solo 0,03 (AAPL FY2024 y FY2025, NVDA FY2025). Con 0,5 % relativo, el diluido 6,08 pasaría por el básico 6,11 de AAPL FY2024 (0,49 %) |
| Hueco | `cifra is None` y `fuente == "ninguna"` | R14 |

```python
import math
ESCALA = [("miles de millones", 1e9), ("mil millones", 1e9), ("billion", 1e9),
          ("millones", 1e6), ("million", 1e6), ("miles", 1e3), ("thousand", 1e3)]  # "billones" (10^12) fuera, a propósito
def cifra_ok(cifra, unidad, verdad, unidad_xbrl) -> dict:
    if verdad is None:
        return {"ok": cifra is None, "motivo": "hueco"}
    if cifra is None:
        return {"ok": False, "motivo": "sin_cifra"}
    v = float(cifra) * next((f for clave, f in ESCALA if clave in normalizar(unidad)), 1.0)
    tol = ({"rel_tol": 0.0, "abs_tol": 0.005} if unidad_xbrl == "USD/shares"   # BPA: al céntimo
           else {"rel_tol": 0.005, "abs_tol": 0.0})                            # USD: 0,5 %
    if math.isclose(v, verdad, **tol):
        return {"ok": True}
    esc = next((e for e in (-9, -6, -3, 3, 6, 9) if math.isclose(v * 10**e, verdad, **tol)), None)
    return {"ok": False, "motivo": f"error_escala 1e{esc}" if esc else "fuera_de_tolerancia"}
```
- Misma `cifra_ok` en el middleware (R05) y en el evaluador (R09b). El `VerificadorXBRL` de [15 §3.4] usa 0,5 % relativo para todo:
  para el BPA, la absoluta, que además hace fallar el "3" redondeado de NVDA [01_requisitos · §5, fallo 8]. "Billones" (10¹²) sale como `error_escala`. (probado)
- La tolerancia **no distingue conceptos**: META FY2024 `CashAndCashEquivalentsAtCarryingValue` (43.889 M) y `ResearchAndDevelopmentExpense`
  (43.873 M) distan un 0,04 % (probado sobre la tabla). Eso lo resuelve (c) con el argumento `concept`.
- Sensibilidad gratis: re-puntuad con 0 %, 0,1 %, 0,5 % y 1 % sin volver a llamar al agente (ejecutar ≠ puntuar, §3.6).

### 3.4 La trayectoria como clasificación de conjuntos (R09c)
Original: TP/FN/FP respecto a una clase [transformers-labs · 05-llm/05-5-eval-classification.ipynb · celda 4]. Aquí la "clase" es la lista
`herramienta_esperada` (`['get_xbrl_fact']` en `ej-001` [clase · sesion1/golden_set_ejemplo.jsonl]) y la verdad, los `tool_calls` de `resultado["messages"]` [api_stack · AIMessage].

```python
REALES = {"list_available", "get_xbrl_fact", "search_filings", "read_section"}   # + las que añadáis; fuera la tool de ToolStrategy
# list_available: neutra en (c), pero cuenta en llamadas (D12, D18)
def trayectoria_ok(resultado, p: dict, mismo_valor=lambda t, fy, c1, c2: False) -> dict:
    tcs = [tc for m in resultado["messages"] for tc in (getattr(m, "tool_calls", None) or [])
           if tc["name"] in REALES]
    usadas = {tc["name"] for tc in tcs}
    requisitos = [set(e.split("|")) for e in p["herramienta_esperada"]]   # "a|b" = cualquiera (convención propia)
    tp = sum(bool(r & usadas) for r in requisitos)                        # FN = len(requisitos) - tp
    args_ok = True
    if p.get("concept_xbrl"):
        fy = int(p["fiscal_year"])
        fys = {fy, fy - 1} if p["familia"] == "comparativa" else {fy}     # FY-1: convención propia [01_requisitos · §6]
        vistos = {int(tc["args"].get("fiscal_year", -1)) for tc in tcs if tc["name"] == "get_xbrl_fact"
                  and str(tc["args"].get("ticker", "")).upper() == p["ticker"]
                  and (tc["args"].get("concept") == p["concept_xbrl"]
                       or mismo_valor(p["ticker"], int(tc["args"].get("fiscal_year", -1)),
                                      tc["args"].get("concept"), p["concept_xbrl"]))}
        args_ok = fys <= vistos
    return {"ok": tp == len(requisitos) and args_ok, "args_ok": args_ok,
            "recall": tp / len(requisitos), "n_llamadas": len(tcs)}
```
- Aprueba si están todas las esperadas (recall = 1) y los argumentos de `get_xbrl_fact` cuadran: caza la confusión de concepto que la
  tolerancia deja pasar y la de año. `mismo_valor` admite otro concepto con igual valor: GOOGL FY2024 reporta `Revenues` y
  `RevenueFromContractWithCustomerExcludingAssessedTax` idénticos [perfil_dataset · xbrl_facts.parquet]. (probado con mensajes sintéticos)
- AND de la lista, `"a|b"` y FY−1 son convención propia: ⚠️ no se sabe qué exigirá el evaluador del día 24 más allá de los nombres
  [01_requisitos · §3]. `n_llamadas` alimenta "llamadas/pregunta" (R11).
- **Decisión posterior (D12):** `"a|b"` se descarta porque `herramienta_esperada` es campo del contrato y solo lleva nombres reales; las
  alternativas van en el extra `herramienta_alternativa`. Versión final: [12 §2 y §4](12_skill_evaluadores.md).

### 3.5 De ScaNN a FAISS exacto, y BM25 al lado (R08)
Original: `SentenceTransformer('distiluse-base-multilingual-cased-v1')` (512 d) codifica fila a fila con `df.apply`; normaliza a mano;
ScaNN con árbol + asymmetric hashing + `reorder(100)`; búsqueda con `final_num_neighbors=3` y latencia en ms
[transformers-labs · 01-embeddings-tokenizers/01-6-scann.ipynb · celdas 4, 6, 8]. Traducción al índice dado, con el código de consulta de
[perfil_dataset · indice/MANIFEST.md] y [miax_s1 · l. 83, 119-124] (⚠️ `faiss` y `sentence-transformers` no están introspectados en `api_stack`):

```python
import re, faiss, numpy as np, pandas as pd
from sentence_transformers import SentenceTransformer
from rank_bm25 import BM25Okapi
PREFIJO = "Represent this sentence for searching relevant passages: "
indice = faiss.read_index("corpus/indice/corpus.faiss")        # IndexFlatIP sobre vectores normalizados
meta = pd.read_parquet("corpus/indice/chunks_meta.parquet")    # fila i = vector i
modelo = SentenceTransformer("BAAI/bge-small-en-v1.5")
def puntuacion_densa(consulta: str) -> np.ndarray:
    q = modelo.encode([PREFIJO + consulta], normalize_embeddings=True,
                      convert_to_numpy=True).astype("float32")   # prefijo SOLO en la consulta
    punt, pos = indice.search(q, indice.ntotal)                  # ranking completo y exacto
    v = np.empty(indice.ntotal, dtype="float32")
    v[pos[0]] = punt[0]                                          # coseno del chunk i en la posición i
    return v
def tokenizar(t: str) -> list[str]:                              # preprocess_text de 01-5 sin NLTK
    return re.findall(r"[a-z0-9]+", t.lower())
bm25 = BM25Okapi([tokenizar(t) for t in meta["texto"]])          # k1=1.5, b=0.75 por defecto
lexico = bm25.get_scores(tokenizar(consulta_en_ingles))          # misma función en corpus y consulta
```
- **No cambiéis a ANN.** Son 1.749 vectores de 384 d [perfil_dataset · indice/MANIFEST.md] y la búsqueda exacta ya es "instantánea"
  [miax_s1 · l. 112]; ScaNN (o IVF/HNSW) cambia exactitud por velocidad y aquí solo puede bajar recall@k. En 01-6, además,
  `num_leaves = num_leaves_to_search = record_count` [celda 6]: el árbol no poda, es una demo. Y solo la búsqueda exacta da el vector
  completo alineado por posición que pide la fusión con BM25 (RRF o suma ponderada: técnica de la clase de RAG, no de este repo).
- Detalles de 01-6 que no hay que copiar: la consulta **no** se normaliza [celda 8] (el orden no cambia, pero la puntuación deja de ser un
  coseno y un umbral no tendría sentido); sus modelos (distiluse 512 d, MiniLM 384 d [celda 4]) no se mezclan con el índice bge; la
  dimensión va a mano [celda 6]. Si re-troceáis: `encode` en lote, sin prefijo en los pasajes, e índice y `chunks_meta.parquet` a la vez [perfil_dataset · indice/MANIFEST.md · Alineación].
- `BM25Okapi(corpus, tokenizer=None, k1=1.5, b=0.75, epsilon=0.25)` recibe el corpus tokenizado [api_stack · rank_bm25.BM25Okapi] (probado con un
  corpus de juguete). La regex parte "10-K", "7A" o "R&D"; cada variante (stopwords, stemming, como `preprocess_text`
  [transformers-labs · 01-embeddings-tokenizers/01-5-nlp-libraries.ipynb · celda 15]) es un arreglo que se mide con §3.1.
- Consulta en inglés, porque el corpus lo está [S1 · celda 13]: mejor reescribirla con el LLM (R08) que pasar a un modelo multilingüe. Para
  la presentación, el heatmap `np.inner(E, E)` de [celda 10] (consulta con y sin prefijo, chunk ancla, distractor) enseña el "fallo silencioso" del prefijo.

### 3.6 Coste, latencia y llamadas por pregunta; tabla micro/macro (R11, R12)
Original: `call_llms` cronometra cada modelo con `time.perf_counter()` y apunta modelo, parámetros, prompt y respuesta en una tabla, sin tokens ni coste
[transformers-labs · 05-llm/05-4-comparison-llms.ipynb · celdas 3, 11]. [15 §3.6] ya suma el `usage_metadata` de `res["messages"]`; esto añade las llamadas al LLM que **no** están en `messages` (reescritura, middleware R05):

```python
import time
from langchain_core.callbacks import get_usage_metadata_callback
def medir(agente, pregunta: str, thread_id: str) -> dict:
    with get_usage_metadata_callback() as cb:               # acumula las llamadas al LLM del contexto
        t0 = time.perf_counter()
        res = agente.invoke({"messages": [{"role": "user", "content": pregunta}]},
                            config={"configurable": {"thread_id": thread_id}})   # hilo nuevo por pregunta
        lat = time.perf_counter() - t0
    en_msgs = sum((getattr(m, "usage_metadata", None) or {}).get("total_tokens", 0) for m in res["messages"])
    uso = dict(cb.usage_metadata)                            # {modelo: {input_tokens, output_tokens, total_tokens, ...}}
    return {"res": res, "latencia_s": lat, "uso": uso,
            "tokens_fuera_del_bucle": sum(u["total_tokens"] for u in uso.values()) - en_msgs}
# usd = sum(coste(u["input_tokens"], u["output_tokens"], m) for m, u in r["uso"].items())   # coste() de S1 · celda 9
```
- `get_usage_metadata_callback(name='usage_metadata_callback')` existe en langchain-core 1.6.1 (fuera de `api_stack`; comprobado). Con un
  modelo falso captura las llamadas hechas **dentro** de herramientas que el agente ejecuta en paralelo, pierde las de un `ThreadPoolExecutor`
  propio y **no cuenta nada** sin `response_metadata["model_name"]` (probado). `langchain-openrouter` 0.2.8 lo rellena con el `model` que
  devuelve OpenRouter [langchain-openrouter 0.2.8 · chat_models.py · l. 888-889, vía `_generate_with_cache` de langchain-core]:
  ⚠️ comprobad con una llamada real que coincide con la clave de `PRECIOS_OPENROUTER` (si no, `coste()` lanza `KeyError`).
- Si OpenRouter envía `usage.cost`, acaba en `response_metadata["cost"]` [ídem · l. 861-866]: ⚠️ por verificar; serviría para contrastar
  la fórmula de S1, que no contempla descuentos de caché. Latencia: `perf_counter` alrededor del `invoke`, tras calentar (`_indice()` carga
  FAISS y bge la primera vez, ~130 MB [miax_s1 · l. 71-76]); media y mediana. El juez de §3.2 va en columna aparte.
- **Micro y macro** [transformers-labs · 05-llm/05-5-eval-classification.ipynb · celdas 25, 36]: micro = aciertos/preguntas; macro = media
  de las familias, cada una con el mismo peso. Una familia sin preguntas (posible en las 10 ciegas) es "—", nunca 0; 05-5 lo esquiva a
  mano con `n_class = 5` para seis etiquetas y la 5 ausente, que con 6 daría 0/0 [celdas 19-20]. En pandas: `pivot_table(index="sistema",
  columns="familia", values="acierto", aggfunc=lambda s: f"{int(s.sum())}/{len(s)}")` para k/n, `groupby` para micro y macro y
  `fillna("—")` (probado con pandas 2.3.3).
- R12: separad **ejecutar** de **puntuar**: una fila JSONL por pregunta (respuesta estructurada, `tool_calls`, `uso`, latencia, modelo,
  commit, fecha) y evaluadores y tablas regenerados desde ahí. Con 20 preguntas cada una vale 5 pp (10 en las ciegas): contad ganadas y
  perdidas, y repetid el baseline para ver el ruido (⚠️ no está comprobado que `temperature=0` sea determinista en OpenRouter).

### 3.7 Tokens: estimar no es facturar; truncado de bge (R08, R11)
Original: `show_tokens` cuenta con `tiktoken.encoding_for_model("gpt-4")` o con `AutoTokenizer.from_pretrained(nombre)(texto).input_ids`
sobre un texto con emojis, tabuladores y `12.0*50=600` [transformers-labs · 01-embeddings-tokenizers/01-2-tokenizers-comparison.ipynb · celda 9];
el README describe `tiktoken` como BPE "for use with OpenAI's models" [transformers-labs · README.md · l. 6]. Por tanto, la factura
de Gemini sale de `usage_metadata` (§3.6), no de `tiktoken`, que tampoco está en el stack [01_requisitos · §4]; y el corpus trae
`n_tokens` precalculado [S1 · celda 8]. **¿Trunca bge?** Los chunks tienen de 60 a 547 tokens (75 % ≤ 500) [perfil_dataset · chunks.jsonl];
bge-small es un BERT con límite probable de 512 ⚠️ y no se sabe con qué tokenizer se calculó `n_tokens` ⚠️. Si un chunk se trunca, un
ancla al final no se alcanza por la vía densa (BM25 sí la ve). Comprobación (⚠️ no probada: el venv no tiene `transformers`):

```python
from transformers import AutoTokenizer      # ⚠️ se supone instalado con sentence-transformers
tok = AutoTokenizer.from_pretrained("BAAI/bge-small-en-v1.5")
n = meta["texto"].map(lambda t: len(tok(t).input_ids))   # 512: ⚠️ contrastar con SentenceTransformer(...).max_seq_length
print((n > 512).sum(), "de", len(meta), "chunks superan 512 tokens WordPiece")
```

## 4. APIs obsoletas o específicas de GCP y su equivalente

| Original | Estado | Equivalente en nuestro stack |
| --- | --- | --- |
| `scann.scann_ops_pybind.builder(...).tree(...).score_ah(...).reorder(100).build()` [01-6 · celda 6] | Fuera del stack; `pip install scann==1.3.0` y reiniciar Colab [01-6 · celda 1] | `faiss.read_index(...)` del índice dado [miax_s1 · l. 83] (§3.5) |
| `searcher.search(tf.reshape(query,[-1]), final_num_neighbors=3)`; `df["textContent"].apply(get_embedding)` [01-6 · celdas 4, 8] | Mezcla TF; codifica fila a fila | `indice.search(q, k)` con `q` (1, d) float32; `modelo.encode(lista, normalize_embeddings=True, convert_to_numpy=True)` [miax_s1 · l. 118-124] |
| Comentario "768 if palm" [01-6 · celda 6] | ⚠️ específico de GCP (embeddings PaLM de Vertex) | `X.shape[1]` (bge-small = 384) |
| Descargas de `storage.googleapis.com/miax/nlp/...` [01-5 · celda 2; 01-6 · celda 2] y `gsutil cp gs://t5-data/...` [01-2 · celda 16] | ⚠️ específico de GCP | El corpus ya viene dado [enunciado · §3] |
| SDK `google-genai` (`generate_content(config=GenerateContentConfig(...))`, `chats.create`) [05-1 · l. 17-30; 05-4 · celdas 7, 11]; OpenAI y Cohere [05-4 · celdas 5-6, 11] | ⚠️ específico de Google; un SDK por proveedor | Un solo proveedor: `init_chat_model("openrouter:google/gemini-3.8-flash", temperature=0)` [api_stack · init_chat_model] + `create_agent` [api_stack · create_agent] |
| `import vertexai` sin usarlo [05-3 · l. 5]; Model Garden [03-7 · celda 6]; T5X, Pax, Merlin, Vertex Pipelines, `gcloud builds submit`, casos `*-vertex` [README · l. 48-64, 126-273] | ⚠️ específico de GCP | Sin equivalente necesario |
| `Fraction(num, den, _normalize=False)` [05-7 · celdas 13, 19] | ⚠️ API obsoleta: `TypeError` en Python 3.13.7 (probado); versión exacta de la retirada ⚠️ por verificar | `num / den` en float |
| `--evaluation_strategy steps` [README · l. 154] frente a `eval_strategy="steps"` [04-6 · celda 12] | ⚠️ API obsoleta (renombrado; el nombre nuevo ya está en 04-6) | No aplica: no entrenamos |
| `wandb.init` / `wandb.Table` / `wandb.log` [05-4 · celdas 3, 16; 04-6 · celdas 0, 9] | Servicio externo con login | JSONL/CSV regenerables (R12, §3.6) |
| `huggingface-cli login` + `hf_hub_download` [03-7 · celda 5] | Innecesario para bge | `miax_s1` carga bge sin token [miax_s1 · l. 93]; si algún día hace falta, token por entorno (R13) |
| `nltk.download('punkt'/'stopwords'/'punkt_tab')` [01-5 · celda 15] | Red en tiempo de ejecución, paquete sin fijar | Regex propia (§3.5); nada de descargas dentro de `evaluar()` (R10) |
| TF/Keras (`TextVectorization`, `Embedding`, `skipgrams`) [01-3 · celda 1; 01-8 · celda 9]; `tiktoken` [01-2 · celda 9] | Fuera del stack | No aplica (bge congelado); para facturar, `usage_metadata` [api_stack · AIMessage] |

## 5. Qué no aplica y por qué

**No copiéis el código de métricas de 05-llm** (fallos comprobados):
- **BLEU da 1,0 a basura**: `calculate_n_gram_overlap` descarta las precisiones nulas antes del `log` [05-7 · celda 19], así que un
  candidato de igual longitud sin n-gramas comunes, o la referencia al revés, da 1,0 (probado). La brevity penalty de las celdas 8-9
  cuenta caracteres (la referencia "mide" 60 y no 15); `bleu` sí usa `.split()` [celda 22] (probado).
- **LCS recursiva**: `lcs_dp` es memoizada pero recursiva y con dos textos de 1.200 palabras `rouge_l` da `RecursionError` [05-6 · celdas 11, 19];
  su `β = P/R` [celda 16] da 0,868 donde el F1 (β = 1) da 0,889 (probado). Quien reporte ROUGE-L, que diga qué β usa.
- **EM sin normalizar** [05-8 · celda 3]: una mayúscula o un `’` convierten un acierto en fallo (§3.2).
- **05-4 no es una comparación justa**: `temperature=1.0` y una muestra por prompt [05-4 · celdas 9, 14]; `max_output_tokens=128` solo
  llega a Cohere y `gpt-4.1` no recibe ni la temperatura, aunque la tabla registra los mismos parámetros para todos [celda 11]. Para
  comparar: el mismo `evaluar()`, `temperature=0` y modelo fijado por configuración, nunca `openrouter:auto` [01_requisitos · §4].
- **Demos de Gradio**: 05-3 no compila (`config=` dos veces en `chats.create` [05-3 · l. 18-26]: `SyntaxError`, probado); 05-1 tiene un
  slider de `top_p` de 1 a 5 [05-1 · l. 38] y lanza con `share=True` [l. 44]. La entrega es `evaluar()`, no una UI (R10).

**No aplica:**
- **ScaNN o cualquier ANN** (§3.5), **W&B y los SDKs de cada proveedor** (rompen el clon limpio, R10; R12 se cumple con ficheros).
- **FinBERT como quinta herramienta** [04-6 · celda 12]: se permite añadir herramientas [01_requisitos · R01], pero ninguna familia ni
  columna de R11 la premia, mete ruido en la trayectoria (R09c), se entrenó con frases de noticias (`financial_phrasebank`) y el notebook
  trunca a `max_length=150` frente a chunks de ~500 tokens. Si se hace, fuera del camino evaluado y tras congelar el baseline.
- **BLEU, ROUGE o BERTScore como métrica principal**: la respuesta es prosa en español sobre un corpus en inglés y lo léxico no ve
  cifras (§3.2). BERTScore, F1 de tokens, LLM-as-judge y pairwise **no** están en el repo.
- **02-rnn-lstm, 03-1…5/9, 04-2…5/7/8 y `transformers-use-cases/`**: arquitectura, pretraining, fine-tuning, resumen y traducción
  (casos `*-vertex` en GCP). No entrenamos: el cerebro es un LLM por API [01_requisitos · §4] y la traducción de la consulta es parte de la reescritura (R08).
- **01-3, 01-4, 01-8, vectores de palabra de 01-5 y 03-8** (que solo deja en `TODO` la carga de billsum y `financial_phrasebank`
  [03-8 · celdas 7-8]): el corpus y el índice vienen dados [enunciado · §3].

## 6. Orden de lectura recomendado

1. `05-llm/05-5-eval-classification.ipynb`, celdas 4-16 y 19-41: TP/FP/FN, P/R/F1, macro y micro (§3.1, §3.4, §3.6).
2. `05-llm/05-8-eval-qna.ipynb`, celdas 2-9: EM y el caso sin respuesta (§3.2). Cinco minutos.
3. `05-llm/05-7-eval-textgeneration.ipynb`, celdas 12-13 (precisión modificada) y 19 (el fallo del BLEU) (§3.2, §5).
4. `01-embeddings-tokenizers/01-6-scann.ipynb`, celdas 4-10: retrieval denso, latencia y heatmap; leedlo con §3.5 al lado.
5. `01-embeddings-tokenizers/01-5-nlp-libraries.ipynb`, celda 15, y `01-2-tokenizers-comparison.ipynb`, celda 9: tokenizar para BM25 y contar tokens (§3.5, §3.7).
6. (Opcional) `05-llm/05-4-comparison-llms.ipynb`, celdas 9 y 11: cómo **no** comparar modelos (§5).
