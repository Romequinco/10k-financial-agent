"""Agente baseline: herramientas 10-K, salida estructurada y ejecución trazable."""
from __future__ import annotations

import time
import uuid
from typing import Any, Literal

from langchain.agents import create_agent
from langchain.agents.structured_output import ToolStrategy
from langchain.messages import AIMessage, ToolMessage
from langchain_core.callbacks import get_usage_metadata_callback
from langgraph.checkpoint.memory import InMemorySaver
from pydantic import BaseModel, Field

from agente10k import config
from agente10k.herramientas import TOOLS


class RespuestaFinanciera(BaseModel):
    """Respuesta trazable a una pregunta sobre los 10-K disponibles."""

    # CONTRATO (enunciado §7): se pueden añadir campos, no quitar ni renombrar estos ocho.
    respuesta: str = Field(description="Respuesta breve y directa, en español.")
    cifra: float | None = Field(default=None, description="Valor XBRL sin escalar; null si no aplica.")
    unidad: str | None = Field(default=None, description="Unidad XBRL, por ejemplo USD o USD/shares.")
    ticker: str | None = Field(default=None, description="Ticker del corpus.")
    ejercicio: int | None = Field(default=None, description="Ejercicio fiscal de cifra.")
    fuente: Literal["xbrl", "texto", "ambas", "ninguna"] = Field(
        description="Origen: XBRL, texto, ambos o ninguna si el dato no está en el corpus.")
    cita: str | None = Field(default=None, description="Frase literal del informe que respalda la respuesta.")
    chunk_id: str | None = Field(default=None, description="Identificador del fragmento citado.")
    # Opcionales: ayudan con comparativas sin modificar el contrato.
    concept_xbrl: str | None = Field(default=None, description="Concepto us-gaap que respalda cifra.")
    ejercicio_base: int | None = Field(default=None, description="Ejercicio previo en una comparativa.")
    cifra_base: float | None = Field(default=None, description="Cifra sin escalar del ejercicio previo.")


SYSTEM_PROMPT = """Eres un analista financiero que responde preguntas sobre informes 10-K de NVDA, MSFT, AAPL, GOOGL, META y AMZN, para FY2024 y FY2025. Usa ÚNICAMENTE las herramientas disponibles.

Universo
- FY es el ejercicio fiscal, no necesariamente el año de presentación. Los items disponibles son 1A (riesgos), 7 (MD&A), 7A (riesgo de mercado) y 8 (estados y notas).

Enrutado
- Toda cifra debe venir de get_xbrl_fact. No copies como cifra un número encontrado en un fragmento.
- Para riesgos, estrategia y explicaciones usa search_filings: consulta en inglés, vocabulario de 10-K y filtros ticker, fiscal_year e item cuando se conozcan.
- Usa read_section solo si search_filings no localiza el pasaje: devuelve mucho más texto.
- Usa list_available únicamente si no sabes si una empresa, ejercicio o sección pertenece al corpus.

Ausencias y comparativas
- Si get_xbrl_fact informa que la empresa no reportó el concepto, o falta empresa/ejercicio, responde fuente="ninguna" y cifra=null. Nunca estimes ni calcules un dato no reportado.
- En comparativas, consulta el mismo concepto para ambos ejercicios. cifra y ejercicio son los más recientes; cifra_base y ejercicio_base, los anteriores. Explica la variación en prosa.

Salida
- Responde breve y en español. cifra conserva exactamente el valor sin escalar y la unidad de get_xbrl_fact; concept_xbrl identifica el concepto.
- fuente es xbrl, texto, ambas o ninguna. Si usas texto, cita debe ser una frase LITERAL de un fragmento leído y chunk_id debe ser el del fragmento.
"""

FALLBACK = {"respuesta": "No se pudo completar la respuesta.", "fuente": "ninguna"}
NOMBRES_HERRAMIENTAS = {herramienta.name for herramienta in TOOLS}


def construir_agente(sistema: str = "baseline"):
    """Monta el baseline sin middleware para medirlo frente al sistema final."""
    if sistema != "baseline":
        raise ValueError("Solo está disponible el sistema 'baseline' en esta fase.")
    return create_agent(
        model=config.crear_modelo(), tools=TOOLS, system_prompt=SYSTEM_PROMPT,
        response_format=ToolStrategy(schema=RespuestaFinanciera), checkpointer=InMemorySaver(),
    )


def _trayectoria(mensajes: list[Any]) -> list[dict[str, Any]]:
    """Extrae llamadas reales, sin deduplicar y sin contar la herramienta sintética."""
    return [
        {"name": llamada["name"], "args": llamada.get("args", {}), "id": llamada.get("id")}
        for mensaje in mensajes if isinstance(mensaje, AIMessage)
        for llamada in (mensaje.tool_calls or []) if llamada.get("name") in NOMBRES_HERRAMIENTAS
    ]


def _uso_en_mensajes(mensajes: list[Any]) -> dict[str, int]:
    """Suma los metadatos de uso que haya adjuntado el proveedor."""
    usos = [getattr(mensaje, "usage_metadata", None) or {} for mensaje in mensajes]
    total = {clave: sum(int(uso.get(clave, 0) or 0) for uso in usos)
             for clave in ("input_tokens", "output_tokens", "total_tokens")}
    return total | {"cache_read": sum(int((uso.get("input_token_details") or {}).get("cache_read", 0) or 0)
                                       for uso in usos)}


def _respuesta_valida(salida: Any) -> RespuestaFinanciera:
    if isinstance(salida, RespuestaFinanciera):
        return salida
    if isinstance(salida, dict):
        return RespuestaFinanciera.model_validate(salida)
    return RespuestaFinanciera(**FALLBACK)


def ejecutar(pregunta: str, sistema: str = "baseline") -> dict:
    """Ejecuta una pregunta en hilo nuevo; devuelve fallback y diagnóstico ante cualquier fallo."""
    thread_id = f"q-{uuid.uuid4()}"
    cfg = {"configurable": {"thread_id": thread_id}, "recursion_limit": 100}
    agente = construir_agente(sistema)
    resultado: dict[str, Any] = {}
    error: str | None = None
    inicio = time.perf_counter()
    # El callback captura uso de todas las vueltas del modelo. Con dobles offline
    # queda vacío, que es preferible a inventar tokens o USD.
    with get_usage_metadata_callback() as callback:
        try:
            resultado = agente.invoke({"messages": [{"role": "user", "content": pregunta}]}, config=cfg)
        except Exception as exc:  # API, herramienta, validación o límite: fallback trazable.
            error = f"{type(exc).__name__}: {exc}"
            try:
                resultado = getattr(agente.get_state(cfg), "values", None) or {}
            except Exception:
                resultado = {}
    latencia = time.perf_counter() - inicio
    mensajes = resultado.get("messages", [])
    salida = resultado.get("structured_response")
    try:
        respuesta = _respuesta_valida(salida)
    except Exception as exc:
        respuesta = RespuestaFinanciera(**FALLBACK)
        error = error or f"Salida estructurada inválida: {type(exc).__name__}: {exc}"
    if salida is None:
        error = error or "sin structured_response"

    costes = [mensaje.response_metadata.get("cost") for mensaje in mensajes
              if isinstance(mensaje, AIMessage) and isinstance(mensaje.response_metadata, dict)]
    tool_calls = _trayectoria(mensajes)
    uso = {nombre: dict(metadatos) for nombre, metadatos in callback.usage_metadata.items()}
    # El precio fiable en esta fase es el que OpenRouter incluya en el mensaje.
    # La tabla de precios versionada se añadirá con la evaluación; hasta entonces
    # no se estima USD cuando el proveedor no lo ha comunicado.
    coste_proveedor = sum(float(coste) for coste in costes if coste is not None) or None
    return {
        "respuesta": respuesta, "error": error, "thread_id": thread_id,
        "tool_calls": tool_calls, "n_llamadas": len(tool_calls),
        "llamadas_modelo": sum(isinstance(mensaje, AIMessage) for mensaje in mensajes),
        "uso": uso, "uso_mensajes": _uso_en_mensajes(mensajes),
        "usd": coste_proveedor, "usd_openrouter": coste_proveedor,
        "latencia_s": latencia, "modelo": config.MODELO_ID,
        "errores_esquema": sum(isinstance(mensaje, ToolMessage) and
                                "Failed to parse structured output" in str(mensaje.content)
                                for mensaje in mensajes),
        "observaciones": [
            {"name": mensaje.name, "tool_call_id": mensaje.tool_call_id, "content": str(mensaje.content)}
            for mensaje in mensajes if isinstance(mensaje, ToolMessage)
            and mensaje.name in {"search_filings", "read_section"}
        ],
    }


def responder(pregunta: str, sistema: str = "baseline") -> RespuestaFinanciera:
    """CONTRATO R10: devuelve siempre una ``RespuestaFinanciera`` válida."""
    return ejecutar(pregunta, sistema)["respuesta"]
