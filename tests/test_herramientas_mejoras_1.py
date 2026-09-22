"""Mejoras de las herramientas sin modelo, sin red y sin cargar BGE (retrieval sustituido por un doble)."""
import concurrent.futures
import contextvars
import inspect
import json
import re

import pytest
from langchain_core.utils.function_calling import convert_to_openai_tool

import agente10k.herramientas as h


def xbrl(ticker, fiscal_year, concept):
    return h.get_xbrl_fact.invoke({"ticker": ticker, "fiscal_year": fiscal_year, "concept": concept})


@pytest.fixture(autouse=True)
def sin_pregunta():
    h.fijar_pregunta_actual("")
    yield
    h.fijar_pregunta_actual("")


@pytest.fixture
def buscador(monkeypatch):
    """Sustituye el retrieval final y registra con qué filtros lo llama la herramienta."""
    llamadas = []

    def buscar(query, **kwargs):
        llamadas.append({"query": query, **kwargs})
        return [{"chunk_id": "NVDA-2025-7-0001", "ticker": "NVDA", "fiscal_year": 2025, "item": "7",
                 "texto": "Revenue increased.", "puntuacion": 0.5}]

    monkeypatch.setattr(h.retrieval, "buscar", buscar)
    return llamadas


# --- contrato con el arnés: PREGUNTA_ACTUAL --------------------------------------------------------------

def test_pregunta_actual_se_fija_borra_y_viaja_a_los_hilos():
    assert h.PREGUNTA_ACTUAL.get() is None
    h.fijar_pregunta_actual("  ¿Riesgos de NVIDIA en FY2025?  ")
    assert h.PREGUNTA_ACTUAL.get() == "¿Riesgos de NVIDIA en FY2025?"
    # LangGraph ejecuta las herramientas en hilos con el contexto copiado: el valor debe verse allí.
    with concurrent.futures.ThreadPoolExecutor(1) as pool:
        assert pool.submit(contextvars.copy_context().run, h.PREGUNTA_ACTUAL.get).result() == "¿Riesgos de NVIDIA en FY2025?"
    h.fijar_pregunta_actual("")
    assert h.PREGUNTA_ACTUAL.get() is None
    h.fijar_pregunta_actual(None)
    assert h.PREGUNTA_ACTUAL.get() is None


# --- inferencia de filtros en la búsqueda final ------------------------------------------------------------

def test_sin_pregunta_no_se_infiere_nada_y_no_cambia_la_salida(buscador):
    texto = h.crear_search_filings("final").invoke({"query": "revenue drivers", "ticker": "NVDA"})
    assert buscador == [{"query": "revenue drivers", "ticker": "NVDA", "fiscal_year": None, "item": None,
                         "k": 5, "modo": "final"}]
    assert "Filtros inferidos" not in texto and texto.startswith("[NVDA-2025-7-0001] NVDA FY2025 Item 7")


def test_por_defecto_solo_se_infieren_ticker_y_ejercicio(buscador):
    h.fijar_pregunta_actual("Según Microsoft, ¿qué riesgos de ciberseguridad describe en FY2025?")
    h.crear_search_filings("final").invoke({"query": "cybersecurity risk"})
    llamada = buscador[0]
    assert (llamada["ticker"], llamada["fiscal_year"], llamada["item"]) == ("MSFT", 2025, None)
    assert "item_blando" not in llamada and llamada["relajar"] == ("fy",)


def test_el_modelo_omite_filtros_y_se_infieren_de_la_pregunta(buscador, monkeypatch):
    monkeypatch.setenv("AGENTE10K_INFERIR_ITEM", "1")          # el item inferido es opt-in
    h.fijar_pregunta_actual("Según Microsoft, ¿qué riesgos de ciberseguridad describe en FY2025?")
    texto = h.crear_search_filings("final").invoke({"query": "cybersecurity risk"})
    llamada = buscador[0]
    assert (llamada["ticker"], llamada["fiscal_year"], llamada["item"]) == ("MSFT", 2025, ("1A",))
    assert llamada["item_blando"] is True and llamada["relajar"] == ("item", "fy")
    assert texto.startswith("[NVDA-2025-7-0001]")           # los resultados no cambian de formato
    assert texto.endswith("(Filtros inferidos de la pregunta: MSFT, FY2025, item 1A (orientativo). "
                          "Indica los tuyos para cambiarlos.)")


def test_comparativa_infiere_ambos_ejercicios(buscador):
    h.fijar_pregunta_actual("¿Cómo evolucionó el gasto en I+D de META entre 2024 y 2025 y por qué?")
    h.crear_search_filings("final").invoke({"query": "research and development expense"})
    assert buscador[0]["fiscal_year"] == (2024, 2025) and buscador[0]["ticker"] == "META"


def test_lo_que_pasa_el_modelo_siempre_manda(buscador):
    h.fijar_pregunta_actual("Riesgos de Microsoft en FY2025 según la sección de factores de riesgo")
    h.crear_search_filings("final").invoke(
        {"query": "risk", "ticker": "AAPL", "fiscal_year": 2024, "item": "7A"})
    llamada = buscador[0]
    assert (llamada["ticker"], llamada["fiscal_year"], llamada["item"]) == ("AAPL", 2024, "7A")
    assert "item_blando" not in llamada and "relajar" not in llamada       # nada inferido: nada se relaja
    parcial = h.crear_search_filings("final").invoke({"query": "risk", "ticker": "AAPL"})
    assert buscador[1]["ticker"] == "AAPL" and buscador[1]["fiscal_year"] == 2025
    assert buscador[1]["relajar"] == ("fy",)
    assert "MSFT" not in parcial                                             # el ticker inferido no pisa al del modelo


def test_solo_se_relaja_lo_inferido(buscador, monkeypatch):
    monkeypatch.setenv("AGENTE10K_INFERIR_ITEM", "1")
    h.fijar_pregunta_actual("Riesgos de Apple")               # solo item inferido
    h.crear_search_filings("final").invoke({"query": "risk", "fiscal_year": 2025})
    assert buscador[0]["relajar"] == ("item",) and buscador[0]["fiscal_year"] == 2025


def test_aviso_cuando_se_relajaron_filtros(monkeypatch):
    monkeypatch.setattr(h.retrieval, "buscar", lambda q, **kw: [
        {"chunk_id": "a", "ticker": "AAPL", "fiscal_year": 2025, "item": "7", "texto": "t", "puntuacion": 0.1},
        {"chunk_id": "b", "ticker": "AAPL", "fiscal_year": 2024, "item": "8", "texto": "u", "puntuacion": 0.1,
         "relajado": "fy"}])
    h.fijar_pregunta_actual("Riesgos de Apple en FY2025")
    texto = h.crear_search_filings("final").invoke({"query": "risk"})
    assert "se completó con otro item o ejercicio" in texto


def test_el_baseline_no_infiere(monkeypatch):
    llamadas = []
    monkeypatch.setattr(h.retrieval, "buscar_denso", lambda q, **kw: llamadas.append(kw) or [])
    h.fijar_pregunta_actual("Riesgos de Microsoft en FY2025")
    h.search_filings.invoke({"query": "risk"})
    assert llamadas == [{"ticker": None, "fiscal_year": None, "item": None, "k": 5}]


def test_pregunta_sin_datos_utiles_no_altera_la_busqueda(buscador):
    h.fijar_pregunta_actual("Compara Apple y Microsoft")
    h.crear_search_filings("final").invoke({"query": "x"})
    assert buscador[0] == {"query": "x", "ticker": None, "fiscal_year": None, "item": None, "k": 5, "modo": "final"}


# --- argumentos corruptos del modelo ----------------------------------------------------------------------

CORRUPTO = ('AMZN", "fiscal_year": 2025, "item": "7", "k": 5}}]</think><tool_call>search_filings</arg_value>'
            '<arg_key>query</arg_key> <arg_value>AWS growth</arg_value><arg_key>ticker</arg_key>')


def test_ticker_corrupto_se_rescata_con_ejercicio_e_item(monkeypatch):
    llamadas = []
    monkeypatch.setattr(h.retrieval, "buscar_denso", lambda q, **kw: llamadas.append(kw) or [])
    h.search_filings.invoke({"query": "AWS growth", "ticker": CORRUPTO})
    assert llamadas == [{"ticker": "AMZN", "fiscal_year": 2025, "item": "7", "k": 5}]


def test_lo_rescatado_no_pisa_lo_que_el_modelo_si_paso(monkeypatch):
    llamadas = []
    monkeypatch.setattr(h.retrieval, "buscar_denso", lambda q, **kw: llamadas.append(kw) or [])
    h.search_filings.invoke({"query": "x", "ticker": CORRUPTO, "fiscal_year": 2024})
    assert llamadas[0]["fiscal_year"] == 2024 and llamadas[0]["item"] == "7"


APELMAZADO = "GOOGL 2025 1A antitrust competition regulatory investigations proceedings"


def test_ticker_apelmazado_por_espacios_se_rescata(monkeypatch):
    # Caso real: el modelo pegó ticker, ejercicio, item y consulta en el argumento ticker, sin
    # comillas ni etiquetas; la búsqueda se rechazaba y el modelo repetía la llamada hasta el límite.
    llamadas = []
    monkeypatch.setattr(h.retrieval, "buscar_denso", lambda q, **kw: llamadas.append(kw) or [])
    h.search_filings.invoke({"query": "antitrust", "ticker": APELMAZADO})
    assert llamadas == [{"ticker": "GOOGL", "fiscal_year": 2025, "item": "1A", "k": 5}]


def test_el_desapelmazado_no_toca_lo_que_no_empieza_por_un_ticker():
    # Un concepto con alias en español lleva espacios y no debe partirse.
    assert "NVDA FY2024 · GrossProfit" in h.get_xbrl_fact.invoke(
        {"ticker": "NVDA", "fiscal_year": 2024, "concept": "beneficio bruto"})
    # Y un ticker que no existe sigue dando el error de ticker, no uno inventado.
    assert "no disponible" in h.search_filings.invoke({"query": "x", "ticker": "TSLA 2025 1A"})


def test_formato_tag_y_otras_herramientas_tambien_rescatan():
    corrupto = "NVDA</arg_value><arg_key>fiscal_year</arg_key> <arg_value>2025</arg_value>"
    assert "NVDA FY2025 · Revenues = 130,497,000,000 USD" in h.get_xbrl_fact.invoke(
        {"ticker": corrupto, "fiscal_year": 2025, "concept": 'Revenues", "fiscal_year": 2025'})
    seccion = h.read_section.invoke({"ticker": 'META", "item": "1A"', "fiscal_year": 2025, "item": ""})
    assert seccion.startswith("[META FY2025 Item 1A")


def test_irrecuperable_da_error_corto_con_guia():
    basura = "<think>" + "x" * 500
    for texto in (h.search_filings.invoke({"query": "x", "ticker": basura}),
                  xbrl(basura, 2025, "Revenues"),
                  h.read_section.invoke({"ticker": "NVDA", "fiscal_year": 2025, "item": basura})):
        assert len(texto) < 400 and "x" * 60 not in texto             # no se repite la basura entera
        assert "no disponible" in texto and ("Usa uno de" in texto or "Items validos" in texto)
    assert "solo el ticker" in h.search_filings.invoke({"query": "x", "ticker": basura})


def test_ejercicio_con_texto_se_normaliza():
    assert h._normalizar_fiscal_year("FY2025") == 2025 and h._normalizar_fiscal_year("fiscal 2024") == 2024
    assert h._normalizar_fiscal_year("dos mil") is None and h._normalizar_fiscal_year(None) is None


# --- get_xbrl_fact: equivalencias, mensajes terminales y aviso de split --------------------------------------

@pytest.mark.parametrize("pedido, concepto", [
    ("us-gaap:Revenues", "Revenues"), ("REVENUES", "Revenues"), ("grossprofit", "GrossProfit"),
    ("beneficio bruto", "GrossProfit"), ("Gasto en I+D", "ResearchAndDevelopmentExpense"),
    ("R&D expense", "ResearchAndDevelopmentExpense"), ("patrimonio neto", "StockholdersEquity"),
    ("flujo de caja operativo", "NetCashProvidedByUsedInOperatingActivities"),
    ("operating cash flow", "NetCashProvidedByUsedInOperatingActivities"),
    ("caja", "CashAndCashEquivalentsAtCarryingValue"), ("Pasivo total", "Liabilities"),
    ("activos totales", "Assets"), ("beneficio neto", "NetIncomeLoss"), ("BPA diluido", "EarningsPerShareDiluted"),
    ("Beneficio por acción básico", "EarningsPerShareBasic"),
])
def test_alias_inequivocos_se_autoresuelven_con_nota(pedido, concepto):
    exacto = xbrl("NVDA", 2025, concepto)
    texto = xbrl("NVDA", 2025, pedido)
    assert texto.startswith(exacto.split(" Aviso:")[0].split(" Nota:")[0])
    if pedido != concepto:
        assert f"'{pedido}' se interpretó como '{concepto}'" in texto
    assert "Valor sin escalar para el campo cifra:" in texto


def test_alias_inequivoco_de_un_hueco_es_hueco_no_error_de_concepto():
    texto = xbrl("AMZN", 2025, "beneficio bruto")
    assert "no reportó 'GrossProfit'" in texto and "fuente='ninguna'" in texto
    assert " = " not in texto


@pytest.mark.parametrize("pedido, opciones", [
    ("BPA", ("EarningsPerShareBasic", "EarningsPerShareDiluted")),
    ("EPS", ("EarningsPerShareBasic", "EarningsPerShareDiluted")),
    ("beneficio por acción", ("EarningsPerShareBasic", "EarningsPerShareDiluted")),
    ("ingresos", h.REVENUE_CONCEPTS), ("Revenue", h.REVENUE_CONCEPTS), ("net sales", h.REVENUE_CONCEPTS),
])
def test_alias_ambiguos_no_se_adivinan(pedido, opciones):
    texto = xbrl("MSFT", 2025, pedido)
    assert " = " not in texto and "es ambiguo" in texto
    assert all(f"'{c}'" in texto for c in opciones)


def test_ingresos_ambiguos_indican_lo_que_reporta_esa_empresa():
    assert "MSFT FY2025 reporta 'RevenueFromContractWithCustomerExcludingAssessedTax'" in xbrl("MSFT", 2025, "ingresos")
    assert "NVDA FY2025 reporta 'Revenues'" in xbrl("NVDA", 2025, "ingresos")


def test_concepto_desconocido_lista_conceptos_y_equivalencias():
    texto = xbrl("NVDA", 2025, "Foo")
    assert "no disponible" in texto and all(c in texto for c in h._recursos()["conceptos"])
    for equivalencia in ("beneficio bruto=GrossProfit", "gasto en I+D=ResearchAndDevelopmentExpense",
                         "patrimonio neto=StockholdersEquity", "flujo de caja operativo=",
                         "caja=CashAndCashEquivalentsAtCarryingValue", "BPA=EarningsPerShareBasic",
                         "pasivo=Liabilities"):
        assert equivalencia in texto


def test_todos_los_alias_apuntan_a_conceptos_reales_y_no_chocan():
    conceptos = set(h._recursos()["conceptos"])
    assert set(h._EQUIVALENCIAS) <= conceptos
    claves = [h._clave(a) for alias in h._EQUIVALENCIAS.values() for a in alias]
    assert len(claves) == len(set(claves))                                   # ningún alias en dos conceptos
    ambiguos = [h._clave(a) for alias in h._AMBIGUAS.values() for a in alias]
    assert not set(claves) & set(ambiguos) and len(ambiguos) == len(set(ambiguos))
    assert not (set(claves) | set(ambiguos)) & {h._clave(c) for c in conceptos if c not in h._EQUIVALENCIAS}


def test_hueco_devuelve_mensaje_terminal_claro_y_corto():
    for ticker, concepto in (("AMZN", "GrossProfit"), ("AMZN", "Liabilities"), ("META", "GrossProfit")):
        texto = xbrl(ticker, 2025, concepto)
        assert texto == (f"{ticker} no reportó '{concepto}' en FY2025. El dato no está en el corpus. "
                         "Responde fuente='ninguna' y cifra=null; no calcules ni sumes componentes ni uses read_section.")
        assert len(texto) < 220


def test_aviso_de_split_solo_en_bpa_de_empresas_con_split():
    for ticker in ("NVDA",):
        for fy in (2024, 2025):
            for concepto in ("EarningsPerShareBasic", "EarningsPerShareDiluted"):
                assert "no son comparables por split" in xbrl(ticker, fy, concepto)
    assert "el 10-K posterior reexpresa el anterior" in xbrl("NVDA", 2025, "EarningsPerShareBasic")
    for ticker in ("MSFT", "AAPL", "GOOGL", "META", "AMZN"):
        for fy in (2024, 2025):
            for concepto in ("EarningsPerShareBasic", "EarningsPerShareDiluted"):
                assert "split" not in xbrl(ticker, fy, concepto)
    assert "split" not in xbrl("NVDA", 2025, "NetIncomeLoss")                 # solo salidas de EPS


def test_aviso_de_split_no_anade_cifras_ni_cambia_las_de_xbrl():
    texto = xbrl("NVDA", 2024, "EarningsPerShareBasic")
    cifra, aviso = texto.split("Valor sin escalar para el campo cifra: ")[1].split(". Aviso:")
    assert cifra == "12.05"
    assert not re.search(r"\d", aviso.replace("10-K", ""))                    # el aviso no lleva ninguna cifra
    assert "2.97 USD/shares" in xbrl("NVDA", 2025, "EarningsPerShareBasic")   # las cifras siguen siendo las de XBRL


def test_umbral_del_aviso_es_3x_y_las_herramientas_son_deterministas(monkeypatch):
    recursos = h._recursos()
    hechos = dict(recursos["hechos"])
    neto = {(t, fy): float(hechos[(t, fy, "NetIncomeLoss")]["value"]) for t in ("MSFT",) for fy in (2024, 2025)}
    bpa25 = dict(hechos[("MSFT", 2025, "EarningsPerShareBasic")])
    razon = neto[("MSFT", 2024)] / float(hechos[("MSFT", 2024, "EarningsPerShareBasic")]["value"])
    for factor, esperado in ((2.9, False), (3.1, True)):     # cociente de acciones entre ejercicios
        bpa25["value"] = neto[("MSFT", 2025)] / (razon * factor)
        monkeypatch.setitem(recursos["hechos"], ("MSFT", 2025, "EarningsPerShareBasic"), bpa25)
        assert ("no son comparables por split" in xbrl("MSFT", 2025, "EarningsPerShareBasic")) is esperado
    assert xbrl("NVDA", 2025, "Revenues") == xbrl("NVDA", 2025, "Revenues")


# --- read_section: max_chars y offset ---------------------------------------------------------------------

def seccion(ticker, fy, item):
    return h._recursos()["secciones"][(ticker, fy, item)]


def partir(salida):
    cabecera, resto = salida.split("\n\n", 1)
    siguiente = re.search(r"\n\n\[Truncado: quedan [\d,]+ caracteres\. Continúa con offset=(\d+),", resto)
    return cabecera, (resto[:siguiente.start()] if siguiente else resto), (int(siguiente.group(1)) if siguiente else None)


def test_read_section_por_defecto_limita_a_6000_y_avisa_como_seguir():
    origen = seccion("META", 2025, "1A")
    salida = h.read_section.invoke({"ticker": "META", "fiscal_year": 2025, "item": "1A"})
    cabecera, cuerpo, siguiente = partir(salida)
    assert cabecera.startswith("[META FY2025 Item 1A · ") and "34,751 tokens" in cabecera   # la procedencia se mantiene
    assert f"caracteres 0-{siguiente:,} de {len(origen['texto']):,}" in cabecera
    assert 0.7 * 6000 <= len(cuerpo) <= 6000 and cuerpo == origen["texto"][:siguiente]
    assert f"Truncado: quedan {len(origen['texto']) - siguiente:,} caracteres" in salida and "search_filings" in salida
    assert len(salida) < 6400


def test_paginando_con_offset_se_recupera_la_seccion_entera():
    origen = seccion("NVDA", 2025, "7A")["texto"]
    reconstruido, offset, paginas = "", 0, 0
    while offset is not None:
        salida = h.read_section.invoke({"ticker": "NVDA", "fiscal_year": 2025, "item": "7A",
                                        "max_chars": 3000, "offset": offset})
        _, cuerpo, offset = partir(salida)
        reconstruido += cuerpo
        paginas += 1
        assert paginas < 200
    assert reconstruido == origen and paginas >= 2


def test_pedir_mas_no_cambia_la_semantica_original():
    origen = seccion("META", 2025, "1A")
    salida = h.read_section.invoke({"ticker": "META", "fiscal_year": 2025, "item": "1A", "max_chars": 10_000_000})
    assert salida == f"[META FY2025 Item 1A · {origen['titulo']} · 34,751 tokens]\n\n{origen['texto']}"
    nvidia = h.read_section.invoke({"ticker": "NVIDIA", "fiscal_year": 2025, "item": "15", "max_chars": 10_000_000})
    assert "FY2025 Item 8" in nvidia and "En el 10-K original es el Item 15." in nvidia


def test_ultima_pagina_y_offsets_invalidos():
    total = len(seccion("META", 2025, "1A")["texto"])
    ultima = h.read_section.invoke({"ticker": "META", "fiscal_year": 2025, "item": "1A", "offset": total - 100})
    assert "Truncado" not in ultima and f"de {total:,}]" in ultima
    fuera = h.read_section.invoke({"ticker": "META", "fiscal_year": 2025, "item": "1A", "offset": total + 5})
    assert "fuera de rango" in fuera and f"{total:,} caracteres" in fuera and len(fuera) < 200
    raro = h.read_section.invoke({"ticker": "META", "fiscal_year": 2025, "item": "1A", "offset": -7, "max_chars": 3})
    assert "caracteres 0-" in raro                                            # offset<0 -> 0; max_chars<500 -> 500


def test_read_section_mantiene_errores_y_es_determinista():
    assert "list_available" in h.read_section.invoke({"ticker": "AAPL", "fiscal_year": 2025, "item": "9"})
    assert "No hay esa sección" in h.read_section.invoke({"ticker": "TSLA", "fiscal_year": 2025, "item": "1A"})
    args = {"ticker": "AAPL", "fiscal_year": 2024, "item": "7A"}
    assert h.read_section.invoke(args) == h.read_section.invoke(args)


# --- contrato y coste fijo de las descripciones ----------------------------------------------------------------

def test_firmas_del_contrato_intactas_y_parametros_nuevos_con_valor_por_defecto():
    esperado = {"list_available": [], "get_xbrl_fact": ["ticker", "fiscal_year", "concept"],
                "search_filings": ["query", "ticker", "fiscal_year", "item", "k"],
                "read_section": ["ticker", "fiscal_year", "item"]}
    for nombre, params in esperado.items():
        firma = inspect.signature(getattr(h, nombre).func).parameters
        assert list(firma)[:len(params)] == params
        assert all(p.default is not inspect.Parameter.empty for n, p in firma.items() if n not in params)
    lectura = inspect.signature(h.read_section.func).parameters
    assert (lectura["max_chars"].default, lectura["offset"].default) == (6000, 0)
    assert h.crear_search_filings("final").args == h.search_filings.args


def test_descripciones_conservan_enrutado_y_vocabulario_y_no_crecen():
    final = h.crear_search_filings("final")
    herramientas = [h.list_available, h.get_xbrl_fact, final, h.read_section]
    assert all("Cuándo usarla" in t.description and "Cuándo NO" in t.description for t in herramientas)
    assert all(c in h.get_xbrl_fact.description for c in h._recursos()["conceptos"])       # R02: vocabulario XBRL
    assert all(i in h.list_available.description and i in h.read_section.description
               for i in ("'1A'", "'7'", "'7A'", "'8'"))
    assert all(i in h.search_filings.description for i in ("'1A'", "'7'", "'7A'", "'8'"))
    assert "'1A', '7', '7A' u '8'" in json.dumps(convert_to_openai_tool(final), ensure_ascii=False)
    assert "último recurso" in h.read_section.description and "último recurso" in final.description
    assert "buscador híbrido" in final.description and "índice denso baseline" in h.search_filings.description
    # Coste fijo por llamada al modelo: las cuatro herramientas medían 4.598 caracteres (esquema OpenAI).
    total = sum(len(json.dumps(convert_to_openai_tool(t), ensure_ascii=False)) for t in herramientas)
    assert total < 4000, total


def test_crear_search_filings_no_muta_el_registro_baseline():
    assert h.crear_search_filings("baseline") is h.search_filings and h.TOOLS[2] is h.search_filings
    with pytest.raises(ValueError):
        h.crear_search_filings("otro")
