"""Pruebas offline del arnés baseline: no usan API ni requieren una clave."""
from langchain.messages import AIMessage, ToolMessage

from agente10k import agente


LLAMADA_XBRL = {
    "name": "get_xbrl_fact", "id": "call-xbrl",
    "args": {"ticker": "NVDA", "fiscal_year": 2024, "concept": "Revenues"},
}
SALIDA = {
    "respuesta": "NVIDIA reportó 60.922 millones de USD.", "cifra": 60_922_000_000,
    "unidad": "USD", "ticker": "NVDA", "ejercicio": 2024, "fuente": "xbrl",
    "concept_xbrl": "Revenues",
}


class AgenteFalso:
    """Doble mínimo que deja inspeccionar el hilo sin ejecutar un modelo."""

    def __init__(self, resultado=None, error=None):
        self.resultado = resultado or {}
        self.error = error
        self.configuraciones = []

    def invoke(self, entrada, config):
        self.configuraciones.append(config)
        if self.error:
            raise self.error
        return self.resultado

    def get_state(self, config):
        class Estado:
            values = {}
        return Estado()


def test_ejecutar_guarda_trayectoria_y_no_cuenta_salida_estructurada(monkeypatch):
    mensajes = [
        AIMessage(content="", tool_calls=[LLAMADA_XBRL]),
        ToolMessage(content="valor sin escalar", tool_call_id="call-xbrl", name="get_xbrl_fact"),
        AIMessage(content="", tool_calls=[{"name": "RespuestaFinanciera", "id": "final", "args": SALIDA}]),
    ]
    falso = AgenteFalso({"messages": mensajes, "structured_response": SALIDA})
    monkeypatch.setattr(agente, "construir_agente", lambda sistema: falso)

    resultado = agente.ejecutar("¿Revenue de NVIDIA?", "baseline")

    assert resultado["error"] is None
    assert resultado["respuesta"].cifra == 60_922_000_000
    assert [llamada["name"] for llamada in resultado["tool_calls"]] == ["get_xbrl_fact"]
    assert resultado["n_llamadas"] == 1
    assert falso.configuraciones[0]["recursion_limit"] == 100
    assert falso.configuraciones[0]["configurable"]["thread_id"] == resultado["thread_id"]


def test_ejecutar_crea_hilos_distintos(monkeypatch):
    falso = AgenteFalso({"messages": [], "structured_response": SALIDA})
    monkeypatch.setattr(agente, "construir_agente", lambda sistema: falso)

    primero = agente.ejecutar("primera")
    segundo = agente.ejecutar("segunda")

    assert primero["thread_id"] != segundo["thread_id"]
    assert falso.configuraciones[0]["configurable"]["thread_id"] != falso.configuraciones[1]["configurable"]["thread_id"]


def test_ejecutar_hace_fallback_si_no_hay_salida(monkeypatch):
    monkeypatch.setattr(agente, "construir_agente", lambda sistema: AgenteFalso({"messages": []}))

    resultado = agente.ejecutar("pregunta")

    assert resultado["respuesta"].fuente == "ninguna"
    assert resultado["respuesta"].cifra is None
    assert resultado["error"] == "sin structured_response"


def test_responder_nunca_propaga_un_error_del_agente(monkeypatch):
    monkeypatch.setattr(agente, "construir_agente", lambda sistema: AgenteFalso(error=RuntimeError("sin red")))

    respuesta = agente.responder("pregunta")

    assert isinstance(respuesta, agente.RespuestaFinanciera)
    assert respuesta.fuente == "ninguna"
