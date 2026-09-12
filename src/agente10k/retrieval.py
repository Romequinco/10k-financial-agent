"""Búsqueda sobre los fragmentos del corpus (guía en docs/11; teoría en docs/04).

Paso 0 (baseline): búsqueda densa con bge-small y el índice FAISS, con el prefijo solo en la consulta.
Mejoras que hay que medir con recall@k tras cada una (R08): filtro por metadatos, BM25 + denso con
RRF y reescritura de la consulta con el LLM (docs/11 §2: un cambio cada vez).
"""
from __future__ import annotations

MODELO_EMBEDDINGS = "BAAI/bge-small-en-v1.5"
PREFIJO_CONSULTA_BGE = "Represent this sentence for searching relevant passages: "


def buscar_denso(query: str, ticker: str | None = None, fiscal_year: int | None = None,
                 item: str | None = None, k: int = 5) -> list[dict]:
    """Paso 0: los k fragmentos más parecidos según el índice FAISS (docs/11 §3)."""
    raise NotImplementedError("TODO · docs/11 §3")


def buscar_bm25(query: str, ticker: str | None = None, fiscal_year: int | None = None,
                item: str | None = None, k: int = 5) -> list[dict]:
    """Búsqueda léxica BM25 sobre los mismos fragmentos (docs/11 §6)."""
    raise NotImplementedError("TODO · docs/11 §6")


def fusionar_rrf(rankings: list[list[str]], k_rrf: int = 60) -> list[str]:
    """Reciprocal Rank Fusion de varias listas de chunk_id (docs/11 §6)."""
    raise NotImplementedError("TODO · docs/11 §6")


def reescribir_consulta(pregunta: str) -> list[str]:
    """Reescribe la pregunta con el LLM en 1–3 consultas en inglés (docs/11 §7)."""
    raise NotImplementedError("TODO · docs/11 §7")


def buscar(query: str, ticker: str | None = None, fiscal_year: int | None = None,
           item: str | None = None, k: int = 5, modo: str = "final") -> list[dict]:
    """Lo que usa search_filings: 'baseline' = paso 0; 'final' = la mejor combinación medida (docs/11 §9)."""
    raise NotImplementedError("TODO · docs/11 §9")
