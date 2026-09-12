# Datos: el 10-K, el corpus y XBRL

> Requisitos: R01, R06, R07, R14 (y, de rebote, R05, R08, R10) · Lee antes: [00_enunciado.md](00_enunciado.md) §3 y
> [01_requisitos_y_contratos.md](01_requisitos_y_contratos.md) §5 · Sigue en: [10_skill_golden_set.md](10_skill_golden_set.md),
> [07_skill_herramientas_docstrings.md](07_skill_herramientas_docstrings.md), [11_skill_mejora_retrieval.md](11_skill_mejora_retrieval.md)

> Fuentes: `perfil_dataset` (LEEME, MANIFEST y manifiesto del índice, literales), [notebook S1 · celdas 5, 7–9, 12–14],
> `miax_s1.py`, `data/dataset/celda_descarga.py`, [enunciado · §3], docs 14–17 y cálculos propios sobre `data/corpus/`.

**v1 · 12-sep-2026.** Referencia de los datos para no tener que abrir `data/`. Marcas: **(datos)** = calculado con pandas sobre
`data/corpus/` (metadatos, offsets y hechos XBRL; el texto de los 10-K no se ha leído, como mucho se han contado coincidencias);
**(probado)** y **(venv)**, como en 14–17; ⚠️ = sin verificar.

## 1. El 10-K y los cuatro items del corpus

El 10-K es el informe anual que toda cotizada en EE. UU. presenta ante la SEC, con los mismos epígrafes y en el mismo orden todos
los años. El corpus se queda con cuatro [notebook S1 · celda 7]:

| Item | Qué contiene | Qué se le pregunta | Tokens por sección (mín–máx) | Chunks | Con tabla |
| --- | --- | --- | --- | --- | --- |
| **1A** · Risk Factors | Los riesgos que declara la compañía | Riesgos nuevos y cómo cambian entre ejercicios | 10.318–34.751 | 533 | 6,4 % |
| **7** · MD&A | La dirección explica sus resultados | Por qué sube o baja una magnitud | 3.814–12.621 | 307 | 39,1 % |
| **7A** · Market Risk | Exposición a tipos de interés, divisa y precios | Preguntas cuantitativas y cortas | 409–1.877 | 37 (1–5 por sección) | 48,6 % |
| **8** · Financial Statements | Estados financieros y sus notas | Cifras y de dónde salen | 15.999–32.351 | 872 | 63,0 % |

Columnas 4–6: (datos). **NVIDIA pone sus estados financieros en el Item 15** y en el 8 deja una remisión de dos líneas; el corpus
sirve el contenido correcto bajo `"8"` y lo anota en `item_origen = "15"` (las 2 secciones de NVDA; las otras 46 tienen
`item_origen == item`) [notebook S1 · celda 7] (datos). Sin eso, `read_section("NVDA", 2025, "8")` devolvería unos cuarenta tokens
inútiles.

## 2. Empresas y cierres fiscales

| Ticker | `empresa` | Cierre del ejercicio | `period_end` FY2024 | `period_end` FY2025 | 10-K presentado en (FY2024 / FY2025) |
| --- | --- | --- | --- | --- | --- |
| NVDA | NVIDIA CORP | domingo de finales de enero | 2024-01-28 | 2025-01-26 | 2024 / 2025 |
| MSFT | MICROSOFT CORP | 30 de junio | 2024-06-30 | 2025-06-30 | 2024 / 2025 |
| AAPL | Apple Inc. | sábado de finales de septiembre | 2024-09-28 | 2025-09-27 | 2024 / 2025 |
| GOOGL | Alphabet Inc. | 31 de diciembre | 2024-12-31 | 2025-12-31 | 2025 / 2026 |
| META | Meta Platforms, Inc. | 31 de diciembre | 2024-12-31 | 2025-12-31 | 2025 / 2026 |
| AMZN | AMAZON COM INC | 31 de diciembre | 2024-12-31 | 2025-12-31 | 2025 / 2026 |

Fechas de cierre del MANIFEST y del parquet; el año de presentación sale del número de *accession* (`…-24-…`, `…-25-…`)
[perfil_dataset · MANIFEST] (datos). **`fiscal_year` no es el año de presentación ni el año natural**: el FY2025 de NVIDIA va de
febrero de 2024 a enero de 2025 y se presentó en febrero de 2025; el de Alphabet se presentó en febrero de 2026
[notebook S1 · celda 7; perfil_dataset · LEEME]. "El revenue de NVIDIA en 2024" es ambiguo (FY2024 o, casi entero, FY2025): en las
preguntas se escribe "ejercicio fiscal 2025 (FY2025)" y las herramientas reciben siempre el campo, nunca una fecha.

## 3. Ficheros del corpus

| Fichero | Filas | Tamaño | Qué es | Lo sirve |
| --- | --- | --- | --- | --- |
| `secciones.jsonl` | 48 | 3,2 MB | Texto íntegro de cada (empresa, ejercicio, item) | `read_section` |
| `chunks.jsonl` | 1.749 | 3,8 MB | Ese mismo texto, troceado | `search_filings` (a través del índice) |
| `xbrl_facts.parquet` | 135 | 6,5 KB | Las cifras reportadas: fuente autorizada y *ground truth* | `get_xbrl_fact` |
| `indice/corpus.faiss` | 1.749 vectores | 2,7 MB | Índice denso de los chunks | `search_filings` |
| `indice/chunks_meta.parquet` | 1.749 | 1,5 MB | Metadatos y texto de cada vector, en el mismo orden | `search_filings` |
| `MANIFEST.md`, `indice/MANIFEST.md`, `LEEME.md` | — | — | Procedencia, hashes y cómo consultar el índice | — |

`list_available` no tiene fichero propio: el universo (6 tickers, 2 FY, 4 items y los 13 conceptos) sale de `secciones` y `xbrl`.

**`secciones.jsonl`**: `ticker`, `empresa`, `cik` (texto con ceros a la izquierda), `fiscal_year` (int), `item` (texto: `"1A"`,
`"7"`, `"7A"`, `"8"`), `titulo`, `texto`, `n_tokens`, `url_origen` (el `.htm` de EDGAR, para verificar cualquier cita),
`accession`, `item_origen`. Total: 649.119 tokens [perfil_dataset · secciones.jsonl].

**`chunks.jsonl`** (columnas iguales en `indice/chunks_meta.parquet`):
- `chunk_id` = `TICKER-FY-ITEM-NNNN`, con `NNNN` = `posicion` desde `0000` (p. ej. `NVDA-2024-1A-0000`) (datos).
- `n_tokens`: media 401,8, mediana 460, mínimo 60 y máximo 547; 6 chunks pasan de 512 [perfil_dataset · chunks.jsonl] (datos).
  ⚠️ No se sabe con qué tokenizer se contó ni si bge-small trunca a 512 (su tokenizer es otro): un ancla al final de uno de esos 6
  chunks podría no llegar a la vía densa [16 §3.7].
- `contiene_tabla`: 721 chunks (41,2 %). Es exacto porque el tabulador solo aparece dentro de tablas: celdas unidas por `\t` y filas
  por `\n` [perfil_dataset · LEEME].
- `inicio_car`, `fin_car`: offsets de **carácter** (índices de `str` de Python), intervalo `[inicio, fin)`, sobre el `texto` de la
  sección. Para los 1.749 chunks se cumple `chunk["texto"] == seccion["texto"][inicio_car:fin_car]`, y los chunks cubren cada
  sección de 0 a `len(texto)` (datos). Las anclas del golden usan la misma convención (ver [10 §2](10_skill_golden_set.md)).
- **Solape.** El enunciado y el LEEME describen trozos de unos 500 tokens con un solape de 80 [enunciado · §3; perfil_dataset · LEEME]. Lo que hay
  en los datos: de 1.701 pares de chunks consecutivos, **1.029 (60 %) no se solapan** (el corte cae en frontera de párrafo y se salta
  el `"\n\n"`: hueco de 2 caracteres en 1.002 pares y de 4 en 27) y 672 se solapan (126 entre 100 y 299 caracteres, 546 con 300 o
  más; máximo 541). El 49 % de los chunks que no cierran su sección acaba a mitad de frase (datos). Lectura: el solape de 80 tokens
  solo se aplica cuando el corte cae dentro de un párrafo. La suma de `n_tokens` de los chunks (702.665) supera en un 8 % a la de las
  secciones (datos).

**`xbrl_facts.parquet`**: `ticker`, `cik`, `fiscal_year` (int), `concept`, `value` (float64), `unit` (`"USD"` en 111 hechos,
`"USD/shares"` en 24), `period_end` (texto `AAAA-MM-DD`), `form` (siempre `"10-K"`). Una fila por (ticker, FY, concepto), sin
duplicados; 13 conceptos × 12 empresa-FY = 156 celdas, de las que 21 están vacías (§5) (datos).

**`indice/`** [perfil_dataset · indice/MANIFEST.md]: `BAAI/bge-small-en-v1.5`, 384 dimensiones, `IndexFlatIP` sobre vectores
normalizados (producto interno = coseno), búsqueda exacta. El prefijo `"Represent this sentence for searching relevant passages: "`
va **solo en la consulta**; omitirlo no da error, solo recupera peor. La fila *i* de `chunks_meta.parquet` describe el vector *i*, y
los dos manifiestos citan el SHA-256 de `chunks.jsonl` (`388ff367…`): si no coincide, índice y metadatos están desalineados y el
retrieval devuelve texto equivocado **sin avisar**; se regeneran siempre juntos. `miax_s1.buscar()` ordena los 1.749 vectores y
después filtra por igualdad exacta, así que su post-filtro no pierde recall [01 §5, trampa 7]. La primera búsqueda descarga
~130 MB de bge [miax_s1.py · _indice()]. Todo lo que cambie el troceado o el modelo exige índice y manifiesto nuevos
([11_skill_mejora_retrieval.md](11_skill_mejora_retrieval.md)).

**`MANIFEST.md` y `LEEME.md`**: CIK, *accession* y fecha de cierre de cada presentación, SHA-256 de los tres artefactos y los tres
avisos (fiscal_year, tabulador, "las cifras salen de XBRL") [perfil_dataset]. **`fuentes_10k_html.zip`** (2,3 MB) trae los 12 HTML
originales de EDGAR (`TICKER/FYaaaa/documento.htm`). No hace falta: sirve para comprobar la procedencia de una cita o para segmentar
los items por tu cuenta, y eso último no es trivial (el 10-K de Microsoft tiene 44 líneas que empiezan por "Item 8" y solo una es el
encabezado) [perfil_dataset · fuentes_10k_html.zip].

## 4. Tokens por sección y coste de `read_section`

| Empresa-FY | 1A | 7 | 7A | 8 | Total |
| --- | ---: | ---: | ---: | ---: | ---: |
| AAPL 2024 | 11.663 | 3.814 | 612 | 15.999 | 32.088 |
| AAPL 2025 | 11.626 | 4.294 | 612 | 16.358 | 32.890 |
| AMZN 2024 | 10.318 | 9.597 | 1.614 | 28.097 | 49.626 |
| AMZN 2025 | 10.516 | 9.034 | 1.547 | 29.103 | 50.200 |
| GOOGL 2024 | 14.727 | 11.947 | 1.877 | 30.380 | 58.931 |
| GOOGL 2025 | 14.984 | 10.648 | 1.579 | 31.845 | 59.056 |
| META 2024 | 33.573 | 12.621 | 1.128 | 28.501 | 75.823 |
| META 2025 | **34.751** | 12.518 | 1.144 | 32.351 | 80.764 |
| MSFT 2024 | 12.650 | 10.295 | 409 | 28.455 | 51.809 |
| MSFT 2025 | 11.793 | 9.510 | 409 | 26.500 | 48.212 |
| NVDA 2024 | 18.681 | 8.348 | 635 | 26.909 | 54.573 |
| NVDA 2025 | 19.476 | 7.824 | 638 | 27.209 | 55.147 |

[perfil_dataset · secciones.jsonl]. Con gemini-3.8-flash (0,75 $/M de entrada, precio del 2-sep [01 §4]): leer el 1A de META FY2025
cuesta 0,026 $ **por vuelta**, y como cada llamada al modelo reenvía el historial, se vuelve a pagar en cada vuelta posterior
[notebook S1 · celda 21]. Referencias de la celda 9: `search_filings` con k=5 ≈ 2.010 tokens y `get_xbrl_fact` ≈ 40. Consecuencia
útil: **todo 7A cabe en 409–1.877 tokens**, así que leerlo entero cuesta como una búsqueda con k=5 (datos).

## 5. XBRL: cobertura y valores

Cobertura (✓ reportado, — no reportado) [perfil_dataset · xbrl_facts.parquet]:

| Concepto | NVDA 24 | NVDA 25 | MSFT 24 | MSFT 25 | AAPL 24 | AAPL 25 | GOOGL 24 | GOOGL 25 | META 24 | META 25 | AMZN 24 | AMZN 25 |
| --- | :-: | :-: | :-: | :-: | :-: | :-: | :-: | :-: | :-: | :-: | :-: | :-: |
| Assets | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| CashAndCashEquivalentsAtCarryingValue | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| EarningsPerShareBasic | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| EarningsPerShareDiluted | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| GrossProfit | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | — | — | — | — | — | — |
| Liabilities | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | — | — |
| NetCashProvidedByUsedInOperatingActivities | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| NetIncomeLoss | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| OperatingIncomeLoss | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| ResearchAndDevelopmentExpense | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | — | — |
| RevenueFromContractWithCustomerExcludingAssessedTax | — | — | ✓ | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ | ✓ | ✓ |
| Revenues | ✓ | ✓ | — | — | — | — | ✓ | ✓ | — | — | — | — |
| StockholdersEquity | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |

Valores completos: **USD en millones** (separador de miles "."; el valor del parquet es millones × 10⁶) y **BPA en USD por acción**
(coma decimal); nombres completos de los conceptos en la matriz de arriba (datos, desde el parquet):

| Concepto | NVDA 24 | NVDA 25 | MSFT 24 | MSFT 25 | AAPL 24 | AAPL 25 | GOOGL 24 | GOOGL 25 | META 24 | META 25 | AMZN 24 | AMZN 25 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Assets | 65.728 | 111.601 | 512.163 | 619.003 | 364.980 | 359.241 | 450.256 | 595.281 | 276.054 | 366.021 | 624.894 | 818.042 |
| CashAndCashEquivalents… | 7.280 | 8.589 | 18.315 | 30.242 | 29.943 | 35.934 | 23.466 | 30.708 | 43.889 | 35.873 | 78.779 | 86.810 |
| EarningsPerShareBasic | 12,05 | 2,97 | 11,86 | 13,70 | 6,11 | 7,49 | 8,13 | 10,91 | 24,61 | 23,98 | 5,66 | 7,29 |
| EarningsPerShareDiluted | 11,93 | 2,94 | 11,80 | 13,64 | 6,08 | 7,46 | 8,04 | 10,81 | 23,86 | 23,49 | 5,53 | 7,17 |
| GrossProfit | 44.301 | 97.858 | 171.008 | 193.893 | 180.683 | 195.201 | — | — | — | — | — | — |
| Liabilities | 22.750 | 32.274 | 243.686 | 275.524 | 308.030 | 285.508 | 125.172 | 180.016 | 93.417 | 148.778 | — | — |
| NetCashProvidedByUsedIn… | 28.090 | 64.089 | 118.548 | 136.162 | 118.254 | 111.482 | 125.299 | 164.713 | 91.328 | 115.800 | 115.877 | 139.514 |
| NetIncomeLoss | 29.760 | 72.880 | 88.136 | 101.832 | 93.736 | 112.010 | 100.118 | 132.170 | 62.360 | 60.458 | 59.248 | 77.670 |
| OperatingIncomeLoss | 32.972 | 81.453 | 109.433 | 128.528 | 123.216 | 133.050 | 112.390 | 129.039 | 69.380 | 83.276 | 68.593 | 79.975 |
| ResearchAndDevelopmentExpense | 8.675 | 12.914 | 29.510 | 32.488 | 31.370 | 34.550 | 49.326 | 61.087 | 43.873 | 57.372 | — | — |
| RevenueFromContractWith… | — | — | 245.122 | 281.724 | 391.035 | 416.161 | 350.018 | — | 164.501 | 200.966 | 637.959 | 716.924 |
| Revenues | 60.922 | 130.497 | — | — | — | — | 350.018 | 402.836 | — | — | — | — |
| StockholdersEquity | 42.978 | 79.327 | 268.477 | 343.479 | 56.950 | 73.733 | 325.084 | 415.265 | 182.637 | 217.243 | 285.970 | 411.065 |

Para el JSON del golden, `cifra_esperada` va **sin escalar** y con punto decimal: 391.035 → `391035000000.0`; 6,08 → `6.08`. Mejor
leerla del parquet con código que copiarla de esta tabla ([10 §7](10_skill_golden_set.md)).

Lo que hay que saber de estos números (datos):
- Los 111 hechos en USD son múltiplos exactos de 10⁶ (el menor, 7.280 M: caja de NVDA en FY2024). Los 24 BPA llevan dos decimales.
- **Menor cambio interanual:** 1,57 % entre los hechos en USD (AAPL `Assets`, 364.980 → 359.241) y 1,55 % en BPA (META diluido,
  23,86 → 23,49). Una tolerancia relativa del 0,5 % en USD no confunde nunca un FY con el otro.
- **BPA básico y diluido** distan 0,03 como mínimo (AAPL en los dos FY, NVDA FY2025). Un 0,5 % relativo daría 6,08 por bueno frente
  a 6,11: el BPA pide tolerancia absoluta ([12_skill_evaluadores.md](12_skill_evaluadores.md)).
- **Pares casi iguales** dentro de la misma empresa-FY: GOOGL FY2024, los dos conceptos de revenue (idénticos); META FY2024, `Cash…`
  frente a `R&D` (0,04 %); GOOGL FY2024, `Liabilities` frente al flujo operativo (0,10 %); AAPL FY2025, flujo operativo frente a
  beneficio neto (0,47 %). La tolerancia no distingue el concepto: lo hace el evaluador de trayectoria mirando los argumentos de
  `get_xbrl_fact` ([12_skill_evaluadores.md](12_skill_evaluadores.md)).

## 6. Trampas

1. **Concepto del revenue por empresa.** NVDA usa `Revenues`; AAPL, MSFT, META y AMZN,
   `RevenueFromContractWithCustomerExcludingAssessedTax`; GOOGL etiqueta los dos en FY2024 (mismo valor) y solo `Revenues` en FY2025
   [enunciado · §3]. Se mira el fichero, nunca por analogía. El docstring del notebook pone `'Revenues'` de ejemplo y ese concepto no
   existe en 4 de las 6 [14 §5].
2. **Huecos.** De las 21 celdas vacías, **10 son huecos reales**: `GrossProfit` de AMZN, GOOGL y META (6), `Liabilities` de AMZN (2)
   y `ResearchAndDevelopmentExpense` de AMZN (2). Las otras **11 no son huecos**: es el revenue bajo el otro concepto. Si
   `get_xbrl_fact("AAPL", 2025, "Revenues")` responde "no reportó", lo correcto es probar el otro concepto; decir "no está" es una
   **abstención indebida** (R14).
3. **Split 10:1 de NVDA.** El BPA reportado baja de 12,05 (FY2024) a 2,97 (FY2025) mientras el beneficio neto sube de 29.760 a
   72.880 M (+145 %). Una comparativa ingenua diría que el BPA cayó un 75 % [01 §5]. En NVDA FY2025 hay 3 menciones de "stock split"
   o "ten-for-one", todas en el Item 8 y en un solo chunk; ninguna en 1A, 7 o 7A, ni en FY2024 (datos: recuento, sin leer el texto).
   El ancla de una comparativa de BPA de NVDA sale, por tanto, del Item 8.
4. **`fiscal_year`** ≠ año de presentación (§2). Tiene que llegar a las tools como `int`: `"2025"` no casa con la igualdad exacta.
5. **Tablas partidas.** 103 chunks empiezan en una fila de tabla (93 en el Item 8) y 172 acaban en una: la cabecera con los años se
   queda en el chunk anterior y una cifra leída de ahí puede ser la del otro ejercicio (datos). Las cifras salen de XBRL
   [perfil_dataset · LEEME], y las anclas son frases, no filas de tabla.
6. **Pandas.** `fila.item` es el método `Series.item`, no la columna: `fila["item"]` [notebook S1 · celda 8]. Y `pd.read_json(...,
   lines=True)` convierte `cik` en entero y pierde los ceros: cargar con `json.loads` línea a línea, como el notebook, o con
   `dtype={"cik": str}` (datos).
7. **BPA redondeado en el baseline.** El `get_xbrl_fact` del notebook formatea con `:,.0f`, así que 2,97 sale como "3"
   [01 §5, fallo 8]. El arreglo, en [07_skill_herramientas_docstrings.md](07_skill_herramientas_docstrings.md).
8. **El formato del `ToolMessage` cambia.** La traza demo dice "cierre 2024-06-30, formulario 10-K" y el notebook, "cierre de
   ejercicio …, según el 10-K" [demo_traza · paso 3; notebook S1 · celda 12]. Ningún evaluador ni middleware debe parsear ese texto: se busca en el parquet por los
   `args` de la llamada.
9. **Filtros de igualdad exacta.** `"nvda"`, `"GOOG"`, `"Item 1A"` o `"7a"` no casan con nada en las tools del notebook
   [14 §5]: hay que normalizar las entradas dentro del cuerpo de la tool.
10. **Idioma.** Corpus y modelo de embeddings en inglés; preguntas en español. La consulta a `search_filings` se escribe en inglés
    [notebook S1 · celda 13] ([11_skill_mejora_retrieval.md](11_skill_mejora_retrieval.md)).

## 7. Cargar los datos y el "paseíto por el dataset"

El consejo del profesor es explorar los DataFrames antes de escribir preguntas o herramientas [transcripcion_10sep · 02:29]. Carga
con comprobación de alineación (nombres de módulo y de variable de entorno: SUGERENCIA):

```python
import hashlib, json, os
from pathlib import Path
import pandas as pd

CORPUS = Path(os.environ.get("AGENTE10K_CORPUS", "data/corpus"))


def _sha256(ruta: Path) -> str:
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def _jsonl(ruta: Path) -> pd.DataFrame:
    with open(ruta, encoding="utf-8") as f:          # json.loads conserva cik e item como texto
        return pd.DataFrame(json.loads(linea) for linea in f if linea.strip())


def cargar_corpus(ruta: Path = CORPUS):
    """(secciones, chunks, xbrl). Falla en voz alta si falta el corpus o el índice no casa con chunks.jsonl."""
    if not (ruta / "chunks.jsonl").is_file():
        raise FileNotFoundError(f"No hay corpus en {ruta.resolve()} (ver §8)")
    huella = _sha256(ruta / "chunks.jsonl")
    for manifiesto in ("MANIFEST.md", "indice/MANIFEST.md"):
        if huella not in (ruta / manifiesto).read_text(encoding="utf-8"):
            raise RuntimeError(f"chunks.jsonl no cuadra con {manifiesto}: índice y metadatos desalineados")
    secciones, chunks = _jsonl(ruta / "secciones.jsonl"), _jsonl(ruta / "chunks.jsonl")
    xbrl = pd.read_parquet(ruta / "xbrl_facts.parquet")
    if (len(secciones), len(xbrl)) != (48, 135):
        raise RuntimeError("Corpus distinto del de la práctica")
    return secciones, chunks, xbrl
```

```python
secciones, chunks, xbrl = cargar_corpus()
print(secciones.pivot_table(index=["ticker", "fiscal_year"], columns="item", values="n_tokens", aggfunc="sum"))
print(chunks.groupby("item").agg(n=("chunk_id", "size"), con_tabla=("contiene_tabla", "mean")))
col = xbrl["ticker"] + "-" + xbrl["fiscal_year"].astype(str)
print(pd.crosstab(xbrl["concept"], col).replace({1: "✓", 0: "—"}))      # la matriz de §5
fila = secciones.iloc[3]
print(fila["ticker"], fila["item"], fila["item_origen"])                  # NVDA 8 15; nunca fila.item
texto = secciones.set_index(["ticker", "fiscal_year", "item"])["texto"]
c = chunks.iloc[100]                                                      # offsets de carácter [ini, fin)
assert c["texto"] == texto[(c["ticker"], c["fiscal_year"], c["item"])][c["inicio_car"]:c["fin_car"]]
```

## 8. Dónde está en disco y "clon limpio" (R10)

- **En este repo** el corpus está descomprimido en `data/corpus/`, y en `data/dataset/` están los tres ZIP del curso,
  `SHA256SUMS.txt` y `celda_descarga.py`, que es la celda 5 del notebook. **`data/` entero está en `.gitignore`**: hoy no se versiona
  nada de los datos (datos).
- **Cómo se obtiene:** los ZIP los reparte el curso (Drive, aula virtual); nada de descargar de EDGAR, que limita a 10 peticiones por
  segundo [enunciado · §3]. `corpus_miax_2026.zip` (1,8 MB, SHA-256 `4233c37f…`) trae los cinco ficheros en la raíz;
  `indice_faiss.zip` (3,8 MB, `6b5610ad…`) trae la carpeta `indice/` (datos; los dos hashes coinciden con los de la celda 5).
- **`celda_descarga.py`** busca los ZIP en unas rutas candidatas, comprueba su SHA-256, los descomprime en `corpus/` y verifica que el
  hash de `chunks.jsonl` aparece en los dos manifiestos. Pero todo va dentro de un `try/except` que solo imprime el error: un ZIP
  corrupto no para nada [14 §5]. Además, el `miax_s1.dir_corpus()` de clase busca en `parents[3]`, que revienta en rutas cortas
  [01 §5, fallo 11].
- **Qué implica para R10** (la estructura del repo se decide aparte): la ruta del corpus es configurable y tiene un valor por
  defecto relativo a la raíz del repo; las comprobaciones de hash **lanzan excepción**; los ZIP (5,6 MB, registros públicos de la SEC
  redistribuibles con fines docentes [perfil_dataset · MANIFEST]) o van en el repo (habría que sacar `data/dataset/*.zip` del
  `.gitignore`) o el README explica dónde dejarlos, y `evaluar()` falla con un mensaje claro si no están. La primera ejecución baja
  ~130 MB de bge sin token: hace falta red. Se ensaya en un clon limpio antes del 22-sep
  ([13_skill_medicion_informe_presentacion.md](13_skill_medicion_informe_presentacion.md)).

```python
import zipfile

PAQUETES = {"corpus_miax_2026.zip": "4233c37fc9e9d12091af7a146063ad70903a3fe51404a485854f4021c63daee4",
            "indice_faiss.zip": "6b5610ad8ac6ea50364445d39bb464d993cbd87048fb07c4fe16657d7ac11655"}


def preparar_corpus(dir_zips: Path, destino: Path = CORPUS) -> None:
    """Descomprime los ZIP del curso comprobando el SHA-256. A diferencia de la celda 5, un fallo PARA."""
    for nombre, esperado in PAQUETES.items():
        obtenido = _sha256(dir_zips / nombre)
        if obtenido != esperado:
            raise RuntimeError(f"{nombre}: SHA-256 {obtenido} ≠ {esperado} (corrupto o de otra versión)")
        with zipfile.ZipFile(dir_zips / nombre) as zf:
            zf.extractall(destino)
    cargar_corpus(destino)            # re-comprueba la alineación índice ↔ chunks
```

## 9. Qué preguntas permiten los datos

| Familia | Qué permiten los datos | Límite |
| --- | --- | --- |
| `numerica` | 135 niveles exactos: 13 conceptos × 12 empresa-FY, en USD o USD/acción | Solo esos 13 conceptos. Segmentos, trimestres, capex, número de acciones o dividendos no están en XBRL: o salen del texto (`fuente="texto"` con cita literal, [09_skill_guardrails_middleware_xbrl.md](09_skill_guardrails_middleware_xbrl.md)) o son hueco |
| `extractiva` | 48 secciones: riesgos (1A), explicaciones de la dirección (7), exposición de mercado (7A), notas de los estados (8) | El ancla es una frase de ≤40 palabras; las filas de tabla no sirven |
| `comparativa` | 67 pares (empresa, concepto) con valor en los dos FY (AAPL, MSFT y NVDA 12; GOOGL y META 11; AMZN 9); el 1A cambia entre el 49 % y el 85 % de los párrafos según la empresa [notebook S1 · celda 30] | El golden fija el FY reciente y su nivel; la variación es derivada ([10 §4](10_skill_golden_set.md)) |
| hueco | 10 celdas reales (§6, trampa 2) y cualquier empresa o FY fuera del corpus | La respuesta correcta es `fuente="ninguna"` sin cifra (R14) |

**Métricas derivadas** que se pueden calcular con dos hechos reportados (datos): margen operativo, margen neto, ROE (beneficio neto /
patrimonio) y conversión de caja (flujo operativo / beneficio neto) en las 12 empresa-FY; margen bruto solo en NVDA, MSFT y AAPL (6);
pasivo / activo y R&D / ingresos en 10 (todas menos AMZN); y crecimientos interanuales en los 67 pares. Son diagnóstico: no hay verdad
XBRL directa y se comparan con tolerancia absoluta en puntos porcentuales ([12_skill_evaluadores.md](12_skill_evaluadores.md)).

**Límite de R14:** no se derivan magnitudes que la compañía no reporta. El margen bruto de AMZN, META o GOOGL es un hueco aunque se
pudiera aproximar con otras partidas, y el pasivo de AMZN no es `Assets − StockholdersEquity`: es "no está en el corpus"
[enunciado · §3; 01 §5].

## 10. Qué implica para la práctica

- **R01/R02:** `get_xbrl_fact` formatea según la unidad y dice "no reportó" con los conceptos disponibles; los docstrings llevan la
  regla del revenue, los items con su significado, los 13 conceptos y el aviso de que `fiscal_year` no es una fecha
  ([07_skill_herramientas_docstrings.md](07_skill_herramientas_docstrings.md)).
- **R05/R09b:** la verdad es el parquet, consultado por (ticker, FY, concepto); tolerancia relativa en USD y absoluta en BPA; los
  pares casi iguales los caza la trayectoria.
- **R06/R07:** anclas con offsets de carácter sobre la sección y comprobadas contra el chunk que las contiene; comparativas de BPA de
  NVDA con ancla en el Item 8 ([10_skill_golden_set.md](10_skill_golden_set.md)).
- **R08:** con la búsqueda exacta, filtrar antes o después no cambia el recall; lo que importa es que los filtros lleguen bien
  escritos. El 7A tiene de 1 a 5 chunks: con filtro por item, recall@5 es trivial ahí ([11_skill_mejora_retrieval.md](11_skill_mejora_retrieval.md)).
- **R10:** ruta configurable, hashes que fallan en voz alta y ensayo de clon limpio (§8).
- **R14:** 10 huecos reales frente a 11 conceptos alternativos del revenue: los dos casos se evalúan (abstención correcta e indebida).

## Fuentes

- `docs/raw/_texto/perfil_dataset.md`: LEEME, MANIFEST e `indice/MANIFEST.md` literales; tokens por sección, chunks por item, matriz y
  valores XBRL.
- [notebook S1 · celdas 5–9, 12–14, 21, 30] y `docs/raw/clase/sesion1/miax_s1.py` (`_indice()`, `buscar()`, `dir_corpus()`).
- `data/dataset/celda_descarga.py` y `SHA256SUMS.txt`; [enunciado · §3]; [transcripcion_10sep · 02:29].
- [01_requisitos_y_contratos.md](01_requisitos_y_contratos.md) §4–5; [14_clase_pistas_del_profesor.md](14_clase_pistas_del_profesor.md) §5;
  [16_repo_transformers_labs.md](16_repo_transformers_labs.md) §3.3 y §3.7.
- Cálculos propios (datos) sobre `data/corpus/` con pandas 2.3.3, el 12-sep-2026: offsets y solapes de los chunks, filas de tabla
  partidas, menor cambio interanual, pares casi iguales, pares con dos FY, recuento de menciones del split y contenido de los ZIP.
