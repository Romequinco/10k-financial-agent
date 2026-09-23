# Requisitos y contratos de la práctica

Checklist operativa del [enunciado](00_enunciado.md) y del notebook de la sesión 1. Cada requisito tiene un
ID (`R01`…`R15`) que el resto de documentos usa para decir qué cubren.

> Fuentes: `00_enunciado.md` (§ = sección del enunciado) y el notebook
> `S1_Herramientas_y_Bucle_Alumno.ipynb` (celda N).

## 1. Calendario

| Fecha | Qué pasa | Qué hay que llevar |
| --- | --- | --- |
| 10 sep (jue) | Sesión 1 práctica: herramientas y bucle | — |
| 12 sep (sáb) | Clase de RAG (módulo NLP) | — |
| **17 sep (jue)** | Sesión 2 práctica: robustez, guardrails, evaluación | **Baseline corriendo + 20 preguntas propias que pasen el validador** (celda 33) |
| 18 sep (vie) | ReAct, con el paper | — |
| 19 sep (sáb) | MCP, ADK y A2A (+ notebook bonus) | — |
| **23 sep, 23:59** | Entrega: repo GitHub + informe PDF por el aula virtual | Todo |
| **24 sep** | 10 preguntas ciegas al empezar la clase + presentación de 8 min + preguntas | Repo que ejecute `evaluar()` sin tocar código |

Peso: **30 % GitHub, 70 % presentación** (§6). Grupos de 3.

## 2. Requisitos

| ID | Requisito | Criterio de "hecho" | § |
| --- | --- | --- | --- |
| R01 | Cuatro herramientas con las firmas del contrato (§3 abajo) | Nombres y parámetros idénticos; se pueden añadir parámetros con valor por defecto y herramientas nuevas | 4.1, 7 |
| R02 | Docstrings de enrutado | Cada docstring dice **cuándo usarla y cuándo NO**, y enumera el vocabulario (`'1A'`, `'7'`, `'7A'`, `'8'`, conceptos XBRL) | 4.1, celda 18 |
| R03 | Salida estructurada obligatoria `RespuestaFinanciera` | Los 8 campos presentes; se pueden añadir, no quitar ni renombrar | 4.2, 7 |
| R04 | Límite de llamadas a herramienta por invocación | El bucle de la celda 23 (margen bruto de Amazon) termina solo | 4.2, celda 23 |
| R05 | Middleware propio de verificación contra XBRL | Extrae las cifras de la respuesta, las contrasta con `xbrl_facts.parquet` y devuelve el desajuste al modelo | 4.2 |
| R06 | Golden set propio | 20 preguntas JSONL, ≥6 comparativas, pasa `validar()` (celda 32) | 4.3, 5 |
| R07 | Anclas de texto, no `chunk_id` | Extractivas y comparativas anclan a **una frase literal** (≤40 palabras) | 4.3 |
| R08 | Mejora medida del retrieval | Filtro por metadatos, BM25 + denso y reescritura de la consulta con el LLM, midiendo **recall@k tras cada arreglo** contra el ancla | 4.4 |
| R09 | Tres evaluadores | (a) la cita existe y respalda lo afirmado; (b) la cifra coincide con XBRL con **tolerancia documentada**; (c) la trayectoria pasó por la herramienta esperada | 4.5 |
| R10 | `responder(pregunta)` y `evaluar(ruta_jsonl)` | Funcionan en un **clon limpio** sin editar nada (ensayarlo antes del 23) | 4.5, 5 |
| R11 | Tabla baseline vs final | Aciertos por familia, recall@k, coste medio/pregunta, latencia media, llamadas/pregunta; mejor valor remarcado; coste y latencia **como columnas** | 5 |
| R12 | Resultados regenerables | Ficheros del baseline (**congelado y etiquetado antes de mejorar**) y del final, regenerables ejecutando el repo; el código genera todas las tablas | 5 |
| R13 | Sin claves en el repo | Claves por entorno/`getpass`, nunca en código ni notebooks | 5, celda 4 |
| R14 | Honestidad ante huecos | Si el dato no está: `fuente="ninguna"` y decirlo, sin estimar | 3, celda 21 |
| R15 | Presentación e informe | Tabla y su lectura (qué mejoró, cuánto, a qué coste); delta de las 10 ciegas frente al golden propio; enrutado exacta/difusa + guardrail; qué no funcionó | 5 |

### Estado de cumplimiento a 23-sep-2026

`Hecho` significa que existe implementación y evidencia local; `Provisional`, que puede demostrarse con el
candidato pero depende de la evaluación oficial de `final`; `Pendiente`, que todavía falta implementar o recibir.

| ID | Estado | Evidencia y trabajo restante |
| --- | --- | --- |
| R01 | Hecho | Las cuatro tools conservan nombre y firma; pruebas de contratos. |
| R02 | Hecho | Docstrings de enrutado implementados y comprobados. |
| R03 | Hecho | `RespuestaFinanciera` mantiene los ocho campos obligatorios y añade campos comparativos opcionales. |
| R04 | Hecho | `guardrails.middleware_final()` aplica `ToolCallLimitMiddleware`/`ModelCallLimitMiddleware`; probado sin red en `tests/test_guardrails_middleware.py`. Falta rellenar la demo del notebook 06. |
| R05 | Hecho | `guardrails.verificar_xbrl()` contrasta cifras contra XBRL de forma determinista; probado sin red en `tests/test_guardrails_verificador.py`. Falta rellenar la demo del notebook 06. |
| R06 | Hecho | `golden/golden_propio.jsonl`: 20 preguntas, 7 comparativas; validación sin errores. |
| R07 | Hecho | Las 13 preguntas extractivas/comparativas tienen ancla literal y offsets comprobados. |
| R08 | Hecho | Escalera versionada en `resultados/retrieval/5976eb180c38/`, incluida reescritura sin fallos. |
| R09 | Hecho | Evaluadores de cita, cifra y trayectoria implementados; baseline puntuado. |
| R10 | Hecho | `responder(pregunta)` usa el sistema `final` por defecto y `evaluar(ruta_jsonl)` funciona sin editar nada; la suite pasa en un clon limpio **sin `.env`** (405+ tests). |
| R11 | Hecho | `evaluacion.tabla_r11()` da la tabla del enunciado: aciertos por familia, recall@k, **coste y latencia como columnas** y el mejor valor marcado con `*`. Si las filas no comparten modelo, avisa y no marca ganador (compara el modelo del agente, no el del juez). El coste deja de ser `0,00` en las tandas de pago del 08: `coste_fuente` pasa de la regla `:free` a `metadata_openrouter`, y es el primer dato real de esa columna. `recall@5` sale vacía en etiquetas nuevas (ver nota al pie de esta tabla). |
| R12 | Hecho | `resultados/final/` medido con el código entregado; réplicas en `final_r2_t*` y comparación con el mismo modelo en `baseline_nexn25pro/`. El notebook 08 añade el par `baseline_pago/` y `final_pago/` (+ `_huecos`) y las re-puntuaciones `final_jp/` y `final_jp_huecos/`, que se regeneran con `repuntuar()` sin llamar al agente. El baseline histórico se conserva intacto. |
| R13 | Hecho | La clave se carga desde entorno/`.env`, que no se versiona; debe repetirse el escaneo antes de entregar. |
| R14 | Hecho | El contrato admite `fuente="ninguna"`; hay un golden separado de seis huecos y evaluación de abstención. |
| R15 | Pendiente | Faltan el PDF (que debe incluir la decisión de proveedor del 08), el ensayo de ocho minutos y los resultados de las diez preguntas ciegas. |

`candidato_07` se conserva como referencia intermedia (retrieval mejorado, sin guardrails). `final` monta
retrieval mejorado + guardrails y es el sistema entregado, medido en `resultados/final/`. Solo queda abierto
R15 (informe y presentación) y el resultado de las diez preguntas ciegas.

> **Nota sobre `recall@5`.** `manifest_ejecucion()` dejó de escribir el campo `paso_aislado` que
> `_recall_aislado()` necesita para localizar el paso en la escalera, así que la columna sale vacía para
> cualquier etiqueta creada con el código actual (las antiguas sí la resuelven). No se arregló antes de la
> entrega para no invalidar los manifiestos de las tandas ya medidas, porque `retrieval` es un campo
> bloqueante de `validar_manifest()`. Para comparar modelos la columna informativa es `recall_agente`.

> **El modelo entregado es el del enunciado.** `docs/01 §4` fija el stack de clase en
> `openrouter:google/gemini-3.8-flash`, que es el valor por defecto de `config.MODELO_ID` y el modelo de
> `resultados/final_pago/`. Se eligió por fiabilidad —0 preguntas perdidas en 40 medidas frente a entre 0 y 7
> por tanda del gratuito— y no por acierto, que no mejora de forma sostenida (0,75 y 0,60 en dos tandas).
> La ronda con `nex-n2.5-pro:free` se hizo por cuota y queda documentada en el notebook 08.

**Criterio transversal de corrección:** acertar por el camino equivocado es **fallo**. Un revenue correcto leído de
la prosa, en vez de `get_xbrl_fact`, lo detecta el evaluador de trayectoria y cuenta como error (§1, celda 29).

## 3. Contratos (no se tocan)

### Herramientas (enunciado §7)

```python
@tool
def list_available() -> str: ...
@tool
def get_xbrl_fact(ticker: str, fiscal_year: int, concept: str) -> str: ...
@tool
def search_filings(query: str, ticker: str | None = None,
                   fiscal_year: int | None = None,
                   item: str | None = None, k: int = 5) -> str: ...
@tool
def read_section(ticker: str, fiscal_year: int, item: str) -> str: ...
```

El evaluador de trayectoria del día 24 busca **estos nombres**. Coste relativo: `get_xbrl_fact` ≈ 40 tokens,
`search_filings` (k=5) ≈ 2.000 tokens, `read_section` hasta 34.751 tokens (META FY2025 1A) (celdas 9 y 14).

### Respuesta del agente (enunciado §7)

`RespuestaFinanciera(respuesta, cifra, unidad, ticker, ejercicio, fuente, cita, chunk_id)` con
`fuente ∈ {"xbrl", "texto", "ambas", "ninguna"}`. En el notebook se monta con
`create_agent(model=..., tools=..., system_prompt=..., response_format=RespuestaFinanciera, checkpointer=InMemorySaver())`
y se lee de `resultado["structured_response"]`. Si el modelo no soporta salida estructurada nativa:
`response_format=ToolStrategy(schema=RespuestaFinanciera)` (celda 26).

> **Decisión posterior:** con nuestro modelo el esquema suelto ya acaba en `ToolStrategy` (V1); se escribe explícito
> (D02 del [README](README.md), [08 §4](08_skill_agente_salida_estructurada.md)). `ToolStrategy` se importa de
> `langchain.agents.structured_output`, como en la celda 26 (venv).

### Pregunta del golden set (enunciado §7 y celda 32)

Campos obligatorios, **todos** presentes aunque sean `null`: `id, pregunta, familia, ticker, fiscal_year,
respuesta_esperada, cifra_esperada, unidad, concept_xbrl, item_esperado, ancla_texto, ancla_inicio, ancla_fin,
chunk_id_esperado, herramienta_esperada, autor`.

| Familia | Qué mide | Qué exige el validador |
| --- | --- | --- |
| `numerica` | El guardrail contra XBRL | `cifra_esperada` no nula; si hay `concept_xbrl`, debe existir para ese ticker y FY |
| `extractiva` | Retrieval y trazabilidad | `ancla_texto` no nula y de ≤40 palabras |
| `comparativa` | Descomponer y comparar dos ejercicios | **Las dos cosas**: cifra (+ concepto válido) **y** ancla |

Además: `id` único, ticker y FY existentes en el corpus, `herramienta_esperada` no vacía, exactamente 20
preguntas y ≥6 comparativas.

## 4. Stack fijado en clase (celda 2, verificado el 2-sep-2026)

```
langchain==1.3.18 langchain-core==1.6.1 langgraph==1.2.11
langchain-openrouter==0.2.8 langchain-huggingface==1.2.2
sentence-transformers==6.0.1 faiss-cpu==1.15.0 rank-bm25==0.2.2
```

- Modelo: `init_chat_model("openrouter:google/gemini-3.8-flash", temperature=0)`. Un proveedor es una cadena. **No usar
  `openrouter:auto` para evaluar**: si el modelo cambia entre ejecuciones, baseline vs final no significa nada.
- `temperature=0` en todo lo que se evalúe.
- API **obsoleta** según el propio notebook: `create_react_agent`, `MemorySaver`, `with_structured_output`,
  `RunnableWithMessageHistory`. Hoy: `create_agent`, `InMemorySaver`, `response_format`.
- Límite de bucle previsto para el 17: `ToolCallLimitMiddleware(run_limit=8)` (celda 23). Con `exit_behavior="continue"`
  (el defecto), por sí solo no corta si el modelo insiste; pila del sistema final: D04 del [README](README.md)
  ([09 §2](09_skill_guardrails_middleware_xbrl.md)). Se importa de `langchain.agents.middleware` y se pasa con
  `create_agent(..., middleware=[...])`; `run_limit` cuenta por invocación y `thread_limit` acumula en todo el hilo (venv).
- El baseline de la celda 26 no lleva middleware y el `recursion_limit` por defecto de langgraph 1.2.11 es 10007 (venv): el
  arnés de los dos sistemas pasa `recursion_limit=100` y captura `GraphRecursionError` (D04, [14 §5](14_clase_pistas_del_profesor.md)).
- Embeddings `BAAI/bge-small-en-v1.5`: prefijo `"Represent this sentence for searching relevant passages: "` **solo en
  la consulta**. Omitirlo no da error, solo recupera peor.
- Precios OpenRouter (USD/M tokens, entrada/salida, a 2-sep): gemini-3.5-flash-lite 0,30/2,50 · gemini-3.8-flash
  0,75/3,75 · claude-opus-5 5/25 · claude-fable-5.1 10/50. **Revisar la víspera**.

## 5. Trampas de los datos que ya sabemos

1. `fiscal_year` ≠ año de presentación. Cierres: NVDA enero, MSFT junio, AAPL septiembre, GOOGL/META/AMZN diciembre.
2. El revenue no tiene concepto único: NVDA `Revenues`; AAPL/MSFT/META/AMZN
   `RevenueFromContractWithCustomerExcludingAssessedTax`; GOOGL ambos en FY2024 y solo `Revenues` en FY2025.
3. Huecos reales: AMZN sin `GrossProfit`, `Liabilities` ni `ResearchAndDevelopmentExpense`; META y GOOGL sin `GrossProfit`.
4. NVDA pone los estados financieros en el Item 15; el corpus los sirve bajo `"8"` y lo deja en `item_origen`.
5. El BPA de NVDA baja de 12,05 (FY2024) a 2,97 (FY2025) por el split 10:1 de 2024. Una comparativa ingenua de BPA
   concluiría que cayó un 75 %.
6. `fila.item` en pandas es el método `Series.item`, no la columna: usar `fila["item"]`.
7. Los filtros de `miax_s1.buscar()` se aplican **después** de ordenar todo el índice (post-filtro).

### Fallos del material de la sesión 1 (comprobados leyendo el código)

8. `get_xbrl_fact` del notebook formatea con `:,.0f` y **redondea el BPA a entero** (2,97 sale como "3"). Hay que
   arreglarlo manteniendo los textos que exigen los asserts de §3 (`60,922,000,000` y `no reportó`) (celdas 12 y 17).
9. `create_agent(model=MODELO)` recibe la **cadena** y no la instancia creada con `temperature=0`, así que el agente del
   notebook no evalúa a temperatura 0. Hay que pasar el modelo ya instanciado (celdas 6 y 26). Confirmado en el código: con
   una cadena, `create_agent` hace `init_chat_model(model)` sin `temperature` (venv).
10. Los asserts de §5 (celda 22) **pasan sin implementar el bucle**: `inspect.getsource` encuentra `ToolMessage` y
    `tool_call_id` en los propios comentarios del TODO. La única prueba real es ejecutar la trayectoria.
11. `miax_s1.CANDIDATOS_CORPUS` usa `Path(__file__).resolve().parents[3]`, que lanza `IndexError` en rutas cortas como
    `/content/miax_s1.py` en Colab. Hay que revisarlo al mover el módulo dentro del repo.
12. `demo_traza.json` no tiene `metadatos.fecha` y `demo_apertura()` lanza `KeyError` al final (celda 1).

## 6. Puntos abiertos

- **Comparativas con dos ejercicios:** la celda 30 dice que la comparativa rellena los campos "por cada ejercicio", pero el
  esquema y `validar()` solo admiten un `fiscal_year` y una `cifra_esperada` (celda 32). En el ejemplo
  `ej-003` se usa el FY más reciente y la cifra de ese año. **Resuelto en D10 ([10 §4](10_skill_golden_set.md)):**
  `fiscal_year` = FY reciente, `cifra_esperada` = su nivel XBRL, extras `fiscal_year_base` y `cifra_esperada_base`.
  Se pueden añadir campos, pero no quitarlos.
- **Huecos (R14):** fuera de los 20, en `golden_huecos.jsonl` con `hueco: true` (D11, [10 §5](10_skill_golden_set.md)).
- **`golden_set_ejemplo.jsonl`, `ej-003`:** reutiliza el ancla y el `chunk_id` de `ej-002`, que es de riesgos de IA
  y no de revenue. Pasa el validador, pero no sirve de modelo.
- **Golden set oficial:** el notebook espera `golden_set.jsonl` con 20 preguntas oficiales; aún no está (C28: la tabla va
  sobre el golden propio y el oficial, si llega, es una fila extra).
- **Fecha de entrega:** el profesor dijo en clase que "se entrega el 24" [transcripcion_10sep · 00:00, 00:08], y el notebook
  también fecha la entrega el 24 (celda 0); el enunciado fija el 23-sep a las 23:59 ("justo antes de la sesión 3", §2), y el
  24 son las preguntas ciegas y la presentación. Ante la duda, vale el 23 (C01).
- **Lo que pidió el profesor y la tabla de requisitos no recoge:** elegir y guardar un modelo de embeddings propio [transcripcion_10sep · 02:26,
  02:31] (C27: se mantiene el índice de bge y otro modelo es un experimento opcional, [11 §11](11_skill_mejora_retrieval.md)), y
  que los evaluadores detecten cuándo el agente dice que no hay respuesta y sí la había [transcripcion_10sep · 02:29] (D11: se
  mide la abstención indebida, [12 §7](12_skill_evaluadores.md)).
- **`response_format`:** en clase se llamó "opcional" [transcripcion_10sep · 02:14], pero el enunciado hace obligatoria la
  salida estructurada (R03). Vale el enunciado.
- **"Run all" en Colab:** la agenda del módulo NLP dice que solo se evalúa un "Run all" exitoso. No está claro si
  aplica a esta práctica o a otra del módulo (C29: repo + `evaluar()`, notebook de demo opcional).

Las preguntas para el profesor y lo que queda por verificar al implementar están reunidos en
[README · Pendientes y dudas abiertas](README.md#pendientes-y-dudas-abiertas).
