"""Guardrails del 06 (piezas puras, sin LLM ni red): ledger, verificador XBRL, saneado de argumentos,
numeración de frases y abstención. Casos de docs/09 §6-§7 más los hallazgos de las auditorías."""
import pytest
from langchain.messages import AIMessage, ToolMessage

from agente10k import guardrails as g
from agente10k.agente import RespuestaFinanciera
from agente10k.evaluadores import sin_estimacion_financiera
from agente10k.herramientas import get_xbrl_fact

REV = ("NVDA", 2024, "Revenues")
BPA25 = ("NVDA", 2025, "EarningsPerShareBasic")
EPS = (("AAPL", 2024, "EarningsPerShareBasic"), ("AAPL", 2024, "EarningsPerShareDiluted"))


def R(**kw):
    return RespuestaFinanciera(**{"respuesta": "x", "fuente": "xbrl", **kw})


def trayectoria(*consultas):
    return [{"name": "get_xbrl_fact", "id": f"c{i}",
             "args": dict(zip(("ticker", "fiscal_year", "concept"), q))} for i, q in enumerate(consultas)]


def problemas(resp, *consultas):
    return g.verificar_cifras(resp, trayectoria(*consultas))


def ledger(*consultas):
    """Ledger con las llamadas reales a la herramienta (determinista y offline)."""
    msgs = []
    for i, q in enumerate(consultas):
        args = dict(zip(("ticker", "fiscal_year", "concept"), q))
        msgs.append(AIMessage(content="", tool_calls=[{"name": "get_xbrl_fact", "id": f"c{i}", "args": args}]))
        msgs.append(ToolMessage(content=str(get_xbrl_fact.invoke(args)), tool_call_id=f"c{i}",
                                name="get_xbrl_fact"))
    return g.libro_hechos(msgs)


# ------------------------------------------------------------------ docs/09 §7 (casos de D15)
def test_casos_de_d15_del_verificador():
    assert problemas(R(cifra=60_922_000_000, unidad="USD"), REV) == []
    assert problemas(R(cifra=61_000_000_000, unidad="USD"), REV) == []               # 0,13 %: dentro del 0,5 %
    assert "no coincide" in problemas(R(cifra=62_000_000_000, unidad="USD"), REV)[0]
    assert problemas(R(cifra=3.0, unidad="USD/shares"), BPA25)                       # 3 frente a 2,97
    assert problemas(R(cifra=6.08, unidad="USD/shares"), EPS[0])                     # diluido por básico
    hueco = RespuestaFinanciera(respuesta="Amazon no reporta GrossProfit.", fuente="ninguna",
                                ticker="AMZN", ejercicio=2025)
    assert problemas(hueco, ("AMZN", 2025, "GrossProfit")) == []
    inventado = hueco.model_copy(update={"respuesta": "Unos 391 billones de dólares.", "cifra": 391e12})
    assert problemas(inventado, ("AMZN", 2025, "GrossProfit"))                       # importe inventado


def test_escala_y_unidad_se_reparan_sin_llamar_al_modelo():
    inf = g.verificar_xbrl(R(cifra=60_922, unidad="USD", ticker="NVDA", ejercicio=2024).model_dump(), ledger(REV), [])
    assert inf.problemas == [] and inf.modelo == []
    assert inf.resp["cifra"] == 60_922_000_000.0 and inf.resp["unidad"] == "USD"
    assert any(c == "escala_corregida" for c, _ in inf.reparaciones)
    inf = g.verificar_xbrl(R(cifra=60_922, unidad="millones de USD", ticker="NVDA", ejercicio=2024).model_dump(),
                           ledger(REV), [])
    assert inf.resp["cifra"] == 60_922_000_000.0 and inf.resp["unidad"] == "USD"      # se ajusta al valor exacto


def test_googl_revenue_equivalente_y_concepto_corregido():
    resp = R(cifra=350_018e6, unidad="USD", ticker="GOOGL", ejercicio=2024,
             concept_xbrl="RevenueFromContractWithCustomerExcludingAssessedTax")
    assert problemas(resp, ("GOOGL", 2024, "Revenues")) == []
    inf = g.verificar_xbrl(R(cifra=6.08, unidad="USD/shares", ticker="AAPL", ejercicio=2024,
                             concept_xbrl="EarningsPerShareBasic").model_dump(), ledger(*EPS), [])
    assert inf.problemas == [] and inf.resp["concept_xbrl"] == "EarningsPerShareDiluted"


def test_comparativa_orientacion_ticker_y_ejercicio_se_corrigen_solos():
    consultas = (("NVDA", 2025, "EarningsPerShareBasic"), ("NVDA", 2024, "EarningsPerShareBasic"))
    invertida = R(cifra=12.05, cifra_base=2.97, unidad="USD/shares", ticker="nvidia", ejercicio=2024,
                  ejercicio_base=2025, concept_xbrl="EarningsPerShareBasic")
    inf = g.verificar_xbrl(invertida.model_dump(), ledger(*consultas), [])
    assert inf.problemas == []
    assert (inf.resp["cifra"], inf.resp["ejercicio"]) == (2.97, 2025)
    assert (inf.resp["cifra_base"], inf.resp["ejercicio_base"]) == (12.05, 2024)
    assert inf.resp["ticker"] == "NVDA"
    # orientación invertida SIN que el modelo declare ejercicios contradictorios: la deduce el ledger
    inf = g.verificar_xbrl(R(cifra=12.05, cifra_base=2.97, unidad="USD/shares", ticker="NVDA",
                             concept_xbrl="EarningsPerShareBasic").model_dump(), ledger(*consultas), [])
    assert (inf.resp["cifra"], inf.resp["cifra_base"]) == (2.97, 12.05)
    assert any(c == "orientacion_invertida" for c, _ in inf.reparaciones)


def test_ejercicio_cruzado_exige_al_modelo_y_no_se_corrige_a_ciegas():
    consultas = (("NVDA", 2025, "EarningsPerShareBasic"), ("NVDA", 2024, "EarningsPerShareBasic"))
    cruzada = R(cifra=12.05, unidad="USD/shares", ticker="NVDA", ejercicio=2025, concept_xbrl="EarningsPerShareBasic")
    inf = g.verificar_xbrl(cruzada.model_dump(), ledger(*consultas), [])
    assert inf.modelo == ["ejercicio_cruzado"]


def test_cifra_ausente_con_fuente_xbrl_se_rellena_del_ledger_si_es_inequivoco():
    inf = g.verificar_xbrl(R(unidad="USD", ticker="AAPL").model_dump(),
                           ledger(("AAPL", 2025, "CashAndCashEquivalentsAtCarryingValue"),
                                  ("AAPL", 2024, "CashAndCashEquivalentsAtCarryingValue")), [])
    assert (inf.resp["cifra"], inf.resp["ejercicio"]) == (35_934_000_000.0, 2025)
    assert (inf.resp["cifra_base"], inf.resp["ejercicio_base"]) == (29_943_000_000.0, 2024)
    # dos conceptos distintos: ambiguo, no se inventa
    inf = g.verificar_xbrl(R(ticker="AAPL").model_dump(),
                           ledger(("AAPL", 2025, "Assets"), ("AAPL", 2025, "NetIncomeLoss")), [])
    assert inf.resp["cifra"] is None


def test_cifra_que_no_es_xbrl_nunca_se_deja_como_cifra_xbrl():
    """g3-010 (candidato): concepto inventado y cifras 538/669 sin get_xbrl_fact detrás."""
    obs = [{"name": "search_filings", "content": "[AAPL-2024-7A-0001] AAPL FY2024 Item 7A\nThe Company had $538 "
                                                  "million in foreign currency forward contracts and $669 million "
                                                  "in options today."}]
    resp = R(cifra=538, cifra_base=669, unidad="USD", ticker="AAPL", ejercicio=2024, fuente="texto",
             concept_xbrl="ForeignExchangeRateRisk")
    inf = g.verificar_xbrl(resp.model_dump(), [], obs)
    assert inf.resp["cifra"] is None and inf.resp["cifra_base"] is None
    assert inf.resp["concept_xbrl"] is None
    assert ("concepto_anulado", "ForeignExchangeRateRisk") in inf.reparaciones
    assert inf.modelo == []                                     # extractiva: se anula sin gastar otra llamada
    # cifra de la que no hay rastro ni en XBRL ni en el texto y sin ninguna herramienta: hay que preguntar
    inf = g.verificar_xbrl(R(cifra=123456, unidad="USD", ticker="AAPL").model_dump(), [], [])
    assert inf.modelo == ["cifra_sin_get_xbrl_fact"]


def test_hueco_con_cifra_derivada_invalida_la_respuesta():
    """h001/h002/h004/h005: cifras derivadas o sumadas de un dato que la herramienta dijo no reportar."""
    hechos = ledger(("AMZN", 2025, "GrossProfit"))
    assert hechos[0].status == "hueco"
    for cifra, unidad in ((50.28, "%"), (338924.0, "USD"), (81.66, None)):
        inf = g.verificar_xbrl(R(cifra=cifra, unidad=unidad, ticker="AMZN", ejercicio=2025, fuente="ambas",
                                 concept_xbrl="GrossProfit").model_dump(), hechos, [])
        assert inf.hueco is not None and inf.hueco.concept == "GrossProfit"
        assert inf.modelo == []                                # abstención directa: sin reintento


def test_hueco_mezclado_con_valores_solo_invalida_la_cifra_sin_respaldo():
    """h004 (META): revenue con valor, GrossProfit sin datos y una cifra derivada de ambos."""
    hechos = ledger(("META", 2024, "Revenues"), ("META", 2024, "GrossProfit"),
                    ("META", 2024, "RevenueFromContractWithCustomerExcludingAssessedTax"))
    assert [h.status for h in hechos] == ["sugerencia", "hueco", "valor"]
    inf = g.verificar_xbrl(R(cifra=81.66, unidad="USD", ticker="META", ejercicio=2024, fuente="ambas").model_dump(),
                           hechos, [])
    assert inf.hueco is not None


def test_ledger_distingue_valor_hueco_sugerencia_error_y_bloqueo():
    hechos = ledger(("NVDA", 2024, "Revenues"), ("AMZN", 2025, "GrossProfit"),
                    ("META", 2024, "Revenues"), ("TSLA", 2025, "Revenues"), ("NVDA", 2024, "Inventado"))
    assert [h.status for h in hechos] == ["valor", "hueco", "sugerencia", "hueco", "error"]
    bloqueada = g.libro_hechos([
        AIMessage(content="", tool_calls=[{"name": "get_xbrl_fact", "id": "x", "args": dict(
            zip(("ticker", "fiscal_year", "concept"), REV))}]),
        ToolMessage(content="Tool call limit exceeded. Do not make additional tool calls.", tool_call_id="x",
                    name="get_xbrl_fact")])
    assert [h.status for h in bloqueada] == ["bloqueada"]
    sin_toolmessage = g.libro_hechos([AIMessage(content="", tool_calls=[{
        "name": "get_xbrl_fact", "id": "x", "args": dict(zip(("ticker", "fiscal_year", "concept"), REV))}])])
    assert sin_toolmessage[0].status == "valor" and sin_toolmessage[0].valor == 60_922_000_000.0


# ------------------------------------------------------------------ prosa e importes
def test_extraer_cifras_de_la_prosa():
    assert g.extraer_cifras("391 billones de dólares") == [391e12]
    assert g.extraer_cifras("El BPA fue de 2,97 USD por acción, tras el split 10:1 (FY2025, Item 7)") == [2.97]
    assert [round(v) for v in g.extraer_cifras("Ingresos de $60,922 millones y 44.301 millones de USD")] == [
        60_922_000_000, 44_301_000_000]
    assert g.extraer_cifras("creció un 14,9 %") == []          # los porcentajes no son importes


# ------------------------------------------------------------------ argumentos corruptos y duplicados
def test_sanear_args_extrae_ticker_fy_e_item_del_marcado():
    corrupto = {"query": "AWS growth", "ticker": 'AMZN", "fiscal_year": 2025, "item": "7", "k": 5}}]</think>'
                                                 '<tool_call>search_filings</arg_value>'}
    limpio, tocado = g.sanear_args(corrupto)
    assert tocado
    assert limpio == {"query": "AWS growth", "ticker": "AMZN", "fiscal_year": 2025, "item": "7", "k": 5}
    sano, tocado = g.sanear_args({"query": "a < b", "ticker": "AMZN"})
    assert not tocado and sano == {"query": "a < b", "ticker": "AMZN"}


def test_firma_normaliza_mayusculas_tipos_y_alias():
    a = {"name": "get_xbrl_fact", "args": {"ticker": "nvidia", "fiscal_year": "2024", "concept": "Revenues"}}
    b = {"name": "get_xbrl_fact", "args": {"ticker": "NVDA", "fiscal_year": 2024, "concept": "Revenues"}}
    assert g.firma(a) == g.firma(b)
    q1 = {"name": "search_filings", "args": {"query": "AI  Risks", "ticker": "msft", "item": "Item 1A"}}
    q2 = {"name": "search_filings", "args": {"query": "ai risks", "ticker": "MSFT", "item": "1A"}}
    assert g.firma(q1) == g.firma(q2)
    assert g.firma(q1) != g.firma({**q2, "args": {**q2["args"], "fiscal_year": 2025}})


# ------------------------------------------------------------------ frases numeradas
BUSQUEDA = (
    "[MSFT-2025-1A-0004] MSFT FY2025 Item 1A · similitud 0.912\n"
    "Our AI systems could be misused in ways that harm people and our reputation. Short one.\n\n"
    "The company may face regulatory scrutiny over the development of artificial intelligence products.\n\n---\n\n"
    "[MSFT-2025-1A-0005] MSFT FY2025 Item 1A · similitud 0.850\n"
    "We rely on third parties to supply components for our devices and cloud infrastructure."
)


def test_numerar_marca_frases_y_el_indice_las_recupera_literales():
    numerada = g.numerar(BUSQUEDA, "search_filings", 1)
    assert "⟨1⟩ Our AI systems" in numerada and "⟨3⟩ We rely on third parties" in numerada
    msg = ToolMessage(content=numerada, tool_call_id="a", name="search_filings", artifact=BUSQUEDA)
    idx = g.indice_frases([msg])
    assert idx[1].chunk_id == "MSFT-2025-1A-0004" and idx[3].chunk_id == "MSFT-2025-1A-0005"
    assert (idx[1].ticker, idx[1].fy, idx[1].item) == ("MSFT", 2025, "1A")
    assert g.original(msg) == BUSQUEDA                       # el guardado NO lleva marcas
    for f in idx.values():                                   # cada frase numerada es literal del original
        assert g.normalizar(f.texto) in g.normalizar(BUSQUEDA)


def test_numerar_continua_la_numeracion_entre_observaciones():
    primera = ToolMessage(content=g.numerar(BUSQUEDA, "search_filings", 1), tool_call_id="a", name="search_filings")
    assert g.siguiente_id([primera]) == 4


def test_numerar_read_section_reconstruye_chunk_id_del_corpus():
    from agente10k.herramientas import read_section
    texto = read_section.invoke({"ticker": "NVDA", "fiscal_year": 2025, "item": "7A"})
    numerada = g.numerar(texto, "read_section", 1)
    msg = ToolMessage(content=numerada, tool_call_id="r", name="read_section", artifact=texto)
    idx = g.indice_frases([msg])
    assert idx and all(f.ticker == "NVDA" and f.fy == 2025 and f.item == "7A" for f in idx.values())
    con_chunk = [f for f in idx.values() if f.chunk_id]
    assert len(con_chunk) > 0.8 * len(idx)
    assert all(g.normalizar(f.texto) in g.normalizar(texto) for f in idx.values())


def test_recortar_deja_una_ventana_literal_de_40_palabras_como_maximo():
    frase = " ".join(f"palabra{i}" for i in range(80)) + " fin"
    corta = g.recortar(frase, "palabra70 palabra71")
    assert len(corta.split()) == 40 and corta in frase
    assert "palabra70" in corta
    assert g.recortar("una frase corta", "x") == "una frase corta"


def test_resolver_cita_ids_dos_piezas_y_alineacion_de_ticker_y_ejercicio():
    numerada = g.numerar(BUSQUEDA, "search_filings", 1)
    msg = ToolMessage(content=numerada, tool_call_id="a", name="search_filings", artifact=BUSQUEDA)
    obs = g.observaciones_texto([msg])
    r, prob, rep = g.resolver_cita({"respuesta": "AI misuse", "frase_ids": [1, 3], "cita": "texto inventado"}, [msg], obs)
    assert prob == []
    assert r["cita"].count(" [...] ") == 1
    assert r["chunk_id"] == "MSFT-2025-1A-0004"
    assert (r["ticker"], r["ejercicio"]) == ("MSFT", 2025)
    assert all(g.normalizar(p) in g.normalizar(BUSQUEDA) for p in r["cita"].split(" [...] "))
    r, prob, _ = g.resolver_cita({"respuesta": "x", "frase_ids": [99]}, [msg], obs)
    assert prob and prob[0][0] == "frase_inexistente" and r["cita"] is None


def test_resolver_cita_textual_literal_encajada_o_descartada():
    numerada = g.numerar(BUSQUEDA, "search_filings", 1)
    msg = ToolMessage(content=numerada, tool_call_id="a", name="search_filings", artifact=BUSQUEDA)
    obs = g.observaciones_texto([msg])
    literal = "The company may face regulatory scrutiny over the development of artificial intelligence products."
    r, prob, rep = g.resolver_cita({"respuesta": "x", "cita": f"⟨2⟩ {literal}", "chunk_id": "MAL"}, [msg], obs)
    assert prob == [] and r["cita"] == literal and r["chunk_id"] == "MSFT-2025-1A-0004"
    casi = "The company may face heavy regulatory scrutiny over the development of artificial intelligence products."
    r, prob, rep = g.resolver_cita({"respuesta": "x", "cita": casi}, [msg], obs)
    assert prob == [] and r["cita"] == literal and any(c == "cita_encajada" for c, _ in rep)
    r, prob, rep = g.resolver_cita({"respuesta": "x", "cita": "Nothing of this appears anywhere in the tools."}, [msg], obs)
    assert r["cita"] is None and r["chunk_id"] is None and prob[0][0] == "cita_no_literal"


# ------------------------------------------------------------------ fuente derivada y abstención
def test_fuente_derivada_de_la_evidencia():
    assert g.derivar_fuente({"cifra": 1.0, "cita": None}) == "xbrl"
    assert g.derivar_fuente({"cifra": None, "cita": "una frase"}) == "texto"
    assert g.derivar_fuente({"cifra": 1.0, "cita": "una frase"}) == "ambas"
    assert g.derivar_fuente({"cifra": None, "cita": "  "}) == "ninguna"


def test_texto_de_hueco_no_trae_importes_ni_verbos_de_estimacion():
    hueco = ledger(("AMZN", 2025, "GrossProfit"))[0]
    texto = g.texto_hueco(hueco)
    assert texto == "No reportado en XBRL para AMZN FY2025: el dato no está en el corpus."
    assert sin_estimacion_financiera(texto) and g.extraer_cifras(texto) == []
    d = g.abstencion({"respuesta": "unos 50,28 %", "cifra": 50.28, "cita": "x", "fuente": "ambas"}, hueco)
    assert (d["fuente"], d["cifra"], d["cifra_base"], d["cita"], d["chunk_id"]) == ("ninguna", None, None, None, None)
    assert (d["ticker"], d["ejercicio"]) == ("AMZN", 2025)


def test_limpiar_abstencion_quita_importes_de_una_abstencion_declarada():
    hueco = ledger(("AMZN", 2025, "GrossProfit"))[0]
    sucia = {"respuesta": "AMZN no reporta GrossProfit, pero con ingresos de 716.924 millones y costes de 356.414 "
                          "millones el margen sería aproximadamente 50 %.", "fuente": "ninguna", "cifra": None}
    limpia, cambio = g.limpiar_abstencion(sucia, hueco)
    assert cambio and limpia["respuesta"] == g.texto_hueco(hueco)
    correcta = {"respuesta": "AMZN no reportó el concepto GrossProfit en FY2025.", "fuente": "ninguna", "cifra": None}
    assert g.limpiar_abstencion(correcta, hueco) == (correcta, False)


# ------------------------------------------------------------------ coherencia pregunta <-> llamada (camino rápido)
@pytest.mark.parametrize("pregunta,concepto,esperado", [
    ("¿Cuál fue el beneficio bruto de NVDA en el ejercicio fiscal 2024?", "GrossProfit", True),
    ("¿Cuál fue el gasto en I+D de MSFT en el ejercicio fiscal 2025?", "ResearchAndDevelopmentExpense", True),
    ("¿Cuál fue el pasivo total de NVDA en el ejercicio fiscal 2025?", "Liabilities", True),
    ("¿Cuál fue el beneficio por acción diluido de AAPL en FY2025?", "EarningsPerShareDiluted", True),
    ("¿Cuál fue el beneficio por acción diluido de AAPL en FY2025?", "EarningsPerShareBasic", False),
    ("¿Cuál fue el patrimonio neto de AMZN?", "NetIncomeLoss", False),               # concepto alternativo
    ("¿Cuál fue el margen bruto de NVDA en FY2025?", "GrossProfit", False),           # magnitud derivada
    ("¿Cómo evolucionaron los ingresos de MSFT entre FY2024 y FY2025?", "Revenues", False),
    ("Háblame de la empresa", "GrossProfit", False),                                  # sin evidencia léxica
])
def test_concepto_coherente_con_la_pregunta(pregunta, concepto, esperado):
    assert g.concepto_coherente(pregunta, concepto) is esperado


def test_ticker_y_ejercicio_deben_estar_en_la_pregunta_sin_ambiguedad():
    q = "¿Cuál fue el pasivo total de Nvidia en el ejercicio fiscal 2025?"
    assert g.ticker_coherente(q, "NVDA") and not g.ticker_coherente(q, "AMZN")
    assert g.ejercicio_coherente(q, 2025) and not g.ejercicio_coherente(q, 2024)
    assert not g.ejercicio_coherente("¿Y entre 2024 y 2025?", 2025)                   # dos años: comparativa
    assert not g.ticker_coherente("¿Ingresos de Apple frente a Microsoft?", "AAPL")


def test_formato_de_valores_en_castellano():
    assert g.formatear_valor(44_301_000_000, "USD") == "44.301 millones de USD"
    assert g.formatear_valor(7.46, "USD/shares") == "7,46 USD por acción"
    assert g.formatear_valor(1_234_567, "USD") == "1.234.567 USD"
    assert g.extraer_cifras(g.formatear_valor(44_301_000_000, "USD")) == [44_301_000_000]
