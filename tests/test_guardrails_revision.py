"""Regresiones de la revisión independiente del 06 (sin red ni LLM).

Cada test cubre un fallo REPRODUCIDO con un modelo falso:
- respuesta estructurada + herramienta real en el mismo mensaje se saltaba el verificador;
- una excepción en la vuelta de reintento devolvía la respuesta que el verificador había rechazado;
- un ``⟨n⟩`` copiado por el modelo salía en ``respuesta``;
- dos conceptos casi iguales (META FY2024: caja e I+D) se resolvían por orden de consulta;
- el camino rápido cortaba preguntas de varias magnitudes o derivadas (crecimiento, «por acción»...).
"""
import pytest
from langchain.messages import AIMessage, ToolMessage

from agente10k import agente, guardrails as g, retrieval
from test_guardrails_middleware import BUSQUEDA, FRASE_2, NV, Falso, correr, final, tc

NV_TOOL = {"name": "get_xbrl_fact", "args": NV, "id": "a"}


def _mismo_mensaje(**kw):
    """Un solo AIMessage con la herramienta real y la respuesta estructurada (el modelo no ha visto el resultado)."""
    cuerpo = {"respuesta": "x", "fuente": "xbrl", "unidad": "USD", "ticker": "NVDA", "ejercicio": 2024,
              "concept_xbrl": "GrossProfit", **kw}
    return AIMessage(content="", tool_calls=[NV_TOOL, {"name": "RespuestaFinanciera", "args": cuerpo, "id": "b"}])


# ------------------------------------------------------------------ mismo mensaje: se verifica
def test_respuesta_y_herramienta_en_el_mismo_mensaje_no_se_saltan_el_verificador():
    res, modelo = correr([_mismo_mensaje(cifra=99_999e6)])
    r = res["structured_response"]
    assert modelo.n == 1                                       # no hay segunda vuelta: la herramienta ya está pendiente
    assert r.cifra is None and r.fuente == "ninguna"           # la cifra inventada se degrada, no sale
    assert res["guard"]["degradada"] and "cifra_sin_respaldo" in res["guard"]["degradaciones"]


def test_mismo_mensaje_con_escala_erronea_se_repara_con_el_valor_del_parquet():
    res, _ = correr([_mismo_mensaje(cifra=44_301)])
    r = res["structured_response"]
    assert (r.cifra, r.unidad, r.fuente) == (44_301e6, "USD", "xbrl")
    assert "escala_corregida" in {c for c, _ in res["guard"]["reparaciones"]}


def test_mismo_mensaje_con_cifra_correcta_pasa_intacta():
    res, _ = correr([_mismo_mensaje(cifra=44_301e6)])
    assert res["structured_response"].cifra == 44_301e6 and not res["guard"]["degradada"]


# ------------------------------------------------------------------ excepción tras un rechazo
def test_excepcion_en_la_vuelta_de_reintento_no_devuelve_la_respuesta_rechazada(monkeypatch):
    agente.limpiar_cache_agentes()
    llamada = AIMessage(content="", tool_calls=[NV_TOOL, {"name": "list_available", "args": {}, "id": "l"}])
    mala = final(2, cifra=99_999e6, unidad="USD", ticker="NVDA", ejercicio=2024, concept_xbrl="GrossProfit",
                 respuesta="Fue 99.999 millones.")
    guion = iter([llamada, mala])      # 1.ª vuelta: herramientas; 2.ª: respuesta errónea; 3.ª (reintento): red caída

    class Modelo(Falso):
        def _generate(self, messages, *a, **k):
            if self.n >= 2:
                raise RuntimeError("429 rate limit simulado")
            return super()._generate(messages, *a, **k)

    monkeypatch.setattr(agente.config, "crear_modelo", lambda *a, **kw: Modelo(messages=guion))
    monkeypatch.setattr(retrieval, "buscar", lambda *a, **kw: [])
    monkeypatch.setattr(retrieval, "precalentar", lambda: None, raising=False)
    try:
        r = agente.ejecutar("¿Cuál fue el beneficio bruto de NVDA en 2024?", "final")
    finally:
        agente.limpiar_cache_agentes()
    assert r["error"] and r["error"].startswith("RuntimeError")          # la causa sigue trazada
    assert r["respuesta"].cifra is None and r["respuesta"].fuente == "ninguna"
    assert r["guard"]["degradada"] and "cifra_sin_respaldo" in r["guard"]["degradaciones"]


# ------------------------------------------------------------------ marcas ⟨n⟩ copiadas por el modelo
def test_marca_de_frase_copiada_en_la_respuesta_no_llega_a_la_salida():
    res, _ = correr([tc("search_filings", {"query": "ai", "ticker": "MSFT"}, 1),
                     final(2, fuente="texto", respuesta="⟨2⟩ Riesgo regulatorio ⟨1⟩", cita="⟨2⟩ " + FRASE_2)])
    r = res["structured_response"]
    assert "⟨" not in r.respuesta and "⟨" not in (r.cita or "")
    assert r.respuesta == "Riesgo regulatorio" and r.cita == FRASE_2


def test_la_nota_de_filtros_de_search_filings_no_se_numera_como_si_fuera_una_frase_del_informe():
    nota = ("\n\n(Filtros inferidos de la pregunta: MSFT, FY2025, item 1A (orientativo). Indica los tuyos "
            "para cambiarlos; con los filtros había pocos resultados y se completó con otro item o ejercicio.)")
    numerada = g.numerar(BUSQUEDA + nota, "search_filings", 1)
    assert numerada.endswith(nota) and numerada.count("⟨") == 3      # 3 frases del informe, ninguna en la nota
    ids = g.indice_frases([ToolMessage(content=numerada, tool_call_id="x", name="search_filings")])
    assert sorted(ids) == [1, 2, 3] and all("Filtros" not in f.texto and "Indica los tuyos" not in f.texto
                                            for f in ids.values())


@pytest.mark.parametrize("concepto", ["us-gaap:GrossProfit", "grossprofit", "beneficio bruto", "Gross Profit"])
def test_alias_de_concepto_aceptado_por_la_herramienta_no_degrada_una_cifra_correcta(concepto):
    """La herramienta resuelve alias y devuelve el valor; el ledger debe usar el concepto que ella resolvió."""
    args = {"ticker": "nvda", "fiscal_year": "2024", "concept": concepto}
    res, _ = correr([AIMessage(content="", tool_calls=[{"name": "get_xbrl_fact", "args": args, "id": "a"},
                                                        {"name": "list_available", "args": {}, "id": "l"}]),
                     final(2, cifra=44_301e6, unidad="USD", ticker="NVDA", ejercicio=2024, concept_xbrl="GrossProfit")])
    r = res["structured_response"]
    assert (r.cifra, r.fuente) == (44_301e6, "xbrl") and not res["guard"]["degradada"]
    assert res["guard"]["reintentos"] == 0
    hechos = g.libro_hechos(res["messages"])
    assert [(h.ticker, h.fy, h.concept, h.status) for h in hechos if h.concept == "GrossProfit"] == [
        ("NVDA", 2024, "GrossProfit", "valor")]


# ------------------------------------------------------------------ concepto casi igual: gana el más cercano
def test_conceptos_casi_iguales_no_cambian_una_cifra_correcta_de_meta():
    caja = g.Hecho("META", 2024, "CashAndCashEquivalentsAtCarryingValue", "valor", 43_889e6, "USD")
    idi = g.Hecho("META", 2024, "ResearchAndDevelopmentExpense", "valor", 43_873e6, "USD")
    resp = {"respuesta": "El gasto en I+D fue 43.873 millones.", "cifra": 43_873e6, "unidad": "USD",
            "ticker": "META", "ejercicio": 2024, "fuente": "xbrl"}
    for orden in ([caja, idi], [idi, caja]):
        r = g.verificar_xbrl(resp, orden, []).resp
        assert (r["cifra"], r["concept_xbrl"]) == (43_873e6, "ResearchAndDevelopmentExpense")


def test_mas_cercano_respeta_la_escala_de_la_unidad():
    a = g.Hecho("META", 2024, "A", "valor", 43_889e6, "USD")
    b = g.Hecho("META", 2024, "B", "valor", 43_873e6, "USD")
    assert g._mas_cercano(43_873, "millones de USD", [a, b]) is b
    assert g._mas_cercano(1, "USD", []) is None


# ------------------------------------------------------------------ camino rápido: más conservador
@pytest.mark.parametrize("pregunta,concepto", [
    ("¿Cuál fue el patrimonio neto y el pasivo total de MSFT en FY2025?", "StockholdersEquity"),
    ("¿Cuáles fueron los ingresos y el beneficio neto de NVDA en FY2024?", "Revenues"),
    ("¿Cuánto crecieron los ingresos de NVDA en FY2025?", "Revenues"),
    ("¿Cuánto aumentó el beneficio neto de Apple en FY2025?", "NetIncomeLoss"),
    ("¿Cuánta caja tenía Apple al cierre de FY2025 y cuál fue su flujo de caja operativo?",
     "CashAndCashEquivalentsAtCarryingValue"),
    ("¿Fue mayor el beneficio neto de NVDA en FY2025?", "NetIncomeLoss"),
    ("¿Cuánto vale el patrimonio neto de Meta por acción en 2025?", "StockholdersEquity"),
    ("What was Apple's net income in fiscal 2025 and how does it compare to revenue?", "NetIncomeLoss"),
])
def test_camino_rapido_no_corta_preguntas_de_varias_magnitudes_o_derivadas(pregunta, concepto):
    assert not g.concepto_coherente(pregunta, concepto)


@pytest.mark.parametrize("pregunta,concepto", [
    ("¿Cuál fue el beneficio bruto de NVDA en el ejercicio fiscal 2024?", "GrossProfit"),
    ("¿Cuál fue el gasto en I+D de MSFT en el ejercicio fiscal 2025?", "ResearchAndDevelopmentExpense"),
    ("¿Cuál fue el beneficio por acción diluido de AAPL en el ejercicio fiscal 2025?", "EarningsPerShareDiluted"),
    ("¿Cuál fue el patrimonio neto de GOOGL en el ejercicio fiscal 2024?", "StockholdersEquity"),
    ("¿Cuál fue el flujo de caja operativo de META en el ejercicio fiscal 2025?",
     "NetCashProvidedByUsedInOperatingActivities"),
    ("¿Cuál fue el pasivo total de NVDA en el ejercicio fiscal 2025?", "Liabilities"),
    ("¿Cuáles fueron los ingresos totales de Alphabet en el ejercicio fiscal 2024?", "Revenues"),
])
def test_camino_rapido_sigue_cortando_las_numericas_simples(pregunta, concepto):
    assert g.concepto_coherente(pregunta, concepto)
