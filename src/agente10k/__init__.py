"""agente10k: agente investigador sobre informes 10-K de la SEC (práctica MIAX).

Uso:
    from agente10k import responder, evaluar
    responder("¿Cuál fue el revenue de NVIDIA en FY2025?")
    evaluar("golden/golden_propio.jsonl")

Las importaciones son perezosas: `import agente10k` no carga langchain ni los embeddings.
"""

__all__ = ["responder", "evaluar", "RespuestaFinanciera"]


def __getattr__(nombre):
    if nombre in ("responder", "RespuestaFinanciera"):
        from agente10k import agente
        return getattr(agente, nombre)
    if nombre == "evaluar":
        from agente10k.evaluacion import evaluar
        return evaluar
    raise AttributeError(f"module 'agente10k' has no attribute {nombre!r}")
