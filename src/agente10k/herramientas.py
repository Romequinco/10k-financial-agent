"""Las cuatro herramientas del contrato para consultar el corpus 10-K."""
from __future__ import annotations

from contextvars import ContextVar
from functools import lru_cache
import re
import unicodedata

from langchain.tools import tool

from agente10k import datos, retrieval

# Pregunta del usuario en curso. El arnés (agente.responder / evaluadores) la fija al empezar cada
# ejecución; la herramienta de búsqueda final la usa para inferir ticker y ejercicio que el modelo
# no pase. Es una ContextVar: LangGraph copia el contexto a los hilos de las herramientas.
PREGUNTA_ACTUAL: ContextVar[str | None] = ContextVar("PREGUNTA_ACTUAL", default=None)


def fijar_pregunta_actual(texto: str) -> None:
    """Registra la pregunta en curso (cadena vacía o None la borra)."""
    PREGUNTA_ACTUAL.set(str(texto).strip() or None if texto is not None else None)


TICKER_ALIASES = {
    "ALPHABET": "GOOGL", "AMAZON": "AMZN", "APPLE": "AAPL",
    "GOOG": "GOOGL", "GOOGLE": "GOOGL", "META PLATFORMS": "META",
    "MICROSOFT": "MSFT", "NVIDIA": "NVDA",
}
FISCAL_YEARS = (2024, 2025)
ITEMS = {
    "1A": "factores de riesgo", "7": "discusión de la dirección (MD&A)",
    "7A": "riesgo de mercado", "8": "estados financieros y notas",
}
REVENUE_CONCEPTS = ("Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax")
K_MAX = 10


@lru_cache(maxsize=1)
def _recursos() -> dict:
    """Carga una vez los datos y crea accesos deterministas por clave."""
    secciones = datos.cargar_secciones()
    xbrl = datos.cargar_xbrl()
    empresas = (secciones[["ticker", "empresa"]].drop_duplicates()
                .set_index("ticker")["empresa"].to_dict())
    return {
        "secciones": {(str(r["ticker"]), int(r["fiscal_year"]), str(r["item"])): r
                       for r in secciones.to_dict("records")},
        "hechos": {(str(r["ticker"]), int(r["fiscal_year"]), str(r["concept"])): r
                    for r in xbrl.to_dict("records")},
        "empresas": empresas,
        "conceptos": sorted(str(c) for c in xbrl["concept"].unique()),
    }


def _normalizar_ticker(valor: object) -> str:
    ticker = str(valor or "").strip().upper()
    return TICKER_ALIASES.get(ticker, ticker)


def _normalizar_fiscal_year(valor: object) -> int | None:
    try:
        return int(valor)
    except (TypeError, ValueError):
        anio = re.search(r"(?<!\d)(20\d\d)(?!\d)", str(valor))   # 'FY2025' -> 2025
        return int(anio.group(1)) if anio else None


def _eco(valor: object, limite: int = 24) -> str:
    """Un argumento ilegible puede medir cientos de caracteres: se repite recortado."""
    texto = str(valor)
    return texto if len(texto) <= limite else texto[:limite] + "…"


_RE_BASURA = re.compile(r"""["',{}<>\n]""")
_RE_PAR_JSON = re.compile(r"""["']?\b(ticker|fiscal_year|item|concept)\b["']?\s*[:=]\s*["']?"""
                          r"""([A-Za-z0-9_.:\- ]{1,60}?)["']?\s*(?=[,}<"'\]]|$)""")
_RE_PAR_TAG = re.compile(r"<arg_key>\s*(ticker|fiscal_year|item|concept)\s*</arg_key>\s*"
                         r"<arg_value>\s*([^<]{1,60}?)\s*</arg_value>")


def _desenredar(valor: object) -> tuple[object, dict]:
    """Rescata un identificador corrupto por el modelo.

    Algunos modelos vuelcan la llamada entera dentro de un argumento (visto en el baseline:
    ticker='AMZN", "fiscal_year": 2025, "item": "7"…</think><tool_call>…'). Devuelve la cabeza limpia
    ('AMZN') y los campos válidos que aparecían dentro de la cadena, para rellenar los que falten.
    """
    if not isinstance(valor, str) or (len(valor) <= 40 and not _RE_BASURA.search(valor)):
        return valor, {}
    cabeza = _RE_BASURA.split(valor.strip().lstrip("\"'"), maxsplit=1)[0].strip()
    campos: dict = {}
    for patron in (_RE_PAR_JSON, _RE_PAR_TAG):
        for m in patron.finditer(valor):
            campos.setdefault(m.group(1), m.group(2).strip())
    return cabeza, campos


_RE_ANIO = re.compile(r"^(19|20)\d{2}$")


def _desapelmazar_ticker(valor: object) -> tuple[object, dict]:
    """Rescata un ticker al que el modelo pegó el resto de la llamada separado por espacios.

    Visto en una tanda real: ticker='GOOGL 2025 1A antitrust competition regulatory...'. Sin
    delimitadores no hay nada que desenredar, la herramienta rechazaba la búsqueda y el modelo
    repetía la misma llamada hasta agotar el límite. Solo se aplica al ticker (los conceptos
    admiten alias en español con espacios, como 'beneficio bruto', y no deben partirse).
    """
    if not isinstance(valor, str) or " " not in valor.strip():
        return valor, {}
    cabeza, *resto = valor.split()
    if _normalizar_ticker(cabeza) not in _recursos()["empresas"]:
        return valor, {}                      # la cabeza no es un ticker: no tocar nada
    campos: dict = {}
    for token in resto:
        limpio = token.strip("\"',")
        if _RE_ANIO.match(limpio):
            campos.setdefault("fiscal_year", limpio)
        elif _normalizar_item(limpio) in ITEMS:
            campos.setdefault("item", _normalizar_item(limpio))
    return cabeza, campos


def _limpiar_args(**args) -> dict:
    """Desenreda los argumentos-identificador y rellena solo los que faltan con lo rescatado."""
    limpios, rescatados = {}, {}
    for nombre, valor in args.items():
        limpios[nombre], extras = _desenredar(valor)
        if nombre == "ticker":
            limpios[nombre], extras_pegados = _desapelmazar_ticker(limpios[nombre])
            extras = {**extras_pegados, **extras}
        for campo, dato in extras.items():
            rescatados.setdefault(campo, dato)
    for campo, dato in rescatados.items():
        if campo in limpios and limpios[campo] in (None, ""):
            limpios[campo] = dato
    return limpios


def _normalizar_item(valor: object) -> str:
    item = str(valor or "").strip().upper()
    if item.startswith("ITEM"):
        item = item[4:].strip()
    item = item.rstrip(".")
    return "8" if item == "15" else item


def _validar_ticker(valor: object) -> tuple[str | None, str | None]:
    ticker = _normalizar_ticker(valor)
    if ticker in _recursos()["empresas"]:
        return ticker, None
    return None, (f"Ticker '{_eco(valor)}' no disponible. Pasa solo el ticker, sin comillas ni otros campos. "
                  f"Usa uno de: {', '.join(sorted(_recursos()['empresas']))}.")


def _validar_fiscal_year(valor: object) -> tuple[int | None, str | None]:
    fiscal_year = _normalizar_fiscal_year(valor)
    if fiscal_year in FISCAL_YEARS:
        return fiscal_year, None
    return None, (f"Ejercicio fiscal '{_eco(valor)}' no disponible. Usa FY2024 o FY2025; "
                  "el ejercicio fiscal no es el año de presentación.")


def _validar_item(valor: object) -> tuple[str | None, str | None]:
    item = _normalizar_item(valor)
    if item in ITEMS:
        return item, None
    validos = "; ".join(f"'{clave}' {titulo}" for clave, titulo in ITEMS.items())
    return None, f"Item '{_eco(valor)}' no disponible. Items validos: {validos}."


def _formatear_valor(valor: float, unidad: str) -> str:
    return f"{float(valor):,.2f}" if unidad == "USD/shares" else f"{float(valor):,.0f}"


def _clave(texto: object) -> str:
    """Forma comparable de un nombre de concepto: sin acentos, sin prefijo us-gaap, solo letras y cifras."""
    plano = unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode().lower().strip()
    return re.sub(r"[^a-z0-9]", "", re.sub(r"^us-?gaap[:_]", "", plano))


# Equivalencias ES/EN -> concepto XBRL. Solo se autoresuelven las inequívocas; las que pueden ser
# dos conceptos (BPA básico/diluido, ingresos según empresa) devuelven guía en lugar de adivinar.
_EQUIVALENCIAS = {
    "Assets": ("activos", "activo total", "activos totales", "total assets"),
    "Liabilities": ("pasivo", "pasivos", "pasivo total", "pasivos totales", "total liabilities"),
    "StockholdersEquity": ("patrimonio neto", "patrimonio", "fondos propios", "capital contable", "equity",
                           "shareholders equity", "stockholders equity", "total equity",
                           "total stockholders equity"),
    "CashAndCashEquivalentsAtCarryingValue": ("caja", "efectivo", "caja y equivalentes", "efectivo y equivalentes",
                                              "caja y equivalentes de caja", "cash", "cash and cash equivalents"),
    "NetIncomeLoss": ("beneficio neto", "resultado neto", "ganancia neta", "ganancias netas", "utilidad neta",
                      "net income", "net earnings", "net profit"),
    "OperatingIncomeLoss": ("beneficio operativo", "resultado operativo", "resultado de explotacion",
                            "utilidad operativa", "operating income", "operating profit", "ebit"),
    "GrossProfit": ("beneficio bruto", "utilidad bruta", "ganancia bruta", "gross profit", "gross income"),
    "ResearchAndDevelopmentExpense": ("gasto en i+d", "gastos en i+d", "gasto de i+d", "i+d", "i+d+i",
                                      "investigacion y desarrollo", "gasto en investigacion y desarrollo",
                                      "r&d", "r&d expense", "research and development",
                                      "research & development"),
    "NetCashProvidedByUsedInOperatingActivities": (
        "flujo de caja operativo", "flujo de caja de operaciones", "flujo de caja de las operaciones",
        "flujos de caja operativos", "flujo de efectivo operativo", "flujo de caja de actividades operativas",
        "operating cash flow", "cash flow from operations", "cash from operations",
        "cash flow from operating activities", "net cash from operating activities", "cfo"),
    "EarningsPerShareBasic": ("bpa basico", "beneficio por accion basico", "ganancias por accion basicas",
                              "basic eps", "eps basic", "eps basico", "basic earnings per share"),
    "EarningsPerShareDiluted": ("bpa diluido", "beneficio por accion diluido", "ganancias por accion diluidas",
                                "diluted eps", "eps diluted", "eps diluido", "diluted earnings per share"),
}
_AMBIGUAS = {
    ("EarningsPerShareBasic", "EarningsPerShareDiluted"): (
        "bpa", "eps", "beneficio por accion", "ganancias por accion", "ganancia por accion",
        "utilidad por accion", "earnings per share"),
    REVENUE_CONCEPTS: ("revenue", "ingresos", "ingresos totales", "ventas", "ventas netas", "net sales",
                       "sales", "total revenue", "total revenues", "facturacion"),
}
_ALIAS_A_CONCEPTO = {_clave(alias): concepto for concepto, alias_ in _EQUIVALENCIAS.items() for alias in alias_}
_ALIAS_AMBIGUO = {_clave(alias): opciones for opciones, alias_ in _AMBIGUAS.items() for alias in alias_}
EQUIVALENCIAS_TXT = ("Equivalencias: beneficio bruto=GrossProfit; gasto en I+D=ResearchAndDevelopmentExpense; "
                     "patrimonio neto=StockholdersEquity; flujo de caja operativo="
                     "NetCashProvidedByUsedInOperatingActivities; caja=CashAndCashEquivalentsAtCarryingValue; "
                     "BPA=EarningsPerShareBasic o EarningsPerShareDiluted; pasivo=Liabilities; activo=Assets; "
                     "beneficio neto=NetIncomeLoss; beneficio operativo=OperatingIncomeLoss; ingresos="
                     "Revenues o RevenueFromContractWithCustomerExcludingAssessedTax (según la empresa).")


def _resolver_concepto(pedido: str, conceptos: list[str]) -> tuple[str | None, tuple[str, ...]]:
    """Concepto exacto para lo pedido (mayúsculas, prefijo us-gaap:, alias) o las opciones si es ambiguo."""
    clave = _clave(pedido)
    exactos = {_clave(c): c for c in conceptos}
    if clave in exactos:
        return exactos[clave], ()
    if _ALIAS_A_CONCEPTO.get(clave) in conceptos:
        return _ALIAS_A_CONCEPTO[clave], ()
    return None, _ALIAS_AMBIGUO.get(clave, ())


def _aviso_split_bpa(ticker: str, concepto: str) -> str:
    """Aviso si el BPA de los dos ejercicios no es comparable por un split (sin añadir cifras).

    Con NetIncomeLoss / BPA se estima el número de acciones de cada ejercicio; si cambia más de 3 veces
    (NVDA, split 10:1: cociente ~10; el resto ~1) los dos BPA están en bases distintas.
    """
    if not concepto.startswith("EarningsPerShare"):
        return ""
    hechos = _recursos()["hechos"]
    acciones = []
    for fy in FISCAL_YEARS:
        neto, bpa = hechos.get((ticker, fy, "NetIncomeLoss")), hechos.get((ticker, fy, concepto))
        if neto is None or bpa is None or not float(bpa["value"]) or not float(neto["value"]):
            return ""
        acciones.append(abs(float(neto["value"]) / float(bpa["value"])))
    if max(acciones) / min(acciones) > 3:
        return (" Aviso: los EPS de ambos ejercicios no son comparables por split; el 10-K posterior "
                "reexpresa el anterior. No concluyas subida ni caída comparándolos.")
    return ""


@tool
def list_available() -> str:
    """Lista empresas, ejercicios, items ('1A', '7', '7A', '8') y conceptos XBRL.

    Cuándo usarla: si dudas de qué existe. Cuándo NO: para cifras (usa get_xbrl_fact); no muestra los huecos.
    """
    try:
        recursos = _recursos()
        cierres = {(ticker, fy): hecho.get("period_end", "?")
                   for (ticker, fy, _), hecho in recursos["hechos"].items()}
        lineas = ["Corpus 10-K disponible:"]
        for ticker, empresa in sorted(recursos["empresas"].items()):
            ejercicios = ", ".join(
                f"FY{fy} (cierre {cierres.get((ticker, fy), '?')})" for fy in FISCAL_YEARS)
            lineas.append(f"- {ticker} ({empresa}): {ejercicios}")
        lineas.append("Items: " + "; ".join(f"'{k}' {v}" for k, v in ITEMS.items()) + ".")
        lineas.append("Conceptos XBRL: " + ", ".join(recursos["conceptos"]) + ".")
        return "\n".join(lineas)
    except Exception as exc:
        return f"ERROR interno en list_available ({type(exc).__name__})."


@tool(parse_docstring=True)
def get_xbrl_fact(ticker: str, fiscal_year: int, concept: str) -> str:
    """Cifra exacta reportada en XBRL; una llamada por ejercicio.

    Cuándo usarla: siempre para cifras. Cuándo NO: riesgos o explicaciones (usa search_filings).
    Conceptos (y su equivalente en español): Assets (activo), Liabilities (pasivo), StockholdersEquity (patrimonio neto), CashAndCashEquivalentsAtCarryingValue (caja), NetIncomeLoss (beneficio neto), OperatingIncomeLoss (beneficio operativo), GrossProfit (beneficio bruto), ResearchAndDevelopmentExpense (gasto en I+D), NetCashProvidedByUsedInOperatingActivities (flujo de caja operativo), EarningsPerShareBasic y EarningsPerShareDiluted (BPA), Revenues (NVDA, GOOGL) y RevenueFromContractWithCustomerExcludingAssessedTax (AAPL, MSFT, META, AMZN).
    Si el hecho no existe no lo estimes: fuente='ninguna'.

    Args:
        ticker: Ticker, como 'NVDA'.
        fiscal_year: 2024 o 2025 (no el año de presentación).
        concept: Concepto XBRL exacto.
    """
    try:
        a = _limpiar_args(ticker=ticker, fiscal_year=fiscal_year, concept=concept)
        ticker_ok, error = _validar_ticker(a["ticker"])
        if error:
            return f"No hay datos. {error}"
        fy_ok, error = _validar_fiscal_year(a["fiscal_year"])
        if error:
            return f"No hay datos. {error}"
        pedido = str(a["concept"]).strip()
        recursos = _recursos()
        concepto, ambiguas, nota = pedido, (), ""
        if (ticker_ok, fy_ok, pedido) not in recursos["hechos"]:
            resuelto, ambiguas = _resolver_concepto(pedido, recursos["conceptos"])
            if resuelto:
                concepto = resuelto
                if resuelto != pedido:
                    nota = (f" Nota: '{_eco(pedido, 40)}' se interpretó como '{resuelto}' (nombre XBRL exacto). "
                            f"Vuelve a llamar con el nombre exacto solo si repites la consulta.")
        hecho = recursos["hechos"].get((ticker_ok, fy_ok, concepto))
        if hecho is not None:
            unidad, valor = str(hecho["unit"]), float(hecho["value"])
            crudo = f"{valor:.2f}" if unidad == "USD/shares" else f"{valor:.0f}"
            return (f"{ticker_ok} FY{fy_ok} · {concepto} = {_formatear_valor(valor, unidad)} {unidad} "
                    f"(cierre {hecho['period_end']}, formulario {hecho['form']}). "
                    f"Valor sin escalar para el campo cifra: {crudo}."
                    + nota + _aviso_split_bpa(ticker_ok, concepto))

        disponibles = {c for (tk, fy, c) in recursos["hechos"] if (tk, fy) == (ticker_ok, fy_ok)}
        if ambiguas:
            mensaje = f"'{_eco(pedido, 40)}' es ambiguo: puede ser " + " o ".join(f"'{c}'" for c in ambiguas)
            propios = [c for c in ambiguas if c in disponibles]
            if set(ambiguas) == set(REVENUE_CONCEPTS) and len(propios) == 1:
                return mensaje + f"; {ticker_ok} FY{fy_ok} reporta '{propios[0]}'. Vuelve a llamar con ese concepto."
            return mensaje + ". Vuelve a llamar con el que corresponda a la pregunta."
        if concepto not in recursos["conceptos"]:
            return (f"Concepto '{_eco(pedido, 40)}' no disponible. Usa uno de: "
                    + ", ".join(recursos["conceptos"]) + ". " + EQUIVALENCIAS_TXT)
        if concepto in REVENUE_CONCEPTS:
            alternativo = REVENUE_CONCEPTS[1 - REVENUE_CONCEPTS.index(concepto)]
            if alternativo in disponibles:
                return (f"{ticker_ok} no reportó '{concepto}' en FY{fy_ok}, pero su revenue está en "
                        f"'{alternativo}'. Vuelve a llamar con ese concepto.")
        return (f"{ticker_ok} no reportó '{concepto}' en FY{fy_ok}. El dato no está en el corpus. "
                "Responde fuente='ninguna' y cifra=null; no calcules ni sumes componentes ni uses read_section.")
    except Exception as exc:
        return f"ERROR interno en get_xbrl_fact ({type(exc).__name__}). No inventes la cifra."


@tool(parse_docstring=True)
def search_filings(query: str, ticker: str | None = None,
                   fiscal_year: int | None = None,
                   item: str | None = None, k: int = 5) -> str:
    """Busca pasajes del 10-K con el índice denso baseline; devuelve chunk_id y texto citable.

    Cuándo usarla: riesgos, estrategia y explicaciones. Query en inglés; empresa, ejercicio e item van en los filtros. Cuándo NO: cifras (usa get_xbrl_fact). Items: '1A' riesgos, '7' MD&A, '7A' riesgo de mercado, '8' estados y notas. Si no basta tras reformular, read_section es el último recurso.

    Args:
        query: Intención de la búsqueda.
        ticker: Empresa (opcional).
        fiscal_year: 2024 o 2025 (opcional).
        item: '1A', '7', '7A' u '8' (opcional).
        k: Fragmentos, de 1 a 10.
    """
    return _buscar_filings(query, ticker, fiscal_year, item, k, modo="baseline")


def _describir_filtros(ticker, ejercicios, items) -> str:
    partes = []
    if ticker:
        partes.append(ticker)
    if ejercicios:
        partes.append("+".join(f"FY{fy}" for fy in ejercicios))
    if items:
        partes.append("item " + "/".join(items))
    return ", ".join(partes)


def _buscar_filings(query, ticker, fiscal_year, item, k, modo):
    try:
        consulta = str(query).strip()
        if not consulta:
            return "No he buscado: query está vacía. Escribe una consulta breve en inglés."
        a = _limpiar_args(ticker=ticker, fiscal_year=fiscal_year, item=item)
        ticker, fiscal_year, item = a["ticker"], a["fiscal_year"], a["item"]
        ticker_ok = fy_ok = item_ok = None
        if ticker is not None:
            ticker_ok, error = _validar_ticker(ticker)
            if error:
                return f"No he buscado. {error}"
        if fiscal_year is not None:
            fy_ok, error = _validar_fiscal_year(fiscal_year)
            if error:
                return f"No he buscado. {error}"
        if item is not None and modo == "baseline":
            item_ok, error = _validar_item(item)
            if error:
                return f"No he buscado. {error}"
        try:
            k_ok = max(1, min(int(k), K_MAX))
        except (TypeError, ValueError):
            return f"No he buscado: k='{_eco(k)}' no es un entero entre 1 y {K_MAX}."
        inferidos = {}
        if modo != "baseline":
            # Lo que el modelo pasa siempre manda; solo se rellena lo que omite. El baseline no infiere.
            inferidos = _filtros_de_la_pregunta(ticker_ok, fy_ok, item_ok)
            if "fiscal_years" in inferidos:
                anios = inferidos["fiscal_years"]
                fy_ok = anios[0] if len(anios) == 1 else anios
            if "ticker" in inferidos:
                ticker_ok = inferidos["ticker"]
            pregunta = PREGUNTA_ACTUAL.get()
            # En el agente solo se filtra por una sección explícita de la pregunta, aunque
            # el modelo omita item o sugiera otra. Sin contexto se admite el argumento directo.
            if pregunta:
                item = retrieval.item_explicito(pregunta)
            if item is not None:
                item_ok, error = _validar_item(item)
                if error:
                    return f"No he buscado. {error}"
                if pregunta:
                    inferidos["items"] = (item_ok,)
        if modo == "baseline":
            resultados = retrieval.buscar_denso(
                consulta, ticker=ticker_ok, fiscal_year=fy_ok, item=item_ok, k=k_ok)
        else:
            resultados = retrieval.buscar(
                consulta, ticker=ticker_ok, fiscal_year=fy_ok, item=item_ok, k=k_ok, modo="final")
        if not resultados:
            return "Sin resultados con esos filtros. Revisa los filtros o prueba otra consulta en inglés."
        bloques = []
        for r in resultados:
            puntuacion = r.get("puntuacion", r.get("score"))
            etiqueta = "similitud" if modo == "baseline" else "BM25"
            score = f" · {etiqueta} {float(puntuacion):.3f}" if puntuacion is not None else ""
            bloques.append(f"[{r['chunk_id']}] {r['ticker']} FY{int(r['fiscal_year'])} "
                           f"Item {r['item']}{score}\n{r['texto']}")
        texto = "\n\n---\n\n".join(bloques)
        notas = []
        if inferidos:
            notas.append("Filtros inferidos de la pregunta: " + _describir_filtros(
                inferidos.get("ticker"), inferidos.get("fiscal_years"), inferidos.get("items"))
                         + ". Indica los tuyos para cambiarlos")
        return texto + (f"\n\n({'; '.join(notas)}.)" if notas else "")
    except Exception as exc:
        return f"ERROR interno en search_filings ({type(exc).__name__}). Prueba otra consulta o filtros."


def _filtros_de_la_pregunta(ticker_ok, fy_ok, item_ok) -> dict:
    """Filtros que la pregunta en curso permite deducir y que el modelo no pasó (vacío si no hay pregunta)."""
    pregunta = PREGUNTA_ACTUAL.get()
    if not pregunta:
        return {}
    deducidos = retrieval.inferir_filtros(pregunta)
    inferidos = {}
    if ticker_ok is None and deducidos["ticker"] in _recursos()["empresas"]:
        inferidos["ticker"] = deducidos["ticker"]
    anios = tuple(fy for fy in deducidos["fiscal_years"] if fy in FISCAL_YEARS)
    if fy_ok is None and anios:
        inferidos["fiscal_years"] = anios
    return inferidos


LECTURA_MAX_CHARS = 6000


def _cortar_en_limite(texto: str, inicio: int, fin: int) -> int:
    """Retrocede el corte al final de párrafo, frase o palabra (dentro del último 30 % de la ventana)."""
    minimo = inicio + int((fin - inicio) * 0.7)
    for separador in ("\n\n", "\n", ". ", " "):
        corte = texto.rfind(separador, minimo, fin)
        if corte != -1:
            return corte + len(separador)
    return fin


@tool(parse_docstring=True)
def read_section(ticker: str, fiscal_year: int, item: str,
                 max_chars: int = LECTURA_MAX_CHARS, offset: int = 0) -> str:
    """Texto de una sección del 10-K: los primeros 6000 caracteres; pagina con offset.

    Cuándo usarla: solo como último recurso si search_filings no encuentra el contexto. Cuándo NO: cifras ni localizar una frase (usa get_xbrl_fact o search_filings). Items: '1A', '7', '7A', '8'. Una sección entera supera 35.000 tokens: sube max_chars solo si hace falta.

    Args:
        ticker: Ticker.
        fiscal_year: 2024 o 2025.
        item: '1A', '7', '7A' u '8'.
        max_chars: Caracteres a devolver (~4 por token).
        offset: Carácter inicial para continuar una lectura truncada.
    """
    try:
        a = _limpiar_args(ticker=ticker, fiscal_year=fiscal_year, item=item)
        ticker_ok, e1 = _validar_ticker(a["ticker"])
        fy_ok, e2 = _validar_fiscal_year(a["fiscal_year"])
        item_ok, e3 = _validar_item(a["item"])
        errores = [e for e in (e1, e2, e3) if e]
        if errores:
            return "No hay esa sección. " + " ".join(errores) + " Usa list_available."
        seccion = _recursos()["secciones"].get((ticker_ok, fy_ok, item_ok))
        if seccion is None:
            return f"No hay Item {item_ok} de {ticker_ok} FY{fy_ok} en el corpus."
        origen = ""
        if str(seccion.get("item_origen", item_ok)) != item_ok:
            origen = f" En el 10-K original es el Item {seccion['item_origen']}."
        texto = str(seccion["texto"])
        total = len(texto)
        try:
            limite = max(500, min(int(max_chars), 1_000_000))
        except (TypeError, ValueError):
            limite = LECTURA_MAX_CHARS
        try:
            inicio = max(0, int(offset))
        except (TypeError, ValueError):
            inicio = 0
        if total and inicio >= total:
            return (f"offset={inicio:,} fuera de rango: Item {item_ok} de {ticker_ok} FY{fy_ok} tiene "
                    f"{total:,} caracteres. Usa un offset entre 0 y {total - 1:,}.")
        fin = total if inicio + limite >= total else _cortar_en_limite(texto, inicio, inicio + limite)
        rango = "" if (inicio, fin) == (0, total) else f" · caracteres {inicio:,}-{fin:,} de {total:,}"
        cabecera = (f"[{ticker_ok} FY{fy_ok} Item {item_ok} · {seccion['titulo']} · "
                    f"{int(seccion['n_tokens']):,} tokens{rango}]{origen}")
        salida = f"{cabecera}\n\n{texto[inicio:fin]}"
        if fin < total:
            salida += (f"\n\n[Truncado: quedan {total - fin:,} caracteres. Continúa con offset={fin}, "
                       "o usa search_filings para localizar el pasaje.]")
        return salida
    except Exception as exc:
        return f"ERROR interno en read_section ({type(exc).__name__}). Prueba search_filings."


HERRAMIENTAS = [list_available, get_xbrl_fact, search_filings, read_section]
TOOLS = HERRAMIENTAS

_DESCRIPCION_FINAL = (
    "Busca pasajes del 10-K con BM25 y palabras clave en inglés; devuelve chunk_id y texto citable.\n"
    "Cuándo usarla: riesgos, estrategia y explicaciones. Cuándo NO: cifras (usa get_xbrl_fact). "
    "Si no basta tras reformular, read_section es el último recurso. Empresa y ejercicio omitidos "
    "se deducen de la pregunta. Usa item solo si la pregunta nombra explícitamente la sección; "
    "en otro caso se busca en todas las secciones, sin inferir item por el tema.\n")


def crear_search_filings(modo: str = "final"):
    """Herramienta con backend fijo; el modelo no puede cambiarlo en sus argumentos.

    El registro TOOLS original sigue siendo baseline para no alterar el notebook 04.
    El sistema final puede sustituir solo search_filings por esta instancia.
    """
    if modo == "baseline":
        return search_filings
    if modo != "final":
        raise ValueError("modo debe ser 'baseline' o 'final'")

    def buscar_final(query: str, ticker: str | None = None,
                     fiscal_year: int | None = None, item: str | None = None,
                     k: int = 5) -> str:
        return _buscar_filings(query, ticker, fiscal_year, item, k, modo="final")

    # Se conserva el esquema público; item es un filtro opcional de la búsqueda BM25.
    return tool("search_filings", args_schema=search_filings.args_schema,
                description=_DESCRIPCION_FINAL + retrieval.REGLAS_BM25)(buscar_final)
