# Skill: medir coste y latencia, tabla baseline vs final, informe y presentación

> Requisitos: R11, R12, R13, R15 (y R10, R14) · Lee antes: [06_teoria_evaluacion_llms.md](06_teoria_evaluacion_llms.md) §9–§11,
> [08_skill_agente_salida_estructurada.md](08_skill_agente_salida_estructurada.md) §7 (`ejecutar()`), [12_skill_evaluadores.md](12_skill_evaluadores.md)
> §7–§8 y §11 (`evaluar()`, `puntuar()`, `resumen.json`), [11_skill_mejora_retrieval.md](11_skill_mejora_retrieval.md) §10 (escalera)

> Fuentes: [enunciado · Datos básicos, §2, §5, §6]; [01 §1, §4, R10–R15]; [notebook S1 · celdas 9, 27, 33]; [transcripcion_10sep · 00:08,
> 00:26–00:28, 02:24–02:31]; [slides RAG · p.40, p.45, p.50]; [slides Tuning · p.54–55]; [slides agenda · p.12]; `miax_s1.py` (`_indice()`, `buscar()`);
> docs 08–12 y 14–17; notas A1, A5, A6, B2, C1, C2, D3 y D12; decisiones D16–D21, D24 y D25 y contradicciones C01, C28 y C29 del mapa de cobertura.

**v1.0 · 12-sep-2026.** Del arnés de medida a la tabla R11, el informe PDF y los 8 minutos del día 24. La medida por pregunta ya la hace
`ejecutar()` ([08 §7](08_skill_agente_salida_estructurada.md)) y la agregación, `puntuar()` ([12 §8](12_skill_evaluadores.md)). Aquí va lo que falta
(precios, calentamiento y el recall de la tabla), cómo congelar el baseline, las tablas generadas desde los ficheros, el protocolo de las
ciegas y la entrega. Marcas: **(probado)** = ejecutado en el venv del stack con ficheros de resultados sintéticos, sin red ni LLM;
**(compila)** = solo `py_compile`, porque necesita faiss y bge; ⚠️ = sin verificar. Módulos y ficheros: **SUGERENCIA**.

## 1. Qué se entrega y de dónde sale cada número

| Entregable | Req. | Sale de | Lo genera |
| --- | --- | --- | --- |
| Tabla baseline frente a final | R11 | `resultados/{baseline_golden,final_golden}/` (`resumen.json`, `predicciones.jsonl`) + `precios.json` | `informe.py` (§5) |
| Escalera de retrieval | R08, R11 | `resultados/retrieval/escalera.csv` | `metricas_retrieval.py` ([11 §8](11_skill_mejora_retrieval.md)) |
| Tablas secundarias | R14, R15 | `puntuaciones.jsonl` y `resumen.json` de cada etiqueta, `experimentos.csv` | `informe.py` (§6–§7) |
| Resultados regenerables | R12 | etiquetas git `baseline-v1` y `final-v1` con sus ficheros | §3–§4 |
| Ciegas, PDF y presentación | R15 | todo lo anterior + `final_ciegas` | §8–§9 |
| Repo sin claves que corre en un clon limpio | R10, R13 | — | §10 |

**Fechas (C01).** Se entrega el **23-sep a las 23:59**: repo + PDF por el aula virtual. El 24 son las ciegas y la presentación
[enunciado · Datos básicos]. En clase se dijo "se entrega el 24" [transcripcion_10sep · 00:08], pero manda el enunciado [01 §6].

## 2. Coste, latencia y llamadas (D16–D18)

El arnés ya lo mide. No se reimplementa:

| Columna R11 | Cómo se mide | Incluye | No incluye |
| --- | --- | --- | --- |
| USD/pregunta | `get_usage_metadata_callback()` alrededor de `invoke`; Σ tokens × precio buscado por prefijo de `model_name` (`usd()`, [08 §7](08_skill_agente_salida_estructurada.md)) | bucle, reintentos de R05, LLM dentro de una tool | juez ([12 §6](12_skill_evaluadores.md)) y reescritura aislada de la escalera ([11 §7](11_skill_mejora_retrieval.md)) |
| Latencia media y mediana (s) | `perf_counter` alrededor de `invoke`, tras `calentar()`; preguntas en secuencia y siempre en el mismo orden | bucle completo y R05 | carga del índice, juez, `top20_sistema()` |
| Llamadas/pregunta | `n_llamadas`: `tool_calls` de la lista blanca, `list_available` incluida, contando repetidas y bloqueadas | — | la tool sintética `RespuestaFinanciera` |
| (diagnóstico) | `llamadas_modelo`, `uso_mensajes`, `tokens_fuera_del_bucle`, `usd_openrouter`, `cache_read` | contraste | — |

- **Callback y no la suma de `messages`**: el callback también ve las llamadas al LLM fuera del bucle, y la diferencia queda en
  `tokens_fuera_del_bucle` [16 §3.6](16_repo_transformers_labs.md) (probado). `get_num_tokens()` no sirve: cuenta con el tokenizador de GPT-2
  [14 §3](14_clase_pistas_del_profesor.md) (venv).
- Si no se descuenta `cache_read`, el coste es una **cota superior**. Si llega `usd_openrouter`, sirve de contraste y no entra en la tabla ⚠️.
- La latencia depende de la carga de OpenRouter. Por eso la repetición del baseline se hace **el mismo día** que la ejecución final (§4).
  Las slides fijan como objetivo < 300 ms de retrieval y 2–3 s de extremo a extremo [slides RAG · p.45]. Con varias vueltas del LLM lo
  segundo no es realista: se reporta lo que salga [06 §11](06_teoria_evaluacion_llms.md).

`evaluar()` llama a `calentar()` y a `top20_sistema()` ([12 §8](12_skill_evaluadores.md)), y `usd()` necesita `PRECIOS`. Faltan estas tres
piezas **(compila)**:

```python
# agente10k/config.py (continúa, SUGERENCIA) · precios fechados (D24)
import json
import os
from pathlib import Path

RUTA_PRECIOS = Path(os.environ.get("AGENTE10K_PRECIOS", "resultados/precios.json"))

def cargar_precios(ruta: Path = RUTA_PRECIOS) -> dict:
    """{'google/gemini-3.8-flash': (0.75, 3.75), ...} en USD/M (entrada, salida). Sin fichero, error: nunca un precio por defecto."""
    return {m: tuple(p) for m, p in json.loads(ruta.read_text(encoding="utf-8"))["usd_por_millon"].items()}

PRECIOS = cargar_precios()                                        # el que usa usd() dentro de ejecutar() (08 §7)

# agente10k/retrieval.py (continúa, SUGERENCIA) · calentamiento (D17) y recall@k aislado de la tabla (D08, D09)
import time
from functools import lru_cache
# from agente10k import miax_s1                                   -> buscar() del notebook: el retrieval del baseline (D21)
# from agente10k.config import SISTEMA, MODELO_ID, crear_modelo   -> 08 §2 y 12 §8
# from agente10k.metricas_retrieval import RUTA_CACHE             -> 11 §8

def calentar() -> float:
    """FAISS, bge (~130 MB la primera vez) y BM25 en memoria sin llamar al LLM. Sus segundos no cuentan en la latencia."""
    t0 = time.perf_counter()
    if SISTEMA == "baseline":
        miax_s1.buscar("warm-up", k=1)                            # carga _indice(), que es lo que usa la search_filings del notebook
    else:
        r = recursos()
        r["emb"].encode([PREFIJO + "warm-up"], normalize_embeddings=True, convert_to_numpy=True)
        r["bm25"].get_scores(tokenizar("revenue"))
    return time.perf_counter() - t0

@lru_cache(maxsize=1)
def reescritor():
    return crear_reescritor(crear_modelo())                       # la misma instancia a temperature=0 (D01)

def top20_sistema(pregunta: str) -> list[dict]:
    """El top-20 que evaluar() guarda en rankings.jsonl: paso 0 en el baseline, paso 3 con los filtros del LLM en el final."""
    if SISTEMA == "baseline":
        return miax_s1.buscar(pregunta, k=20)                     # ≡ buscar_v2(..., cfg=PASO0) [11 §3]
    cache = cargar_cache(RUTA_CACHE)                              # la caché de la escalera: sin llamadas nuevas
    rw = reescribir(pregunta, reescritor(), cache, MODELO_ID)
    guardar_cache(RUTA_CACHE, cache)
    return [recursos()["filas"][i] for i in buscar_reescrita(rw["busqueda"], k=20)]
```

`resultados/precios.json` con los precios de la celda 9 y su fecha [notebook S1 · celda 9]:

```json
{"fecha_revision": "2026-09-02", "fuente": "https://openrouter.ai/api/v1/models (notebook S1 · celda 9)",
 "unidad": "USD por millón de tokens [entrada, salida]",
 "usd_por_millon": {"google/gemini-3.8-flash": [0.75, 3.75], "google/gemini-3.5-flash-lite": [0.30, 2.50],
                    "anthropic/claude-opus-5": [5.00, 25.00], "anthropic/claude-fable-5.1": [10.00, 50.00]},
 "historial": []}
```

- **Re-precio sin volver a ejecutar.** Cada fila de `predicciones.jsonl` guarda `uso` (tokens por modelo), así que `informe.py` recalcula el
  USD de **todas** las etiquetas con el `precios.json` vigente. Aunque el baseline se ejecute el 16 y el final el 22, los dos se comparan con
  la misma tabla de precios. El `usd_medio` de cada `resumen.json` usa los precios del día de la ejecución, así que manda el de `informe.py`.
- **22-sep (D24):** se revisan los precios en la misma fuente ("REVISAR LA VÍSPERA: OpenRouter cambia precios sin avisar" [notebook S1 · celda 9]).
  Si cambian, la entrada vieja pasa a `historial`, se actualiza `usd_por_millon` y se regeneran las tablas. ⚠️ Comprobad la unidad de la API:
  si da el precio por token, hay que multiplicar por 10⁶.

## 3. Congelar el baseline (R12, D21)

"Hay que guardar el baseline etiquetado antes de empezar a mejorarlo: es media tabla del informe" [enunciado · §5]. El baseline es la versión
del profesor (D21, [08 §1](08_skill_agente_salida_estructurada.md)): las tools del notebook con su cuerpo tal cual (BPA redondeado incluido),
`list_available` mínima, los docstrings y el `SYSTEM` de la celda 21 y `create_agent` sin middleware. Solo cambian el modelo (una instancia a
`temperature=0`) y el arnés. Todo lo demás es mejora medida y va al registro de §7.

Pasos, antes del 17-sep: esa sesión empieza ejecutando cada baseline contra cinco preguntas duras [14 §1](14_clase_pistas_del_profesor.md).

1. Validar `golden/golden_propio.jsonl` y `golden/golden_huecos.jsonl` y hacer commit **antes** de ejecutar ([10 §1](10_skill_golden_set.md)).
2. Poner `SISTEMA = "baseline"` en `config.py`, con `precios.json` a fecha del 2-sep y los tests en verde. Hacer commit: se ejecuta con el
   árbol limpio (`git status --porcelain` vacío), así el `commit` que guarda cada fila es el del código ejecutado.
3. Ejecutar. La etiqueta se pasa explícita: sin ella, el *stem* del fichero daría `baseline_golden_propio`, que `generar()` (§6) no busca
   (solo avisa de que falta `baseline_golden`). El recall@5 del baseline (paso 0)
   lo calcula `evaluar()` en `rankings.jsonl`; la escalera completa se mide después ([11 §8](11_skill_mejora_retrieval.md)).

```bash
python -m agente10k golden/golden_propio.jsonl baseline_golden     # D19
python -m agente10k golden/golden_huecos.jsonl baseline_huecos     # el "antes" de R14 (celda 23)
```

4. Revisar la `tasa_fallo` del resumen. Si hay errores de red o de clave (400/401 [14 §4](14_clase_pistas_del_profesor.md)), se repite **la
   tanda entera** (nunca preguntas sueltas) y se anota. Un fallo del agente (bucle, *fallback*) no se repite: forma parte del baseline.
5. Congelar. `baseline-v1` es el commit que solo añade los resultados al código ejecutado:

```bash
git add resultados/baseline_golden resultados/baseline_huecos resultados/cache    # cache: veredictos del juez
git commit -m "Baseline congelado: golden propio y huecos"
git tag -a baseline-v1 -m "Baseline del profesor (D21): gemini-3.8-flash, temperature=0"
git push origin main baseline-v1
```

- A partir de aquí, `resultados/baseline_*` **no se sobrescribe**. Si cambian los evaluadores, se vuelve a puntuar con
  `puntuar("baseline_golden")` ([12 §8](12_skill_evaluadores.md)), con el juez desde la caché.
- **Regenerar el baseline** (R12) y medir su ruido: se ejecuta desde su etiqueta en otra carpeta, sin tocar `main`. `data/` no se versiona
  [02 §8](02_datos_corpus_y_xbrl.md), así que se apunta al corpus y a los resultados del repo principal (en PowerShell: `$env:AGENTE10K_CORPUS = "…"`):

```bash
git worktree add ../base-v1 baseline-v1 && cd ../base-v1
AGENTE10K_CORPUS=../10k-financial-agent/data/corpus AGENTE10K_RESULTADOS=../10k-financial-agent/resultados \
  python -m agente10k golden/golden_propio.jsonl baseline_golden_r2
```

## 4. Ejecución final y repeticiones

1. Congelar en un commit la configuración del final (prompt, docstrings, `CONFIG` de retrieval y pila de middleware) con `SISTEMA = "final"`.
   Cada mejora tiene ya su fila en `experimentos.csv` (§7).
2. El 22-sep, revisar los precios (§2) y ejecutar todo **el mismo día**:

```bash
python -m agente10k golden/golden_propio.jsonl final_golden
python -m agente10k golden/golden_huecos.jsonl final_huecos
python -m agente10k golden/golden_set.jsonl final_oficial       # solo si llega el oficial (C28), + baseline_oficial desde ../base-v1
#   en ../base-v1 (como en §3): baseline_golden_r2              # ruido, y latencia comparable con la del final
python -m agente10k golden/golden_propio.jsonl final_golden_r2  # opcional, si hay saldo
python -m agente10k.informe                                     # todas las tablas, desde los ficheros (§5–§7)
```

3. **Las repeticiones estiman el ruido y no se promedian** [06 §9](06_teoria_evaluacion_llms.md). En la tabla van la ejecución congelada del
   baseline y la primera del final. `temperature=0` no garantiza determinismo en OpenRouter y `seed` no está verificado (D01) ⚠️.
4. **Saldo.** El profesor habla de "10, 20 céntimos" por pregunta o por sesión [transcripcion_10sep · 00:28]. La campaña completa son
   ~110 invocaciones más el juez, así que conviene mirar el saldo antes. El USD real sale del primer `resumen.json` ⚠️.
5. `final-v1` se etiqueta **después** del ensayo en clon limpio de §10. Es el commit que se ejecuta el 24.

## 5. La tabla R11, generada por código

El enunciado pide aciertos por familia, recall@k, coste medio por pregunta, latencia media y llamadas por pregunta. El mejor valor va
remarcado, y el coste y la latencia son **columnas**, no una nota al pie [enunciado · §5]. Se añaden micro, macro y la mediana de latencia
(D14, D17). Todo en Python puro, sin pandas ni `tabulate` **(probado)**:

```python
# agente10k/informe.py (SUGERENCIA) · python -m agente10k.informe  -> resultados/tablas/*.md y *.csv
import csv
import json
import math
import statistics
from collections import Counter
# from agente10k.api import RESULTADOS, usd                           -> 12 §8 y 08 §7
# from agente10k.config import RUTA_PRECIOS, cargar_precios           -> §2
# from agente10k.evaluadores import enrutado, metricas_abstencion     -> 12 §4 y §7 (17 §3.9)
FAM = {"numerica": "Numérica", "extractiva": "Extractiva", "comparativa": "Comparativa"}
MEJOR = {**dict.fromkeys(FAM.values(), max), "Micro": max, "Macro": max, "recall@5": max, "USD/pregunta": min,
         "Latencia media (s)": min, "Latencia mediana (s)": min, "Llamadas/pregunta": min}
COLS_R11 = ["Sistema", *MEJOR]
pct = lambda v: "—" if v is None else f"{v:.0%}".replace("%", " %")
existe = lambda etq: (RESULTADOS / etq / "resumen.json").is_file()

def leer(etq: str) -> tuple[dict, list[dict], list[dict]]:
    """resumen, predicciones y puntuaciones de una etiqueta (D19)."""
    d = RESULTADOS / etq
    jl = lambda n: [json.loads(x) for x in (d / n).read_text(encoding="utf-8").splitlines() if x.strip()]
    return json.loads((d / "resumen.json").read_text(encoding="utf-8")), jl("predicciones.jsonl"), jl("puntuaciones.jsonl")

def ratio(v) -> float | None:                                  # '7/9' -> 0.78; '—' -> None
    if isinstance(v, str) and "/" in v:
        k, n = map(int, v.split("/"))
        return k / n if n else None
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None

def micro_kn(familias: dict) -> str:
    kn = [tuple(map(int, v.split("/"))) for v in familias.values() if isinstance(v, str) and "/" in v]
    return f"{sum(k for k, _ in kn)}/{sum(n for _, n in kn)}" if kn else "—"

def fmt(col: str, v) -> str:
    if v is None or v == "—":
        return "—"
    if col == "Micro":
        return f"{pct(ratio(v))} ({v})"
    if col == "Macro":
        return pct(v)
    if isinstance(v, (str, int)):
        return str(v)
    return (f"{v:.4f}" if col.startswith("USD") else f"{v:.1f}").replace(".", ",")

def markdown(filas: list[dict], cols: list[str], mejor: dict = MEJOR) -> str:
    """Mejor valor por columna en negrita; en empate, todos; con menos de dos valores, ninguno."""
    b = set()
    for col, fn in mejor.items():
        vals = [(i, ratio(f.get(col))) for i, f in enumerate(filas) if ratio(f.get(col)) is not None]
        if len(vals) > 1:
            m = fn(v for _, v in vals)
            b |= {(i, col) for i, v in vals if math.isclose(v, m, rel_tol=1e-9, abs_tol=1e-12)}
    celda = lambda i, c, v: f"**{fmt(c, v)}**" if (i, c) in b else fmt(c, v)
    return "\n".join(["| " + " | ".join(cols) + " |", "|" + " --- |" * len(cols)]
                     + ["| " + " | ".join(celda(i, c, f.get(c)) for c in cols) + " |" for i, f in enumerate(filas)])

def fila_r11(nombre: str, etq: str, precios: dict) -> dict:
    r, pred, _ = leer(etq)
    coste = [usd(f["uso"], precios) for f in pred if "uso" in f]   # re-precio con el precios.json vigente (§2); sin 'uso' = no ejecutó
    return {"Sistema": nombre, **{FAM[f]: r["familias"].get(f, "—") for f in FAM}, "Micro": micro_kn(r["familias"]),
            "Macro": r.get("macro"), "recall@5": r.get("recall@5", "—"), "USD/pregunta": statistics.fmean(coste) if coste else None,
            "Latencia media (s)": r.get("latencia_media_s"), "Latencia mediana (s)": r.get("latencia_mediana_s"),
            "Llamadas/pregunta": r.get("llamadas_media"), "_meta": r}

def aviso_recall(fila: dict, paso: str) -> str:
    """El recall@5 de R11 es el del paso de la escalera que usa el sistema (11 §1). Si no cuadra, algo cambió entre medidas."""
    ruta = RESULTADOS / "retrieval" / "escalera.csv"
    if not ruta.is_file() or "/" not in str(fila["recall@5"]):
        return ""
    with open(ruta, encoding="utf-8") as fh:
        e = {r["paso"]: r for r in csv.DictReader(fh)}.get(paso)
    ok = e is not None and f"{e['hits@5']}/{e['n']}" == fila["recall@5"]
    return "" if ok else f" ⚠️ recall@5 ≠ escalera {paso}."

def tabla_r11(bloques: dict, precios: dict, fecha_precios: str) -> tuple[str, list[dict]]:
    md, todas = [], []
    for titulo, sistemas in bloques.items():
        filas = [fila_r11(n, e, precios) for n, e in sistemas if existe(e)]
        if not filas:
            continue
        paso = lambda f: "0_denso" if f["Sistema"].startswith("Baseline") else "3_reescritura"
        notas = [f"{f['Sistema']}: {f['_meta'].get('modelo')} @ {f['_meta'].get('commit')} ({f['_meta'].get('fecha')}); fallos "
                 f"{pct(f['_meta'].get('tasa_fallo'))}; juez aparte {fmt('USD', (f['_meta'].get('juez') or {}).get('usd'))} USD."
                 + (aviso_recall(f, paso(f)) if titulo == "Golden propio" else "") for f in filas]   # la escalera es del propio
        md.append(f"**{titulo}**\n\n{markdown(filas, COLS_R11)}\n\n" + "\n".join(f"- {x}" for x in notas)
                  + f"\n- Precios de {fecha_precios}. Cifra: USD ±0,5 % relativo, BPA ±0,005. recall@5 aislado: paso 0 (baseline) y"
                    " paso 3 con filtros del LLM (final).")
        todas += [{"bloque": titulo, **{c: f[c] for c in COLS_R11}} for f in filas]
    return "\n\n".join(md), todas
```

Así queda (plantilla; los valores salen del código):

| Sistema | Numérica | Extractiva | Comparativa | Micro | Macro | recall@5 | USD/pregunta | Latencia media (s) | Latencia mediana (s) | Llamadas/pregunta |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Baseline | a/6 | b/6 | c/8 | x % (k/20) | y % | r/14 | 0,0xxx | xx,x | xx,x | x,x |
| Final | … | … | … | … | … | … | … | … | … | … |

- **Siempre k/n.** Una familia vacía se muestra como "—" y no entra en la macro [12 §7](12_skill_evaluadores.md). Cada pregunta vale 5 pp y
  cada ancla, ≈ 7 pp [06 §9](06_teoria_evaluacion_llms.md).
- **Negrita por bloque.** El golden oficial (C28) va en un bloque aparte con su propia negrita: la tabla del enunciado es la del golden
  propio [enunciado · §5]. Una llamada menos solo es mejor con aciertos parecidos: eso se dice en la lectura [06 §11](06_teoria_evaluacion_llms.md).
- **Los huecos no van en esta tabla:** están en `final_huecos` y tienen su propia tabla de abstención (§6, D11). El coste del juez va en la
  nota de cada sistema, fuera de la columna (D16).
- **Lectura para el PDF (R15)**, en tres frases con números: "El final acierta k/20 frente a k'/20 (+X pp: G ganadas y P perdidas; al repetir
  el baseline cambian R). El recall@5 pasa de a/14 a b/14. Cuesta C USD por pregunta (×m) y tarda L s (…), con N llamadas; lo que más aportó
  fue …, y … no movió nada". Así se defiende una mejora con datos, como "hemos gastado un 30 % menos de tokens" [transcripcion_10sep · 02:24].

## 6. Tablas secundarias

Van en el anexo del PDF y responden a "¿mejoró de verdad y qué costó?" [enunciado · §5] **(probado)**:

```python
# agente10k/informe.py (continúa)
def p_signo(g: int, p: int) -> float:
    """Test de signo exacto bilateral (= McNemar exacto) sobre las discordantes. Propuesta propia (06 §9): se informa, no se presume."""
    n = g + p
    return 1.0 if n == 0 else min(1.0, 2 * sum(math.comb(n, i) for i in range(min(g, p) + 1)) / 2 ** n)

def ganadas_perdidas(antes: str, despues: str) -> dict:
    """Pareado por id. Las dos etiquetas tienen que estar puntuadas con el MISMO evaluador (antes, puntuar())."""
    a, d = ({x["id"]: x.get("acierto") for x in leer(e)[2]} for e in (antes, despues))
    ids = [i for i in a if a[i] is not None and d.get(i) is not None]
    g, p = [i for i in ids if d[i] and not a[i]], [i for i in ids if a[i] and not d[i]]
    return {"Comparación": f"{antes} → {despues}", "n": len(ids), "Ganadas": len(g), "Perdidas": len(p),
            "p (signo)": f"{p_signo(len(g), len(p)):.2f}".replace(".", ","), "Ids ganadas": " ".join(g), "Ids perdidas": " ".join(p)}

def ruido(etq: str, rep: str) -> dict:
    """Dos ejecuciones sin cambiar nada: ¿cuántas preguntas cambian de trayectoria, de respuesta o de acierto?"""
    a, b = ({f["id"]: f for f in leer(e)[1]} for e in (etq, rep))
    firma = lambda f: ([t["name"] for t in f["tool_calls"]], f["respuesta"].get("fuente"), f["respuesta"].get("cifra"))
    gp = ganadas_perdidas(etq, rep)
    return {"Repetición": f"{etq} vs {rep}", "Idénticas": f"{sum(firma(a[i]) == firma(b[i]) for i in a if i in b)}/{gp['n']}",
            "Aciertos que cambian": gp["Ganadas"] + gp["Perdidas"]}

def causa(s: dict) -> str:
    """Primera causa de fallo de una fila de puntuaciones.jsonl, de lo más grave a lo más fino (taxonomía propia)."""
    if s.get("acierto") is not False:
        return "acierto" if s.get("acierto") else "no evaluable"
    if err := s.get("error") or s.get("error_puntuar"):
        return "error: " + str(err).split(":")[0]
    if s.get("abstencion_indebida"):
        return "abstención indebida"
    if s.get("familia") == "hueco" and not (s.get("abstiene") and s.get("sin_cifra")):
        return "hueco no declarado"
    if s.get("c") is False:
        return "herramienta no usada" if (s.get("c_recall") or 0) < 1 else "argumentos de get_xbrl_fact"
    if s.get("b") is False:
        return "escala" if "error_escala" in str(s.get("b_motivo")) else "cifra"
    if s.get("a") is False:
        return ("sin cita" if not s.get("a_cita") else "juez sin parseo" if s.get("juez_fallo") else
                "cita inexistente" if not s.get("a_existe") else "cita no vista" if not s.get("a_vista") else "cita no respalda")
    return "respuesta incorrecta" if s.get("correcta_ok") is False else "otro"

def fila_abstencion(nombre: str, golden: str, huecos: str) -> dict:
    """R14 en las dos direcciones (D11) y el punto riesgo-cobertura del sistema (17 §3.9)."""
    pg, ph = leer(golden)[2], leer(huecos)[2] if existe(huecos) else []
    dato, hh = [x for x in pg if x.get("hay_dato")], [x for x in ph if x.get("familia") == "hueco"]
    m = metricas_abstencion([x for x in pg + ph if x.get("acierto") is not None and "abstiene" in x])
    r05 = [x.get("r05") or {} for x in pg + ph]
    return {"Sistema": nombre, "Abst. correcta (huecos)": f"{sum(bool(x.get('abstiene')) for x in hh)}/{len(hh)}",
            "Abst. indebida (con dato)": f"{sum(bool(x.get('abstencion_indebida')) for x in dato)}/{len(dato)}",
            "Cobertura": pct(m["cobertura"]), "Acierto condicionado": pct(m["acierto_condicionado"]),
            "Alucinación": pct(m["tasa_alucinacion"]), "Score t=0,75": f"{m['score_t0.75']:.2f}".replace(".", ","),
            "R05 reintentos / degradadas": f"{sum(x.get('reintentos', 0) for x in r05)} / {sum(bool(x.get('degradada')) for x in r05)}"}

def fila_coste(nombre: str, etq: str, precios: dict) -> dict:
    r, pred, punt = leer(etq)
    pred = [f for f in pred if "uso" in f]                                     # las que llegaron a ejecutarse, como en 12 §8
    tok = lambda k: statistics.fmean(sum(u.get(k, 0) for u in f["uso"].values()) for f in pred)
    total, aciertos = sum(usd(f["uso"], precios) for f in pred), sum(x.get("acierto") is True for x in punt)
    orr = [f["usd_openrouter"] for f in pred if f.get("usd_openrouter")]
    return {"Sistema": nombre, "Tokens entrada/preg.": round(tok("input_tokens")), "Tokens salida/preg.": round(tok("output_tokens")),
            "Fuera del bucle/preg.": round(statistics.fmean(f.get("tokens_fuera_del_bucle") or 0 for f in pred)),
            "USD/acierto": total / aciertos if aciertos else None, "USD OpenRouter/preg.": statistics.fmean(orr) if orr else None,
            "USD juez (total)": (r.get("juez") or {}).get("usd")}

def tabla_ciegas(golden: str, ciegas: str, huecos: str | None = None) -> list[dict]:
    """Delta de las ciegas frente al golden propio (R15), por familia, en k/n y pp."""
    rg, rc = leer(golden)[0]["familias"], leer(ciegas)[0]["familias"]
    ref = {**rg, "hueco": leer(huecos)[0]["familias"].get("hueco", "—")} if huecos and existe(huecos) else rg
    filas = []
    for f in (*FAM, "hueco", "total"):
        g, c = (micro_kn(rg), micro_kn(rc)) if f == "total" else (ref.get(f, "—"), rc.get(f, "—"))
        d = None if ratio(g) is None or ratio(c) is None else round(100 * (ratio(c) - ratio(g)))
        filas.append({"Familia": FAM.get(f, f.capitalize()), "Golden propio": g, "Ciegas": c, "Δ pp": d})
    return filas

def generar() -> None:
    precios, fecha = cargar_precios(), json.loads(RUTA_PRECIOS.read_text(encoding="utf-8"))["fecha_revision"]
    out = RESULTADOS / "tablas"
    out.mkdir(parents=True, exist_ok=True)
    def guardar(nombre: str, filas: list[dict], md: str | None = None) -> None:
        if not filas:
            return
        (out / f"{nombre}.md").write_text((md or markdown(filas, list(filas[0]), mejor={})) + "\n", encoding="utf-8")
        with open(out / f"{nombre}.csv", "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(filas[0]))
            w.writeheader()
            w.writerows(filas)
    if faltan := [e for e in ("baseline_golden", "final_golden", "baseline_huecos", "final_huecos") if not existe(e)]:
        print(f"⚠️ Sin resumen.json para {', '.join(faltan)}: sus filas no salen (¿evaluar() sin etiqueta? 12 §8)")
    sis = [(n, e) for n, e in (("Baseline", "baseline_golden"), ("Final", "final_golden")) if existe(e)]
    md, filas = tabla_r11({"Golden propio": sis, "Golden oficial (C28, fila extra)": [("Baseline", "baseline_oficial"),
                                                                                       ("Final", "final_oficial")]}, precios, fecha)
    guardar("baseline_vs_final", filas, md)
    pares = [(a, b) for a, b in (("baseline_golden", "final_golden"), ("baseline_golden", "baseline_golden_r2"),
                                 ("final_golden", "final_golden_r2")) if existe(a) and existe(b)]
    guardar("ganadas_perdidas", [ganadas_perdidas(a, b) for a, b in pares])
    guardar("ruido", [ruido(a, b) for a, b in pares if a.split("_")[0] == b.split("_")[0]])
    guardar("sensibilidad_tolerancia", [{"Sistema": n, **{k.replace(".", ","): pct(v) for k, v in leer(e)[0]["sensibilidad_micro"].items()}}
                                        for n, e in sis])
    guardar("enrutado", [{"Sistema": n, "Familia": fam or "todas", "Herramienta": h, "TP": c["tp"], "FP": c["fp"], "FN": c["fn"],
                          "P": pct(c["precision"]), "R": pct(c["recall"]), "F1": pct(c["f1"])}
                         for n, e in sis for fam in (None, *FAM)
                         for h, c in sorted(enrutado([f for f in leer(e)[1] if fam in (None, f.get("familia"))]).items())])
    guardar("abstencion", [fila_abstencion(n, e, e.replace("golden", "huecos")) for n, e in sis])
    guardar("coste", [fila_coste(n, e, precios) for n, e in sis])
    cuenta = {n: Counter(causa(x) for x in leer(e)[2]) for n, e in sis + [("Ciegas", "final_ciegas")] if existe(e)}
    guardar("causas", [{"Causa": k, **{n: c.get(k, 0) for n, c in cuenta.items()}} for k in sorted(set().union(*cuenta.values()))]
            if cuenta else [])
    if existe("final_ciegas"):
        guardar("ciegas", tabla_ciegas("final_golden", "final_ciegas", "final_huecos"))
    if (RESULTADOS / "experimentos.csv").is_file():
        with open(RESULTADOS / "experimentos.csv", encoding="utf-8") as fh:
            guardar("que_no_funciono", [x for x in csv.DictReader(fh) if x.get("decision") != "entra"])

if __name__ == "__main__":
    generar()
```

| Fichero en `resultados/tablas/` | Qué enseña | Para qué pregunta |
| --- | --- | --- |
| `ganadas_perdidas` y `ruido` | Preguntas que el final gana y pierde, con su id y el p del test de signo; cuántas cambian al repetir sin tocar nada | "¿mejoró de verdad?": +2 netas pueden ser 2–0 o 6–4 [06 §9](06_teoria_evaluacion_llms.md). Con 5–1 sale p ≈ 0,22: se da la dirección, no se reclama significación (probado) |
| `sensibilidad_tolerancia` | Micro con 0, 0,1, 0,5 y 1 % en USD, re-puntuada sin ejecutar (D06) | "¿por qué 0,5 %?"; de 0,5 a 1 % no debería cambiar nada |
| `enrutado` | P/R/F1 por herramienta, en total y por familia ([12 §4](12_skill_evaluadores.md)) | "¿Cómo enruta entre la exacta y la difusa?" [enunciado · §5] |
| `abstencion` | Abstención correcta en huecos e indebida en las 20, cobertura, alucinación, score con t = 0,75 y R05 | Honestidad (R14). Baseline y final como dos puntos de la curva riesgo-cobertura [17 §3.9](17_repo_generative_ai.md) |
| `coste` | Tokens por pregunta, tokens fuera del bucle, USD/acierto, contraste con OpenRouter y juez | "¿Qué costó?" El USD/acierto (propuesta de [16 §3.6](16_repo_transformers_labs.md)) lee el trade-off [slides RAG · p.40] |
| `causas` | Primera causa de cada fallo, por sistema y en las ciegas | Qué arreglar y, el 24, qué fallos son nuevos (§8) |
| `escalera` | [11 §10](11_skill_mejora_retrieval.md), tal cual | Qué aportó cada arreglo de retrieval |

La carpeta sigue el modelo de hallcheck, que escribe resultados, métricas y un informe por ejecución
[generative-ai · gemini/sample-apps/gemini-hallcheck/src/gemhall/eval.py · l. 25-118]. `generar()` es determinista: ejecutado dos veces, las
tablas no cambian (§10).

## 7. Registro de experimentos: "qué no funcionó" (R15)

"Un arreglo razonable que no movió la métrica es un resultado" [enunciado · §5]. Cada cambio sobre el baseline se apunta **al medirlo**,
no al final, en `resultados/experimentos.csv` (sugerencia; `informe.py` lo lee):

| fecha | commit | cambio | hipótesis | métrica | antes | después | Δ coste / latencia | decision | nota |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| dd-sep | abc1234 | un solo cambio | por qué debería ayudar | recall@5 o micro | k/n | k/n | +x USD / +y s | entra / no entra | etiqueta de resultados |

- **Un cambio por fila**, medido contra la fila anterior con las mismas preguntas y en el mismo orden [11 §2](11_skill_mejora_retrieval.md).
  Un cambio del agente se ejecuta con su propia etiqueta (`python -m agente10k golden/golden_propio.jsonl exp_bm25`) y sus ficheros se
  guardan (R12). Un cambio del evaluador solo se vuelve a puntuar.
- Lo que conviene comprobar y contar en k/n: BM25 sin reescritura, el filtro con el techo ya alto, preguntas perdidas con la reescritura y la
  distancia entre filtros oráculo y del LLM ([11 §12](11_skill_mejora_retrieval.md)); forzar `tool_choice` ([08 §11](08_skill_agente_salida_estructurada.md));
  `sin_repetir` ([09 §3](09_skill_guardrails_middleware_xbrl.md)); listar los huecos en el prompt (experimento de D22); un modelo más barato,
  solo como experimento [14 §2](14_clase_pistas_del_profesor.md).
- Un Δ dentro del ruido de §6 cuenta como "no movió la métrica". Se decide con razones generales, no mirando qué pregunta concreta cambió:
  eso sería iterar contra el golden ([06 §10](06_teoria_evaluacion_llms.md)).

## 8. Protocolo del día 24: las 10 ciegas

Se entregan al empezar la clase y se ejecutan en el aula contra el repo ya entregado; el resultado entra en la presentación
[enunciado · Datos básicos]. Son el hold-out: no se itera contra ellas, y el ganador se prueba "on a blind case"
[generative-ai · tools/llmevalkit/README.md · «Tutorial» paso 5].

**La noche del 23:**
- [ ] Clon limpio de `final-v1` en el portátil que se va a usar, y otro en un segundo portátil: venv instalado, corpus comprobado con
  SHA-256, bge ya en caché (con una ejecución de humo) y `OPENROUTER_API_KEY` en el entorno, nunca en un fichero del repo.
- [ ] Saldo de OpenRouter comprobado. Tiempo estimado: 10 × la latencia media de `final_golden`, más el baseline si se ejecuta.
- [ ] Plan B de red: datos del móvil, porque en Colab se vieron errores 400/401 que un alumno atribuyó a IPs bloqueadas
  [14 §4](14_clase_pistas_del_profesor.md). Plan C: el `demo.ipynb` de §10 en Colab.
- [ ] Worktree de `baseline-v1` preparado (§3) para ejecutar también el baseline sobre las ciegas, si da tiempo.
- [ ] Si las ciegas llegan en otro formato (lista JSON, CSV o texto), un conversor a JSONL ya probado: convertir el fichero no es tocar
  código. ⚠️ Formato desconocido (duda 9 de [14 §8](14_clase_pistas_del_profesor.md)); lo que aguanta `evaluar()`, en [12 §11](12_skill_evaluadores.md).

**En el aula:**

```bash
python -m agente10k ciegas.jsonl final_ciegas          # en el clon de final-v1: imprime el resumen
#   en ../base-v1, si hay tiempo: ... ciegas.jsonl baseline_ciegas   (separa la mejora general de la memoria)
python -m agente10k.informe                            # añade tablas/ciegas.md y la columna "Ciegas" de causas.md
```

Después de ver las preguntas **no se toca nada**: una pregunta que revienta se queda con su *fallback* y su `error` (D04), y eso es un dato.

**Lectura: memoria frente a generalización.** "Si baja, hay que explicar qué parte de la mejora era general y qué parte era memoria del
conjunto con el que se iteró; eso es un hallazgo, no un suspenso" [enunciado · §5].

1. **Granularidad:** cada ciega vale 10 pp. Antes de interpretar una caída de una o dos preguntas, se mira el ruido de §6: si al repetir el
   baseline sin tocar nada ya cambian R aciertos de 20 (R × 5 pp), una diferencia de ese tamaño no demuestra nada.
2. **Por familia**, con `tabla_ciegas()`. Si se ejecutó `baseline_ciegas`, se compara la mejora final − baseline en las ciegas con la del golden:
   si se mantiene, era general; si desaparece, era memoria.
3. **Por causa** (`causas.md`). Las mismas causas que en el golden, con frecuencia parecida, apuntan a una debilidad conocida. Causas nuevas
   (un concepto, un item o un tipo de pregunta que el golden no tenía) apuntan a un hueco de cobertura del golden.
4. **Síntomas de memoria** que hay que revisar con honestidad [06 §10](06_teoria_evaluacion_llms.md): casos del golden dentro de docstrings
   o del prompt; reglas para una pregunta concreta; hiperparámetros ajustados mirando el golden; preguntas escritas con el vocabulario del
   chunk, que inflan BM25. Es el *reward hacking* de las slides de Tuning [slides Tuning · p.54–55].
5. Si las ciegas no traen ancla, no hay recall ("—"). Si no traen `herramienta_esperada`, (c) usa la lista por familia (`c_por_defecto`).
   Las dos cosas se dicen [12 §11](12_skill_evaluadores.md).

## 9. Informe PDF y presentación de 8 minutos (propuesta propia)

Ninguna fuente da estructura ni extensión (hueco 7 del mapa). El 70 % de la nota es la presentación, y "se presentará el pdf entregado en el
aula virtual" [enunciado · §6], así que **el PDF es a la vez informe y soporte de la presentación**: apaisado, una idea por página, 9 páginas
más anexos. Las ciegas no pueden estar dentro, porque el PDF se entrega el 23. Su página va con la tabla vacía y el protocolo, y el 24 se
enseña `resultados/tablas/ciegas.md` en pantalla. ⚠️ Preguntar el 17 si se puede añadir un anexo con las ciegas.

| Pág. | Contenido | Sale de |
| --- | --- | --- |
| 1 | Portada: grupo, URL del repo, commit de `final-v1`, modelo y fecha de los precios | `resumen.json` |
| 2 | Problema y diseño: las 4 tools y su coste (≈40 / ≈2.000 / hasta 34.751 tokens [01 §3]), diagrama del agente y acierto por familia (D14) | [01](01_requisitos_y_contratos.md), [08](08_skill_agente_salida_estructurada.md) |
| 3 | **Tabla R11** + las tres frases de lectura (§5) | `baseline_vs_final.md` |
| 4 | Qué cambió del baseline al final, cada cambio con su efecto; ganadas/perdidas y ruido | `experimentos.csv`, `ganadas_perdidas.md`, `ruido.md` |
| 5 | Retrieval: escalera en k/n, techos y % de filtros bien extraídos | [11 §10](11_skill_mejora_retrieval.md) |
| 6 | Enrutado exacta/difusa y guardrails: P/R/F1 por herramienta, la celda 23 antes y después, R05 con un mensaje real y abstención | `enrutado.md`, `abstencion.md`, [09 §10](09_skill_guardrails_middleware_xbrl.md) |
| 7 | Las 10 ciegas: tabla por familia y causas (vacía en el PDF) | §8 |
| 8 | Qué no funcionó: 2–3 filas con k/n y coste | `que_no_funciono.md` |
| 9 | Limitaciones y conclusión: n = 20, ruido, κ del juez, tolerancias y coste como cota superior | `validacion_juez.md` ([12 §9](12_skill_evaluadores.md)) |
| Anexos | A. Metodología (tolerancias, recall@5, acierto, juez); B. Tablas secundarias; C. Golden (reparto y huecos); D. Cómo reproducir (comandos de §3, §4 y §8) | §6, [10](10_skill_golden_set.md) |

**Guion de 8 minutos**, con tres personas (A, B y C) y ensayado con cronómetro:

| Minuto | Pág. | Qué se cuenta | Quién |
| --- | --- | --- | --- |
| 0:00–0:40 | 1–2 | Tesis: el retrieval es una herramienta más y acertar por el camino equivocado es fallo [enunciado · §1] | A |
| 0:40–2:10 | 3 | Tabla R11: qué mejoró, cuánto (k/n frente al ruido) y a qué coste (USD, s, llamadas) | A |
| 2:10–3:10 | 4–5 | Qué cambió y qué aportó cada cosa; escalera de retrieval (paso 0 → 3, con filtros del LLM) | B |
| 3:10–4:30 | 6 | Cómo enruta y qué guardrail le impide afirmar una cifra que no ha verificado [enunciado · §5] | C |
| 4:30–6:15 | 7 + terminal | Ciegas: resultado, delta por familia y causas; memoria frente a generalización | C |
| 6:15–7:15 | 8 | Qué no funcionó | B |
| 7:15–8:00 | 9 | Una conclusión y las limitaciones; recorrido de 20 s por el repo ("lo vais a tener que presentar, aunque sea brevemente" [transcripcion_10sep · 02:31]) | A |

**Preguntas probables** (con la respuesta en el anexo): ¿mejoró de verdad? → ganadas/perdidas frente al ruido y p del test de signo. ¿Qué
costó? → USD/acierto, latencia y tokens. ¿Por qué un 0,5 %? → D06 y la sensibilidad. ¿Cómo sabéis que el juez acierta? → κ y la matriz de
confusión. ¿El recall usa filtros oráculo? → no: son el techo, y la tabla lleva los del LLM. ¿Y si no llama a `get_xbrl_fact`? → falla (c) y
R05 lo devuelve al modelo.

## 10. Checklist de entrega: clon limpio y claves (D25)

- [ ] `requirements.txt` con los pines de la celda 2 [01 §4](01_requisitos_y_contratos.md), más `pandas` y `pyarrow` fijados. ⚠️ La versión
  está por decidir: la de Colab el día del ensayo; [16](16_repo_transformers_labs.md) se probó con pandas 2.3.3.
- [ ] Corpus: los ZIP en el repo (quitando `data/dataset/*.zip` del `.gitignore`) o el README explica dónde dejarlos. `preparar_corpus()`
  **lanza** una excepción si el SHA-256 no cuadra [02 §8](02_datos_corpus_y_xbrl.md). `AGENTE10K_CORPUS` tiene un valor por defecto relativo
  y no queda ningún `parents[3]` [01 §5, fallo 11]. bge baja la primera vez sin token (hace falta red). Nada de NLTK.
- [ ] Clave: `OPENROUTER_API_KEY` por entorno → Secrets de Colab → `getpass` ([08 §2](08_skill_agente_salida_estructurada.md)).
  `git grep -nE "sk-or-v1-|API_KEY\s*=\s*['\"]"` sale vacío, y `git log -p --all | grep -c "sk-or-v1-"` da 0; los notebooks, sin salidas
  que la muestren. Una clave que llegó a subirse se **revoca** en OpenRouter: borrarla del historial no basta [transcripcion_04sep · 00:36].
- [ ] `resultados/` versionado: `baseline_*`, `final_*`, `exp_*`, `retrieval/`, `tablas/`, `cache/` (reescrituras y juez), `precios.json`
  (revisado el 22-sep) y `experimentos.csv`.
- [ ] Etiquetas `baseline-v1` y `final-v1` en el remoto (`git push origin --tags`) y el repo accesible para el profesor ⚠️ (público o con invitación).
- [ ] **Ensayo en clon limpio antes del 22-sep**, y otra vez con `final-v1` (en Windows, `.venv\Scripts\activate`):

```bash
git clone --branch final-v1 <url-del-repo> clon && cd clon
python -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
python -m pytest -q                                            # sin red ni LLM
python -m agente10k golden/humo.jsonl humo                     # 2 preguntas con la API real (D20)
python -m agente10k.informe && git diff --exit-code resultados/tablas   # las tablas se regeneran idénticas
```

- [ ] Diez "ciegas simuladas", escritas por quien no escribió el golden y con **solo** los campos oficiales (una hueco y otra sin ancla),
  ejecutadas en el clon sin editar nada [12 §11](12_skill_evaluadores.md).
- [ ] C29: el "Run all" de Colab está en la agenda del módulo NLP, no en el enunciado [slides agenda · p.12]. Se cubre con un `demo.ipynb`
  **opcional** que clona, instala, lee la clave de Secrets y llama a `responder()` y a `evaluar("golden/humo.jsonl")`. Se ensaya en un runtime
  nuevo: instalar versiones fijadas puede obligar a reiniciar la sesión, y `getpass` detiene un "Run all" desatendido [A6 · R10] ⚠️.
- [ ] PDF subido al aula virtual **antes del 23-sep a las 23:59** (C01), con la URL del repo y el commit de `final-v1`.

## Checklist de hecho

- [ ] **R11:** `tablas/baseline_vs_final.md` generada por `informe.py`: aciertos k/n por familia, micro y macro, recall@5 (paso 0 y paso 3
  con filtros del LLM, cuadrando con la escalera), USD/pregunta, latencia media y mediana y llamadas/pregunta **como columnas**, mejor valor
  en negrita y juez aparte.
- [ ] **R11:** el USD de todas las etiquetas sale del mismo `precios.json` fechado (revisado el 22-sep) y se recalcula desde `uso`.
- [ ] **R12:** `baseline-v1` con `resultados/baseline_{golden,huecos}` antes de la primera mejora, y `final-v1`. `puntuar()` e `informe.py`
  regeneran todo sin llamar al agente, y el baseline se ha repetido para medir el ruido.
- [ ] **R13:** sin claves en el árbol ni en la historia.
- [ ] **R15:** tablas de ganadas/perdidas, ruido, sensibilidad, enrutado, abstención, coste, causas y qué no funcionó; PDF según §9; guion
  ensayado en ≤ 8 min.
- [ ] **R15:** protocolo de las ciegas ensayado con las diez simuladas, con `tabla_ciegas()` y `causas.md` generadas.
- [ ] **R10:** clon limpio ensayado antes del 22-sep y repetido con `final-v1`.

## Fuentes

- [enunciado · Datos básicos, §1, §2, §5, §6] (`00_enunciado.md`); [01_requisitos_y_contratos.md](01_requisitos_y_contratos.md) §1, §3, §4, §6 y R10–R15.
- [notebook S1 · celdas 9 (precios y `coste()`), 27 (hilo nuevo) y 33 (para el 17)]; `miax_s1.py` · `_indice()` (~130 MB de bge) y `buscar()`.
- [transcripcion_10sep · 00:08 (entrega), 00:26–00:28 (coste y latencia), 02:10–02:12 (400/401), 02:24 ("30 % menos de tokens"), 02:31
  (GitHub y presentarlo)]; [transcripcion_04sep · 00:36] (claves), vía [14](14_clase_pistas_del_profesor.md) §1–§4 y §8.
- [slides RAG · p.40, p.45, p.50] vía nota A5; [slides Tuning · p.54–55] y [slides agenda · p.12] vía nota A6 y [14 §7](14_clase_pistas_del_profesor.md).
- [16 §3.6](16_repo_transformers_labs.md) (callback, micro/macro, ganadas/perdidas); [17 §3.1, §3.6, §3.9](17_repo_generative_ai.md)
  (enrutado, coste por llamada, abstención); [15 §3.6](15_repo_genai_labs.md) (`responder()` con coste y latencia).
- generative-ai · `gemini/sample-apps/gemini-hallcheck/src/gemhall/eval.py` (artefactos por ejecución) y `tools/llmevalkit/README.md` (blind case), vía nota D12 y [06 §10](06_teoria_evaluacion_llms.md).
- [api_stack · create_agent, AIMessage]; `langchain_core.callbacks.get_usage_metadata_callback(name='usage_metadata_callback')` (langchain-core 1.6.1, venv).
- Docs hermanos: [02 §8](02_datos_corpus_y_xbrl.md), [06 §9–§11](06_teoria_evaluacion_llms.md), [08 §2, §7, §10–§11](08_skill_agente_salida_estructurada.md),
  [09 §3, §10](09_skill_guardrails_middleware_xbrl.md), [10 §1](10_skill_golden_set.md), [11 §2–§3, §7–§10, §12](11_skill_mejora_retrieval.md),
  [12 §4, §7–§9, §11](12_skill_evaluadores.md).
- Notas de trabajo (no versionadas): A1 (R11–R12), A5 (R11/R12/R15), A6 ("Run all", *reward hacking*), B2 (R11/R12), C1 (R11), C2 (R11 y
  lectura), D3 (tabla R11 y enrutado), D12 (hallcheck) y el mapa de cobertura (D16–D21, D24, D25; C01, C28, C29; hueco 7).
- Pruebas propias en el venv del stack: `informe.py` completo con ficheros sintéticos de ocho etiquetas, bloque oficial incluido (negrita
  con empates, re-precio, aviso de recall, ganadas/perdidas, test de signo con 5–1 → 0,22, ruido, causas, abstención, coste, ciegas y
  generación determinista).
