"""El agente: esquema de salida, system prompt, montaje y responder() (guía en docs/08; teoría en docs/05)."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class RespuestaFinanciera(BaseModel):
    """Respuesta trazable a una pregunta sobre informes 10-K."""

    # CONTRATO (enunciado §7): se pueden añadir campos, no quitar ni renombrar estos ocho.
    respuesta: str = Field(description="Respuesta en prosa, breve y directa")
    cifra: float | None = Field(default=None, description="Valor numérico, si la pregunta pide uno")
    unidad: str | None = Field(default=None, description="USD, shares, porcentaje…")
    ticker: str | None = None
    ejercicio: int | None = None
    fuente: Literal["xbrl", "texto", "ambas", "ninguna"] = Field(
        description="De dónde sale el dato. 'ninguna' si no está en el corpus"
    )
    cita: str | None = Field(default=None, description="Texto literal del informe que respalda la respuesta")
    chunk_id: str | None = Field(default=None, description="Identificador del fragmento citado, para verificar")


# TODO · docs/08 §5: reglas de enrutado (cifras → get_xbrl_fact; texto → search_filings; read_section
# solo como último recurso), huecos → fuente="ninguna", consultas en inglés y citar chunk_id.
SYSTEM_PROMPT = ""


def construir_agente(sistema: str = "final"):
    """Monta el agente con create_agent: modelo de config.crear_modelo(), las 4 herramientas,
    SYSTEM_PROMPT, response_format con RespuestaFinanciera, InMemorySaver y, en 'final', los
    guardrails de guardrails.middleware_final() (docs/08 §4 y §6)."""
    raise NotImplementedError("TODO · docs/08 §6")


def ejecutar(pregunta: str, sistema: str = "final") -> dict:
    """Ejecuta una pregunta con un thread_id nuevo y devuelve respuesta, trayectoria, tokens, coste y
    latencia; nunca lanza (docs/08 §7, docs/13 §2). Lo usan responder() y evaluar()."""
    raise NotImplementedError("TODO · docs/08 §7")


def responder(pregunta: str, sistema: str = "final") -> RespuestaFinanciera:
    """CONTRATO (R10): responde una pregunta con la RespuestaFinanciera validada (docs/08 §7)."""
    raise NotImplementedError("TODO · docs/08 §7")
