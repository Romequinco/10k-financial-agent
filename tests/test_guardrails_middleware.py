"""Middleware del 06 montado en un agente real de LangChain con un modelo falso (sin red ni LLM).

Cubre R04 (límites), R05 (verificación XBRL con un reintento y degradación), la cita por frase numerada,
la fuente derivada, el camino rápido y la salida garantizada sin ``structured_response``.
"""
import pytest
from langchain.agents import create_agent
from langchain.agents.structured_output import ToolStrategy
from langchain.messages import AIMessage, HumanMessage, ToolMessage
from langchain.tools import tool
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langgraph.checkpoint.memory import InMemorySaver

from agente10k import guardrails as g
from agente10k.agente import RespuestaFinanciera
from agente10k.herramientas import get_xbrl_fact, list_available, read_section

BUSQUEDA = (
    "[MSFT-2025-1A-0004] MSFT FY2025 Item 1A · similitud 0.912\n"
    "Our AI systems could be misused in ways that harm people and our reputation today.\n\n"
    "The company may face regulatory scrutiny over the development of artificial intelligence products.\n\n---\n\n"
    "[MSFT-2025-1A-0005] MSFT FY2025 Item 1A · similitud 0.850\n"
    "We rely on third parties to supply components for our devices and cloud infrastructure."
)
FRASE_1 = "Our AI systems could be misused in ways that harm people and our reputation today."
FRASE_2 = "The company may face regulatory scrutiny over the development of artificial intelligence products."
NV = {"ticker": "NVDA", "fiscal_year": 2024, "concept": "GrossProfit"}
AM = {"ticker": "AMZN", "fiscal_year": 2025, "concept": "GrossProfit"}
LLAMADAS_BUSQUEDA: list[dict] = []


@tool
def search_filings(query: str, ticker: str | None = None, fiscal_year: int | None = None,
                   item: str | None = None, k: int = 5) -> str:
    """Busca pasajes (doble de prueba)."""
    LLAMADAS_BUSQUEDA.append({"query": query, "ticker": ticker, "fiscal_year": fiscal_year, "item": item})
    return BUSQUEDA


@pytest.fixture(autouse=True)
def _limpiar_llamadas():
    LLAMADAS_BUSQUEDA.clear()


class Falso(GenericFakeChatModel):
    """Modelo falso que cuenta sus llamadas y acepta bind_tools."""

    n: int = 0
    vistos: list = []

    def bind_tools(self, tools, **kw):
        return self

    def _generate(self, messages, *a, **k):
        object.__setattr__(self, "n", self.n + 1)
        self.vistos.append(list(messages))
        return super()._generate(messages, *a, **k)


def tc(nombre, args, i):
    return AIMessage(content="", tool_calls=[{"name": nombre, "args": args, "id": f"c{i}"}])


def final(i, **kw):
    return tc("RespuestaFinanciera", {"respuesta": "x", "fuente": "xbrl", **kw}, i)


def correr(mensajes, *, camino_rapido=False, pregunta="q", middleware=None, recursion=100, tools=None):
    modelo = Falso(messages=iter(mensajes), vistos=[])
    agente = create_agent(
        model=modelo, tools=tools or [get_xbrl_fact, search_filings, read_section, list_available],
        response_format=ToolStrategy(schema=RespuestaFinanciera),
        middleware=middleware if middleware is not None else g.middleware_final(camino_rapido=camino_rapido),
        checkpointer=InMemorySaver())
    res = agente.invoke({"messages": [{"role": "user", "content": pregunta}]},
                        config={"configurable": {"thread_id": "t"}, "recursion_limit": recursion})
    return res, modelo


def guard(res):
    return res.get("guard") or {}


# ------------------------------------------------------------------ R04: la pila
def test_middleware_final_es_la_pila_real_del_docs_09():
    pila = g.middleware_final()
    assert [type(m).__name__ for m in pila] == [
        "ToolCallLimitMiddleware", "ToolCallLimitMiddleware", "ModelCallLimitMiddleware", "GuardrailsFinal"]
    assert pila[0].run_limit == 8 and pila[0].tool_name is None and pila[0].exit_behavior == "continue"
    assert pila[1].tool_name == "read_section" and pila[1].run_limit == 1
    assert pila[2].run_limit == 10 and pila[2].exit_behavior == "end"


def test_modelo_que_siempre_pide_herramientas_termina_con_respuesta_rescatada():
    """R04: el bucle de la celda 23 termina solo y no queda sin structured_response."""
    def bucle():
        i = 0
        while True:
            i += 1
            yield tc("get_xbrl_fact", {**AM, "fiscal_year": 2024 if i % 2 else 2025}, i)

    res, modelo = correr(bucle())
    r = res["structured_response"]
    assert modelo.n <= g.RUN_LIMIT_MODELO
    assert r is not None and r.fuente == "ninguna" and r.cifra is None
    assert guard(res)["degradada"] and "sin_structured_response" in guard(res)["degradaciones"]
    assert guard(res)["causa"] == "grafo_terminado_sin_respuesta"
    assert r.respuesta == "No reportado en XBRL para AMZN FY2024: el dato no está en el corpus."


def test_read_section_solo_una_vez_por_pregunta():
    args = {"ticker": "NVDA", "fiscal_year": 2025, "item": "7A"}
    res, _ = correr([tc("read_section", args, 1), tc("read_section", {**args, "item": "7"}, 2),
                     final(3, fuente="ninguna")])
    msgs = [m for m in res["messages"] if isinstance(m, ToolMessage) and m.name == "read_section"]
    assert len(msgs) == 2
    assert "limit exceeded" in str(msgs[1].content).lower()
    assert res["structured_response"] is not None


def test_ocho_llamadas_reales_y_la_novena_se_bloquea_pero_la_respuesta_se_conserva():
    llamadas = [tc("search_filings", {"query": f"consulta distinta {i}", "ticker": "MSFT"}, i) for i in range(1, 10)]
    res, _ = correr(llamadas + [final(10, fuente="ninguna")])
    assert len(LLAMADAS_BUSQUEDA) == 8                        # la novena no se ejecuta
    novena = [m for m in res["messages"] if isinstance(m, ToolMessage) and m.tool_call_id == "c9"][0]
    assert "limit exceeded" in str(novena.content).lower()
    assert res["structured_response"] is not None
    assert guard(res)["limite_alcanzado"]


# ------------------------------------------------------------------ R05: verificación de cifras
def test_respuesta_correcta_pasa_intacta_sin_reintento():
    res, modelo = correr([tc("get_xbrl_fact", NV, 1),
                          final(2, cifra=44301e6, unidad="USD", ticker="NVDA", ejercicio=2024,
                                concept_xbrl="GrossProfit")])
    r = res["structured_response"]
    assert modelo.n == 2 and (r.cifra, r.fuente, r.ticker, r.ejercicio) == (44301e6, "xbrl", "NVDA", 2024)
    assert guard(res)["reintentos"] == 0 and not guard(res)["degradada"]


def test_hueco_con_cifra_derivada_se_degrada_a_ninguna_sin_reintentar():
    res, modelo = correr([tc("get_xbrl_fact", AM, 1),
                          final(2, cifra=50.28, unidad="%", ticker="AMZN", ejercicio=2025, fuente="ambas",
                                concept_xbrl="GrossProfit", respuesta="El margen bruto fue de 50,28 %.")])
    r = res["structured_response"]
    assert modelo.n == 2                                       # sin segunda vuelta: ahorra tokens
    assert (r.fuente, r.cifra, r.cifra_base, r.cita) == ("ninguna", None, None, None)
    assert r.respuesta == "No reportado en XBRL para AMZN FY2025: el dato no está en el corpus."
    assert guard(res)["hueco"] and guard(res)["reintentos"] == 0
    assert guard(res)["fuente_declarada"] == "ambas" and guard(res)["fuente_derivada"] == "ninguna"


def test_hueco_con_abstencion_correcta_no_se_toca():
    res, _ = correr([tc("get_xbrl_fact", AM, 1),
                     final(2, fuente="ninguna", ticker="AMZN", ejercicio=2025,
                           respuesta="AMZN no reportó GrossProfit en FY2025.")])
    r = res["structured_response"]
    assert r.respuesta == "AMZN no reportó GrossProfit en FY2025." and r.fuente == "ninguna"


def test_escala_mal_se_corrige_sin_reintento():
    res, modelo = correr([tc("get_xbrl_fact", NV, 1), final(2, cifra=44301, unidad="USD", ticker="NVDA", ejercicio=2024)])
    assert modelo.n == 2 and res["structured_response"].cifra == 44301e6


def test_valor_distinto_reintenta_una_vez_y_el_modelo_corrige():
    res, modelo = correr([tc("get_xbrl_fact", NV, 1),
                          final(2, cifra=45000e6, unidad="USD", ticker="NVDA", ejercicio=2024),
                          final(3, cifra=44301e6, unidad="USD", ticker="NVDA", ejercicio=2024)])
    r = res["structured_response"]
    assert modelo.n == 3 and r.cifra == 44301e6 and r.fuente == "xbrl"
    assert guard(res)["reintentos"] == 1 and not guard(res)["degradada"]
    reintento = [m for m in res["messages"] if isinstance(m, HumanMessage) and g.MARCA in str(m.content)]
    assert len(reintento) == 1 and "no coincide" in reintento[0].content and "GrossProfit FY2024" in reintento[0].content


def test_valor_distinto_que_sigue_mal_se_degrada_sin_inventar():
    res, modelo = correr([tc("get_xbrl_fact", NV, 1),
                          final(2, cifra=45000e6, unidad="USD", ticker="NVDA", ejercicio=2024),
                          final(3, cifra=46000e6, unidad="USD", ticker="NVDA", ejercicio=2024)])
    r = res["structured_response"]
    assert modelo.n == 3                                       # UN reintento, no más
    assert (r.cifra, r.cifra_base, r.fuente) == (None, None, "ninguna")
    assert r.respuesta == g.TEXTO_DEGRADADA
    assert guard(res)["degradada"] and guard(res)["reintentos"] == 1


def test_el_reintento_puede_ser_otra_llamada_a_herramienta_sin_perder_la_respuesta_previa():
    """Tras el aviso el modelo consulta otro ejercicio y responde bien: la respuesta vieja no debe reaparecer."""
    args25 = {**NV, "fiscal_year": 2025}
    res, modelo = correr([tc("get_xbrl_fact", NV, 1),
                          final(2, cifra=45000e6, unidad="USD", ticker="NVDA", ejercicio=2024),
                          tc("get_xbrl_fact", args25, 3),
                          final(4, cifra=44301e6, unidad="USD", ticker="NVDA", ejercicio=2024)])
    r = res["structured_response"]
    assert modelo.n == 4 and r.cifra == 44301e6 and guard(res)["reintentos"] == 1


def test_comparativa_con_cifras_cruzadas_se_reorienta_sin_llamar_al_modelo():
    a = {"ticker": "NVDA", "fiscal_year": 2025, "concept": "EarningsPerShareBasic"}
    b = {**a, "fiscal_year": 2024}
    res, modelo = correr([tc("get_xbrl_fact", a, 1), tc("get_xbrl_fact", b, 2),
                          final(3, cifra=12.05, cifra_base=2.97, unidad="USD/shares", ticker="NVDA",
                                ejercicio=2025, ejercicio_base=2024, fuente="xbrl",
                                concept_xbrl="EarningsPerShareBasic")])
    r = res["structured_response"]
    assert modelo.n == 3 and (r.cifra, r.cifra_base, r.ejercicio, r.ejercicio_base) == (2.97, 12.05, 2025, 2024)


def test_cifra_de_texto_en_extractiva_se_anula_y_no_queda_como_xbrl():
    res, modelo = correr([tc("search_filings", {"query": "x", "ticker": "MSFT"}, 1),
                          final(2, fuente="texto", cifra=538, unidad="USD", concept_xbrl="ForeignExchangeRateRisk",
                                ticker="MSFT", frase_ids=[1])])
    r = res["structured_response"]
    assert (r.cifra, r.concept_xbrl) == (None, None) and r.fuente == "texto" and r.cita == FRASE_1
    assert modelo.n == 2


# ------------------------------------------------------------------ cita por frase numerada
def test_el_modelo_ve_frases_numeradas_pero_lo_guardado_no_lleva_marcas():
    res, modelo = correr([tc("search_filings", {"query": "x", "ticker": "MSFT"}, 1), final(2, fuente="texto", frase_ids=[2])])
    visto = next(m for m in res["messages"] if isinstance(m, ToolMessage) and m.name == "search_filings")
    assert "⟨1⟩ Our AI systems" in visto.content and "⟨2⟩ The company may face" in visto.content
    assert visto.artifact == BUSQUEDA and "⟨" not in visto.artifact
    assert g.observaciones_texto(res["messages"])[0]["content"] == BUSQUEDA
    ultima_vuelta = modelo.vistos[-1]                       # lo que recibió el modelo en su última llamada
    assert any("⟨1⟩" in str(m.content) for m in ultima_vuelta if isinstance(m, ToolMessage))


def test_frase_ids_se_resuelven_a_cita_y_chunk_id_literales():
    res, _ = correr([tc("search_filings", {"query": "x", "ticker": "MSFT"}, 1),
                     final(2, fuente="texto", respuesta="Riesgo de uso indebido de la IA.", frase_ids=[1, 3])])
    r = res["structured_response"]
    assert r.cita == f"{FRASE_1} [...] We rely on third parties to supply components for our devices and cloud infrastructure."
    assert r.chunk_id == "MSFT-2025-1A-0004" and r.fuente == "texto" and (r.ticker, r.ejercicio) == ("MSFT", 2025)
    assert all(pieza in BUSQUEDA for pieza in r.cita.split(" [...] "))


def test_cita_textual_literal_del_modelo_se_verifica_y_se_corrige_el_chunk_id():
    res, _ = correr([tc("search_filings", {"query": "x", "ticker": "MSFT"}, 1),
                     final(2, fuente="texto", cita=FRASE_2, chunk_id="CHUNK-INVENTADO", ticker="MSFT", ejercicio=2025)])
    r = res["structured_response"]
    assert r.cita == FRASE_2 and r.chunk_id == "MSFT-2025-1A-0004"


def test_cita_vacia_con_texto_pide_frase_ids_una_vez_y_se_resuelve():
    res, modelo = correr([tc("search_filings", {"query": "x", "ticker": "MSFT"}, 1),
                          final(2, fuente="texto", respuesta="AI risk"),
                          final(3, fuente="texto", respuesta="AI risk", frase_ids=[2])])
    r = res["structured_response"]
    assert modelo.n == 3 and r.cita == FRASE_2 and r.fuente == "texto"
    aviso = [m for m in res["messages"] if isinstance(m, HumanMessage) and g.MARCA in str(m.content)][0]
    assert "frase_ids" in aviso.content and "⟨n⟩" in aviso.content
    assert guard(res)["reintentos"] == 1


def test_comparativa_con_texto_consultado_pero_sin_cita_pide_la_frase_aunque_declare_xbrl():
    a = {"ticker": "NVDA", "fiscal_year": 2025, "concept": "EarningsPerShareBasic"}
    comp = dict(cifra=2.97, cifra_base=12.05, unidad="USD/shares", ticker="NVDA", ejercicio=2025,
                ejercicio_base=2024, concept_xbrl="EarningsPerShareBasic")
    res, modelo = correr([tc("get_xbrl_fact", a, 1), tc("get_xbrl_fact", {**a, "fiscal_year": 2024}, 2),
                          tc("search_filings", {"query": "split", "ticker": "NVDA"}, 3),
                          final(4, fuente="xbrl", **comp), final(5, fuente="ambas", frase_ids=[2], **comp)])
    r = res["structured_response"]
    assert modelo.n == 5 and r.fuente == "ambas" and r.cita == FRASE_2 and r.cifra_base == 12.05
    assert guard(res)["reintentos"] == 1


def test_cita_inventada_y_frase_inexistente_se_descartan_tras_un_reintento():
    res, modelo = correr([tc("search_filings", {"query": "x", "ticker": "MSFT"}, 1),
                          final(2, fuente="texto", cita="Frase que ninguna herramienta devolvió jamás en su vida."),
                          final(3, fuente="texto", frase_ids=[77])])
    r = res["structured_response"]
    assert modelo.n == 3
    assert (r.cita, r.chunk_id, r.fuente) == (None, None, "ninguna")     # sin evidencia verificada: no hay 'texto'
    assert r.respuesta.startswith(g.TEXTO_SIN_EVIDENCIA)
    assert guard(res)["degradada"]


def test_fuente_declarada_se_sobrescribe_con_la_derivada_de_la_evidencia():
    # el modelo dice 'xbrl' pero solo hay texto citado
    res, _ = correr([tc("search_filings", {"query": "x", "ticker": "MSFT"}, 1), final(2, fuente="xbrl", frase_ids=[1])])
    assert res["structured_response"].fuente == "texto"
    # el modelo dice 'texto' pero solo hay cifra verificada
    res, _ = correr([tc("get_xbrl_fact", NV, 1),
                     final(2, fuente="texto", cifra=44301e6, unidad="USD", ticker="NVDA", ejercicio=2024)])
    assert res["structured_response"].fuente == "xbrl"
    # cifra verificada y cita verificada
    res, _ = correr([tc("get_xbrl_fact", NV, 1), tc("search_filings", {"query": "x", "ticker": "NVDA"}, 2),
                     final(3, fuente="xbrl", cifra=44301e6, unidad="USD", ticker="NVDA", ejercicio=2024, frase_ids=[1])])
    assert res["structured_response"].fuente == "ambas"
    # ninguna cosa verificada
    res, _ = correr([tc("list_available", {}, 1), final(2, fuente="ninguna", respuesta="No consta en el corpus.")])
    assert res["structured_response"].fuente == "ninguna"


def test_llamadas_paralelas_no_repiten_ids_de_frase():
    dos = AIMessage(content="", tool_calls=[
        {"name": "search_filings", "args": {"query": "a", "ticker": "MSFT"}, "id": "p1"},
        {"name": "search_filings", "args": {"query": "b", "ticker": "MSFT"}, "id": "p2"}])
    res, _ = correr([dos, final(3, fuente="texto", frase_ids=[1])])
    numeros = []
    for m in res["messages"]:
        if isinstance(m, ToolMessage) and m.name == "search_filings":
            numeros += g.re.findall(r"⟨(\d+)⟩", m.content)
    assert len(numeros) == len(set(numeros)) == 6


# ------------------------------------------------------------------ argumentos corruptos y duplicados
def test_llamada_repetida_no_reejecuta_la_herramienta():
    res, _ = correr([tc("search_filings", {"query": "AI  risks", "ticker": "MSFT"}, 1),
                     tc("search_filings", {"query": "ai risks", "ticker": "msft"}, 2),
                     final(3, fuente="texto", frase_ids=[1])])
    assert len(LLAMADAS_BUSQUEDA) == 1
    bloqueada = [m for m in res["messages"] if isinstance(m, ToolMessage) and m.tool_call_id == "c2"][0]
    assert bloqueada.content.startswith("Llamada repetida")
    assert guard(res)["duplicadas"] == 1
    assert res["structured_response"].cita == FRASE_1                 # el id 1 sigue vigente
    # El aviso recuerda qué frases ya tiene: sin eso el modelo se queda sin nada que citar y repite
    # la llamada hasta agotar el límite (visto en una tanda real: 9 búsquedas idénticas y sin cita).
    assert "elige frase_ids entre ellas" in bloqueada.content
    assert g.re.search(r"⟨\d+⟩ a ⟨\d+⟩", bloqueada.content)


def test_el_aviso_de_repetida_no_promete_frases_si_no_hay_ninguna():
    assert g._aviso_repetida([]) == g.MSG_REPETIDA


def test_dos_llamadas_identicas_en_el_mismo_mensaje_se_ejecutan_las_dos():
    doble = AIMessage(content="", tool_calls=[
        {"name": "search_filings", "args": {"query": "a", "ticker": "MSFT"}, "id": "p1"},
        {"name": "search_filings", "args": {"query": "a", "ticker": "MSFT"}, "id": "p2"}])
    res, _ = correr([doble, final(3, fuente="ninguna")])
    assert len(LLAMADAS_BUSQUEDA) == 2                       # la mejora sobre docs/09 §3: no se bloquean entre sí


def test_argumentos_con_marcado_filtrado_se_reparan_en_el_estado_y_en_la_ejecucion():
    corrupto = {"query": "AWS growth", "ticker": 'MSFT", "fiscal_year": 2025, "item": "1A"}}]</think>'
                                                 '<tool_call>search_filings</arg_value>'}
    res, _ = correr([tc("search_filings", corrupto, 1), final(2, fuente="texto", frase_ids=[1])])
    assert LLAMADAS_BUSQUEDA[0]["ticker"] == "MSFT" and LLAMADAS_BUSQUEDA[0]["fiscal_year"] == 2025
    llamada = next(t for m in res["messages"] if isinstance(m, AIMessage) for t in m.tool_calls
                   if t["name"] == "search_filings")
    assert llamada["args"]["ticker"].startswith("MSFT")   # la trayectoria conserva lo que el modelo emitió; la tool lo sanea
    assert llamada["id"] == "c1"                                                     # misma llamada, no sintética


def test_wrap_tool_call_sanea_argumentos_aunque_el_estado_no_se_haya_reparado():
    class Peticion:
        def __init__(self, tool_call):
            self.tool_call, self.state = tool_call, {"messages": []}

        def override(self, **cambios):
            return Peticion(cambios.get("tool_call", self.tool_call))

    vistos = []

    def manejador(peticion):
        vistos.append(peticion.tool_call["args"])
        return ToolMessage(content="[MSFT-2025-1A-0001] MSFT FY2025 Item 1A\nSome sentence with enough words in it today.",
                           tool_call_id="c1", name="search_filings")

    corrupto = {"name": "search_filings", "id": "c1", "args": {
        "query": "q", "ticker": 'MSFT", "fiscal_year": 2025}}]</think>'}}
    res = g.GuardrailsFinal().wrap_tool_call(Peticion(corrupto), manejador)
    assert vistos == [{"query": "q", "ticker": "MSFT", "fiscal_year": 2025}]
    assert "⟨1⟩" in res.content and res.artifact.startswith("[MSFT-2025-1A-0001]")


def test_variable_de_entorno_apaga_el_camino_rapido(monkeypatch):
    assert g.middleware_final()[-1].camino_rapido is True
    monkeypatch.setenv("AGENTE10K_CAMINO_RAPIDO", "0")
    assert g.middleware_final()[-1].camino_rapido is False
    assert g.middleware_final(camino_rapido=True)[-1].camino_rapido is True      # el parámetro manda


def test_el_codigo_nunca_sintetiza_tool_calls():
    res, _ = correr([tc("get_xbrl_fact", NV, 1),
                     final(2, cifra=44301, unidad="USD", ticker="NVDA", ejercicio=2024)])
    reales = [t for m in res["messages"] if isinstance(m, AIMessage) for t in m.tool_calls
              if t["name"] in g.NOMBRES_TOOLS]
    assert [t["name"] for t in reales] == ["get_xbrl_fact"]


# ------------------------------------------------------------------ salida garantizada
def test_texto_plano_reintenta_una_vez_con_el_esquema_y_acepta_la_respuesta():
    res, modelo = correr([tc("get_xbrl_fact", NV, 1), AIMessage(content="Es 44.301 millones."),
                          final(3, cifra=44301e6, unidad="USD", ticker="NVDA", ejercicio=2024)])
    assert modelo.n == 3 and res["structured_response"].cifra == 44301e6
    assert guard(res)["reintentos_esquema"] == 1


def test_texto_plano_dos_veces_rescata_del_ledger_en_lugar_de_fallback_vacio():
    res, modelo = correr([tc("get_xbrl_fact", NV, 1), AIMessage(content="Es 44.301 millones."),
                          AIMessage(content="Insisto. Es 44.301 millones.")])
    r = res["structured_response"]
    assert modelo.n == 3
    assert (r.cifra, r.fuente, r.ejercicio, r.ticker, r.concept_xbrl) == (44301e6, "xbrl", 2024, "NVDA", "GrossProfit")
    assert "44.301" in r.respuesta and not r.respuesta.startswith(g.TEXTO_SIN_EVIDENCIA)
    assert "sin_structured_response" in guard(res)["degradaciones"]


def test_rescate_sin_ledger_marca_la_respuesta_como_no_verificada():
    res, _ = correr([AIMessage(content="Creo que fue 44.301 millones."), AIMessage(content="Sí, 44.301.")])
    r = res["structured_response"]
    assert r.fuente == "ninguna" and r.cifra is None and r.respuesta.startswith(g.TEXTO_SIN_EVIDENCIA)


def test_rescate_ante_hueco_usa_la_plantilla_de_abstencion():
    res, _ = correr([tc("get_xbrl_fact", AM, 1), AIMessage(content="No lo sé."), AIMessage(content="Unos 50 %.")])
    r = res["structured_response"]
    assert r.fuente == "ninguna" and r.respuesta == "No reportado en XBRL para AMZN FY2025: el dato no está en el corpus."


def test_rescatar_respuesta_desde_un_estado_sin_structured_response():
    msgs = [HumanMessage("q"), AIMessage(content="", tool_calls=[{"name": "get_xbrl_fact", "id": "a", "args": NV}]),
            ToolMessage(content="NVDA FY2024 · GrossProfit = 44,301,000,000 USD. Valor sin escalar para el campo cifra: 44301000000.",
                        tool_call_id="a", name="get_xbrl_fact"), AIMessage(content="Beneficio bruto: 44.301 millones.")]
    r, guard_r = g.rescatar_respuesta(msgs)
    assert isinstance(r, RespuestaFinanciera) and r.cifra == 44301e6 and guard_r["degradada"]


# ------------------------------------------------------------------ camino rápido
def test_camino_rapido_construye_la_respuesta_del_ledger_y_ahorra_la_segunda_llamada():
    pregunta = "¿Cuál fue el beneficio bruto de NVDA en el ejercicio fiscal 2024?"
    res, modelo = correr([tc("get_xbrl_fact", NV, 1)], camino_rapido=True, pregunta=pregunta)
    r = res["structured_response"]
    assert modelo.n == 1                                       # el modelo solo eligió la herramienta
    assert (r.cifra, r.unidad, r.ticker, r.ejercicio, r.fuente, r.concept_xbrl) == (
        44301e6, "USD", "NVDA", 2024, "xbrl", "GrossProfit")
    assert "44.301 millones de USD" in r.respuesta
    assert guard(res)["camino_rapido"] is True
    reales = [t for m in res["messages"] if isinstance(m, AIMessage) for t in m.tool_calls]
    assert [t["name"] for t in reales] == ["get_xbrl_fact"]    # la llamada fue del modelo, nada sintetizado


def test_camino_rapido_hueco_se_abstiene_sin_segunda_llamada():
    res, modelo = correr([tc("get_xbrl_fact", AM, 1)], camino_rapido=True,
                         pregunta="¿Cuál fue el margen bruto de AMZN en el ejercicio fiscal 2025?")
    r = res["structured_response"]
    assert modelo.n == 1 and (r.fuente, r.cifra) == ("ninguna", None)
    assert r.respuesta == "No reportado en XBRL para AMZN FY2025: el dato no está en el corpus."


@pytest.mark.parametrize("pregunta,llamadas", [
    # concepto alternativo (el modelo pidió otra magnitud)
    ("¿Cuál fue el patrimonio neto de NVDA en el ejercicio fiscal 2024?", [tc("get_xbrl_fact", NV, 1)]),
    # magnitud derivada
    ("¿Cuál fue el margen bruto de NVDA en el ejercicio fiscal 2024?", [tc("get_xbrl_fact", NV, 1)]),
    # comparativa / explicativa
    ("¿Cómo evolucionó el beneficio bruto de NVDA entre 2024 y 2025 y por qué?", [tc("get_xbrl_fact", NV, 1)]),
    # ticker o ejercicio que no coinciden con la pregunta
    ("¿Cuál fue el beneficio bruto de MSFT en el ejercicio fiscal 2024?", [tc("get_xbrl_fact", NV, 1)]),
    ("¿Cuál fue el beneficio bruto de NVDA en el ejercicio fiscal 2025?", [tc("get_xbrl_fact", NV, 1)]),
    # sugerencia de la herramienta: no es un valor ni un hueco
    ("¿Cuáles fueron los ingresos de META en el ejercicio fiscal 2024?",
     [tc("get_xbrl_fact", {"ticker": "META", "fiscal_year": 2024, "concept": "Revenues"}, 1)]),
])
def test_camino_rapido_no_corta_si_hay_duda(pregunta, llamadas):
    res, modelo = correr(llamadas + [final(9, fuente="ninguna", respuesta="No consta.")], camino_rapido=True,
                         pregunta=pregunta)
    assert modelo.n == 2 and guard(res)["camino_rapido"] is False


def test_camino_rapido_no_corta_con_mas_de_una_llamada():
    args25 = {**NV, "fiscal_year": 2025}
    res, modelo = correr([AIMessage(content="", tool_calls=[
        {"name": "get_xbrl_fact", "args": NV, "id": "a"}, {"name": "get_xbrl_fact", "args": args25, "id": "b"}]),
        final(3, fuente="ninguna", respuesta="No consta.")],
        camino_rapido=True, pregunta="¿Cuál fue el beneficio bruto de NVDA en el ejercicio fiscal 2024?")
    assert modelo.n == 2


def test_camino_rapido_desactivable_por_parametro():
    res, modelo = correr([tc("get_xbrl_fact", NV, 1),
                          final(2, cifra=44301e6, unidad="USD", ticker="NVDA", ejercicio=2024)],
                         camino_rapido=False, pregunta="¿Cuál fue el beneficio bruto de NVDA en el ejercicio fiscal 2024?")
    assert modelo.n == 2 and guard(res)["camino_rapido"] is False
