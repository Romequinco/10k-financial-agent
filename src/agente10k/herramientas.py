"""Las cuatro herramientas del agente (enunciado §7; guía en docs/07).

Nombres y parámetros son CONTRATO: las 10 preguntas ciegas y el evaluador de trayectoria del día 24
los buscan tal cual. Se puede reescribir el cuerpo, mejorar el docstring y añadir parámetros con valor
por defecto, pero no renombrar ni quitar nada (tests/test_contratos.py lo comprueba).
El docstring es lo único que ve el modelo para decidir si llama a la herramienta: es prompt, no
documentación (docs/07 §2–§3).
"""
from langchain.tools import tool


@tool
def list_available() -> str:
    """Devuelve las empresas y ejercicios fiscales disponibles en el corpus."""
    raise NotImplementedError("TODO · docs/07 §5")


@tool
def get_xbrl_fact(ticker: str, fiscal_year: int, concept: str) -> str:
    """Devuelve el valor EXACTO de una magnitud financiera tal y como la
    compañía la reportó en XBRL. Es la fuente autorizada para cualquier
    cifra. Úsala SIEMPRE en lugar de leer un número del texto."""
    raise NotImplementedError("TODO · docs/07 §5")


@tool
def search_filings(query: str, ticker: str | None = None,
                   fiscal_year: int | None = None,
                   item: str | None = None, k: int = 5) -> str:
    """Busca fragmentos de texto relevantes en los 10-K del corpus.
    Devuelve k fragmentos, cada uno con su chunk_id para poder citarlo."""
    raise NotImplementedError("TODO · docs/07 §5 y docs/11 §9 (usa retrieval.buscar)")


@tool
def read_section(ticker: str, fiscal_year: int, item: str) -> str:
    """Devuelve el TEXTO COMPLETO de una sección. Es CARA: puede devolver
    decenas de miles de tokens."""
    raise NotImplementedError("TODO · docs/07 §5")


HERRAMIENTAS = [list_available, get_xbrl_fact, search_filings, read_section]
