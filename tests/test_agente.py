"""Pruebas offline del arnés baseline: no usan API ni requieren una clave."""
from langchain.messages import AIMessage, ToolMessage

from agente10k import agente, config


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


class AgenteConSecuencia(AgenteFalso):
    """Doble que falla con una secuencia controlada antes de responder."""

    def __init__(self, secuencia):
        super().__init__()
        self.secuencia = iter(secuencia)

    def invoke(self, entrada, config):
        self.configuraciones.append(config)
        siguiente = next(self.secuencia)
        if isinstance(siguiente, Exception):
            raise siguiente
        return siguiente


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


def test_ejecutar_registra_modelo_real_y_fallback(monkeypatch):
    mensajes = [AIMessage(content="", response_metadata={"model_name": "respaldo"})]
    falso = AgenteFalso({"messages": mensajes, "structured_response": SALIDA})
    monkeypatch.setattr(agente, "construir_agente", lambda sistema, modelo=None: falso)
    monkeypatch.setattr(agente.config, "CASCADA_MODELOS", ("principal", "respaldo", "ultimo"))

    resultado = agente.ejecutar("pregunta", "cascada")

    assert resultado["modelo_solicitado"] == "principal"
    assert resultado["modelo_real"] == "respaldo"
    assert resultado["hubo_fallback"] is True
    assert resultado["posicion_cascada"] == 2


def test_baseline_no_activa_suplentes(monkeypatch):
    creado = {}
    monkeypatch.setattr(agente.config, "crear_modelo", lambda modelo, fallbacks=None: creado.update(
        {"modelo": modelo, "fallbacks": fallbacks}) or object())
    monkeypatch.setattr(agente, "create_agent", lambda **kwargs: kwargs)

    montaje = agente.construir_agente("baseline")

    assert creado["modelo"] == agente.config.MODELO_ID
    assert creado["fallbacks"] == ()
    assert montaje["model"] is not None


def test_cascada_admite_orden_elegido_en_el_experimento(monkeypatch):
    creado = {}
    monkeypatch.setattr(agente.config, "crear_modelo", lambda modelo, fallbacks=None: creado.update(
        {"modelo": modelo, "fallbacks": fallbacks}) or object())
    monkeypatch.setattr(agente, "create_agent", lambda **kwargs: kwargs)

    agente.construir_agente("cascada", modelo="A", fallbacks=["B", "C"])

    assert creado == {"modelo": "A", "fallbacks": ("B", "C")}


def test_configuracion_openrouter_envia_orden_completo_de_cascada(monkeypatch):
    """El payload conserva principal y respaldos en el orden de preferencia."""
    creado = {}

    class ChatOpenRouterFalso:
        def __init__(self, **kwargs):
            creado.update(kwargs)

    import langchain_openrouter
    monkeypatch.setattr(langchain_openrouter, "ChatOpenRouter", ChatOpenRouterFalso)
    # Clave ficticia: el cliente se crea pero no se usa, y así la prueba pasa en un clon limpio
    # sin .env (antes fallaba ahí y el corrector veía rojo sin tener nada roto).
    monkeypatch.setenv("OPENROUTER_API_KEY", "clave-de-prueba-no-real")

    config.crear_modelo(
        "openrouter:principal", fallbacks=("openrouter:respaldo-1", "openrouter:respaldo-2"),
    )

    assert creado["model"] == "principal"
    assert creado["temperature"] == 0
    assert creado["model_kwargs"] == {"models": ["principal", "respaldo-1", "respaldo-2"]}


def test_cascada_reintenta_limite_temporal_y_conserva_diagnostico(monkeypatch):
    falso = AgenteConSecuencia([
        RuntimeError("429 rate limit"), RuntimeError("timeout del proveedor"),
        {"messages": [], "structured_response": SALIDA},
    ])
    monkeypatch.setattr(agente, "construir_agente", lambda sistema: falso)
    monkeypatch.setattr(agente.time, "sleep", lambda _: None)

    resultado = agente.ejecutar("pregunta", "cascada")

    assert resultado["error"] is None
    assert resultado["intentos"] == 3
    assert resultado["reintentos"] == 2
    assert resultado["errores_intentos"] == [
        "RuntimeError: 429 rate limit", "RuntimeError: timeout del proveedor",
    ]
    assert len(falso.configuraciones) == 3


def test_cascada_no_reintenta_error_no_recuperable(monkeypatch):
    falso = AgenteConSecuencia([ValueError("argumento inválido")])
    monkeypatch.setattr(agente, "construir_agente", lambda sistema: falso)

    resultado = agente.ejecutar("pregunta", "cascada")

    assert resultado["intentos"] == 1
    assert resultado["reintentos"] == 0
    assert resultado["error"] == "ValueError: argumento inválido"


def test_baseline_no_reintenta_ni_siquiera_un_rate_limit(monkeypatch):
    falso = AgenteConSecuencia([RuntimeError("429 rate limit")])
    monkeypatch.setattr(agente, "construir_agente", lambda sistema: falso)

    resultado = agente.ejecutar("pregunta", "baseline")

    assert resultado["intentos"] == 1
    assert resultado["error"] == "RuntimeError: 429 rate limit"
