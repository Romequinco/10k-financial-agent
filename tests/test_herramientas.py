"""Pruebas de herramientas sin modelo ni red."""
import agente10k.herramientas as h


def x(ticker, fiscal_year, concept):
    return h.get_xbrl_fact.invoke({"ticker": ticker, "fiscal_year": fiscal_year, "concept": concept})


def test_disponibilidad_sin_revelar_huecos():
    texto = h.list_available.invoke({})
    assert all(t in texto for t in ("NVDA", "MSFT", "AAPL", "GOOGL", "META", "AMZN"))
    assert "FY2024" in texto and "FY2025" in texto
    assert texto.count("GrossProfit") == 1 and "no reportó" not in texto


def test_cifras_exactas_y_bpa():
    assert "60,922,000,000 USD" in x("NVDA", 2024, "Revenues")
    assert "2.97 USD/shares" in x("NVDA", 2025, "EarningsPerShareBasic")
    assert "12.05 USD/shares" in x("NVDA", 2024, "EarningsPerShareBasic")
    assert "11.93 USD/shares" in x("NVDA", 2024, "EarningsPerShareDiluted")


def test_aliases_y_normalizacion():
    assert x("nvidia ", "2024", "Revenues") == x("NVDA", 2024, "Revenues")
    assert "402,836,000,000 USD" in x("GOOG", 2025, "Revenues")
    assert "MSFT" in x("microsoft", 2025, "NetIncomeLoss")


def test_revenue_alternativo_y_huecos_reales():
    texto = x("AAPL", 2025, "Revenues")
    assert "RevenueFromContractWithCustomerExcludingAssessedTax" in texto
    assert "fuente='ninguna'" not in texto
    for ticker, concepto in (("AMZN", "GrossProfit"), ("AMZN", "Liabilities"),
                             ("AMZN", "ResearchAndDevelopmentExpense"),
                             ("META", "GrossProfit"), ("GOOGL", "GrossProfit")):
        texto = x(ticker, 2025, concepto)
        assert "no reportó" in texto and "fuente='ninguna'" in texto


def test_entradas_invalidas_devuelven_ayuda():
    for args in (("TSLA", 2025, "Revenues"), ("NVDA", 2023, "Revenues"),
                 ("NVDA", 2025, "Revenue")):
        texto = x(*args)
        assert isinstance(texto, str) and " = " not in texto
    assert "Vuelve a llamar" in x("NVDA", 2025, "us-gaap:Revenues")


def test_read_section_normaliza_y_explica_item_15():
    meta = h.read_section.invoke({"ticker": "meta", "fiscal_year": 2025, "item": "Item 1A"})
    assert "34,751 tokens" in meta
    nvidia = h.read_section.invoke({"ticker": "NVIDIA", "fiscal_year": 2025, "item": "15"})
    assert "FY2025 Item 8" in nvidia and "Item 15" in nvidia
    assert "list_available" in h.read_section.invoke({"ticker": "AAPL", "fiscal_year": 2025, "item": "9"})


def test_search_usa_solo_denso_y_formatea(monkeypatch):
    llamadas = []
    def buscar(query, ticker=None, fiscal_year=None, item=None, k=5):
        llamadas.append((query, ticker, fiscal_year, item, k))
        return [{"chunk_id": "MSFT-2025-1A-0004", "ticker": "MSFT",
                 "fiscal_year": 2025, "item": "1A", "texto": "AI may be misused.",
                 "puntuacion": 0.742}]
    monkeypatch.setattr(h.retrieval, "buscar_denso", buscar)
    texto = h.search_filings.invoke({"query": "misuse of AI", "ticker": "microsoft",
                                     "fiscal_year": "2025", "item": "item 1a", "k": 50})
    assert llamadas == [("misuse of AI", "MSFT", 2025, "1A", 10)]
    assert "[MSFT-2025-1A-0004]" in texto and "similitud 0.742" in texto


def test_search_rechaza_filtros_sin_buscar(monkeypatch):
    monkeypatch.setattr(h.retrieval, "buscar_denso", lambda *a, **kw: (_ for _ in ()).throw(AssertionError()))
    assert "No he buscado" in h.search_filings.invoke({"query": "risk", "ticker": "TSLA"})
    assert "No he buscado" in h.search_filings.invoke({"query": "risk", "item": "9"})
    assert "vacía" in h.search_filings.invoke({"query": "  "})


def test_docstrings_orientan_el_enrutado():
    assert all("Cuándo usarla" in tool.description and "Cuándo NO" in tool.description
               for tool in h.HERRAMIENTAS)
    assert "último recurso" in h.read_section.description
    assert all(item in h.search_filings.description for item in ("'1A'", "'7'", "'7A'", "'8'"))
