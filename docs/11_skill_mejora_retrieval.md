# Skill: mejora medida del retrieval (recall@k)

> Requisitos: R08, R11 (columna recall@k), R12 (rankings y caché) · Lee antes: [04_teoria_rag_retrieval.md](04_teoria_rag_retrieval.md),
> [03_teoria_tokenizacion_embeddings.md](03_teoria_tokenizacion_embeddings.md), [02 §3](02_datos_corpus_y_xbrl.md), [10 §6](10_skill_golden_set.md),
> [16 §3.1 y §3.5](16_repo_transformers_labs.md), [17 §3.7](17_repo_generative_ai.md)

> Fuentes: `00_enunciado.md` §4.4, `01_requisitos_y_contratos.md` (R08, §4, §5), `miax_s1.py` (`_indice()`, `buscar()`,
> `formatear_fragmentos()`), slides de RAG, docs 14–17, notas A5, B2, C1 y D12, `api_stack_langchain.md` y las decisiones comunes D01, D02,
> D07–D10, D13, D16, D19 y D22 del mapa de cobertura (nota interna).

**v1.0 · 12-sep-2026.** Los tres arreglos obligatorios (filtro por metadatos, BM25 + denso y reescritura con el LLM), medidos con recall@k
contra el ancla tras cada uno, y cómo se enchufan en `search_filings` sin tocar su firma. Marcas: **(probado)** = ejecutado en el venv del
stack con datos de juguete, índice y codificador falsos y un modelo falso (el venv no tiene faiss, sentence-transformers ni pandas);
**(venv)** = introspección; ⚠️ = sin verificar. Módulos `agente10k/…`: **SUGERENCIA**. **Revisar tras el 17-sep**: la sesión 2 abre
`search_filings` y ahí se sabrá cómo mide el profesor el filtro [14 §6](14_clase_pistas_del_profesor.md).

> **Actualización 21-sep-2026.** La guía ya está implementada en `agente10k.retrieval`,
> `agente10k.herramientas` y `agente10k.evaluacion`. La ejecución completa seleccionada es
> `resultados/retrieval/5976eb180c38/`: 2/13 → 4/13 → 5/13 → 5/13 en recall@5 para denso, filtro,
> BM25 y reescritura, sin fallos de reescritura. `candidato_07` usa el backend mejorado en la tool pública
> `search_filings`; todavía no incluye los guardrails del 06.

### Lectura correcta de las cifras

- **Oficial para R08:** la escalera aislada y persistida en la huella anterior, medida contra las 13 anclas.
- **Provisional:** la calidad extremo a extremo de `resultados/candidato_07/`, cuando exista su ejecución completa.
- **Exploratorio:** `resultados/experimentos/ingles_20260917/`. Su 12/13 usa consultas y filtros manuales de
  diagnóstico y no es rendimiento del agente, del candidato ni del sistema final.
- **Oficial para R11/R12:** `resultados/final/` y `resultados/baseline_nexn25pro/` (mismo modelo), tras integrar
  y probar `middleware_final()`. Una sola ejecución; repetirla antes de defenderla como definitiva.

## 1. Qué se entrega

- R08: partir de la búsqueda densa entregada, aplicar como mínimo filtro, híbrido y reescritura, y medir recall@k contra el ancla **después
  de cada arreglo** [enunciado · §4.4].
- `resultados/retrieval/rankings_<paso>.jsonl` (un top-20 por pregunta y paso), `techos.jsonl` y `escalera.csv|md` (D19). Todo sale de ahí (R12).
- La columna recall@5 de la tabla R11: **baseline = paso 0**; **final = paso 3 con los filtros que extrae el LLM**, nunca los oráculo (D09).
- La `search_filings` final, que envuelve `buscar_v2()` con la configuración fija (§9), y el material de "qué no funcionó" para R15 (§12).

## 2. Protocolo: un cambio cada vez

1. **Fijad antes de medir**, en `config.py` y en un commit: golden (anclas), `n_cand=20`, `k_rrf=60` con pesos iguales, `k1=1.5, b=0.75,
   ε=0.25`, tokenizer `[a-z0-9]+`, prompt de reescritura y modelo (D09). Ajustarlos mirando las 14 anclas es sobreajuste: cada pregunta mueve
   ~7 pp y la mejora de ClearBox tras validación cruzada (~0,04 en recall@1) no llega a una pregunta [17 §3.7](17_repo_generative_ai.md).
2. **Comprobad las anclas**: `anclas_no_indexables` = 0 con el índice entregado. Un ancla partida entre dos chunks es un falso negativo del
   golden, no del retrieval: el 60 % de los cortes no se solapa (V6) [10 §6](10_skill_golden_set.md).
3. **Un solo ranking top-20** por pregunta y paso, guardado; @1, @3, @5, @10 y MRR@10 se recortan de ahí, sin re-ejecutar por cada k
   [17 §3.7](17_repo_generative_ai.md). Principal: **recall@5**, el `k` por defecto del contrato.
4. **Escalera incremental**: entre dos filas consecutivas solo cambia un arreglo; mismas preguntas y mismo orden.
5. **Siempre k/n**, desglosado por `item`, y con filtros también el acierto aleatorio `min(1, k/|candidatos|)`: el 7A tiene de 1 a 5 chunks y
   con filtro de item ahí recall@5 es trivial [perfil_dataset · chunks.jsonl] (D08).
6. **Dos modos**: *aislado* (se llama a la función de búsqueda; es la cifra de la tabla) y *dentro del agente* (`recall_agente`, diagnóstico).

| Paso | Qué añade | Consulta | Filtros | Coste extra |
| --- | --- | --- | --- | --- |
| 0 · baseline | Denso bge exacto, prefijo solo en la consulta (= `miax_s1.buscar()`) | pregunta tal cual | ninguno | — |
| 1 · + filtro | Pre-filtro `ticker`/`fiscal_year`/`item` y ranking dentro de los candidatos | pregunta tal cual | **oráculo** (techo) | — |
| 2 · + BM25 | `BM25Okapi` con IDF global + RRF (k=60, pesos iguales, `n_cand=20` por lista) | pregunta tal cual | oráculo | ms de CPU |
| 3 · + reescritura | `reescribir()` → `Busqueda` (1–3 consultas en inglés + filtros), cacheada; multi-query y una subconsulta por FY | reescrita | **los del LLM** | 1 llamada al LLM por pregunta |

## 3. Carga y búsqueda densa exacta (paso 0)

`buscar()` codifica `PREFIJO + query`, pide al índice **los 1.749** vectores y filtra después [miax_s1 · buscar()]. Aquí se guarda el vector
de puntuaciones completo en el orden del índice, que es lo que necesita la fusión con BM25 [16 §3.5](16_repo_transformers_labs.md).

```python
# agente10k/retrieval.py (SUGERENCIA) · carga única, búsqueda densa exacta y pre-filtro
import re
from functools import lru_cache

import numpy as np
from rank_bm25 import BM25Okapi

# from agente10k.config import CORPUS                          -> ruta configurable (02 §7, D25)
MODELO_EMB = "BAAI/bge-small-en-v1.5"
PREFIJO = "Represent this sentence for searching relevant passages: "   # SOLO en la consulta

def tokenizar(t: str) -> list[str]:
    """La MISMA para corpus y consulta. BM25Okapi no pasa a minúsculas, y con un str itera letras y da un ranking basura sin avisar."""
    return re.findall(r"[a-z0-9]+", t.lower())

@lru_cache(maxsize=1)
def recursos() -> dict:
    """Índice, metadatos, codificador y BM25, una sola vez (~130 MB de bge la primera)."""
    import faiss, pandas as pd
    from sentence_transformers import SentenceTransformer
    indice = faiss.read_index(str(CORPUS / "indice" / "corpus.faiss"))
    filas = pd.read_parquet(CORPUS / "indice" / "chunks_meta.parquet").to_dict("records")   # fila i <-> vector i
    if indice.ntotal != len(filas):
        raise RuntimeError("Índice y chunks_meta desalineados: regenerad los dos juntos")
    col = lambda c: np.array([f[c] for f in filas])
    return {"indice": indice, "emb": SentenceTransformer(MODELO_EMB), "filas": filas, "ticker": col("ticker"),
            "fy": col("fiscal_year").astype(int), "item": col("item"),
            "bm25": BM25Okapi([tokenizar(f["texto"]) for f in filas])}              # IDF GLOBAL (1.749 chunks)

@lru_cache(maxsize=512)
def puntuacion_densa(consulta: str) -> np.ndarray:
    """Coseno con TODOS los chunks, en el orden del índice (IndexFlatIP sobre vectores normalizados)."""
    r = recursos()
    q = r["emb"].encode([PREFIJO + consulta], normalize_embeddings=True, convert_to_numpy=True).astype("float32")
    punt, pos = r["indice"].search(q, r["indice"].ntotal)
    v = np.empty(r["indice"].ntotal, dtype="float32")
    v[pos[0]] = punt[0]
    return v

def norm_item(item) -> str | None:                     # 'Item 1A', '1a' -> '1A' (la misma que las tools, 07)
    return re.sub(r"(?i)^\s*item\s*", "", str(item or "")).strip().upper() or None

def candidatos(ticker=None, fiscal_year=None, item=None) -> np.ndarray:
    """PRE-filtro por igualdad sobre valores ya normalizados. Sin filtros, los 1.749."""
    r = recursos()
    m = np.ones(len(r["filas"]), dtype=bool)
    if ticker:
        m &= r["ticker"] == ticker
    if fiscal_year:
        m &= r["fy"] == int(fiscal_year)
    if item:
        m &= r["item"] == norm_item(item)
    return np.flatnonzero(m)
```

- Alineación: además de `ntotal == len(filas)`, `cargar_corpus()` de [02 §7](02_datos_corpus_y_xbrl.md) comprueba el SHA-256 de
  `chunks.jsonl` contra los dos manifiestos. Un índice desalineado devuelve texto equivocado **sin error**.
- `puntuacion_densa` va cacheada por consulta, porque los pasos 0–2 repiten la pregunta. Para medir ms se vacía la caché antes de cada paso (§8).
  `reconstruct_n` para sacar la matriz está ⚠️ sin comprobar en faiss-cpu 1.15; `search(q, ntotal)` es lo que ya hace `buscar()`.

## 4. recall@k contra el ancla (D08)

Conjunto: las preguntas con `ancla_texto` (extractivas y comparativas; en las comparativas, el ancla del FY reciente, D10). Acierto @k: algún
chunk del top-k contiene `normalizar(ancla)` entero (substring estricto, la `normalizar` de [10 §6](10_skill_golden_set.md)). Con una sola
ancla, recall@k = hit-rate@k. La cobertura de 4-gramas ≥ 0,8 ([16 §3.2](16_repo_transformers_labs.md)) solo diagnostica, y solo si se re-trocea.

```python
# agente10k/metricas_retrieval.py (SUGERENCIA)
import json, time
from pathlib import Path
# from agente10k.normalizacion import normalizar               -> D07, la misma en todo el repo
# from agente10k.retrieval import recursos
KS = (1, 3, 5, 10)

def textos_indice() -> dict[str, str]:
    return {f["chunk_id"]: normalizar(f["texto"]) for f in recursos()["filas"]}

def relevantes(ancla: str, textos: dict[str, str]) -> set[str]:
    """Chunks del índice EN USO que contienen el ancla entera (con solape, a veces dos)."""
    a = normalizar(ancla)
    return {cid for cid, t in textos.items() if a in t}

def anclas_no_indexables(golden: list[dict], textos: dict[str, str]) -> list[str]:
    return [p["id"] for p in golden if p.get("ancla_texto") and not relevantes(p["ancla_texto"], textos)]

def medir_paso(golden: list[dict], paso: str, rankear, dir_ret: Path) -> list[dict]:
    """rankear(p) -> (índices de fila ordenados, info). Guarda UN top-20 por pregunta; los k salen de ahí."""
    ids, filas = [f["chunk_id"] for f in recursos()["filas"]], []
    for p in (p for p in golden if p.get("ancla_texto")):
        t0 = time.perf_counter()
        orden, info = rankear(p)
        filas.append({"id": p["id"], "familia": p.get("familia"), "item": p.get("item_esperado"),
                      "ms": round(1000 * (time.perf_counter() - t0), 1), "ranking": [ids[i] for i in orden[:20]], **info})
    dir_ret.mkdir(parents=True, exist_ok=True)
    with open(dir_ret / f"rankings_{paso}.jsonl", "w", encoding="utf-8") as fh:
        fh.writelines(json.dumps(f, ensure_ascii=False, default=str) + "\n" for f in filas)
    return filas

def puntuar_rankings(filas: list[dict], golden: list[dict], textos: dict[str, str]) -> dict:
    """hits y recall@k, MRR@10, ms y desglose por item. Un ancla no indexable cuenta como fallo."""
    anclas = {p["id"]: p["ancla_texto"] for p in golden if p.get("ancla_texto")}
    det = []
    for f in filas:
        rel = relevantes(anclas[f["id"]], textos)
        rango = next((r for r, cid in enumerate(f["ranking"], start=1) if cid in rel), None)
        det.append({"id": f["id"], "item": f["item"], "n_rel": len(rel), "rango": rango})
    en = lambda d, k: d["rango"] is not None and d["rango"] <= k
    n = len(det) or 1
    res = {"n": len(det), "no_indexables": sum(d["n_rel"] == 0 for d in det),
           "mrr@10": round(sum(1 / d["rango"] for d in det if en(d, 10)) / n, 3),
           "ms_medio": round(sum(f["ms"] for f in filas) / n, 1)}
    for k in KS:
        res[f"hits@{k}"] = h = sum(en(d, k) for d in det)
        res[f"recall@{k}"] = round(h / n, 3)
    res["por_item@5"] = {it: f"{sum(en(d, 5) for d in det if d['item'] == it)}/{sum(d['item'] == it for d in det)}"
                         for it in sorted({d["item"] for d in det}, key=str)}
    return res | {"detalle": det}
```

## 5. Paso 1 · filtro por metadatos (C20)

- **Qué significa aquí.** `buscar()` ordena el índice entero y filtra después: con búsqueda exacta, pre- y post-filtro dan el **mismo** top-k
  [miax_s1 · buscar(); 01 §5, trampa 7] **(probado)**. Mover el filtro no sube nada por sí solo. Se miden tres cosas:
  1. el **techo** con los filtros oráculo del golden (paso 1 de la escalera);
  2. si el agente **pasa** los filtros: el % de `search_filings` con `ticker`, `fiscal_year` e `item` correctos, que depende del docstring
     ([07](07_skill_herramientas_docstrings.md)) [B2 · R08];
  3. el **pre-filtro obligatorio** en cuanto se corta un top-N (el `n_cand` del híbrido o un rerank): filtrar después de cortar sí pierde recall.
- **Un filtro erróneo deja el recall a 0**; uno ausente solo lo diluye. Se cuentan por separado.

```python
# agente10k/metricas_retrieval.py (continúa) · ¿llegan bien los filtros?
# from agente10k.normalizacion import normalizar_ticker         -> 09 §4 (alias: GOOG, Alphabet -> GOOGL)
# from agente10k.retrieval import norm_item
def _int(x):
    try:
        return int(str(x).upper().replace("FY", "").strip())
    except ValueError:
        return None

def fys_esperados(p: dict) -> set[int]:
    fy = int(p["fiscal_year"])
    return {fy, int(p.get("fiscal_year_base") or ({2024, 2025} - {fy}).pop())} if p.get("familia") == "comparativa" else {fy}

def _estado(valor, ok: bool) -> str:
    return "ausente" if valor in (None, "", []) else ("ok" if ok else "erroneo")

def estado_filtros(ticker, fy_bruto, fy_ok: bool, item, p: dict) -> dict:
    return {"ticker": _estado(ticker, normalizar_ticker(ticker) == p["ticker"]), "fy": _estado(fy_bruto, fy_ok),
            "item": _estado(item, norm_item(item) == p.get("item_esperado"))}

def filtros_busqueda(b: dict, p: dict) -> dict:                 # lo que devolvió reescribir()
    fys = b.get("fiscal_years") or []
    return estado_filtros(b.get("ticker"), fys, {_int(f) for f in fys} == fys_esperados(p), b.get("item"), p)

def filtros_agente(pred: dict, p: dict) -> list[dict]:          # cada search_filings de la trayectoria (fila de 13)
    return [estado_filtros(a.get("ticker"), a.get("fiscal_year"), _int(a.get("fiscal_year")) in fys_esperados(p), a.get("item"), p)
            for a in (t["args"] for t in pred["tool_calls"] if t["name"] == "search_filings")]
```

Trampas del filtro: `fiscal_year` no es el año de presentación; el Item 15 de NVDA se sirve como `"8"`; `fila["item"]`, nunca `fila.item`
[01 §5]. Reintentar sin `item` cuando no hay resultados es un arreglo más: se mide aparte, no entra de tapadillo [A5 · R08].

## 6. Paso 2 · BM25 + denso con RRF (C18, C19)

- **IDF global**: `BM25Okapi` se construye una vez sobre los 1.749 chunks y solo se puntúan los candidatos con `get_batch_scores(tokens, ids)`,
  que da lo mismo que `get_scores(tokens)[ids]` **(probado)**. Un BM25 construido solo con los candidatos cambia los IDF, y hay secciones de 1 a
  5 chunks [D12 · R08]. Firmas: `BM25Okapi(corpus, tokenizer=None, k1=1.5, b=0.75, epsilon=0.25)`, `get_batch_scores(query, doc_ids)` (venv).
- **Fuera los score 0**: sin tokens en común (pregunta en español, corpus en inglés), `argsort` ordena por posición y RRF premiaría los
  primeros chunks de cada sección **(probado)**.
- **RRF k=60 y pesos iguales**, fijado antes de medir. El notebook de Google suma 1/rango sin constante y ClearBox usa 40: no se mezclan
  fórmulas entre filas [17 §3.7](17_repo_generative_ai.md) (C18). El tokenizer `[a-z0-9]+` parte "10-K", "7A" o "60,922": sus variantes son
  experimentos medidos (C19) [16 §3.5](16_repo_transformers_labs.md).

```python
# agente10k/retrieval.py (continúa) · híbrido
CONFIG = {"bm25": True, "n_cand": 20, "k_rrf": 60}     # sistema final: fijada ANTES de medir (D09)
PASO0 = {"bm25": False, "n_cand": 20, "k_rrf": 60}     # solo denso (= miax_s1.buscar)

def rank_denso(consulta: str, cand: np.ndarray, n: int) -> np.ndarray:
    s = puntuacion_densa(consulta)[cand]
    return cand[np.argsort(-s, kind="stable")[:n]]

def rank_bm25(consulta: str, cand: np.ndarray, n: int) -> np.ndarray:
    s = np.asarray(recursos()["bm25"].get_batch_scores(tokenizar(consulta), cand.tolist()))
    orden = np.argsort(-s, kind="stable")
    return cand[orden[s[orden] > 0][:n]]               # sin coincidencias no hay señal

def rrf(listas, k_rrf: int = 60, pesos=None) -> list[int]:
    """Suma w / (k_rrf + rango), rango desde 1 [slides RAG · p.42]. Empate: gana el que apareció antes."""
    pesos, punt = pesos or [1.0] * len(listas), {}
    for w, lista in zip(pesos, listas):
        for rango, i in enumerate(lista, start=1):
            punt[int(i)] = punt.get(int(i), 0.0) + w / (k_rrf + rango)
    return sorted(punt, key=punt.get, reverse=True)

def buscar_v2(consultas, ticker=None, fiscal_year=None, item=None, k: int = 5, cfg=CONFIG) -> list[int]:
    """Pre-filtro -> denso (+ BM25) por consulta, n_cand por lista -> RRF -> top-k (índices de fila)."""
    cand = candidatos(ticker, fiscal_year, item)
    if cand.size == 0:
        return []
    listas = []
    for q in [consultas] if isinstance(consultas, str) else consultas:     # multi-query [slides RAG · p.37]
        listas.append(rank_denso(q, cand, cfg["n_cand"]))
        if cfg["bm25"]:
            listas.append(rank_bm25(q, cand, cfg["n_cand"]))
    return rrf(listas, cfg["k_rrf"])[:k]
```

Con `PASO0` y sin filtros, `buscar_v2(pregunta, k=20)` reproduce el orden de `buscar(pregunta, k=20)` (con una sola lista, RRF conserva el
orden): comprobadlo con dos preguntas reales antes de medir **(probado con índice falso)**.

## 7. Paso 3 · reescritura con el LLM (C21)

- **Qué hace:** traduce y expande la pregunta a 1–3 consultas en inglés con vocabulario de 10-K y extrae los filtros. El corpus y
  bge-small-**en** están en inglés [notebook S1 · celda 13; 14 §7]. La consulta de búsqueda no es la pregunta respondida [slides RAG · p.36].
- **Comparativas:** descomposición *single-step*, una subconsulta por FY (el reciente primero) fusionadas con RRF. Con k=5 salen 3 chunks del FY
  reciente y 2 del base, alternados: el `ceil(k/2)` de [A5 · snippet 4] **(probado)**.
- **Dónde vive** (D09): en el agente reescribe **el propio modelo**, que escribe `query` en inglés y pasa los filtros siguiendo el docstring.
  `reescribir()` es su medida en modo aislado, con **las mismas reglas** que el docstring de `search_filings`
  ([07](07_skill_herramientas_docstrings.md); un test comprueba que el texto coincide). Un multi-query *dentro* de la tool solo entra si sube
  el recall, y entonces su coste lo captura el callback de [08 §7](08_skill_agente_salida_estructurada.md) (D16).
- **Coste:** una llamada por pregunta, cacheada en `resultados/cache/reescrituras.json` por (modelo, pregunta). La escalera se regenera sin
  pagar y la primera pasada deja tokens y ms. Modelo: la misma instancia a `temperature=0` que el agente (D01).

```python
# agente10k/retrieval.py (continúa) · reescritura
import json, time
from pathlib import Path

from langchain.agents import create_agent
from langchain.agents.structured_output import ToolStrategy
from langchain_core.callbacks import get_usage_metadata_callback
from pydantic import BaseModel, Field

class Busqueda(BaseModel):
    """Search request for the 10-K corpus."""
    consultas: list[str] = Field(description="1-3 short ENGLISH search queries in 10-K wording; no company name, no year")
    ticker: str | None = Field(default=None, description="NVDA, MSFT, AAPL, GOOGL, META or AMZN")
    fiscal_years: list[int] = Field(default_factory=list, description="Fiscal years asked (2024, 2025); both if compared")
    item: str | None = Field(default=None, description="'1A' risk factors, '7' MD&A, '7A' market risk, '8' financial statements")

INSTRUCCIONES_BUSQUEDA = """You turn a question about the 10-K filings of NVDA, MSFT, AAPL, GOOGL, META and AMZN
(fiscal years 2024 and 2025) into a search request.
- Write 1-3 short ENGLISH queries with the wording of a 10-K. Never put the company or the year in the queries.
- Company, fiscal year and section go in the filter fields. The fiscal year is the one the question names, not the filing year.
- Sections: '1A' risk factors, '7' MD&A, '7A' market risk, '8' financial statements.
- If the question compares two fiscal years, list both."""

def crear_reescritor(modelo):
    """`modelo` = la INSTANCIA a temperature=0 (D01). tools=[]: nodo de modelo + tool sintética del esquema (D02)."""
    return create_agent(model=modelo, tools=[], system_prompt=INSTRUCCIONES_BUSQUEDA,
                        response_format=ToolStrategy(schema=Busqueda))

def reescribir(pregunta: str, reescritor, cache: dict, modelo_id: str) -> dict:
    clave = f"{modelo_id}::{pregunta}"
    if clave not in cache:
        with get_usage_metadata_callback() as cb:
            t0 = time.perf_counter()
            b = reescritor.invoke({"messages": [{"role": "user", "content": pregunta}]}).get("structured_response")
            ms = 1000 * (time.perf_counter() - t0)
        cache[clave] = {"busqueda": (b or Busqueda(consultas=[pregunta])).model_dump(), "fallo": b is None,
                        "uso": {m: dict(u) for m, u in cb.usage_metadata.items()}, "ms": round(ms)}
    return cache[clave]

def buscar_reescrita(b: dict, k: int = 5, cfg=CONFIG) -> list[int]:
    """Busqueda -> ranking. Comparativas: una subconsulta por FY, el más reciente primero, fusionadas con RRF."""
    ticker = normalizar_ticker(b.get("ticker")) or None                 # 09 §4
    fys = sorted({int(f) for f in b.get("fiscal_years") or []}, reverse=True) or [None]
    listas = [buscar_v2(b["consultas"], ticker, fy, b.get("item"), k=cfg["n_cand"], cfg=cfg) for fy in fys]
    return (listas[0] if len(listas) == 1 else rrf(listas, cfg["k_rrf"]))[:k]

cargar_cache = lambda ruta: json.loads(ruta.read_text(encoding="utf-8")) if ruta.is_file() else {}
guardar_cache = lambda ruta, cache: (ruta.parent.mkdir(parents=True, exist_ok=True),
                                     ruta.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8"))
```

- `create_agent(modelo, tools=[], response_format=ToolStrategy(Busqueda))` devuelve `structured_response` con un modelo falso que llama a la
  tool `Busqueda` **(probado)**. Con Gemini real ⚠️: si llega `None`, la entrada queda con `fallo=True` y la pregunta cruda como consulta; se
  cuenta, no se esconde. Nunca `with_structured_output`, obsoleto según el notebook [01 §4].
- Coste medio de la reescritura: `usd()` de [08 §7](08_skill_agente_salida_estructurada.md) sobre el `uso` de cada entrada, con los precios de
  `resultados/precios.json` (D24). Va a la escalera, **no** a la columna de coste de R11: en el agente no hay llamada extra (D09, D16).
- HyDE no aparece en las slides; si se prueba, es otra fila y otra llamada [A5 · R08].

## 8. Ejecutar la escalera

```python
# agente10k/metricas_retrieval.py (continúa) · python -m agente10k.metricas_retrieval golden/golden_propio.jsonl
# from agente10k.retrieval import (CONFIG, PASO0, buscar_v2, buscar_reescrita, candidatos, rank_bm25, rank_denso,
#                                  reescribir, puntuacion_densa, cargar_cache, guardar_cache)
RUTA_CACHE = Path("resultados/cache/reescrituras.json")
oraculo = lambda p: {"ticker": p["ticker"], "fiscal_year": p["fiscal_year"], "item": p.get("item_esperado")}

def pasos(rw) -> dict:
    """rw(p) -> entrada de caché de reescribir(). Los 'd_' son diagnósticos, no filas de la escalera."""
    return {"0_denso":       lambda p: (buscar_v2(p["pregunta"], k=20, cfg=PASO0), {}),
            "1_filtro":      lambda p: (buscar_v2(p["pregunta"], k=20, cfg=PASO0, **oraculo(p)), {}),
            "2_bm25":        lambda p: (buscar_v2(p["pregunta"], k=20, cfg=CONFIG, **oraculo(p)), {}),
            "3_reescritura": lambda p: (buscar_reescrita(rw(p)["busqueda"], k=20), {"filtros": filtros_busqueda(rw(p)["busqueda"], p)}),
            "d_rw_oraculo":  lambda p: (buscar_v2(rw(p)["busqueda"]["consultas"], k=20, cfg=CONFIG, **oraculo(p)), {}),
            "d_solo_bm25":   lambda p: (list(rank_bm25(p["pregunta"], candidatos(**oraculo(p)), 20)), {})}

def techos(p: dict, textos: dict[str, str], ids: list[str]) -> dict:
    """RRF solo reordena: si el ancla no está en la unión de las dos listas, fusionar no ayuda [17 §3.7]."""
    rel, cand = relevantes(p["ancla_texto"], textos), candidatos(**oraculo(p))
    d, b = rank_denso(p["pregunta"], cand, 20), rank_bm25(p["pregunta"], cand, 20)
    en = lambda idx: bool(rel & {ids[i] for i in idx})
    return {"id": p["id"], "n_cand": len(cand), "aleatorio@5": min(1.0, 5 / max(1, len(cand))), "techo_filtro": en(cand),
            "hit_denso@20": en(d), "hit_bm25@20": en(b), "techo_hibrido": en(list(d) + list(b))}

def escalera(golden, reescritor, modelo_id, dir_ret=Path("resultados/retrieval"), exigir_anclas=True) -> list[dict]:
    textos, cache = textos_indice(), cargar_cache(RUTA_CACHE)
    if (faltan := anclas_no_indexables(golden, textos)) and exigir_anclas:
        raise ValueError(f"Anclas que no están enteras en ningún chunk: {faltan} (10 §6)")
    con_ancla = [p for p in golden if p.get("ancla_texto")]
    rw = lambda p: reescribir(p["pregunta"], reescritor, cache, modelo_id)
    for p in con_ancla:
        rw(p)                                           # el LLM, fuera del cronómetro de los rankings
    guardar_cache(RUTA_CACHE, cache)
    filas = []
    for paso, fn in pasos(rw).items():
        puntuacion_densa.cache_clear()                  # ms honestos
        res = puntuar_rankings(medir_paso(golden, paso, fn, dir_ret), golden, textos)
        filas.append({"paso": paso} | {k: v for k, v in res.items() if k != "detalle"})
    ids = [f["chunk_id"] for f in recursos()["filas"]]
    with open(dir_ret / "techos.jsonl", "w", encoding="utf-8") as fh:
        fh.writelines(json.dumps(techos(p, textos, ids)) + "\n" for p in con_ancla)
    return filas                                        # -> escalera.csv y escalera.md (§10)
```

**Anexo, rejilla 2³** (filtros {no, oráculo} × BM25 {no, sí} × reescritura {no, sí}): el mismo `medir_paso` con `cfg=PASO0|CONFIG`, consultas
`p["pregunta"]` o `rw(p)["busqueda"]["consultas"]` y `**oraculo(p)` o nada. Enseña interacciones (BM25 puede no mover nada hasta que la
consulta está en inglés) y alimenta "qué no funcionó" [A5 · R08].

## 9. Integración en `search_filings` sin tocar la firma

Firma, nombre y docstring son contrato y [07](07_skill_herramientas_docstrings.md); aquí solo el cuerpo. `CONFIG` vive en el código y se guarda
en `resumen.json`; **nunca** es un parámetro que vea el modelo: así `evaluar()` funciona igual en un clon limpio y el LLM no puede cambiar el
modo de búsqueda [A5 · snippet 3] (D09).

Esquema del cuerpo; la versión que se entrega es la de [07 §5](07_skill_herramientas_docstrings.md) (valida filtros, `try/except`,
`'15'`→`'8'`, aviso de k recortado) con `BACKEND = "v2"`.

```python
# agente10k/herramientas.py (SUGERENCIA) · solo el cuerpo; docstring y parse_docstring: 20
from langchain.tools import tool
# from agente10k.retrieval import CONFIG, buscar_v2, puntuacion_densa, recursos
# from agente10k.normalizacion import normalizar_ticker

@tool
def search_filings(query: str, ticker: str | None = None, fiscal_year: int | None = None,
                   item: str | None = None, k: int = 5) -> str:
    """(docstring de 20: cuándo sí y cuándo no, consulta en INGLÉS, filtros, coste; mismas reglas que INSTRUCCIONES_BUSQUEDA)"""
    k = max(1, min(k, 10))                              # los tipos ya los validó @tool (ver nota)
    ids = buscar_v2([query], normalizar_ticker(ticker) or None, fiscal_year, item, k=k, cfg=CONFIG)
    if not ids:
        return "Sin resultados con esos filtros. Revisa ticker, fiscal_year e item, o quita alguno."
    filas, sim = recursos()["filas"], puntuacion_densa(query)
    return "\n\n---\n\n".join(f"[{filas[i]['chunk_id']}] {filas[i]['ticker']} FY{filas[i]['fiscal_year']} "
                              f"Item {filas[i]['item']} (similitud {sim[i]:.3f})\n{filas[i]['texto']}" for i in ids)

def recall_agente(pred: dict, ancla: str) -> bool:
    """Modo 'dentro del agente' (D08): ¿llegó el ancla en algún search_filings? (observaciones: filas de 13)"""
    vistos = " ".join(normalizar(o["content"]) for o in pred.get("observaciones", []) if o["name"] == "search_filings")
    return normalizar(ancla) in vistos
```

- Mismo formato que `formatear_fragmentos()` [miax_s1]: `[chunk_id]` delante (el agente cita con él) y el texto completo en el contenido del
  `ToolMessage`, que es lo que usa la etapa 1 del evaluador (a) para la "cita vista" (D13) **(probado)**. Los mensajes con los valores válidos
  los amplía [07](07_skill_herramientas_docstrings.md) (D22). Una comparativa en el agente son **dos** llamadas, una por `fiscal_year`.
- **Tipos:** `@tool` valida los argumentos con pydantic **antes** del cuerpo. `"2025"` y `"7"` llegan convertidos a `int`; `"FY2025"` no entra:
  dentro de `create_agent` vuelve al modelo como `ToolMessage` con `status="error"` y "Please fix the error and try again", sin excepción; con
  `.invoke()` directo lanza `ValidationError` **(probado)**. Un `try/except` de tipos dentro del cuerpo no sirve de nada.

## 10. Diagnósticos y plantilla de tabla

`escalera.md`, generado desde `escalera.csv` (k/n = hits/n, con n ≈ 14):

| Paso | Consulta | Filtros | recall@1 | recall@3 | **recall@5** | recall@10 | MRR@10 | ms/consulta | USD reescritura/preg. |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0 · denso (baseline → R11) | pregunta | — | x/14 | x/14 | **x/14** | x/14 | 0,xx | x | — |
| 1 · + filtro | pregunta | oráculo | … | … | … | … | … | … | — |
| 2 · + BM25 (RRF) | pregunta | oráculo | … | … | … | … | … | … | — |
| 3 · + reescritura (final → R11) | reescrita | LLM | … | … | … | … | … | … | 0,000x |
| d · reescritura + oráculo | reescrita | oráculo | … | … | … | … | … | … | (la misma) |
| d · solo BM25 | pregunta | oráculo | … | … | … | … | … | … | — |

En el mismo fichero:
- **Por item** (`por_item@5` de cada paso y aleatorio@5 medio de `techos.jsonl`): lo difícil son 1A y 8 (30–90 candidatos); el 7A es trivial.
- **Techos** (k/n): `techo_filtro`, `hit_denso@20`, `hit_bm25@20` y `techo_hibrido`. Techo alto con recall@5 bajo → problema de orden
  (rerank); techo bajo → consulta (reescritura) o troceado.
- **Filtros** (% ok / ausente / erróneo por campo) de `reescribir()` y de las `search_filings` de la ejecución final. Si el oráculo y el LLM
  distan mucho, el problema está en el docstring o en el prompt, no en el índice [B2 · R08].
- **Anexo:** rejilla 2³ y `recall_agente` por pregunta junto al recall aislado.

## 11. Opcionales, siempre después de los tres

Cada uno es una fila nueva, medida contra el paso 3 con su coste y su latencia. El profesor espera mejoras "sobre todo" en troceado y búsqueda,
y habló de elegir y guardar embeddings propios [transcripcion_10sep · 02:26, 02:31]: ⚠️ preguntar el 17 si es obligatorio (C27).

| Opcional | Qué implica | Cuidado |
| --- | --- | --- |
| Rerank con cross-encoder (top-20 → top-5) | ⚠️ `CrossEncoder` de sentence-transformers 6.0.1 sin comprobar; otro modelo que baja en el clon limpio | Techo = hit@20 previo; ms a R11 |
| Re-troceado respetando frases | Índice + `chunks_meta.parquet` + manifiesto nuevos, en otra carpeta; cambian los `chunk_id` (el ancla no) | `anclas_no_indexables` otra vez, con `exigir_anclas=False` (cuentan como fallo); el baseline sigue con el índice entregado |
| Cabecera "TICKER FY Item" solo en el texto que se embebe | Re-embeber los 1.749; `texto` y `chunk_id` intactos | Aporta en búsquedas sin filtro (hipótesis) [A5 · snippet 8] |
| Prefijo BGE sí/no | Gratis | Enseña el fallo silencioso en la presentación [16 §3.5](16_repo_transformers_labs.md) |
| Variantes del tokenizer (conservar `60,922`, `2.97`, `7a`) | BM25 rehecho | Una variante = una fila [A34 · snippet 1] |
| Otro modelo de embeddings | Reindexar, con su prefijo y su manifiesto [slides RAG · p.44] | Nunca mezclar modelos entre consulta e índice |
| Vecinos por `posicion` (*small-to-big*); sin tablas en preguntas de prosa | Más tokens por llamada | El 41 % de los chunks tiene tabla [perfil_dataset · LEEME] |

Un índice nuevo va en su carpeta: `encode` en lote **sin** prefijo en los pasajes, `faiss.IndexFlatIP(dim)` + `add` + `write_index` (⚠️ faiss
sin introspección), `chunks_meta.parquet` en el mismo orden y un manifiesto con modelo, prefijo de consulta, `n`, dimensión y SHA-256 de los
chunks; `recursos()` lee carpeta y modelo de ahí (sugerencia: `AGENTE10K_INDICE`). Se guarda en el repo o se regenera en cada ejecución
[transcripcion_10sep · 02:31].

## 12. Trampas y lectura para R15

1. **Prefijo BGE** omitido en la consulta, o puesto en los pasajes al reindexar: no da error, solo recupera peor [01 §4].
2. **BM25 con un `str` o con mayúsculas**, sin error: con un `str`, ranking basura (distinto de cero con el corpus real,
   [03 §2](03_teoria_tokenizacion_embeddings.md)); con mayúsculas, 0. Y si no se quitan los 0, orden por posición **(probado)**.
3. **Índice desalineado** con `chunks_meta.parquet`: texto equivocado sin aviso. Hash y `ntotal` antes de nada [02 §3](02_datos_corpus_y_xbrl.md).
4. **Post-filtro después de cortar un top-N** (híbrido, rerank): pierde recall; el pre-filtro va antes del corte.
5. **Medir con filtros oráculo y presentarlo como el sistema final**: la cifra de R11 es la del paso 3 con los filtros del LLM.
6. **Ajustar `n_cand`, `k_rrf`, pesos o el prompt contra el golden**: sobreajuste que destapan las ciegas [slides Tuning · p.55].
7. **Caché sin el id del modelo en la clave**, o escalera medida con una versión del golden y tabla con otra.
8. **Precision@k** con una sola ancla vale como mucho 1/k; nDCG apenas aporta sobre MRR [17 §3.7](17_repo_generative_ai.md).
9. **Buen recall no es buena respuesta**: el retrieval se evalúa aparte del acierto extremo a extremo [slides RAG · p.46].

**"Qué no funcionó"** (R15): un arreglo razonable que no mueve recall@5 también es un resultado [enunciado · §5]. Conviene comprobarlo y
contarlo en k/n en estos casos: BM25 sin reescritura con preguntas en español (hipótesis: no mueve nada hasta el paso 3); un filtro que no
aporta porque el techo ya era alto; la reescritura que empeora alguna pregunta (ganadas y perdidas por `id` entre `rankings_2_bm25` y
`rankings_3_reescritura`); y la distancia entre `d_rw_oraculo` y el paso 3, que es lo que se pierde por filtros mal extraídos. Se registra en
la tabla de [13](13_skill_medicion_informe_presentacion.md).

## Checklist de hecho

- [ ] **R08** · Configuración de la escalera (D09) commiteada **antes** de la primera medida; `anclas_no_indexables` = 0 con el índice entregado.
- [ ] **R08** · `rankings_{0_denso,1_filtro,2_bm25,3_reescritura}.jsonl` guardados (top-20 por pregunta); `escalera.md` con recall@1/3/5/10
      en k/n, MRR@10, ms y coste de la reescritura, desglose por item con el aleatorio, techos y filtros.
- [ ] **R08** · Paso 1 con filtros oráculo **y** % de filtros ok/ausente/erróneo de `reescribir()` y de las `search_filings` del agente.
- [ ] **R08** · BM25 con IDF global, `get_batch_scores` sobre tokens y sin los score 0; RRF k=60; `buscar_v2` con `PASO0` reproduce `buscar()`.
- [ ] **R08** · `reescribir()` con `ToolStrategy(Busqueda)`, `tools=[]` y la instancia a `temperature=0`; caché en `resultados/cache/`.
- [ ] **R11** · recall@5 del baseline = paso 0 y del final = paso 3 (filtros del LLM), en k/n, listos para [13](13_skill_medicion_informe_presentacion.md).
- [ ] **R12** · La escalera se regenera desde los ficheros y la caché, sin llamadas nuevas al LLM.
- [ ] `search_filings` final envuelve `buscar_v2` sin cambiar la firma; un test comprueba que su docstring lleva las reglas de `INSTRUCCIONES_BUSQUEDA`.
- [ ] Anotado qué arreglo no movió la métrica, con su coste (R15). Revisado tras la sesión del 17.

## Fuentes

- [enunciado · §3, §4.3, §4.4, §5]: índice entregado, anclas de texto, R08 y "qué no funcionó".
- [01 R08, §4, §5](01_requisitos_y_contratos.md): stack, prefijo BGE, trampas 1, 4, 6 y 7.
- [miax_s1 · _indice(), buscar(), formatear_fragmentos()]: carga, búsqueda exacta con post-filtro y formato de salida.
- [slides RAG · p.36–37, 42, 44, 46] vía nota A5 (escalera y snippets 3, 4 y 8); [slides Tuning · p.55] vía [14 §7](14_clase_pistas_del_profesor.md).
- [transcripcion_10sep · 02:26, 02:31] vía [14 §2](14_clase_pistas_del_profesor.md); [notebook S1 · celda 13].
- [16 §3.1, §3.2, §3.5](16_repo_transformers_labs.md); [17 §3.7](17_repo_generative_ai.md) (hybrid-search · celdas 55 y 59; clearbox · celdas 31–35 y 41);
  notas B2, C1 y D12 (S1–S4 y la tabla de diagnósticos por paso); A34 · snippet 1.
- [api_stack · rank_bm25.BM25Okapi, create_agent, structured_output.ToolStrategy]; `get_usage_metadata_callback` (venv).
- [perfil_dataset · chunks.jsonl, indice/MANIFEST, LEEME] y V5/V6 del mapa (offsets y solape, calculados sobre los datos).
- Pruebas propias en el venv del stack (índice y codificador falsos, modelo falso): pre-filtro = post-filtro con búsqueda exacta,
  `get_batch_scores`, score 0, RRF y empates, `buscar_v2` ≡ `buscar()`, subconsultas por FY, `reescribir()` con `tools=[]`, métricas,
  `anclas_no_indexables`, escalera completa y validación de tipos de `@tool` dentro de `create_agent`.
