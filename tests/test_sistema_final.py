"""Arquitectura del 07: candidato aislado y final condicionado por el 06."""
import pytest
from langchain.messages import AIMessage, SystemMessage

from agente10k import agente, guardrails, herramientas, retrieval


def _doblar_montaje(monkeypatch):
    creado = {}
    monkeypatch.setattr(agente.config, "crear_modelo", lambda *a, **kw: object())
    monkeypatch.setattr(agente, "create_agent", lambda **kw: creado.update(kw) or kw)
    return creado


def test_responder_usa_final_por_defecto_y_permite_baseline_explicito(monkeypatch):
    llamadas = []
    salida = agente.RespuestaFinanciera(respuesta="Sin datos", fuente="ninguna")
    monkeypatch.setattr(agente, "ejecutar", lambda pregunta, sistema, **kw:
                        llamadas.append((pregunta, sistema, kw)) or {"respuesta": salida})
    assert agente.responder("pregunta", modelo="modelo-elegido") is salida
    assert agente.responder("referencia", sistema="baseline") is salida
    assert llamadas[0] == ("pregunta", "final", {"modelo": "modelo-elegido", "fallbacks": None})
    assert llamadas[1][1] == "baseline"


def test_candidato_sustituye_solo_search_filings(monkeypatch):
    creado = _doblar_montaje(monkeypatch)

    agente.construir_agente("candidato_07")

    tools = creado["tools"]
    assert [tool.name for tool in tools] == [tool.name for tool in herramientas.TOOLS]
    assert tools[2] is not herramientas.search_filings
    assert tools[0] is herramientas.list_available
    assert tools[1] is herramientas.get_xbrl_fact
    assert tools[3] is herramientas.read_section
    assert creado["middleware"] == ()


@pytest.mark.parametrize("sistema", ["candidato_07", "final"])
@pytest.mark.parametrize("seccion,item_esperado", [("", None), (" en el Item 1A", "1A")])
def test_agente_usa_bm25_con_item_opcional_y_modelo_configurado(monkeypatch, sistema, seccion, item_esperado):
    llamadas = []

    def buscar(*args, **kwargs):
        llamadas.append(kwargs)
        return [{"chunk_id": "bm25", "ticker": "MSFT", "fiscal_year": 2025,
                 "item": "1A", "texto": "AI risks", "puntuacion": 0.7}]

    monkeypatch.setattr(retrieval, "buscar_bm25", buscar)
    monkeypatch.setattr(retrieval, "buscar_denso", lambda *a, **kw: pytest.fail("No debe usar denso"))
    monkeypatch.setattr(retrieval, "buscar_hibrido", lambda *a, **kw: pytest.fail("No debe usar híbrido"))
    monkeypatch.setattr(guardrails, "middleware_final", lambda: [object()])
    modelos = []
    monkeypatch.setattr(agente.config, "crear_modelo", lambda modelo, **kw: modelos.append(modelo) or object())
    monkeypatch.setattr(agente, "create_agent", lambda **kw: kw)
    montaje = agente.construir_agente(sistema)
    tools = montaje["tools"]
    assert modelos == [agente.config.MODELO_ID]
    assert retrieval.REGLAS_BM25 in montaje["system_prompt"]
    token = herramientas.PREGUNTA_ACTUAL.set(f"Riesgos de Microsoft FY2025{seccion}")
    try:
        texto = tools[2].invoke({
            "query": "AI risks", "ticker": "MSFT", "fiscal_year": 2025, "k": 5,
        })
    finally:
        herramientas.PREGUNTA_ACTUAL.reset(token)

    assert "[bm25]" in texto and "BM25" in texto
    assert llamadas == [{
        "ticker": "MSFT", "fiscal_year": 2025, "item": item_esperado, "k": 5,
    }]
    assert herramientas.TOOLS[2] is herramientas.search_filings


def test_final_no_cae_al_baseline_si_guardrails_siguen_pendientes(monkeypatch):
    monkeypatch.setattr(
        guardrails, "middleware_final",
        lambda: (_ for _ in ()).throw(NotImplementedError("pendiente")),
    )
    monkeypatch.setattr(
        agente.config, "crear_modelo",
        lambda *a, **kw: pytest.fail("No debe crear el modelo sin guardrails"),
    )

    with pytest.raises(agente.SistemaFinalNoDisponible, match="requiere los guardrails"):
        agente.construir_agente("final")


def test_final_conecta_guardrails_y_retrieval_mejorado(monkeypatch):
    creado = _doblar_montaje(monkeypatch)
    centinela = object()
    monkeypatch.setattr(guardrails, "middleware_final", lambda: [centinela])

    agente.construir_agente("final")

    assert creado["middleware"] == (centinela,)
    assert creado["tools"][2] is not herramientas.search_filings
    assert "BM25" in creado["tools"][2].description


def test_final_rechaza_pila_de_guardrails_vacia(monkeypatch):
    monkeypatch.setattr(guardrails, "middleware_final", lambda: [])

    with pytest.raises(agente.SistemaFinalNoDisponible, match="pila de guardrails no vacía"):
        agente.construir_agente("final")


def test_sistema_desconocido_falla_antes_de_crear_cliente(monkeypatch):
    monkeypatch.setattr(
        agente.config, "crear_modelo",
        lambda *a, **kw: pytest.fail("No debe crear un cliente para un sistema inválido"),
    )

    with pytest.raises(ValueError, match="candidato_07"):
        agente.construir_agente("inventado")


def test_prompt_baseline_permanece_congelado_y_candidato_extiende(monkeypatch):
    creado = _doblar_montaje(monkeypatch)

    agente.construir_agente("baseline")
    prompt_baseline = creado["system_prompt"]
    agente.construir_agente("candidato_07")
    prompt_candidato = creado["system_prompt"]

    assert prompt_baseline is agente.SYSTEM_PROMPT
    assert prompt_candidato == agente.SYSTEM_PROMPT_CANDIDATO
    assert retrieval.REGLAS_BM25 in prompt_candidato
    assert prompt_candidato.startswith(prompt_baseline)
    assert agente.TRAZABILIDAD_CANDIDATO not in prompt_baseline


def test_prompt_candidato_exige_trazabilidad_generica():
    prompt = agente._prompt_sistema("candidato_07")

    assert "preguntas extractivas" in prompt
    assert "UNA frase literal completa" in prompt
    assert "chunk_id" in prompt
    assert "get_xbrl_fact para ambos ejercicios" in prompt
    assert 'fuente="ambas"' in prompt
    assert 'fuente no puede ser "xbrl"' in prompt
    assert "no lo estimes, no lo derives y no lo calcules" in prompt
    assert "respuesta_esperada" not in prompt
    assert "ancla_texto" not in prompt


def test_final_extiende_el_prompt_base_con_su_propia_trazabilidad(monkeypatch):
    """El final ya no reutiliza el prompt del candidato: numera frases (frase_ids) y limita las llamadas."""
    creado = _doblar_montaje(monkeypatch)
    monkeypatch.setattr(guardrails, "middleware_final", lambda: [object()])

    agente.construir_agente("final")

    assert creado["system_prompt"] == agente.SYSTEM_PROMPT_FINAL
    assert creado["system_prompt"].startswith(agente.SYSTEM_PROMPT)
    assert creado["system_prompt"] != agente.SYSTEM_PROMPT_CANDIDATO
    assert "frase_ids" in creado["system_prompt"]


def test_modo_acotado_del_candidato_recibe_su_prompt(monkeypatch):
    recibidos = []

    class ModeloFalso:
        def bind_tools(self, tools):
            return self

        def invoke(self, mensajes):
            recibidos.append(mensajes)
            return AIMessage(content="respuesta de humo")

    monkeypatch.setattr(agente.config, "crear_modelo", lambda *a, **kw: ModeloFalso())

    agente._ejecutar_openrouter_acotado(
        "pregunta extractiva", "openrouter:modelo-falso", (), "candidato_07", "hilo",
        herramientas=list(herramientas.TOOLS),
    )

    assert isinstance(recibidos[0][0], SystemMessage)
    assert recibidos[0][0].content == agente.SYSTEM_PROMPT_CANDIDATO
