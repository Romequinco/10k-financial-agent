"""Regresiones del notebook 06: prosa, concepto pedido y rescate; sin red ni modelo real."""
import pytest
from langchain.messages import AIMessage, HumanMessage, ToolMessage

from agente10k import guardrails as g
from agente10k.herramientas import get_xbrl_fact
from test_guardrails_middleware import AM, NV, correr, final, tc


def respuesta_nv(i, texto):
    return final(i, cifra=44_301e6, unidad="USD", ticker="NVDA", ejercicio=2024,
                 concept_xbrl="GrossProfit", respuesta=texto)


@pytest.mark.parametrize("corrige", [True, False])
def test_importe_en_prosa_reintenta_y_solo_retira_el_texto_si_persiste(corrige):
    mala = "El beneficio bruto fue de 99.999 millones de USD."
    buena = "El beneficio bruto fue de 44.301 millones de USD."
    res, modelo = correr([tc("get_xbrl_fact", NV, 1), respuesta_nv(2, mala),
                          respuesta_nv(3, buena if corrige else mala)])
    r, guard = res["structured_response"], res["guard"]
    assert modelo.n == 3 and guard["reintentos"] == 1
    assert r.cifra == 44_301e6 and r.fuente == "xbrl"
    assert r.respuesta == (buena if corrige else g.TEXTO_PROSA_RETIRADA)
    assert guard["degradada"] is (not corrige)
    aviso = next(m.content for m in res["messages"] if isinstance(m, HumanMessage) and g.MARCA in m.content)
    assert "Importes en respuesta" in aviso and "no basta con cambiar cifra" in aviso


def test_importe_correcto_en_prosa_no_pide_reintento():
    texto = "El beneficio bruto fue de 44.301 millones de USD."
    res, modelo = correr([tc("get_xbrl_fact", NV, 1), respuesta_nv(2, texto)])
    assert modelo.n == 2 and res["guard"]["reintentos"] == 0
    assert res["structured_response"].respuesta == texto


def test_cita_inventada_no_puede_respaldar_su_propio_importe():
    inf = g.verificar_xbrl({"fuente": "texto", "respuesta": "Ingresó 999 millones de USD.",
                           "cita": "Revenue was $999 million."}, [], [])
    assert "importe_prosa_sin_respaldo" in inf.modelo
    assert not g._sin_importes_sin_soporte(inf.resp, [], [])


def test_importe_de_observacion_real_no_exige_xbrl_en_prosa():
    obs = [{"name": "search_filings", "content": "[AAPL-2024-7A-0001] AAPL FY2024 Item 7A\n"
            "The Company had $538 million in foreign currency forward contracts."}]
    inf = g.verificar_xbrl({"fuente": "texto", "respuesta": "Contratos por 538 millones de USD."}, [], obs)
    assert inf.modelo == []


@pytest.mark.parametrize("texto", [
    "No está en el corpus, pero estimo un margen del 50,28 %.",
    "No está disponible, pero estimo 99.999 millones de USD.",
    "El margen fue de 50,28 %.",
])
@pytest.mark.parametrize("fuente", ["ninguna", "xbrl"])
def test_hueco_con_estimacion_solo_en_prosa_se_limpia_sin_reintento(texto, fuente):
    res, modelo = correr([tc("get_xbrl_fact", AM, 1),
                          final(2, fuente=fuente, respuesta=texto, ticker="AMZN", ejercicio=2025)],
                         pregunta="¿Cuál fue el margen bruto de AMZN FY2025?")
    r = res["structured_response"]
    assert modelo.n == 2 and res["guard"]["reintentos"] == 0
    assert (r.cifra, r.cifra_base, r.fuente) == (None, None, "ninguna")
    assert g.importes_prosa(r.respuesta) == [] and "FY2025" in r.respuesta


@pytest.mark.parametrize("fy", [2024, 2025])
def test_rescate_del_bucle_respeta_el_ejercicio_pedido(fy):
    def bucle():
        i = 0
        while True:
            i += 1
            yield tc("get_xbrl_fact", {**AM, "fiscal_year": 2024 if i % 2 else 2025}, i)

    res, modelo = correr(bucle(), pregunta=f"¿Cuál fue el margen bruto de AMZN FY{fy}?")
    r = res["structured_response"]
    assert modelo.n == g.RUN_LIMIT_MODELO
    assert r.ejercicio == fy and f"FY{fy}" in r.respuesta and r.fuente == "ninguna"


def test_hueco_de_otro_ejercicio_no_demuestra_ausencia_del_pedido():
    res, _ = correr([tc("get_xbrl_fact", {**AM, "fiscal_year": 2024}, 1),
                     final(2, cifra=50, unidad="%", concept_xbrl="GrossProfit")],
                    pregunta="¿Cuál fue el margen bruto de AMZN FY2025?")
    r = res["structured_response"]
    assert r.cifra is None and r.ejercicio is None
    assert "No he podido verificar" in r.respuesta and "no reportado" not in r.respuesta.lower()


@pytest.mark.parametrize("corrige", [True, False])
def test_bpa_basico_no_se_cambia_a_diluido_para_aceptar_el_numero(corrige):
    basic = {"ticker": "AAPL", "fiscal_year": 2024, "concept": "EarningsPerShareBasic"}
    diluted = {**basic, "concept": "EarningsPerShareDiluted"}
    valor = g.datos.valor_xbrl("AAPL", 2024, "EarningsPerShareBasic")[0]
    campos = dict(unidad="USD/shares", ticker="AAPL", ejercicio=2024, concept_xbrl="EarningsPerShareBasic")
    res, modelo = correr([tc("get_xbrl_fact", basic, 1), tc("get_xbrl_fact", diluted, 2),
                          final(3, cifra=6.08, **campos), final(4, cifra=valor if corrige else 6.08, **campos)],
                         pregunta="¿Cuál fue el BPA básico de AAPL en FY2024?")
    r = res["structured_response"]
    assert modelo.n == 4 and res["guard"]["reintentos"] == 1
    assert r.cifra == (valor if corrige else None)
    assert r.concept_xbrl == ("EarningsPerShareBasic" if corrige else None)
    assert r.fuente == ("xbrl" if corrige else "ninguna")


def test_rescate_de_texto_plano_tampoco_filtra_un_importe_falso():
    msgs = [HumanMessage("¿Cuál fue el beneficio bruto de NVDA en 2024?"), tc("get_xbrl_fact", NV, 1),
            ToolMessage(content=get_xbrl_fact.invoke(NV), name="get_xbrl_fact", tool_call_id="c1"),
            AIMessage(content="El beneficio bruto fue de 99.999 millones de USD.")]
    r, guard = g.rescatar_respuesta(msgs)
    assert r.cifra == 44_301e6 and r.respuesta == g.TEXTO_PROSA_RETIRADA
    assert "importe_prosa_sin_respaldo" in guard["degradaciones"]


def test_diferencia_solo_se_respalda_entre_misma_empresa_concepto_y_unidad():
    hechos = [g.Hecho("NVDA", 2024, "Revenues", "valor", 100e6, "USD"),
              g.Hecho("NVDA", 2025, "Revenues", "valor", 150e6, "USD")]
    assert not g.importes_sin_respaldo("Creció 50 millones de USD.", hechos, [])
    hechos[1].concept = "GrossProfit"
    assert g.importes_sin_respaldo("Creció 50 millones de USD.", hechos, [])


def test_rescate_sin_consultas_no_afirma_ausencia_ni_conserva_porcentajes_estimados():
    r, guard = g.rescatar_respuesta([HumanMessage("¿Cuál fue el margen de AMZN FY2025?"),
                                   AIMessage(content="No está disponible, pero estimo un 50,28 %.")])
    assert r.fuente == "ninguna" and g.importes_prosa(r.respuesta) == []
    assert r.respuesta == "No he podido verificar el dato solicitado; no lo estimo."
    assert any(c == "abstencion_limpiada" for c, _ in guard["reparaciones"])


def test_bpa_diluido_en_ingles_no_se_confunde_con_basico():
    assert not g.concepto_coherente("What was AAPL diluted EPS in FY2024?", "EarningsPerShareBasic")
    assert g.concepto_coherente("What was AAPL diluted EPS in FY2024?", "EarningsPerShareDiluted")
