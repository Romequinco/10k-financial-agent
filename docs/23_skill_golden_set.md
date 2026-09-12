# Skill: escribir el golden set (20 preguntas)

> Requisitos: R06, R07, R14 (y alimenta R08, R09, R11) · Lee antes: [02_datos_corpus_y_xbrl.md](02_datos_corpus_y_xbrl.md),
> [01_requisitos_y_contratos.md](01_requisitos_y_contratos.md) §3 y §6, [30_clase_pistas_del_profesor.md](30_clase_pistas_del_profesor.md) §5
> · Después: [25_skill_evaluadores.md](25_skill_evaluadores.md), [24_skill_mejora_retrieval.md](24_skill_mejora_retrieval.md)

> Fuentes: [notebook S1 · celdas 22, 30–33], `golden_set_ejemplo.jsonl`, `demo_traza.json`, [enunciado · §4.3, §5, §7],
> [transcripcion_10sep · 02:26–02:31], [33 §3.8–3.9], [32 §3.2] y comprobaciones propias sobre `data/corpus/`.

**v1 · 12-sep-2026.** Cómo escribir las 20 preguntas propias para que pasen `validar()` (el de la celda 32, el oficial) y
`validar_estricto()` (el nuestro), más un fichero aparte de huecos. Marcas: **(datos)** = comprobado sobre `data/corpus/`;
**(probado)** = los snippets de esta skill se ejecutaron contra el corpus real y `golden_set_ejemplo.jsonl`; ⚠️ = sin verificar.
Nombres de ficheros y módulos: SUGERENCIA.

## 0. Para qué sirve y cuándo

- **17-sep:** hay que llegar con el baseline corriendo y las 20 preguntas pasando `validar(..., exigir_20=True)`, con al menos 6
  comparativas [notebook S1 · celda 33]. Un golden que no pasa el validador "no se corrige: se devuelve" [notebook S1 · celda 32].
- **23-sep:** va en el repo y es la base de la tabla baseline frente a final (R11) [enunciado · §5]. Si llega el golden oficial de 20,
  se añade como fila extra; la tabla se hace sobre el propio [01 §6].
- **24-sep:** 10 preguntas ciegas; su delta frente al golden propio mide cuánto de la mejora era memoria del conjunto con el que se
  iteró [enunciado · §5]. Por eso **no se itera contra el golden**: se congela antes del baseline (*reward hacking*, [slides Tuning · p.55]).
- `numerica` mide el guardrail contra XBRL; `extractiva`, retrieval y trazabilidad; `comparativa`, que el agente descomponga y compare
  dos ejercicios: es la familia que justifica tener un agente [notebook S1 · celda 30].

## 1. Proceso

1. **Paseíto por los datos** (1 h): tablas de [02 §4–§6](02_datos_corpus_y_xbrl.md) y la carga de [02 §7](02_datos_corpus_y_xbrl.md)
   [transcripcion_10sep · 02:29].
2. **Reparto de huecos** en la matriz de §3: cada miembro se lleva ~7 preguntas repartidas por familias y empresas.
3. **Elegir el hecho o la frase**: cifras del parquet (§7) y anclas con las herramientas y el script de §6. Nunca de memoria ni de un
   LLM.
4. **Redactar** pregunta y `respuesta_esperada` en español natural, autocontenidas (empresa y "ejercicio fiscal AAAA" explícitos).
5. **Validar**: `validar_estricto()` y después `validar()` (§8), en verde las dos.
6. **Revisión en pareja** (§9) y *commit* del golden **antes** de ejecutar el baseline.

## 2. El esquema, campo a campo

Los 16 campos del contrato van **todos**, aunque sean `null` [enunciado · §7]. Los extra se toleran.

| Campo | Qué exige `validar()` | Convención del grupo |
| --- | --- | --- |
| `id` | Único | `gN-001`…`gN-020` (N = número de grupo); huecos `gN-h001` |
| `pregunta` | — | Español, autocontenida: empresa + "ejercicio fiscal 2025 (FY2025)". No copiar frases del chunk: infla BM25 y el recall [33 §3.8] |
| `familia` | `extractiva`, `numerica` o `comparativa` | — |
| `ticker` | Está en el corpus (igualdad exacta: `GOOGL` sí, `GOOG` no) | Mayúsculas |
| `fiscal_year` | `int(...)` ∈ {2024, 2025} | `int`; en comparativas, **2025** (§4) |
| `respuesta_esperada` | — | Lo que diría una respuesta correcta, con unidad y escala. La usa el juez de corrección ([25](25_skill_evaluadores.md)) |
| `cifra_esperada` | No nula en `numerica` y `comparativa` | Valor del parquet **sin escalar** (`60922000000.0`, `2.97`); `null` en extractivas y huecos |
| `unidad` | — | Literal de XBRL: `"USD"` o `"USD/shares"` |
| `concept_xbrl` | Si tiene valor, existe para (ticker, FY) | Siempre en numéricas y comparativas; regla del revenue de [02 §6](02_datos_corpus_y_xbrl.md) |
| `item_esperado` | — | Item de la sección del ancla: `"1A"`, `"7"`, `"7A"` u `"8"` (texto) |
| `ancla_texto` | No vacía y ≤40 palabras (`split()`) en `extractiva` y `comparativa` | **Una** frase literal, tal cual está en `secciones.jsonl` |
| `ancla_inicio`, `ancla_fin` | — | Offsets de carácter `[inicio, fin)` sobre el `texto` de la sección |
| `chunk_id_esperado` | — | Un chunk que contiene el ancla **entera** (informativo: cambia al re-trocear) |
| `herramienta_esperada` | Lista no vacía | **Solo nombres reales** del contrato (el evaluador de trayectoria del profesor "busca estos nombres" [enunciado · §7]); todos se exigen (AND), sin orden; `list_available` no se pone: es neutra. Las alternativas, en el extra `herramienta_alternativa` (D12) |
| `autor` | — | `"grupo-N"`, sin nombres |
| extra | Se ignoran | `fiscal_year_base`, `cifra_esperada_base`, `ancla_texto_base`, `variacion_esperada` (§4), `hueco` (§5), `origen` (§9), `herramienta_alternativa` (§7: `{"search_filings": ["read_section"]}` = vale cualquiera de las dos) |

**Reglas exactas de `validar()`** [notebook S1 · celda 32]: (1) si falta alguno de los 16 campos anota un solo problema y salta el
resto de esa pregunta; (2) `id` repetido; (3) familia válida; (4) ticker del corpus; (5) FY del corpus; (6) en numéricas y
comparativas, cifra no nula y, si hay concepto, que exista para ese ticker y FY; (7) en extractivas y comparativas, ancla no vacía
de ≤40 palabras; (8) `herramienta_esperada` no vacía; (9) con `exigir_20=True`, exactamente 20 preguntas y ≥6 comparativas.

**Lo que no mira** (y hace `validar_estricto`, §8): que la cifra sea la de XBRL; que el ancla exista literal, sea una frase y quepa
en un chunk; offsets, `item_esperado`, `chunk_id_esperado` y `unidad`; que los nombres de herramienta existan. **Dónde revienta:**
con `fiscal_year: null` (`int(None)`) o un ancla que no sea `str`; y en las comparativas sus mensajes hablan de "extractiva" o
"numérica" [30 §5].

**Offsets, comprobados con ej-002** (MSFT FY2025, Item 1A, 8891–8950). Leyendo solo ese tramo:

```python
import json

with open("data/corpus/secciones.jsonl", encoding="utf-8") as f:
    sec = next(s for s in map(json.loads, f) if (s["ticker"], s["fiscal_year"], s["item"]) == ("MSFT", 2025, "1A"))
tramo = sec["texto"][8891:8950]
print(len(tramo), repr(tramo))       # 59 caracteres: el ancla_texto de ej-002, idéntica
```

Resultado (probado): 59 caracteres, idénticos a `ancla_texto`, y el tramo cae entero en `MSFT-2025-1A-0004` (caracteres 7148–9560),
que es su `chunk_id_esperado`. Los chunks usan la misma convención: `chunk["texto"] == seccion[inicio_car:fin_car]` en los 1.749
(datos) [02 §3](02_datos_corpus_y_xbrl.md).

## 3. Reparto y cobertura

**6 numéricas, 6 extractivas y 8 comparativas**: 14 preguntas con ancla (cada una mueve el recall@k unos 7 puntos) y 14 con cifra.
Propuesta de matriz, con valores del parquet; cambiad lo que queráis mientras se mantenga la cobertura:

| id | Familia | Ticker | FY (base) | Concepto · item del ancla | Qué pone a prueba |
| --- | --- | --- | --- | --- | --- |
| 001 | numerica | NVDA | 2025 | `Revenues` = 130.497 M | FY que cierra en enero; revenue de NVDA |
| 002 | numerica | GOOGL | 2025 | `Revenues` = 402.836 M | GOOGL solo etiqueta `Revenues` en FY2025 |
| 003 | numerica | AAPL | 2024 | `EarningsPerShareDiluted` = 6,08 | Diluido (6,08) frente a básico (6,11) |
| 004 | numerica | NVDA | 2025 | `EarningsPerShareBasic` = 2,97 | El "3" redondeado del baseline |
| 005 | numerica | META | 2024 | `CashAndCashEquivalentsAtCarryingValue` = 43.889 M | Casi igual que su R&D (0,04 %): lo caza la trayectoria |
| 006 | numerica | AMZN | 2024 | `NetCashProvidedByUsedInOperatingActivities` = 115.877 M | AMZN sí tiene datos: abstención indebida |
| 007 | extractiva | MSFT | 2025 | · 1A | Frase sustantiva, no la de tema (lección de ej-002) |
| 008 | extractiva | NVDA | 2024 | · 8 | Item 15 servido como `"8"` |
| 009 | extractiva | AAPL | 2024 | · 7A | Item de 2 chunks: `read_section` sale barata |
| 010 | extractiva | META | 2025 | · 1A | La sección más larga (34.751 tokens) |
| 011 | extractiva | AMZN | 2025 | · 7 | MD&A |
| 012 | extractiva | GOOGL | 2024 | · 8 | Nota de los estados financieros (tablas partidas cerca) |
| 013 | comparativa | NVDA | 2025 (2024) | `EarningsPerShareBasic` 2,97 / 12,05 · 8 | Split 10:1; su ancla solo puede salir del Item 8 |
| 014 | comparativa | NVDA | 2025 (2024) | `Revenues` 130.497 / 60.922 M · 7 | +114,2 %; FY de enero |
| 015 | comparativa | MSFT | 2025 (2024) | `RevenueFromContract…` 281.724 / 245.122 M · 1A | Riesgo nuevo + cifra, el patrón de la celda 22 |
| 016 | comparativa | AAPL | 2025 (2024) | `NetIncomeLoss` 112.010 / 93.736 M · 7 | Cierre en septiembre |
| 017 | comparativa | GOOGL | 2025 (2024) | `Revenues` 402.836 / 350.018 M · 7 | En FY2024 valen los dos conceptos del revenue |
| 018 | comparativa | META | 2025 (2024) | `NetIncomeLoss` 60.458 / 62.360 M · 7 | Baja un 3,0 % mientras el operativo sube un 20,0 % |
| 019 | comparativa | AMZN | 2025 (2024) | `OperatingIncomeLoss` 79.975 / 68.593 M · 7 | AMZN sin `GrossProfit`: comparar lo que sí hay |
| 020 | comparativa | MSFT | 2025 (2024) | `ResearchAndDevelopmentExpense` 32.488 / 29.510 M · 7 | Cierre en junio |

Cobertura que tiene que salir (compruébala con el código de §8): **las 6 empresas** (≥3 preguntas cada una), **los 2 FY** en
numéricas y extractivas, **los 4 items** entre las anclas y **cada trampa** de [02 §6](02_datos_corpus_y_xbrl.md): FY ≠ año de
presentación, concepto del revenue (NVDA, GOOGL), split de NVDA, Item 15 → `"8"`, BPA básico/diluido y pares casi iguales. Los huecos
van aparte (§5). Las variaciones de la tabla son (datos).

## 4. Comparativas

Convención común del grupo (la comparten los evaluadores de [25](25_skill_evaluadores.md) y el esquema de respuesta de
[21](21_skill_agente_salida_estructurada.md)):

- `fiscal_year = 2025` (el FY reciente) y `cifra_esperada` = **nivel** XBRL de FY2025 de `concept_xbrl`, **nunca la variación**.
- `ancla_texto` = frase literal del 10-K de FY2025, a ser posible del Item 7, que explique el cambio o dé la parte cualitativa;
  `item_esperado` = el item de esa frase.
- `herramienta_esperada = ["get_xbrl_fact", "search_filings"]`: una comparativa exige cifra y ancla a la vez [notebook S1 · celda 32].
- Campos extra: `fiscal_year_base = 2024` y `cifra_esperada_base` (XBRL de FY2024, mismo concepto), obligatorios en nuestro golden;
  `ancla_texto_base` y `variacion_esperada` (fracción, p. ej. `0.1493`), opcionales y solo de diagnóstico.
- Si en las ciegas faltan esos campos, los evaluadores toman como base el otro FY de {2024, 2025}.
- El agente responde con `cifra`/`ejercicio` del FY reciente y `cifra_base`/`ejercicio_base` del base
  ([21](21_skill_agente_salida_estructurada.md)).

Por qué así: la celda 30 pide los campos de los dos ejercicios, pero la plantilla y `validar()` solo admiten un `fiscal_year` y una
`cifra_esperada` [notebook S1 · celdas 30, 32; 30 §5]; ej-003 y la traza demo ya usan FY reciente + nivel. **ej-003 no sirve de
modelo** [01 §6]: reutiliza ancla, offsets y `chunk_id` de ej-002 (riesgos de IA, Item 1A) con `item_esperado: "7"`, pregunta
cuánto creció pero guarda el nivel y solo pide `get_xbrl_fact` (datos). `validar_estricto` lo rechaza (probado).

Casos especiales:
- **Split de NVDA (013):** se comparan los valores **reportados** (12,05 y 2,97), sin ajustar, y la respuesta tiene que mencionar el
  split. Las únicas menciones de "stock split" o "ten-for-one" de NVDA están en el Item 8 de FY2025, en un solo chunk (datos,
  recuento): el ancla sale de ahí e `item_esperado = "8"`. No pongáis `variacion_esperada`: el −75 % ingenuo es justo la trampa.
- **"Riesgo nuevo" (015):** comprobad que la frase no está en FY2024 (la traza demo lo da por hecho [demo_traza · pasos 1–2]):
  `normalizar(ancla) not in normalizar(texto_seccion("MSFT", 2024, "1A"))`, con las funciones de §6.
- **GOOGL (017):** `concept_xbrl = "Revenues"`, que existe en los dos FY; en FY2024 vale cualquiera de los dos conceptos (mismo valor).

## 5. Huecos (R14): fuera de los 20

`validar()` exige `cifra_esperada` en `numerica` y ancla en `extractiva` [notebook S1 · celda 32]: una pregunta cuya respuesta es
"no está" no cabe en los 20. Opciones: (a) cifra inventada, que rompe el evaluador de cifra; (b) disfrazarla de extractiva con un ancla
que no la responde; (c) **fichero aparte**. Recomendación: **(c)**.

- `golden/golden_huecos.jsonl` con 3–5 preguntas: AMZN `GrossProfit`, META `GrossProfit` (preguntada como margen bruto), AMZN
  `Liabilities` o `ResearchAndDevelopmentExpense` y, si queréis, una empresa fuera del corpus.
- Formato: `familia = "numerica"`, `cifra_esperada = null`, `unidad = null`, `concept_xbrl` = el concepto que **no** está,
  `herramienta_esperada = ["get_xbrl_fact"]` y el campo extra `"hueco": true`. Para la empresa fuera del corpus,
  además, `"herramienta_alternativa": {"get_xbrl_fact": ["list_available"]}`: basta `list_available` y (c) no mira los argumentos
  de `get_xbrl_fact` fuera de las 6 empresas ([25 §4](25_skill_evaluadores.md)).
- No pasan `validar()` (a propósito), sí `validar_estricto()`; se evalúan con el mismo `evaluar()`, en fila aparte (`final_huecos`).
- Es hueco si `hueco == true`, si es numérica con `cifra_esperada` nula o si el concepto no existe para ese ticker y FY. **Acierto** =
  `fuente == "ninguna"` ∧ `cifra is None` ∧ trayectoria correcta. También se mide la abstención indebida (un "ninguna" con dato),
  que el profesor pidió detectar [transcripcion_10sep · 02:29; 33 §3.9]: por eso la 006 es de AMZN y con dato.
- No se deriva una magnitud no reportada: el margen bruto de META es "no está" [enunciado · §3].

## 6. Anclas: cómo encontrarlas

Criterios: **una** frase literal de ≤40 palabras, la que lleva la información sustantiva y no la de tema (ej-002 ancla la de tema; el
uso indebido está en la siguiente [demo_traza · paso 1]); sin filas de tabla ni saltos de línea; que responda a la pregunta; que quepa
entera en un chunk. Con anclas largas se mide el tamaño de la ventana, no el retrieval [notebook S1 · celda 32]. Hay 126 cortes con
poco solape y el 49 % de los chunks acaba a mitad de frase [02 §3](02_datos_corpus_y_xbrl.md): **comprobadlo siempre**.

Pasos: (1) buscad con `search_filings` (consulta en inglés, filtros de ticker, FY e item) o con `contexto()`, que muestra ventanas
alrededor de un patrón con sus offsets; (2) copiad la frase; (3) `localizar_ancla()` devuelve el texto **literal** de la sección, los
offsets y los chunks que la contienen enteros; (4) pegad esa salida en el JSON.

```python
# SUGERENCIA: golden/utiles_golden.py; cargar_corpus() es la de 02 §7
import json, re

from agente10k.normalizacion import normalizar      # SUGERENCIA: la única normalizar() y su _TRAD (D07; 32 §3.2, 22 §4)

secciones, chunks, xbrl = cargar_corpus()
_VARIANTES = {"'": "['’‘]", '"': '["“”]', "-": "[-–—]"}


def texto_seccion(ticker: str, fy: int, item: str) -> str:
    s = secciones[(secciones["ticker"] == ticker) & (secciones["fiscal_year"] == int(fy)) & (secciones["item"] == item)]
    return s.iloc[0]["texto"] if len(s) else ""


_TXT = dict(zip(chunks["chunk_id"], chunks["texto"]))
texto_chunk = lambda cid: _TXT.get(cid or "", "")       # texto del chunk o "" (etapa 1 de la cita, 25 §5)


def valor_xbrl(ticker: str, fy: int, concepto: str) -> tuple[float, str] | None:   # el contrato de 22 §4
    v = xbrl[(xbrl["ticker"] == ticker) & (xbrl["fiscal_year"] == int(fy)) & (xbrl["concept"] == concepto)]
    return (float(v.iloc[0]["value"]), v.iloc[0]["unit"]) if len(v) else None


def chunks_con(ticker: str, fy: int, item: str, ini: int, fin: int) -> list[str]:
    """chunk_id de los chunks que contienen ENTERO el tramo [ini, fin) de la sección."""
    c = chunks[(chunks["ticker"] == ticker) & (chunks["fiscal_year"] == int(fy)) & (chunks["item"] == item)
               & (chunks["inicio_car"] <= ini) & (chunks["fin_car"] >= fin)]
    return c["chunk_id"].tolist()


def contexto(ticker: str, fy: int, item: str, patron: str, ancho: int = 200, maximo: int = 8) -> None:
    t = texto_seccion(ticker, fy, item)
    for m in list(re.finditer(patron, t, flags=re.I))[:maximo]:
        a, b = max(0, m.start() - ancho), min(len(t), m.end() + ancho)
        print(f"[{a}:{b}]", re.sub(r"\s+", " ", t[a:b]), "\n")


def localizar_ancla(ticker: str, fy: int, item: str, frase: str) -> dict | None:
    """Offsets de `frase` en la sección, tolerando espacios y comillas o guiones tipográficos."""
    t = texto_seccion(ticker, fy, item)
    ini = t.find(frase)
    if ini >= 0:
        fin = ini + len(frase)
    else:
        patron = r"\s+".join("".join(_VARIANTES.get(ch, re.escape(ch)) for ch in pal) for pal in frase.split())
        if not (m := re.search(patron, t)):
            return None
        ini, fin = m.span()
    literal = t[ini:fin]
    ids = chunks_con(ticker, fy, item, ini, fin)
    return {"ancla_texto": literal, "ancla_inicio": ini, "ancla_fin": fin, "chunk_id_esperado": ids[0] if ids else None,
            "palabras": len(literal.split()), "chunks": ids, "salto_de_linea": "\n" in literal,
            "veces_en_seccion": normalizar(t).count(normalizar(literal))}
```

`contexto("NVDA", 2025, "8", r"stock split")` enseña las ventanas del split; `localizar_ancla(...)` con la frase copiada devuelve lo
que va al JSON. Si `chunks` sale vacío, el ancla está partida: elegid otra frase (es la comprobación `anclas_no_indexables` que
[24](24_skill_mejora_retrieval.md) repite con cada troceado nuevo). Si `veces_en_seccion > 1`, es texto repetido y el ancla no discrimina.
Probado con ej-002: offsets 8891–8950 y `MSFT-2025-1A-0004`, también con espacios dobles en la frase copiada.

## 7. Plantillas

En el `.jsonl`, **una línea por pregunta** (`json.dumps(p, ensure_ascii=False)`). Numéricas, con valores reales del parquet
(pasan `validar()`; `validar_estricto()` solo pide cambiar `N` por el número del grupo):

```json
{"id": "gN-001", "pregunta": "¿Cuál fue el revenue de NVIDIA en su ejercicio fiscal 2025 (FY2025)?", "familia": "numerica", "ticker": "NVDA", "fiscal_year": 2025, "respuesta_esperada": "130.497 millones de dólares", "cifra_esperada": 130497000000.0, "unidad": "USD", "concept_xbrl": "Revenues", "item_esperado": null, "ancla_texto": null, "ancla_inicio": null, "ancla_fin": null, "chunk_id_esperado": null, "herramienta_esperada": ["get_xbrl_fact"], "autor": "grupo-N", "origen": "manual"}
{"id": "gN-002", "pregunta": "¿Cuáles fueron los ingresos (revenue) de Alphabet en el ejercicio fiscal 2025?", "familia": "numerica", "ticker": "GOOGL", "fiscal_year": 2025, "respuesta_esperada": "402.836 millones de dólares", "cifra_esperada": 402836000000.0, "unidad": "USD", "concept_xbrl": "Revenues", "item_esperado": null, "ancla_texto": null, "ancla_inicio": null, "ancla_fin": null, "chunk_id_esperado": null, "herramienta_esperada": ["get_xbrl_fact"], "autor": "grupo-N", "origen": "manual"}
{"id": "gN-003", "pregunta": "¿Cuál fue el beneficio por acción diluido de Apple en el ejercicio fiscal 2024?", "familia": "numerica", "ticker": "AAPL", "fiscal_year": 2024, "respuesta_esperada": "6,08 dólares por acción (diluido)", "cifra_esperada": 6.08, "unidad": "USD/shares", "concept_xbrl": "EarningsPerShareDiluted", "item_esperado": null, "ancla_texto": null, "ancla_inicio": null, "ancla_fin": null, "chunk_id_esperado": null, "herramienta_esperada": ["get_xbrl_fact"], "autor": "grupo-N", "origen": "manual"}
{"id": "gN-004", "pregunta": "¿Cuál fue el beneficio por acción básico de NVIDIA en el ejercicio fiscal 2025?", "familia": "numerica", "ticker": "NVDA", "fiscal_year": 2025, "respuesta_esperada": "2,97 dólares por acción (básico)", "cifra_esperada": 2.97, "unidad": "USD/shares", "concept_xbrl": "EarningsPerShareBasic", "item_esperado": null, "ancla_texto": null, "ancla_inicio": null, "ancla_fin": null, "chunk_id_esperado": null, "herramienta_esperada": ["get_xbrl_fact"], "autor": "grupo-N", "origen": "manual"}
{"id": "gN-005", "pregunta": "¿Cuánto efectivo y equivalentes tenía Meta al cierre del ejercicio fiscal 2024?", "familia": "numerica", "ticker": "META", "fiscal_year": 2024, "respuesta_esperada": "43.889 millones de dólares", "cifra_esperada": 43889000000.0, "unidad": "USD", "concept_xbrl": "CashAndCashEquivalentsAtCarryingValue", "item_esperado": null, "ancla_texto": null, "ancla_inicio": null, "ancla_fin": null, "chunk_id_esperado": null, "herramienta_esperada": ["get_xbrl_fact"], "autor": "grupo-N", "origen": "manual"}
{"id": "gN-006", "pregunta": "¿Cuál fue el flujo de caja de las operaciones de Amazon en el ejercicio fiscal 2024?", "familia": "numerica", "ticker": "AMZN", "fiscal_year": 2024, "respuesta_esperada": "115.877 millones de dólares", "cifra_esperada": 115877000000.0, "unidad": "USD", "concept_xbrl": "NetCashProvidedByUsedInOperatingActivities", "item_esperado": null, "ancla_texto": null, "ancla_inicio": null, "ancla_fin": null, "chunk_id_esperado": null, "herramienta_esperada": ["get_xbrl_fact"], "autor": "grupo-N", "origen": "manual"}
```

Comparativa (013, con el ancla por rellenar; así pasa `validar()` y `validar_estricto()` la rechaza hasta que se rellene):

```json
{"id": "gN-013", "familia": "comparativa", "ticker": "NVDA", "fiscal_year": 2025,
 "pregunta": "¿Cómo cambió el beneficio por acción básico de NVIDIA entre los ejercicios fiscales 2024 y 2025? ¿Son comparables las dos cifras?",
 "respuesta_esperada": "Bajó de 12,05 USD (FY2024) a 2,97 USD (FY2025), pero no es comparable: en 2024 NVIDIA hizo un split de 10 por 1. <<completar con el ancla>>",
 "cifra_esperada": 2.97, "unidad": "USD/shares", "concept_xbrl": "EarningsPerShareBasic",
 "item_esperado": "8", "ancla_texto": "<<rellenar: frase del Item 8 de NVDA FY2025 sobre el split>>",
 "ancla_inicio": null, "ancla_fin": null, "chunk_id_esperado": null,
 "herramienta_esperada": ["get_xbrl_fact", "search_filings"], "autor": "grupo-N",
 "fiscal_year_base": 2024, "cifra_esperada_base": 12.05, "ancla_texto_base": null, "variacion_esperada": null, "origen": "manual"}
```

La 015 cambia a `"ticker": "MSFT"`, `"concept_xbrl": "RevenueFromContractWithCustomerExcludingAssessedTax"`,
`"cifra_esperada": 281724000000.0`, `"unidad": "USD"`, `"item_esperado": "1A"`, `"cifra_esperada_base": 245122000000.0` y
`"variacion_esperada": 0.1493`.

Extractiva (009) y hueco:

```json
{"id": "gN-009", "familia": "extractiva", "ticker": "AAPL", "fiscal_year": 2024,
 "pregunta": "¿A qué riesgos de mercado dice Apple que está expuesta en el ejercicio fiscal 2024?",
 "respuesta_esperada": "<<rellenar: lo que dice el ancla, en español>>",
 "cifra_esperada": null, "unidad": null, "concept_xbrl": null,
 "item_esperado": "7A", "ancla_texto": "<<rellenar: salida de localizar_ancla()>>", "ancla_inicio": null, "ancla_fin": null,
 "chunk_id_esperado": null, "herramienta_esperada": ["search_filings"], "autor": "grupo-N",
 "herramienta_alternativa": {"search_filings": ["read_section"]}, "origen": "manual"}
{"id": "gN-h001", "pregunta": "¿Cuál fue el beneficio bruto (gross profit) de Amazon en el ejercicio fiscal 2025?", "familia": "numerica", "ticker": "AMZN", "fiscal_year": 2025, "respuesta_esperada": "Amazon no reporta GrossProfit en FY2025: el dato no está en el corpus y no se estima.", "cifra_esperada": null, "unidad": null, "concept_xbrl": "GrossProfit", "item_esperado": null, "ancla_texto": null, "ancla_inicio": null, "ancla_fin": null, "chunk_id_esperado": null, "herramienta_esperada": ["get_xbrl_fact"], "autor": "grupo-N", "hueco": true, "origen": "manual"}
```

En extractivas del 7A, `["search_filings"]` más el extra `"herramienta_alternativa": {"search_filings": ["read_section"]}`: la sección
entera cuesta como una búsqueda con k=5 [02 §4](02_datos_corpus_y_xbrl.md), y `herramienta_esperada` sigue teniendo solo nombres reales
(D12). El resto de extractivas, `["search_filings"]` sin extra.

## 8. Validar fuera del notebook

`validar()` no se reescribe: se ejecuta **la celda 32 tal cual**, sacándola del `.ipynb`, que conviene tener en el repo porque de
él sale el baseline ([21](21_skill_agente_salida_estructurada.md)). Así se usa el validador "que se entrega" aunque cambie.
`validar_estricto()` va primero porque no revienta con tipos raros.

```python
# SUGERENCIA: python -m golden.validar golden/golden_propio.jsonl  (usa las funciones de §6)
import json, os, re, sys
from pathlib import Path
import pandas as pd

VALIDAS = {"list_available", "get_xbrl_fact", "search_filings", "read_section"}
ITEMS = {"1A", "7", "7A", "8"}


def _herramientas(p: dict) -> set[str]:
    """herramienta_esperada (solo nombres reales) + las alternativas del extra herramienta_alternativa (D12)."""
    alt = p.get("herramienta_alternativa") if isinstance(p.get("herramienta_alternativa"), dict) else {}
    return set(map(str, p.get("herramienta_esperada") or [])) | {str(h) for hs in alt.values() for h in hs}


def _distinto(a, b) -> bool:
    return b is None or a is None or abs(float(a) - b) > 1e-9 * abs(b)


def validar_estricto(preguntas: list[dict]) -> list[str]:
    """Lo que validar() no mira. Lista vacía = correcto."""
    probs = []
    for p in preguntas:
        pid = p.get("id", "(sin id)")
        mal = lambda m, pid=pid: probs.append(f"{pid}: {m}")
        if not isinstance(p.get("fiscal_year"), int) or not isinstance(p.get("ancla_texto") or "", str):
            mal("fiscal_year tiene que ser int y ancla_texto str o null (validar() revienta)")
            continue
        if not re.fullmatch(r"g\d+-h?\d{3}", str(pid)) or not re.fullmatch(r"grupo-\d+", str(p.get("autor"))):
            mal("id 'gN-001' y autor 'grupo-N' con el número del grupo, sin nombres")
        if "<<" in json.dumps(p, ensure_ascii=False):
            mal("quedan marcadores <<rellenar>>")
        if raras := _herramientas(p) - VALIDAS:
            mal(f"herramientas desconocidas {sorted(raras)} (nada de 'a|b': alternativas en herramienta_alternativa, D12)")
        alt = p.get("herramienta_alternativa")
        if alt is not None and not (isinstance(alt, dict) and set(alt) <= set(map(str, p.get("herramienta_esperada") or []))):
            mal("herramienta_alternativa: un dict cuyas claves estén en herramienta_esperada")
        fam, tk, fy, con = p.get("familia"), p.get("ticker"), p["fiscal_year"], p.get("concept_xbrl")
        v, u = (valor_xbrl(tk, fy, con) or (None, None)) if con else (None, None)
        if p.get("hueco") is True:                                    # huecos: fichero aparte
            if fam != "numerica" or p.get("cifra_esperada") is not None or v is not None or not con:
                mal("hueco: numerica, cifra_esperada null y un concept_xbrl que NO está para ese ticker y FY")
        elif fam in {"numerica", "comparativa"}:
            if v is None:
                mal("sin concept_xbrl válido para ese ticker y FY")
            elif _distinto(p.get("cifra_esperada"), v) or p.get("unidad") != u:
                mal(f"cifra_esperada/unidad ≠ XBRL ({v!r} {u})")
        if fam in {"numerica", "comparativa"} and "get_xbrl_fact" not in _herramientas(p):
            mal("una cifra se comprueba con get_xbrl_fact: añádela a herramienta_esperada")
        if a := p.get("ancla_texto"):
            it, ini, fin = p.get("item_esperado"), p.get("ancla_inicio"), p.get("ancla_fin")
            t = texto_seccion(tk, fy, it) if it in ITEMS else ""
            if not t:
                mal(f"item_esperado '{it}' no válido")
            elif normalizar(a) not in normalizar(t):
                mal(f"ancla no literal en {tk} FY{fy} Item {it}")
            elif not (isinstance(ini, int) and isinstance(fin, int) and t[ini:fin] == a):
                mal("offsets o ancla no literales: copia la salida de localizar_ancla()")
            elif not (ids := chunks_con(tk, fy, it, ini, fin)):
                mal("el ancla no cabe entera en ningún chunk: elige otra frase")
            elif p.get("chunk_id_esperado") not in ids:
                mal(f"chunk_id_esperado tiene que ser uno de {ids}")
            if "\n" in a or len(a.split()) > 40:
                mal("el ancla es UNA frase de ≤40 palabras, sin saltos de línea")
            if not _herramientas(p) & {"search_filings", "read_section"}:
                mal("un ancla de texto pide search_filings (o read_section) en herramienta_esperada")
        if fam == "comparativa":
            base = p.get("fiscal_year_base")
            vb = (valor_xbrl(tk, base, con) or (None,))[0] if con and base in {2024, 2025} else None
            if fy != 2025 or base != 2024:
                mal("comparativa: fiscal_year 2025 y el campo extra fiscal_year_base 2024 (obligatorio aquí)")
            elif _distinto(p.get("cifra_esperada_base"), vb):
                mal(f"cifra_esperada_base ≠ XBRL FY{base} ({vb!r})")
            elif p.get("variacion_esperada") is not None and v and abs(p["variacion_esperada"] - (v - vb) / vb) > 5e-4:
                mal(f"variacion_esperada ≠ {(v - vb) / vb:.4f}")
    return probs


def cargar_validar(ruta_ipynb: str):
    """validar() tal cual se entrega: ejecuta la celda del notebook S1 que define 'def validar('."""
    nb = json.loads(Path(ruta_ipynb).read_text(encoding="utf-8"))
    fuente = next("".join(c["source"]) for c in nb["cells"]
                  if c["cell_type"] == "code" and "def validar(" in "".join(c["source"]))
    ns = {"secciones": secciones, "xbrl": xbrl, "golden": []}
    exec(fuente, ns)                     # define PLANTILLA y validar() y pasa sus propios asserts de §7
    return ns["validar"]


if __name__ == "__main__":
    preguntas = [json.loads(linea) for linea in Path(sys.argv[1]).read_text(encoding="utf-8").splitlines() if linea.strip()]
    solo_huecos = all(p.get("hueco") for p in preguntas)
    estricto = validar_estricto(preguntas)
    validar = cargar_validar(os.environ.get("AGENTE10K_NOTEBOOK_S1", "notebooks/S1_Herramientas_y_Bucle_Alumno.ipynb"))
    try:
        profe = validar(preguntas, exigir_20=not solo_huecos)
    except Exception as e:                                     # fiscal_year null, ancla que no es str
        profe = [f"validar() revienta: {e!r}"]
    for nombre, ps in (("validar()", profe), ("validar_estricto()", estricto)):
        print(f"{nombre}: {len(ps)} problemas", *(f"  - {x}" for x in ps), sep="\n")
    g = pd.DataFrame(preguntas)
    print(pd.crosstab(g["ticker"], g["familia"]), g.loc[g["ancla_texto"].notna(), "item_esperado"].value_counts(), sep="\n")
    sys.exit(int(bool(estricto or (profe and not solo_huecos))))
```

Probado contra el corpus: `validar()` no pone pegas a ej-001…003 (`exigir_20=False`); `validar_estricto()` señala `id`/`autor` en los
tres y, en ej-003, el ancla ajena al Item 7, la falta de `search_filings` y de los campos `*_base`. Las seis numéricas de §7 pasan todo
con el `N` sustituido; offsets, `chunk_id`, unidad y nombres de herramienta alterados a propósito se detectan. Con un fichero de huecos,
`validar()` lista sus problemas (esperados) y el script solo falla por `validar_estricto()`.

## 9. Generación asistida (opcional) y revisión en pareja

**Asistida.** Patrón auto-rag-eval corregido de [33 §3.8](33_repo_generative_ai.md): muestreo estratificado con semilla fija, el LLM
propone pregunta + ancla a partir de **un** chunk (guardad su `chunk_id`), filtro determinista (`localizar_ancla`, ≤40 palabras) antes
del crítico LLM y **curación humana** en español natural, sin el vocabulario del chunk. La cifra, siempre del parquet. Marcad
`"origen": "asistida_curada"` (las manuales, `"manual"`). ⚠️ No sabemos si cuentan como propias: preguntarlo el 17.

**Revisión en pareja** (no la hace quien la escribió): ¿se contesta con el corpus y de una sola forma? ¿FY inequívoco? ¿El ancla dice
lo que pone `respuesta_esperada`, con unidad y escala? ¿`herramienta_esperada` premia el camino correcto (cifra ⇒ `get_xbrl_fact`)?
Después, *commit*; a partir de ahí solo se corrigen errores, explicados en el mensaje del commit.

## Checklist de hecho

- [ ] **R06:** `golden/golden_propio.jsonl` con 20 preguntas y ≥6 comparativas (propuesta 6/6/8); `validar(..., exigir_20=True)`
      ejecutado desde el `.ipynb` sin problemas, y `validar_estricto()` también (cifras y unidades = XBRL, herramientas válidas).
- [ ] **R06:** cobertura: 6 empresas, 2 FY, los 4 items entre las anclas y cada trampa de [02 §6](02_datos_corpus_y_xbrl.md).
- [ ] **R07:** 14 anclas de una frase (≤40 palabras), literales, con offsets `[inicio, fin)` sobre la sección, enteras en
      `chunk_id_esperado` y con `veces_en_seccion == 1`.
- [ ] **R06/R07:** comparativas con FY 2025 + nivel, `fiscal_year_base`, `cifra_esperada_base`, ancla del FY reciente y
      `["get_xbrl_fact", "search_filings"]`; la de NVDA menciona el split y ancla en el Item 8.
- [ ] **R14:** `golden/golden_huecos.jsonl` con 3–5 huecos (`hueco: true`, cifra nula, concepto ausente) que pasan `validar_estricto()`.
- [ ] Revisión en pareja y *commit* **antes** de ejecutar y etiquetar el baseline (R12). Sin nombres de alumnos ni claves (R13).

## Fuentes

- [notebook S1 · celdas 22, 30–33] (`PLANTILLA`, `validar()`), `golden_set_ejemplo.jsonl` (ej-001…003) y `demo_traza.json`
  (en `docs/raw/clase/sesion1/`); [enunciado · §4.3, §5, §7]; [transcripcion_10sep · 02:26–02:31]; [slides Tuning · p.55].
- [01](01_requisitos_y_contratos.md) §3 y §6; [30](30_clase_pistas_del_profesor.md) §5; [32](32_repo_transformers_labs.md) §3.2
  (`normalizar`); [33](33_repo_generative_ai.md) §3.8 (auto-rag-eval) y §3.9 (abstención); [02](02_datos_corpus_y_xbrl.md).
- Nota de trabajo A1 (análisis de `validar()` y de ej-001…003) y mapa de cobertura del 12-sep (convenciones de comparativas y huecos).
- Pruebas propias (12-sep-2026, pandas 2.3.3) contra el corpus real: offsets de ej-002, recuento de menciones del split,
  `localizar_ancla`, `validar_estricto`, `cargar_validar` y la CLI de §8.
