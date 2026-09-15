"""Las cuatro herramientas del contrato para consultar el corpus 10-K."""
from __future__ import annotations

from functools import lru_cache

from langchain.tools import tool

from agente10k import datos, retrieval

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
        return None


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
    return None, f"Ticker '{valor}' no disponible. Usa uno de: {', '.join(sorted(_recursos()['empresas']))}."


def _validar_fiscal_year(valor: object) -> tuple[int | None, str | None]:
    fiscal_year = _normalizar_fiscal_year(valor)
    if fiscal_year in FISCAL_YEARS:
        return fiscal_year, None
    return None, (f"Ejercicio fiscal '{valor}' no disponible. Usa FY2024 o FY2025; "
                  "el ejercicio fiscal no es el año de presentación.")


def _validar_item(valor: object) -> tuple[str | None, str | None]:
    item = _normalizar_item(valor)
    if item in ITEMS:
        return item, None
    validos = "; ".join(f"'{clave}' {titulo}" for clave, titulo in ITEMS.items())
    return None, f"Item '{valor}' no disponible. Items validos: {validos}."


def _formatear_valor(valor: float, unidad: str) -> str:
    return f"{float(valor):,.2f}" if unidad == "USD/shares" else f"{float(valor):,.0f}"


@tool
def list_available() -> str:
    """Lista empresas, ejercicios, secciones y conceptos XBRL del corpus.

    Cuándo usarla: si no sabes si una empresa, ejercicio o sección están
    disponibles. Cuándo NO: para obtener una cifra; usa get_xbrl_fact. Tampoco
    revela de antemano los huecos, que deben comprobarse con get_xbrl_fact.
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


@tool
def get_xbrl_fact(ticker: str, fiscal_year: int, concept: str) -> str:
    """Devuelve una cifra exacta reportada en XBRL.

    Cuándo usarla: siempre para cifras, una vez por ejercicio en una
    comparativa. Cuándo NO: para riesgos o explicaciones. No la uses en esos
    casos; usa search_filings.
    Conceptos admitidos:
    Assets, Liabilities, StockholdersEquity,
    CashAndCashEquivalentsAtCarryingValue, NetIncomeLoss,
    OperatingIncomeLoss, GrossProfit, ResearchAndDevelopmentExpense,
    NetCashProvidedByUsedInOperatingActivities, EarningsPerShareBasic,
    EarningsPerShareDiluted, Revenues y
    RevenueFromContractWithCustomerExcludingAssessedTax. NVDA y GOOGL usan
    Revenues; AAPL, MSFT, META y AMZN suelen usar el concepto largo.
    """
    try:
        ticker_ok, error = _validar_ticker(ticker)
        if error:
            return f"No hay datos. {error}"
        fy_ok, error = _validar_fiscal_year(fiscal_year)
        if error:
            return f"No hay datos. {error}"
        concepto = str(concept).strip()
        recursos = _recursos()
        hecho = recursos["hechos"].get((ticker_ok, fy_ok, concepto))
        if hecho is not None:
            unidad, valor = str(hecho["unit"]), float(hecho["value"])
            crudo = f"{valor:.2f}" if unidad == "USD/shares" else f"{valor:.0f}"
            return (f"{ticker_ok} FY{fy_ok} · {concepto} = {_formatear_valor(valor, unidad)} {unidad} "
                    f"(cierre {hecho['period_end']}, formulario {hecho['form']}). "
                    f"Valor sin escalar para el campo cifra: {crudo}.")

        por_minusculas = {c.lower(): c for c in recursos["conceptos"]}
        sugerido = por_minusculas.get(concepto.lower().removeprefix("us-gaap:"))
        if sugerido and sugerido != concepto:
            return f"'{concept}' no es el nombre exacto. Vuelve a llamar con '{sugerido}'."
        if concepto not in recursos["conceptos"]:
            return (f"Concepto '{concept}' no disponible. Usa uno de: "
                    + ", ".join(recursos["conceptos"]) + ".")
        disponibles = {c for (tk, fy, c) in recursos["hechos"] if (tk, fy) == (ticker_ok, fy_ok)}
        if concepto in REVENUE_CONCEPTS:
            alternativo = REVENUE_CONCEPTS[1 - REVENUE_CONCEPTS.index(concepto)]
            if alternativo in disponibles:
                return (f"{ticker_ok} no reportó '{concepto}' en FY{fy_ok}, pero su revenue está en "
                        f"'{alternativo}'. Vuelve a llamar con ese concepto.")
        return (f"{ticker_ok} no reportó '{concepto}' en FY{fy_ok}. El dato no está en el corpus: "
                "no lo estimes ni lo calcules; responde con fuente='ninguna'.")
    except Exception as exc:
        return f"ERROR interno en get_xbrl_fact ({type(exc).__name__}). No inventes la cifra."


@tool
def search_filings(query: str, ticker: str | None = None,
                   fiscal_year: int | None = None,
                   item: str | None = None, k: int = 5) -> str:
    """Busca pasajes con el índice denso baseline y devuelve su chunk_id.

    Cuándo usarla: para riesgos, estrategia y explicaciones. Escribe query en
    inglés y pon empresa, ejercicio e item en los filtros. Cuándo NO: para
    cifras; usa get_xbrl_fact. Items: '1A' riesgos, '7' MD&A, '7A' riesgo de
    mercado y '8' estados y notas. Si no basta tras reformular, read_section
    es el último recurso.
    """
    try:
        consulta = str(query).strip()
        if not consulta:
            return "No he buscado: query está vacía. Escribe una consulta breve en inglés."
        ticker_ok = fy_ok = item_ok = None
        if ticker is not None:
            ticker_ok, error = _validar_ticker(ticker)
            if error:
                return f"No he buscado. {error}"
        if fiscal_year is not None:
            fy_ok, error = _validar_fiscal_year(fiscal_year)
            if error:
                return f"No he buscado. {error}"
        if item is not None:
            item_ok, error = _validar_item(item)
            if error:
                return f"No he buscado. {error}"
        try:
            k_ok = max(1, min(int(k), K_MAX))
        except (TypeError, ValueError):
            return f"No he buscado: k='{k}' no es un entero entre 1 y {K_MAX}."
        resultados = retrieval.buscar_denso(
            consulta, ticker=ticker_ok, fiscal_year=fy_ok, item=item_ok, k=k_ok)
        if not resultados:
            return "Sin resultados con esos filtros. Revisa los filtros o prueba otra consulta en inglés."
        bloques = []
        for r in resultados:
            puntuacion = r.get("puntuacion", r.get("score"))
            score = f" · similitud {float(puntuacion):.3f}" if puntuacion is not None else ""
            bloques.append(f"[{r['chunk_id']}] {r['ticker']} FY{int(r['fiscal_year'])} "
                           f"Item {r['item']}{score}\n{r['texto']}")
        return "\n\n---\n\n".join(bloques)
    except Exception as exc:
        return f"ERROR interno en search_filings ({type(exc).__name__}). Prueba otra consulta o filtros."


@tool
def read_section(ticker: str, fiscal_year: int, item: str) -> str:
    """Devuelve el texto completo de una sección del 10-K.

    Cuándo usarla: solo como último recurso si search_filings no encuentra el
    contexto. Cuándo NO: para cifras ni para localizar una frase; usa
    get_xbrl_fact o search_filings. Puede devolver hasta 35.000 tokens. Items:
    '1A', '7', '7A' y '8'.
    """
    try:
        ticker_ok, e1 = _validar_ticker(ticker)
        fy_ok, e2 = _validar_fiscal_year(fiscal_year)
        item_ok, e3 = _validar_item(item)
        errores = [e for e in (e1, e2, e3) if e]
        if errores:
            return "No hay esa sección. " + " ".join(errores) + " Usa list_available."
        seccion = _recursos()["secciones"].get((ticker_ok, fy_ok, item_ok))
        if seccion is None:
            return f"No hay Item {item_ok} de {ticker_ok} FY{fy_ok} en el corpus."
        origen = ""
        if str(seccion.get("item_origen", item_ok)) != item_ok:
            origen = f" En el 10-K original es el Item {seccion['item_origen']}."
        cabecera = (f"[{ticker_ok} FY{fy_ok} Item {item_ok} · {seccion['titulo']} · "
                    f"{int(seccion['n_tokens']):,} tokens]{origen}")
        return f"{cabecera}\n\n{seccion['texto']}"
    except Exception as exc:
        return f"ERROR interno en read_section ({type(exc).__name__}). Prueba search_filings."


HERRAMIENTAS = [list_available, get_xbrl_fact, search_filings, read_section]
TOOLS = HERRAMIENTAS
