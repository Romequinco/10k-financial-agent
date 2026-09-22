"""Montaje del sistema final en agente.py (sin red): esquema, prompts, caché, ejecutar() y rescate."""
import hashlib

import pytest
from langchain.messages import AIMessage, HumanMessage, ToolMessage

from agente10k import agente, config, guardrails, herramientas, retrieval
from test_guardrails_middleware import FRASE_2, NV, Falso, final, tc

HASH_SYSTEM_PROMPT = "a106bf7ae914830afcb33f9792f718bede0263963299ee6cde5a65b41c2d79ad"
CAMPOS_ORIGINALES = {"respuesta", "cifra", "unidad", "ticker", "ejercicio", "fuente", "cita", "chunk_id",
                     "concept_xbrl", "ejercicio_base", "cifra_base"}
PREGUNTA_NUMERICA = "¿Cuál fue el beneficio bruto de NVDA en el ejercicio fiscal 2024?"
HITS = [{"chunk_id": "MSFT-2025-1A-0004", "ticker": "MSFT", "fiscal_year": 2025, "item": "1A", "puntuacion": 0.9,
         "texto": "Our AI systems could be misused in ways that harm people and our reputation today. " + FRASE_2}]


@pytest.fixture(autouse=True)
def _cache_limpia():
    agente.limpiar_cache_agentes()
    yield
    agente.limpiar_cache_agentes()


def _con_modelo(monkeypatch, mensajes):
    """Sistema real (create_agent y middleware reales) con un modelo falso en lugar de OpenRouter."""
    modelos = []

    def crear(*a, **kw):
        modelo = Falso(messages=iter(mensajes), vistos=[])
        modelos.append(modelo)
        return modelo

    monkeypatch.setattr(agente.config, "crear_modelo", crear)
    return modelos


def _sin_retrieval_real(monkeypatch):
    monkeypatch.setattr(retrieval, "buscar", lambda *a, **kw: HITS)
    monkeypatch.setattr(retrieval, "precalentar", lambda: None, raising=False)


# ------------------------------------------------------------------ regex de _respuesta_acotada
def test_respuesta_acotada_lee_el_bpa_aunque_la_frase_termine_en_punto():
    evidencia = ("AAPL FY2025 · EarningsPerShareDiluted = 7.46 USD/shares (cierre 2025-09-27, formulario 10-K). "
                 "Valor sin escalar para el campo cifra: 7.46.")
    r = agente._respuesta_acotada("p", "get_xbrl_fact", {"ticker": "AAPL", "fiscal_year": 2025,
                                                         "concept": "EarningsPerShareDiluted"}, evidencia, "t")
    assert (r.cifra, r.unidad) == (7.46, "USD/shares")


def test_respuesta_acotada_admite_valores_negativos_y_enteros():
    evidencia = ("AMZN FY2025 · NetIncomeLoss = -1,234 USD (cierre 2025-12-31, formulario 10-K). "
                 "Valor sin escalar para el campo cifra: -1234.")
    r = agente._respuesta_acotada("p", "get_xbrl_fact", {"ticker": "AMZN"}, evidencia, "t")
    assert (r.cifra, r.unidad) == (-1234.0, "USD")
    r = agente._respuesta_acotada("p", "get_xbrl_fact", {"ticker": "NVDA"},
                                  "NVDA FY2024 · GrossProfit = 44,301,000,000 USD (cierre x). "
                                  "Valor sin escalar para el campo cifra: 44301000000.", "t")
    assert r.cifra == 44_301_000_000.0


# ------------------------------------------------------------------ esquema y prompts
def test_esquema_de_baseline_y_candidato_no_incluye_campos_del_final():
    assert set(agente.RespuestaSinFrases.model_json_schema()["properties"]) == CAMPOS_ORIGINALES
    assert set(agente.RespuestaFinanciera.model_json_schema()["properties"]) == CAMPOS_ORIGINALES | {"frase_ids"}
    assert agente.RespuestaSinFrases.__name__ == "RespuestaFinanciera"      # el nombre de la tool estructurada
    assert agente.RespuestaSinFrases.model_json_schema()["required"] == ["respuesta", "fuente"]


@pytest.mark.parametrize("sistema,esperado", [
    ("baseline", "sin_frases"), ("cascada", "sin_frases"), ("candidato_07", "sin_frases"), ("final", "completo")])
def test_cada_sistema_usa_su_esquema(monkeypatch, sistema, esperado):
    creado = {}
    monkeypatch.setattr(agente.config, "crear_modelo", lambda *a, **kw: object())
    monkeypatch.setattr(agente, "create_agent", lambda **kw: creado.update(kw) or kw)
    agente.construir_agente(sistema)
    esquema = creado["response_format"].schema
    assert esquema is (agente.RespuestaFinanciera if esperado == "completo" else agente.RespuestaSinFrases)


def test_prompt_baseline_congelado_y_final_propio_sin_tocar_el_del_candidato():
    assert hashlib.sha256(agente.SYSTEM_PROMPT.encode()).hexdigest() == HASH_SYSTEM_PROMPT
    assert agente._prompt_sistema("baseline") is agente.SYSTEM_PROMPT
    assert agente._prompt_sistema("candidato_07") == agente.SYSTEM_PROMPT + agente.TRAZABILIDAD_CANDIDATO
    final = agente._prompt_sistema("final")
    assert final == agente.SYSTEM_PROMPT_FINAL == agente.SYSTEM_PROMPT + agente.TRAZABILIDAD_FINAL
    assert "frase_ids" not in agente.SYSTEM_PROMPT_CANDIDATO and "frase_ids" not in agente.SYSTEM_PROMPT
    for clave in ("frase_ids", "⟨n⟩", "como máximo 4 llamadas", "una o dos frases", 'fuente="ninguna"',
                  "cifra procede solo de get_xbrl_fact"):
        assert clave in final
    assert "ancla_texto" not in final and "respuesta_esperada" not in final      # nada del golden


def test_respuesta_valida_convierte_el_esquema_sin_frases():
    salida = agente.RespuestaSinFrases(respuesta="x", fuente="ninguna")
    r = agente._respuesta_valida(salida)
    assert isinstance(r, agente.RespuestaFinanciera) and r.frase_ids is None


# ------------------------------------------------------------------ el sistema final ya se monta
def test_final_se_monta_con_la_pila_real_y_no_lanza_sistema_final_no_disponible(monkeypatch):
    _con_modelo(monkeypatch, [])
    _sin_retrieval_real(monkeypatch)
    ag = agente.construir_agente("final")                    # antes: SistemaFinalNoDisponible
    assert ag is not None
    _, middleware = agente._componentes_sistema("final")
    assert [type(m).__name__ for m in middleware] == [
        "ToolCallLimitMiddleware", "ToolCallLimitMiddleware", "ModelCallLimitMiddleware", "GuardrailsFinal"]


def test_final_sigue_sin_caer_al_baseline_si_la_pila_estuviera_vacia(monkeypatch):
    monkeypatch.setattr(guardrails, "middleware_final", lambda: [])
    with pytest.raises(agente.SistemaFinalNoDisponible):
        agente._componentes_sistema("final")


# ------------------------------------------------------------------ ejecutar() del final
def test_ejecutar_final_camino_rapido_devuelve_guard_y_una_sola_llamada_al_modelo(monkeypatch):
    modelos = _con_modelo(monkeypatch, [tc("get_xbrl_fact", NV, 1)])
    _sin_retrieval_real(monkeypatch)
    r = agente.ejecutar(PREGUNTA_NUMERICA, "final")
    assert r["error"] is None and r["llamadas_modelo"] == 1 and modelos[0].n == 1
    assert (r["respuesta"].cifra, r["respuesta"].fuente) == (44301e6, "xbrl")
    assert r["guard"]["camino_rapido"] is True and "reintentos" in r["guard"] and "degradaciones" in r["guard"]
    assert [t["name"] for t in r["tool_calls"]] == ["get_xbrl_fact"] and r["n_llamadas"] == 1


def test_ejecutar_final_texto_resuelve_frase_ids_y_guarda_observaciones_sin_marcas(monkeypatch):
    _con_modelo(monkeypatch, [tc("search_filings", {"query": "ai misuse", "ticker": "MSFT"}, 1),
                              final(2, fuente="texto", respuesta="Riesgo de mal uso de la IA.", frase_ids=[2])])
    _sin_retrieval_real(monkeypatch)
    r = agente.ejecutar("¿Qué dice Microsoft sobre el uso indebido de sus sistemas de IA en FY2025?", "final")
    assert r["respuesta"].cita == FRASE_2 and r["respuesta"].chunk_id == "MSFT-2025-1A-0004"
    assert r["respuesta"].fuente == "texto" and r["respuesta"].frase_ids == [2]
    obs = r["observaciones"]
    assert len(obs) == 1 and "⟨" not in obs[0]["content"] and obs[0]["content"].startswith("[MSFT-2025-1A-0004]")
    assert FRASE_2 in obs[0]["content"]                       # la cita es literal de lo GUARDADO (no partido)
    assert r["guard"]["reparaciones"] and r["guard"]["fuente_derivada"] == "texto"


def test_ejecutar_final_pasa_la_pregunta_a_herramientas_y_la_limpia(monkeypatch):
    llamadas = []
    monkeypatch.setattr(herramientas, "fijar_pregunta_actual", lambda t: llamadas.append(t), raising=False)
    _con_modelo(monkeypatch, [tc("get_xbrl_fact", NV, 1)])
    _sin_retrieval_real(monkeypatch)
    agente.ejecutar(PREGUNTA_NUMERICA, "final")
    assert llamadas == [PREGUNTA_NUMERICA, ""]


def test_el_baseline_no_recibe_la_pregunta_ni_calienta_el_retrieval(monkeypatch):
    llamadas, calentado = [], []
    monkeypatch.setattr(herramientas, "fijar_pregunta_actual", lambda t: llamadas.append(t), raising=False)
    monkeypatch.setattr(retrieval, "precalentar", lambda: calentado.append(1), raising=False)
    _con_modelo(monkeypatch, [tc("get_xbrl_fact", NV, 1),
                              tc("RespuestaFinanciera", {"respuesta": "x", "fuente": "xbrl", "cifra": 44301e6,
                                                         "unidad": "USD"}, 2)])
    r = agente.ejecutar(PREGUNTA_NUMERICA, "baseline")
    assert llamadas == [] and calentado == []
    assert r["guard"] == {} and r["respuesta"].cifra == 44301e6 and r["respuesta"].frase_ids is None


def test_final_precalienta_el_retrieval_una_sola_vez_y_reutiliza_el_agente(monkeypatch):
    calentado, creados = [], []
    monkeypatch.setattr(retrieval, "precalentar", lambda: calentado.append(1), raising=False)
    monkeypatch.setattr(retrieval, "buscar", lambda *a, **kw: HITS)
    monkeypatch.setattr(agente.config, "crear_modelo", lambda *a, **kw: creados.append(1) or Falso(
        messages=iter([tc("get_xbrl_fact", NV, 1), tc("get_xbrl_fact", NV, 2)]), vistos=[]))
    for _ in range(2):
        agente.ejecutar(PREGUNTA_NUMERICA, "final")
    assert calentado == [1] and creados == [1]               # un solo agente y un solo calentamiento


def test_precalentamiento_fallido_no_tumba_la_pregunta(monkeypatch):
    def falla():
        raise RuntimeError("sin modelo BGE")

    monkeypatch.setattr(retrieval, "precalentar", falla, raising=False)
    _con_modelo(monkeypatch, [tc("get_xbrl_fact", NV, 1)])
    monkeypatch.setattr(retrieval, "buscar", lambda *a, **kw: HITS)
    assert agente.ejecutar(PREGUNTA_NUMERICA, "final")["respuesta"].cifra == 44301e6


# ------------------------------------------------------------------ caché de agentes
def test_cache_construye_un_agente_por_sistema_y_permite_desactivarla(monkeypatch):
    construidos = []

    class AgenteFalso:
        def invoke(self, entrada, config):
            return {"messages": [], "structured_response": agente.RespuestaFinanciera(respuesta="x", fuente="ninguna")}

        def get_state(self, config):
            return type("E", (), {"values": {}})()

    monkeypatch.setattr(agente, "construir_agente", lambda sistema, **kw: construidos.append(sistema) or AgenteFalso())
    agente.ejecutar("a", "baseline")
    agente.ejecutar("b", "baseline")
    assert construidos == ["baseline"]
    agente.ejecutar("c", "candidato_07")
    assert construidos == ["baseline", "candidato_07"]
    agente.ejecutar("d", "baseline", usar_cache=False)
    assert construidos == ["baseline", "candidato_07", "baseline"]


def test_cada_pregunta_usa_su_hilo_aunque_el_agente_se_reutilice(monkeypatch):
    _con_modelo(monkeypatch, [tc("get_xbrl_fact", NV, 1), tc("get_xbrl_fact", NV, 2)])
    monkeypatch.setattr(retrieval, "buscar", lambda *a, **kw: HITS)
    monkeypatch.setattr(retrieval, "precalentar", lambda: None, raising=False)
    a = agente.ejecutar(PREGUNTA_NUMERICA, "final")
    b = agente.ejecutar(PREGUNTA_NUMERICA, "final")
    assert a["thread_id"] != b["thread_id"]
    assert a["respuesta"].cifra == b["respuesta"].cifra == 44301e6


# ------------------------------------------------------------------ rescate cuando el grafo revienta
def test_ejecutar_final_rescata_del_estado_si_el_grafo_lanza_una_excepcion(monkeypatch):
    mensajes = [HumanMessage("q"), AIMessage(content="", tool_calls=[{"name": "get_xbrl_fact", "id": "a", "args": NV}]),
                ToolMessage(content="NVDA FY2024 · GrossProfit = 44,301,000,000 USD (cierre x). Valor sin escalar "
                                    "para el campo cifra: 44301000000.", tool_call_id="a", name="get_xbrl_fact"),
                AIMessage(content="El beneficio bruto de NVDA fue de 44.301 millones de USD.")]

    class AgenteRoto:
        def invoke(self, entrada, config):
            raise RuntimeError("GraphRecursionError simulado")

        def get_state(self, config):
            return type("E", (), {"values": {"messages": mensajes}})()

    monkeypatch.setattr(agente, "construir_agente", lambda sistema, **kw: AgenteRoto())
    r = agente.ejecutar(PREGUNTA_NUMERICA, "final")
    assert r["error"].startswith("RuntimeError")             # el error sigue trazado
    assert r["respuesta"].cifra == 44301e6 and r["respuesta"].fuente == "xbrl"
    assert r["guard"]["degradada"] and r["guard"]["fuente_derivada"] == "xbrl"


def test_ejecutar_sin_guardrails_sigue_devolviendo_el_fallback_vacio(monkeypatch):
    class AgenteRoto:
        def invoke(self, entrada, config):
            raise RuntimeError("caída")

        def get_state(self, config):
            return type("E", (), {"values": {}})()

    monkeypatch.setattr(agente, "construir_agente", lambda sistema, **kw: AgenteRoto())
    r = agente.ejecutar("p", "candidato_07")
    assert r["respuesta"].fuente == "ninguna" and r["respuesta"].respuesta == agente.FALLBACK["respuesta"]
    assert r["guard"] == {}
