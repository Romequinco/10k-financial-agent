# Skill: las 4 herramientas y sus docstrings

> Requisitos: R01, R02, R14 (y alimenta R04, R05, R08, R09c y R15) · Lee antes: [05_teoria_agentes_react_tools.md](05_teoria_agentes_react_tools.md) §2 y §7,
> [02_datos_corpus_y_xbrl.md](02_datos_corpus_y_xbrl.md) §1–§6, [01_requisitos_y_contratos.md](01_requisitos_y_contratos.md) §3 y §5 · Después:
> [08 §5](08_skill_agente_salida_estructurada.md) (system prompt y montaje), [11 §9](11_skill_mejora_retrieval.md) (retrieval de `search_filings`),
> [09](09_skill_guardrails_middleware_xbrl.md) (límites y R05), [12 §4](12_skill_evaluadores.md) (trayectoria)

> Fuentes: [enunciado · §4.1, §7]; [notebook S1 · celdas 11–18, 21]; `miax_s1.py` (`buscar()`, `formatear_fragmentos()`); [transcripcion_10sep ·
> 00:31–01:58, 02:12] vía [14 §3](14_clase_pistas_del_profesor.md); [15 §3.8](15_repo_genai_labs.md); [17 §3.3, §3.6](17_repo_generative_ai.md); notas A1
> (R01, R02 y snippets 1, 2 y 4), A5 (R02) y D4 (R01, R02); `perfil_dataset`; [api_stack · langchain.tools.tool, ToolErrorMiddleware]; decisiones
> D09, D11, D12, D21 y D22 del mapa de cobertura (nota interna).

**v1.0 · 12-sep-2026.** El cinturón de herramientas del sistema final: código completo de las cuatro, docstrings de enrutado, tests y cómo medir el
enrutado. Marcas: **(probado)** = ejecutado en el venv del stack (langchain 1.3.18, langchain-core 1.6.1) contra `data/corpus/` real y dentro de
`create_agent` con `GenericFakeChatModel`, sin red (confirma la API y el flujo, no cómo elige Gemini); **(venv)** = introspección del código
instalado; **(datos)** = comprobado sobre el corpus; ⚠️ = sin verificar. Módulos `agente10k/…`: **SUGERENCIA**. **Revisar tras el 17-sep** (solución
del ejercicio 2).

## 1. Qué se construye

Firmas, nombres y `-> str` son contrato: se puede reimplementar el cuerpo, añadir parámetros con valor por defecto y añadir herramientas, pero no
tocar lo que hay; el evaluador de trayectoria del 24 busca estos nombres [enunciado · §7; 01 R01].

| Tool | Baseline (notebook tal cual, D21) | Final (esta skill) |
| --- | --- | --- |
| `list_available` | TODO 1 mínimo: ticker, empresa, FY e items (§4) | + cierre de cada FY, título de cada item y los 13 conceptos; **sin** la lista de huecos |
| `get_xbrl_fact` | Celda 12: igualdad exacta, `:,.0f` (el BPA 2,97 sale "3") y un docstring con 4 conceptos y `'Revenues'` de ejemplo | Normaliza ticker y FY, BPA con 2 decimales, 13 conceptos y regla del revenue, pista cuando el revenue está en el otro concepto, "no reportó… no lo estimes", nunca lanza |
| `search_filings` | `miax_s1.buscar()` + `formatear_fragmentos()`, filtros por igualdad exacta, `k` sin tope | Valida y normaliza filtros, `k` en [1, 10], backend configurable (11 §9), reglas de consulta = las de `INSTRUCCIONES_BUSQUEDA` |
| `read_section` | Texto íntegro o aviso | + cabecera con título, tamaño e item de origen; valida entradas; docstring con coste y "cuándo NO" |

Lo que ve el modelo y lo que no (nombre, parámetros, docstring y resultado, sí; cuerpo, comentarios y coste, no) está en [05 §2](05_teoria_agentes_react_tools.md).

## 2. Reglas de diseño (D22)

1. **Firmas exactas y texto de salida.** `item` sigue siendo `str | None`: pasarlo a `Literal` cambiaría la anotación del contrato [D4 · R02]; el
   vocabulario va en el docstring y se valida en el cuerpo. Nada de `response_format="content_and_artifact"`: el evaluador (a) comprueba la "cita
   vista" contra el **contenido** del `ToolMessage`, que ya trae el texto (C17) [12 §5](12_skill_evaluadores.md).
2. **Normalizar en su capa.** Ticker con `strip`, mayúsculas y alias (`normalizar_ticker` de [09 §4](09_skill_guardrails_middleware_xbrl.md), una sola
   definición); item con `norm_item` de [11 §3](11_skill_mejora_retrieval.md) más `'15'` → `'8'` (NVDA); `fiscal_year` a `int`. "Cada unidad tiene que
   ser completamente independiente, funcional e idempotente" [transcripcion_10sep · 01:24]. Las comparaciones del notebook son de igualdad exacta:
   `"nvda"`, `"GOOG"` o `"Item 1A"` no casaban con nada [01 §5, trampa 9].
3. **Nunca lanzar.** Dentro de `create_agent`, una excepción en el cuerpo **tumba la pregunta entera**; un tipo inválido (`fiscal_year="FY2025"`) o
   una tool inexistente, en cambio, vuelven al modelo como `ToolMessage` con `status="error"` y el bucle sigue **(probado)**. Por eso cada cuerpo va en
   `try/except` y devuelve texto: "te va a petar el programa completamente" [transcripcion_10sep · 00:33–00:36]. `ToolErrorMiddleware` existe pero es
   *opt-in* y no está en la pila de D04 [api_stack · ToolErrorMiddleware].
4. **Errores que enseñan.** Una entrada inválida devuelve los valores válidos y qué hacer; nunca un 0 por defecto (el anti-ejemplo que devuelve `0.0`
   si no encuentra el pedido) [17 §3.3](17_repo_generative_ai.md). El aviso "no reportó" de la celda 12 es lo que separa "no está" de una cifra
   inventada [notebook S1 · celda 12].
5. **Sin volcados.** `k` acotado a 10; `read_section` es la única vía cara y lo dice. Volcar datos masivos por una tool es un "suspenso"
   [transcripcion_10sep · 02:12].
6. **Ninguna tool del contrato llama a otra.** El profesor lo permite en general [transcripcion_10sep · 00:46–00:49], pero la llamada interna no sale
   en la trayectoria y (c) busca los nombres (D12). Compartir funciones internas (`_datos()`) sí.
7. **Huecos, no en `list_available` ni en el prompt** (C16). Si el agente los ve listados contesta "ninguna" sin llamar a `get_xbrl_fact` y
   suspende (c); los huecos los descubre la herramienta. Listarlos es un experimento aparte ([08 §5](08_skill_agente_salida_estructurada.md)).
8. **El concepto no se corrige en silencio.** Ticker e item se normalizan porque los evaluadores también los normalizan; el concepto se compara
   literal en (c) [12 §4](12_skill_evaluadores.md), así que ante `"revenues"` o `"us-gaap:Revenues"` la tool propone el nombre exacto en vez de
   aceptarlo.

## 3. La plantilla del docstring y `parse_docstring`

"El docstring es *prompt engineering*, no documentación": decid cuándo llamarla, cuándo **no** y meted el vocabulario [notebook S1 · celda 18].
Plantilla, en este orden de bloques (separados por una línea en blanco):

1. **Qué hace**, en una frase (para `get_xbrl_fact`, la del enunciado: "valor EXACTO… Úsala SIEMPRE en lugar de leer un número del texto").
2. **Cuándo usarla / Cuándo NO**, con la herramienta alternativa nombrada. "Esa frase vale más que las otras cinco" [notebook S1 · celda 18].
3. **Vocabulario cerrado**: los 13 conceptos con su nombre exacto, la regla del revenue por ticker, los items con su significado y "FY ≠ año de
   presentación" [02 §5–§6](02_datos_corpus_y_xbrl.md). Es el "use only the column names you can see" de text-to-SQL [15 §3.8](15_repo_genai_labs.md);
   el parámetro débil es `concept` [transcripcion_10sep · 00:33].
4. **Devuelve** (formato, unidad, `chunk_id`), **coste** en tokens y **un ejemplo de llamada**; para `search_filings`, además, la regla "lo semántico
   va a `query`; empresa, año y sección, a los filtros" [slides RAG · p.15, p.29].
5. **`Args:`**, al final, una línea por parámetro.

Qué hace `@tool(parse_docstring=True)` (venv, `_parse_google_docstring` de langchain-core 1.6.1; **probado**):

- La descripción que ve el modelo son los bloques **anteriores** a `Args:`, unidos con un espacio. **Todo lo que va después del bloque `Args:` se
  descarta**, y también los bloques que empiezan por `Returns:` o `Example:`. Por eso aquí se escribe "Devuelve:" y "Ejemplo:" y van antes de `Args:`.
- Cada línea de `Args:` pasa a la `description` del parámetro en el esquema JSON; el bloque termina en la primera línea en blanco, y un `Args:` mal
  formado lanza `ValueError` al decorar [api_stack · langchain.tools.tool; 17 §3.3].
- Sin `parse_docstring` (el baseline) el docstring entero, `Args:` incluido, va a la descripción y los parámetros no llevan `description` (venv).

**Coste.** Los esquemas de las cuatro tools del §5 suman unos 6.900 caracteres de JSON (probado), del orden de 1.700–2.000 tokens (⚠️ estimación a
3,5–4 caracteres por token), y viajan en **cada** llamada al modelo junto con el system prompt [17 §3.6](17_repo_generative_ai.md): ≈ 0,0015 $ por
llamada a 0,75 $/M. Es el precio de enrutar bien; se mide con los `input_tokens` de la primera llamada (baseline frente a final) y entra en la columna
de coste. Si un caso raro enruta mal, la solución es "una mejor redacción", no alargar [transcripcion_10sep · 01:58].

## 4. Paso 1: el baseline (D21)

El baseline son las celdas 12–14 **tal cual** (BPA redondeado incluido), el `SYSTEM` de la celda 21 y el TODO 1 resuelto de forma mínima, con el
docstring de la celda 15 [notebook S1 · celdas 12–15, 21]. Cualquier otra cosa es mejora medida y va a la lista de "qué cambió".

```python
# baseline: TODO 1 de la celda 15 (usa `secciones` de la celda 8)
@tool
def list_available() -> str:
    """Lista qué compañías, ejercicios y secciones existen en el corpus.

    Úsala SIEMPRE antes de responder que un dato no existe, y antes de
    llamar a cualquier otra herramienta si no estás seguro de que la
    compañía o el ejercicio que te piden estén en el corpus.
    """
    lineas = []
    for (tk, empresa), g in secciones.groupby(["ticker", "empresa"]):
        fys = ", ".join(f"FY{fy}" for fy in sorted(g["fiscal_year"].astype(int).unique()))
        lineas.append(f"{tk} ({empresa}): {fys} · items {', '.join(sorted(g['item'].unique()))}")
    return "\n".join(lineas)          # "AAPL (Apple Inc.): FY2024, FY2025 · items 1A, 7, 7A, 8" … (probado)
```

## 5. Paso 2: las cuatro herramientas finales

Código completo. Usa `cargar_corpus()` de [02 §7](02_datos_corpus_y_xbrl.md), `normalizar_ticker` de [09 §4](09_skill_guardrails_middleware_xbrl.md) y
`norm_item` de [11 §3](11_skill_mejora_retrieval.md): una definición de cada cosa para las tools, R05, los evaluadores y la escalera.

```python
# agente10k/herramientas.py (SUGERENCIA) · las 4 tools del contrato [enunciado · §7]
from functools import lru_cache

from langchain.tools import tool

from agente10k.datos import cargar_corpus               # 02 §7: ruta configurable, hashes, alineación
from agente10k.normalizacion import normalizar_ticker   # 09 §4: strip, upper y ALIAS (GOOG -> GOOGL...)
from agente10k.retrieval import norm_item              # 11 §3: 'Item 1A', '1a' -> '1A'

FYS = (2024, 2025)
ITEMS = {"1A": "Risk Factors (factores de riesgo)",
         "7": "Management's Discussion and Analysis, MD&A (explicaciones de la dirección)",
         "7A": "Quantitative and Qualitative Disclosures About Market Risk (riesgo de mercado)",
         "8": "Financial Statements and Supplementary Data (estados financieros y notas)"}
REVENUE = ("Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax")
K_MAX = 10
BACKEND = "miax_s1"   # "v2" tras 24: configuración del código, nunca un parámetro que vea el modelo (D09)

@lru_cache(maxsize=1)
def _datos() -> dict:
    """Carga única e índices por clave: sin filtros de pandas en cada llamada ni `fila.item`."""
    secciones, _, xbrl = cargar_corpus()
    return {"hechos": {(r["ticker"], int(r["fiscal_year"]), r["concept"]): r for r in xbrl.to_dict("records")},
            "secciones": {(r["ticker"], int(r["fiscal_year"]), r["item"]): r
                          for r in secciones.to_dict("records")},
            "empresas": dict(zip(secciones["ticker"], secciones["empresa"])),
            "conceptos": sorted(set(xbrl["concept"]))}

def _ticker(t):
    tk = normalizar_ticker(t)
    if tk in _datos()["empresas"]:
        return tk, None
    validas = ", ".join(f"{k} ({v})" for k, v in sorted(_datos()["empresas"].items()))
    return None, f"'{t}' no está en el corpus; compañías disponibles: {validas}."

def _fy(fy):
    try:
        f = int(fy)
    except (TypeError, ValueError):
        f = None
    if f in FYS:
        return f, None
    return None, (f"No hay FY{fy} en el corpus: solo FY2024 y FY2025 (fiscal_year es el ejercicio fiscal, "
                  "no el año de presentación).")

def _item(it):
    i = norm_item(it)
    i = "8" if i == "15" else i           # NVDA publica sus estados en el Item 15; el corpus los sirve como '8'
    if i in ITEMS:
        return i, None
    return None, f"Item '{it}' no válido. Items: " + "; ".join(f"'{k}' {v}" for k, v in ITEMS.items()) + "."

def _fmt(valor: float, unidad: str) -> str:
    """USD: 60,922,000,000 (lo exige el assert de §3). BPA: 2.97, nunca redondeado a entero (01 §5, fallo 8)."""
    return f"{valor:,.2f}" if unidad == "USD/shares" else f"{valor:,.0f}"

@tool(parse_docstring=True)
def list_available() -> str:
    """Universo del corpus: compañías (ticker y nombre), ejercicios fiscales con su fecha de cierre, items y
    los 13 conceptos XBRL. No devuelve cifras ni texto de los informes.

    Cuándo usarla: si la pregunta nombra una compañía, un ejercicio o una sección que no sabes si están en el
    corpus (p. ej. Tesla o FY2023), y antes de responder que una compañía o un ejercicio no están.
    Cuándo NO: si la pregunta ya nombra NVDA, MSFT, AAPL, GOOGL, META o AMZN y FY2024 o FY2025. Tampoco para
    saber si existe una cifra concreta: eso lo dice get_xbrl_fact.

    Devuelve: unas 10 líneas de texto (unos 350 tokens).
    """
    try:
        d = _datos()
        cierres = {(t, f): h["period_end"] for (t, f, _), h in d["hechos"].items()}
        lineas = ["Corpus: informes 10-K de 6 compañías, ejercicios fiscales (FY) 2024 y 2025. Nada más."]
        for tk, empresa in sorted(d["empresas"].items()):
            fys = ", ".join(f"FY{f} (cierre {cierres.get((tk, f), '?')})" for f in FYS)
            lineas.append(f"- {tk} · {empresa}: {fys}")
        lineas.append("Items de cada informe: " + "; ".join(f"'{k}' {v}" for k, v in ITEMS.items()) + ".")
        lineas.append("Conceptos XBRL (get_xbrl_fact): " + ", ".join(d["conceptos"]) + ".")
        lineas.append("Si piden una compañía o un ejercicio fuera de esta lista: fuente='ninguna'.")
        return "\n".join(lineas)
    except Exception as e:                  # en create_agent, una excepción tumba la pregunta entera (probado)
        return f"ERROR interno en list_available ({type(e).__name__}). Continúa sin ella."

@tool(parse_docstring=True)
def get_xbrl_fact(ticker: str, fiscal_year: int, concept: str) -> str:
    """Devuelve el valor EXACTO de una magnitud financiera tal y como la compañía la reportó en XBRL.

    Es la fuente autorizada para cualquier cifra. Úsala SIEMPRE en lugar de leer un número del texto.
    Cuándo usarla: cualquier cifra de la lista de conceptos, una llamada por compañía y ejercicio. En una
    comparativa, dos llamadas con el MISMO concepto, una por ejercicio (puedes pedirlas a la vez).
    Cuándo NO: riesgos, estrategia o por qué cambió una cifra (search_filings). No hay segmentos, trimestres
    ni magnitudes fuera de la lista.

    Conceptos (nombre exacto): Assets (activo total), Liabilities (pasivo total), StockholdersEquity
    (patrimonio neto), CashAndCashEquivalentsAtCarryingValue (caja y equivalentes), NetIncomeLoss (beneficio
    neto), OperatingIncomeLoss (resultado operativo), GrossProfit (beneficio bruto),
    ResearchAndDevelopmentExpense (gasto en I+D), NetCashProvidedByUsedInOperatingActivities (flujo de caja
    operativo), EarningsPerShareBasic y EarningsPerShareDiluted (BPA básico y diluido, en USD/shares),
    Revenues y RevenueFromContractWithCustomerExcludingAssessedTax (ingresos).
    Ingresos (revenue): NVDA y GOOGL usan 'Revenues'; AAPL, MSFT, META y AMZN usan
    'RevenueFromContractWithCustomerExcludingAssessedTax'. Nunca por analogía con otra compañía.
    fiscal_year es el ejercicio fiscal (2024 o 2025), no el año de presentación: NVDA cierra en enero,
    MSFT en junio, AAPL en septiembre y GOOGL, META y AMZN en diciembre.
    Si contesta que la compañía "no reportó" el concepto y no te propone otro para el mismo dato, el dato
    no está en el corpus: no lo estimes ni lo calcules con otros conceptos; responde con fuente='ninguna'.

    Devuelve: una línea con el valor sin redondear, la unidad (USD o USD/shares) y el cierre del ejercicio,
    o el aviso "no reportó" con los conceptos disponibles. Coste: unos 40 tokens.
    Ejemplo: get_xbrl_fact(ticker="MSFT", fiscal_year=2025,
    concept="RevenueFromContractWithCustomerExcludingAssessedTax").

    Args:
        ticker: NVDA, MSFT, AAPL, GOOGL, META o AMZN.
        fiscal_year: Ejercicio fiscal, 2024 o 2025.
        concept: Nombre exacto del concepto us-gaap, uno de la lista.
    """
    try:
        tk, error = _ticker(ticker)
        fy, error = (None, error) if error else _fy(fiscal_year)
        if error:
            return f"No hay datos: {error} Usa list_available para ver qué hay; si no está, fuente='ninguna'."
        d, c = _datos(), str(concept).strip()
        h = d["hechos"].get((tk, fy, c))
        if h is not None:
            u = h["unit"]
            crudo = f"{h['value']:.2f}" if u == "USD/shares" else f"{h['value']:.0f}"
            return (f"{tk} FY{fy} · {c} = {_fmt(h['value'], u)} {u} (cierre de ejercicio {h['period_end']}, "
                    f"según el {h['form']}). Para 'cifra', sin escalar: {crudo}")
        exacto = {x.lower(): x for x in d["conceptos"]}.get(c.lower().removeprefix("us-gaap:"))
        if exacto and exacto != c:          # sin corregir en silencio: (c) compara el nombre (12 §4)
            return f"'{concept}' no es el nombre exacto: ¿querías '{exacto}'? Vuelve a llamar con ese nombre."
        disponibles = sorted(k[2] for k in d["hechos"] if k[:2] == (tk, fy))
        if c not in d["conceptos"]:
            return (f"'{concept}' no es un concepto del corpus. Usa uno de estos (nombre exacto): "
                    f"{', '.join(d['conceptos'])}.")
        if c in REVENUE and (otro := REVENUE[1 - REVENUE.index(c)]) in disponibles:   # no es un hueco (02 §6)
            return (f"{tk} no reportó '{c}' en FY{fy}, pero su revenue está en '{otro}': vuelve a llamar con "
                    "ese concepto.")
        return (f"{tk} no reportó '{c}' en FY{fy}. Si la pregunta pide exactamente ese dato, no está en el "
                f"corpus: no lo estimes ni lo calcules, responde con fuente='ninguna'. Conceptos disponibles "
                f"para {tk} FY{fy}: {', '.join(disponibles)}.")
    except Exception as e:
        return f"ERROR interno en get_xbrl_fact ({type(e).__name__}). No inventes la cifra."

def _buscar(query: str, ticker, fy, item, k: int) -> list[dict]:
    """Dicts con chunk_id, ticker, fiscal_year, item, texto y puntuacion (el formato de miax_s1.buscar)."""
    if BACKEND == "miax_s1":                    # baseline y paso 0 de la escalera [notebook S1 · celda 13]
        import miax_s1
        return miax_s1.buscar(query, ticker=ticker, fiscal_year=fy, item=item, k=k)
    from agente10k.retrieval import CONFIG, buscar_v2, puntuacion_densa, recursos   # 11 §3, §6 y §9
    filas, sim = recursos()["filas"], puntuacion_densa(query)
    ids = buscar_v2([query], ticker, fy, item, k=k, cfg=CONFIG)
    return [{**filas[i], "puntuacion": float(sim[i])} for i in ids]

@tool(parse_docstring=True)
def search_filings(query: str, ticker: str | None = None, fiscal_year: int | None = None,
                   item: str | None = None, k: int = 5) -> str:
    """Busca fragmentos de texto relevantes en los 10-K del corpus. Devuelve k fragmentos, cada uno con su
    chunk_id para poder citarlo.

    Cuándo usarla: preguntas cualitativas (riesgos, estrategia, litigios, por qué subió o bajó una cifra
    según la dirección) y para encontrar la frase literal que vas a citar.
    Cuándo NO: nunca para obtener una cifra, aunque el fragmento traiga números: para eso está get_xbrl_fact.
    Tampoco para saber qué compañías hay (list_available).

    Consulta: query corta, en INGLÉS y con el vocabulario de un 10-K (p. ej. "risks related to AI
    regulation", "drivers of revenue growth"). No pongas la compañía ni el año en query: van en ticker y
    fiscal_year, que pasas siempre que los sepas. fiscal_year es el ejercicio fiscal que nombra la pregunta,
    no el año de presentación. Si la pregunta compara dos ejercicios, haz una llamada por ejercicio con la
    misma query.
    Items: '1A' factores de riesgo; '7' MD&A (la dirección explica por qué cambian las cifras); '7A' riesgo
    de mercado (tipos de interés, divisa); '8' estados financieros y notas. Si no hay resultados, quita item
    o reformula.

    Devuelve: bloques "[chunk_id] TICKER FYaaaa Item X (similitud 0.xxx)" con el texto, separados por '---'.
    Para citar, copia una frase LITERAL de ese texto y su chunk_id. Coste: unos 400 tokens por fragmento
    (k=5, unos 2.000); k máximo 10.
    Ejemplo: search_filings(query="risks from misuse of AI systems by third parties", ticker="MSFT",
    fiscal_year=2025, item="1A", k=5).

    Args:
        query: Qué buscar, en inglés, sin compañía ni año.
        ticker: NVDA, MSFT, AAPL, GOOGL, META o AMZN. Omítelo solo si la pregunta no nombra compañía.
        fiscal_year: 2024 o 2025, el ejercicio fiscal que nombra la pregunta.
        item: '1A', '7', '7A' u '8'.
        k: Número de fragmentos, de 1 a 10.
    """
    try:
        if not str(query or "").strip():
            return "query está vacía: escribe qué buscas, en inglés."
        tk = fy = it = None
        errores = []
        if ticker:
            tk, e = _ticker(ticker)
            errores += [e] if e else []
        if fiscal_year is not None:
            fy, e = _fy(fiscal_year)
            errores += [e] if e else []
        if item:
            it, e = _item(item)
            errores += [e] if e else []
        if errores:
            return "Filtro no válido, no he buscado nada. " + " ".join(errores)
        k_usado = max(1, min(int(k), K_MAX))
        res = _buscar(query, tk, fy, it, k_usado)
        if not res:
            return "Sin resultados con esos filtros. Quita item o reformula la consulta en inglés."
        aviso = f"(k recortado a {k_usado})\n\n" if k_usado != k else ""
        return aviso + "\n\n---\n\n".join(               # mismo formato que miax_s1.formatear_fragmentos()
            f"[{r['chunk_id']}] {r['ticker']} FY{r['fiscal_year']} Item {r['item']} "
            f"(similitud {r['puntuacion']:.3f})\n{r['texto']}" for r in res)
    except Exception as e:
        return f"ERROR interno en search_filings ({type(e).__name__}). Reformula o quita algún filtro."

@tool(parse_docstring=True)
def read_section(ticker: str, fiscal_year: int, item: str) -> str:
    """Devuelve el TEXTO COMPLETO de una sección (Item) de un 10-K. Es CARA: hasta 35.000 tokens.

    Cuándo usarla: solo si search_filings, tras reformular, no encuentra el pasaje y necesitas el contexto
    entero de UNA sección. El Item 7A es corto (400 a 1.900 tokens): leerlo cuesta como una búsqueda.
    Cuándo NO: nunca para cifras (get_xbrl_fact); nunca para localizar una frase (search_filings con item);
    nunca varias secciones "por si acaso". Como mucho, dos por pregunta.

    Coste: '1A' de 10.000 a 35.000 tokens; '7' de 3.800 a 12.600; '8' de 16.000 a 32.400; '7A' de 400 a
    1.900. Todo lo que devuelve se vuelve a pagar en cada paso posterior del agente.
    Items: '1A' factores de riesgo; '7' MD&A; '7A' riesgo de mercado; '8' estados financieros y notas (los de
    NVDA están en su Item 15 y aquí se sirven como '8'). fiscal_year es el ejercicio fiscal (2024 o 2025),
    no el año de presentación.

    Devuelve: una cabecera con el tamaño y el texto íntegro de la sección.
    Ejemplo: read_section(ticker="AAPL", fiscal_year=2024, item="7A").

    Args:
        ticker: NVDA, MSFT, AAPL, GOOGL, META o AMZN.
        fiscal_year: Ejercicio fiscal, 2024 o 2025.
        item: '1A', '7', '7A' u '8'.
    """
    try:
        (tk, e1), (fy, e2), (it, e3) = _ticker(ticker), _fy(fiscal_year), _item(item)
        if e1 or e2 or e3:
            return "No hay esa sección. " + " ".join(e for e in (e1, e2, e3) if e) + " Usa list_available."
        s = _datos()["secciones"].get((tk, fy, it))
        if s is None:
            return f"No hay Item {it} de {tk} FY{fy} en el corpus. Usa list_available para ver qué hay."
        origen = f" En el 10-K original es el Item {s['item_origen']}." if s["item_origen"] != it else ""
        cabecera = f"[{tk} FY{fy} Item {it} · {s['titulo']} · {int(s['n_tokens']):,} tokens]{origen}"
        return f"{cabecera}\n\n{s['texto']}"
    except Exception as e:
        return f"ERROR interno en read_section ({type(e).__name__}). Prueba search_filings con item."

TOOLS = [list_available, get_xbrl_fact, search_filings, read_section]      # orden fijo
```

Qué devuelve (probado, contra el corpus real):

```text
NVDA 2024 Revenues   -> NVDA FY2024 · Revenues = 60,922,000,000 USD (cierre de ejercicio 2024-01-28, según el 10-K). Para 'cifra', sin escalar: 60922000000
NVDA 2025 EPS básico -> NVDA FY2025 · EarningsPerShareBasic = 2.97 USD/shares (…). Para 'cifra', sin escalar: 2.97
AAPL 2025 Revenues   -> AAPL no reportó 'Revenues' en FY2025, pero su revenue está en 'RevenueFrom…ExcludingAssessedTax': vuelve a llamar con ese concepto.
AMZN 2025 GrossProfit-> AMZN no reportó 'GrossProfit' en FY2025. Si la pregunta pide exactamente ese dato, no está en el corpus: … fuente='ninguna'. …
read_section NVDA 8  -> [NVDA FY2025 Item 8 · Financial Statements and Supplementary Data · 27,209 tokens] En el 10-K original es el Item 15. …
list_available()     -> 10 líneas, 1.294 caracteres: "- AAPL · Apple Inc.: FY2024 (cierre 2024-09-28), FY2025 (cierre 2025-09-27)" …
```

- **`get_xbrl_fact`.** Conserva los dos textos que exigen los asserts de §3 (`60,922,000,000` y `no reportó`) y deja de redondear el BPA: 12,05 y
  11,93 (básico y diluido de NVDA FY2024) ya no salen los dos como "12" [01 §5, fallo 8]. La cola "Para 'cifra', sin escalar" ataca el error de
  escala (`cifra=60922` con `unidad="USD"`) que vigila R05 [08 §13, trampa 6](08_skill_agente_salida_estructurada.md). De las 21 celdas vacías del
  parquet, 11 son el revenue bajo el otro concepto y no un hueco [02 §6, trampa 2]: la pista evita la **abstención indebida**. Los 10 huecos reales
  reciben "no reportó… fuente='ninguna'" (R14). El formato del `ToolMessage` no es contrato: R05 y (b) buscan en el parquet por los `args`, nunca
  parsean este texto [02 §6, trampa 8].
- **`search_filings`.** El día 1 envuelve `miax_s1.buscar()` (paso 0 de la escalera); tras [11](11_skill_mejora_retrieval.md), `BACKEND = "v2"` pasa a
  `buscar_v2` con la `CONFIG` fija, sin tocar firma ni docstring. Los tipos ya los valida `@tool` antes del cuerpo: `"2025"` entra como 2025 y
  `"FY2025"` vuelve al modelo como error [11 §9]. Un filtro inválido no se ignora en silencio: un filtro erróneo deja el recall a 0 [11 §5].
- **`read_section`.** La cabecera deja el tamaño en la trayectoria y aclara el Item 15 de NVDA; el texto va íntegro, así que la "cita vista" de (a)
  sigue funcionando. Parámetros nuevos con valor por defecto (p. ej. `parte: int = 1` para paginar) están permitidos, pero multiplican las llamadas
  contra `ToolCallLimitMiddleware(tool_name="read_section", run_limit=2)` de D04: solo como experimento medido.
- **`list_available`.** Lo que pidió el profesor, lo más concisa posible: empresa, ejercicios e items, mejor con su título; sin texto, tokens ni URL
  [transcripcion_10sep · 01:19]. Tiene sentido aunque el universo vaya también en el prompt (C15): es contrato y es la vía para "Tesla" o "el
  Santander de 2005" [transcripcion_10sep · 01:09, 01:23].

## 6. Paso 3: system prompt y coherencia

El texto del `SYSTEM` final está en [08 §5](08_skill_agente_salida_estructurada.md): universo, reglas de enrutado, qué hacer si el dato no está,
comparativas, semántica de `fuente` y cita literal, **sin** huecos (D22). Docstrings y prompt no pueden contradecirse:

| Regla | Docstring | `SYSTEM` (08 §5) |
| --- | --- | --- |
| Toda cifra sale de `get_xbrl_fact`, una llamada por compañía y FY | `get_xbrl_fact`, `search_filings` ("Cuándo NO") | "Enrutado" |
| Consulta en inglés, sin compañía ni año; filtros siempre que se sepan | `search_filings` | "Enrutado" |
| `list_available` solo ante la duda | `list_available` | "Enrutado" |
| Comparativa: dos `get_xbrl_fact` con el mismo concepto + una `search_filings` por FY con la misma query | `get_xbrl_fact`, `search_filings` | "Comparativas" |
| "No reportó" sin alternativa → `fuente="ninguna"`, sin estimar | `get_xbrl_fact` | "Si el dato no está" |
| `read_section`, último recurso | `read_section` | "Enrutado" |

Las reglas de la consulta son las mismas que las de `INSTRUCCIONES_BUSQUEDA`, el reescritor en modo aislado de [11 §7](11_skill_mejora_retrieval.md),
porque dentro del agente reescribe el propio modelo al rellenar `query` (D09). Un test lo comprueba (§8).

## 7. Paso 4: experimento docstring vago frente a preciso (R02, R15)

El ejercicio 2 de la celda 17, medido. Mejora sobre el notebook: la variante vaga conserva el **nombre** `get_xbrl_fact` (en la celda 17 se llama
`get_xbrl_fact_vago`), así que lo único que cambia es la descripción. `tool(nombre, description=…)` sobre la función cruda da un esquema sin
descripciones de parámetros (probado). La pregunta de la celda es la primera de la lista; el resto no es del golden, para no afinar contra él.

```python
# experimentos/docstrings.py (SUGERENCIA) · necesita la clave; cuesta céntimos
from pathlib import Path

import pandas as pd
from langchain.tools import tool

from agente10k.herramientas import get_xbrl_fact, list_available, read_section, search_filings

vago = tool("get_xbrl_fact", description="Devuelve un dato financiero.")(get_xbrl_fact.func)  # mismo nombre y cuerpo
VARIANTES = {"preciso": [list_available, get_xbrl_fact, search_filings, read_section],
             "vago": [list_available, vago, search_filings, read_section]}
PREGUNTAS = [   # (pregunta, tool esperada, concepto esperado)
    ("¿Cuál fue el beneficio neto de Apple en el ejercicio 2025?", "get_xbrl_fact", "NetIncomeLoss"),   # celda 17
    ("¿Qué ingresos reportó Meta en FY2024?", "get_xbrl_fact", "RevenueFromContractWithCustomerExcludingAssessedTax"),
    ("¿Cuál fue el BPA diluido de Alphabet en FY2025?", "get_xbrl_fact", "EarningsPerShareDiluted"),
    ("¿Qué dice Microsoft sobre la regulación de la IA en sus riesgos de FY2025?", "search_filings", None),
]

def experimento_docstrings(modelo, repeticiones: int = 2, ruta="resultados/experimentos/docstrings.csv") -> list[dict]:
    filas = []
    for variante, tools in VARIANTES.items():
        con_tools = modelo.bind_tools(tools)                 # `modelo`: la instancia a temperature=0 (D01)
        for pregunta, tool_esp, concepto_esp in PREGUNTAS:
            for rep in range(repeticiones):                  # 2 pasadas: ruido a temperature=0 (D21)
                r = con_tools.invoke([{"role": "user", "content": pregunta}])
                tc = r.tool_calls[0] if r.tool_calls else {"name": "(ninguna)", "args": {}}
                filas.append({"variante": variante, "pregunta": pregunta, "rep": rep, "tool": tc["name"],
                              "args": tc["args"], "tool_ok": tc["name"] == tool_esp,
                              "concepto_ok": concepto_esp is None or tc["args"].get("concept") == concepto_esp,
                              "input_tokens": (r.usage_metadata or {}).get("input_tokens")})
    Path(ruta).parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(filas).to_csv(ruta, index=False)            # regenerable desde el repo (R12)
    return filas
```

- Qué se reporta: `tool_ok` y `concepto_ok` por variante (k/n) y la diferencia de `input_tokens`, que es lo que cuesta el docstring preciso en cada
  llamada. La pregunta de la celda 17 es justo esa: "¿de dónde iba a sacar el nombre correcto con el docstring vago?" [notebook S1 · celda 17].
- La misma función sirve para la celda 16 (Tesla, con y sin `list_available` en la lista). En clase no salió: "a lo mejor he puesto un modelo más
  tonto" [transcripcion_10sep · 01:54]. Si con Gemini no hay diferencia, **es un resultado** (R15).

## 8. Paso 5: tests sin LLM ni red

```python
# tests/test_herramientas.py (SUGERENCIA) · pytest; necesita el corpus (02 §8), no la clave
import pytest
from langchain_core.utils.function_calling import convert_to_openai_tool

import agente10k.herramientas as H
from agente10k.herramientas import TOOLS, get_xbrl_fact, list_available, read_section, search_filings
from agente10k.retrieval import INSTRUCCIONES_BUSQUEDA                                        # 11 §7

def X(t, fy, c):
    return get_xbrl_fact.invoke({"ticker": t, "fiscal_year": fy, "concept": c})

def test_asserts_de_la_celda_17():
    assert "NVDA" in list_available.invoke({})
    assert "60,922,000,000" in X("NVDA", 2024, "Revenues")
    assert "no reportó" in X("AMZN", 2025, "GrossProfit")

def test_bpa_y_normalizacion():
    assert "2.97 USD/shares" in X("NVDA", 2025, "EarningsPerShareBasic")                       # no "3"
    assert "12.05" in X("NVDA", 2024, "EarningsPerShareBasic") and "11.93" in X("NVDA", 2024, "EarningsPerShareDiluted")
    assert X("nvda ", "2024", "Revenues") == X("NVDA", 2024, "Revenues")                        # "2024": lo convierte @tool
    assert "402,836,000,000" in X("GOOG", 2025, "Revenues")

def test_revenue_no_es_hueco_y_el_hueco_si():
    r = X("AAPL", 2025, "Revenues")
    assert "RevenueFromContractWithCustomerExcludingAssessedTax" in r and "ninguna" not in r
    assert "fuente='ninguna'" in X("AMZN", 2024, "Liabilities")

@pytest.mark.parametrize("t, fy, c", [("TSLA", 2025, "Revenues"), ("NVDA", 2023, "Revenues"),
                                      ("NVDA", 2024, "Revenue"), ("NVDA", 2024, "us-gaap:Revenues")])
def test_entrada_invalida_da_texto_sin_valor(t, fy, c):
    r = X(t, fy, c)
    assert isinstance(r, str) and " = " not in r                                                 # ni excepción ni 0

def test_read_section_y_list_available():
    assert "34,751 tokens" in read_section.invoke({"ticker": "meta", "fiscal_year": 2025, "item": "Item 1A"})
    assert "Item 15" in read_section.invoke({"ticker": "NVDA", "fiscal_year": 2025, "item": "8"})
    assert "list_available" in read_section.invoke({"ticker": "AAPL", "fiscal_year": 2025, "item": "9"})
    t = list_available.invoke({})
    assert t.count("GrossProfit") == 1 and "no reportó" not in t                                # sin huecos (C16)

def test_search_filings_valida_y_formatea(monkeypatch):
    llamadas = []
    def falso(q, tk, fy, it, k):
        llamadas.append((q, tk, fy, it, k))
        return [{"chunk_id": "MSFT-2025-1A-0004", "ticker": "MSFT", "fiscal_year": 2025, "item": "1A",
                 "texto": "Texto.", "puntuacion": 0.74}]
    monkeypatch.setattr(H, "_buscar", falso)
    r = search_filings.invoke({"query": "misuse of AI", "ticker": "microsoft", "fiscal_year": 2025,
                               "item": "item 1a", "k": 50})
    assert llamadas[-1] == ("misuse of AI", "MSFT", 2025, "1A", 10) and "[MSFT-2025-1A-0004]" in r
    assert "no he buscado" in search_filings.invoke({"query": "x", "ticker": "TSLA"})
    monkeypatch.setattr(H, "_buscar", lambda *a: 1 / 0)
    assert search_filings.invoke({"query": "x"}).startswith("ERROR interno")                  # nunca lanza

def test_lo_que_ve_el_modelo():
    for t in TOOLS:
        f = convert_to_openai_tool(t)["function"]
        assert "Cuándo NO" in f["description"] and "Devuelve:" in f["description"]             # nada perdido tras Args
        assert all(p.get("description") for p in f["parameters"].get("properties", {}).values())
    assert all(c in get_xbrl_fact.description for c in H._datos()["conceptos"])                # los 13, exactos
    for es, en in [("INGLÉS", "ENGLISH"), ("ni el año", "or the year"),
                   ("no el año de presentación", "not the filing year"), ("dos ejercicios", "two fiscal years")]:
        assert es in search_filings.description and en in INSTRUCCIONES_BUSQUEDA              # mismas reglas (11 §7)
```

Probado así: todos los casos anteriores contra el corpus real, más las cuatro tools dentro de `create_agent` con un modelo falso: dos
`get_xbrl_fact` en el mismo `AIMessage` (`"msft"` normalizado) devuelven dos `ToolMessage` con su `tool_call_id`, `item="7a"` llega como `"7A"` y
un fallo interno de carga vuelve como texto sin romper el bucle. El test de `search_filings` con el backend real (bge, ~130 MB) va aparte, en la
escalera de [11](11_skill_mejora_retrieval.md).

## 9. Paso 6: medir el enrutado (R15)

"Cómo enruta el agente entre la herramienta exacta y la difusa" es un punto obligatorio de la presentación [enunciado · §5]. Tres medidas, todas
desde los ficheros de resultados (D19):

- **% de filtros correctos** en cada `search_filings` (ticker, FY e item: ok / ausente / erróneo): `filtros_agente()` de
  [11 §5](11_skill_mejora_retrieval.md). Depende del docstring, no del índice.
- **P/R/F1 por herramienta** y **concepto correcto** en `get_xbrl_fact` (`c_args_ok`): `enrutado()` y `evaluar_trayectoria()` de
  [12 §4](12_skill_evaluadores.md).
- **Matriz familia × herramienta**, la tabla de la diapositiva:

```python
# agente10k/informe.py (continúa, SUGERENCIA) · filas con "golden" y "tool_calls" (lista blanca, 12-13)
HERRAMIENTAS = ("list_available", "get_xbrl_fact", "search_filings", "read_section")

def matriz_enrutado(filas: list[dict]) -> dict:
    """k/n de las preguntas de cada familia que usaron cada herramienta al menos una vez."""
    m = {}
    for f in filas:
        fam = "hueco" if f["golden"].get("hueco") else f["golden"].get("familia")
        usadas = {tc["name"] for tc in f["tool_calls"]}
        n, cuenta = m.get(fam, (0, dict.fromkeys(HERRAMIENTAS, 0)))
        m[fam] = (n + 1, {h: cuenta[h] + (h in usadas) for h in HERRAMIENTAS})
    return {fam: {h: f"{c}/{n}" for h, c in cuenta.items()} for fam, (n, cuenta) in m.items()}
```

Lectura esperada del sistema final: `numerica` y `hueco` → `get_xbrl_fact` en n/n; `extractiva` → `search_filings` sin `get_xbrl_fact`;
`comparativa` → las dos; `read_section`, cerca de 0. Baseline frente a final, en la misma tabla.

## 10. Trampas

1. Poner "Returns:" o "Example:" en el docstring, o cualquier texto después de `Args:`, con `parse_docstring=True`: el modelo no lo ve (venv).
2. Dejar `get_xbrl_fact_vago` en la lista final: el evaluador busca los nombres exactos [notebook S1 · celda 17].
3. `'Revenues'` como único ejemplo: no existe en AAPL, MSFT, META ni AMZN [01 §5, trampa 2].
4. Un cuerpo que lanza: en `create_agent` aborta la pregunta; en `evaluar()` se convierte en *fallback* y fallo (probado).
5. Listar los huecos en `list_available` o en el docstring "para evitar el bucle": arregla R04 a costa de (c) [09 §11](09_skill_guardrails_middleware_xbrl.md).
6. Corregir el concepto en silencio: la tool acierta y (c) suspende por el nombre (§2, regla 8).
7. `fila.item` en pandas es un método: corchetes, o índices por clave como en `_datos()` [01 §5, trampa 6].
8. Cambiar el modo de búsqueda con un parámetro visible para el modelo: la escalera deja de ser comparable (D09).
9. Olvidar que el docstring se paga en cada llamada: medirlo, no suponerlo (§3).

## Checklist de hecho

- [ ] **R01** · Las cuatro tools con nombres, parámetros y `-> str` idénticos al contrato; `TOOLS` en orden fijo; ninguna llama a otra del contrato.
- [ ] **R01** · Los asserts de la celda 17 pasan: `"NVDA"`, `"60,922,000,000"` y `"no reportó"`; el BPA sale con dos decimales.
- [ ] **R01** · Entradas normalizadas (alias de ticker, item, FY) y `k` en [1, 10]; ninguna entrada inválida lanza ni devuelve un 0 (tests del §8).
- [ ] **R02** · Cada docstring sigue la plantilla (qué hace, cuándo sí, cuándo NO, vocabulario, devuelve, coste, ejemplo, `Args:` al final) y el
      esquema JSON conserva todo (test `test_lo_que_ve_el_modelo`).
- [ ] **R02** · `get_xbrl_fact` enumera los 13 conceptos exactos, la regla del revenue por ticker y "FY ≠ año de presentación"; `search_filings` y
      `read_section` enumeran `'1A'`, `'7'`, `'7A'` y `'8'` con su significado.
- [ ] **R02** · Reglas de consulta idénticas en `search_filings` e `INSTRUCCIONES_BUSQUEDA`; docstrings coherentes con el `SYSTEM` de 08 §5.
- [ ] **R14** · "No reportó… fuente='ninguna'" en los 10 huecos, pista del revenue en las 11 celdas que no lo son, y `list_available` sin huecos.
- [ ] **R15** · Experimento vago/preciso ejecutado y guardado (`docstrings.csv`); matriz familia × herramienta y % de filtros correctos generados
      desde los resultados, para baseline y final.
- [ ] Baseline congelado con las tools del notebook tal cual (§4) antes de sustituirlas por las del §5 (D21).

## Fuentes

- [enunciado · §1, §4.1, §5, §7]: contrato de las herramientas, criterio de corrección y punto de enrutado de la presentación.
- [01 §3, §5](01_requisitos_y_contratos.md): firmas, coste relativo, trampas 2, 3, 6 y 9 y fallo 8.
- [notebook S1 · celdas 8, 11–18, 21]: tools de partida, TODO 1, experimento de la celda 16, ejercicio 2 y asserts de §3, reglas del docstring y `SYSTEM`.
- `miax_s1.py`: `buscar()` (post-filtro, formato de resultados) y `formatear_fragmentos()`.
- [transcripcion_10sep · 00:31–00:49, 01:09, 01:19–01:24, 01:47, 01:54–01:58, 02:12], vía [14 §2–§3](14_clase_pistas_del_profesor.md).
- [15 §3.8](15_repo_genai_labs.md) (anti-ejemplos de descripción, vocabulario cerrado); [17 §3.3, §3.6](17_repo_generative_ai.md) (errores como datos,
  `parse_docstring`, coste del prompt); notas A1 (R01, R02, snippets 1, 2 y 4), A5 (R02: [slides RAG · p.15, p.29]) y D4 (R01, R02).
- [02 §1–§6](02_datos_corpus_y_xbrl.md), `perfil_dataset`: items y títulos, cierres, cobertura XBRL, tokens por sección.
- [api_stack · langchain.tools.tool, ToolErrorMiddleware, create_agent]; venv: `_parse_google_docstring`, `_default_handle_tool_errors`,
  `convert_to_openai_tool`.
- Docs hermanos: [08 §5, §13](08_skill_agente_salida_estructurada.md), [09 §2, §4, §11](09_skill_guardrails_middleware_xbrl.md),
  [11 §3, §5, §7, §9](11_skill_mejora_retrieval.md), [12 §4, §5](12_skill_evaluadores.md).
