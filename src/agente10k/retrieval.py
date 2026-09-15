"""Búsqueda sobre los fragmentos del corpus (guía en docs/11; teoría en docs/04).

Paso 0 (baseline): búsqueda densa con bge-small y el índice FAISS, con el prefijo solo en la consulta.
Mejoras que hay que medir con recall@k tras cada una (R08): filtro por metadatos, BM25 + denso con
RRF y reescritura de la consulta con el LLM (docs/11 §2: un cambio cada vez).
"""
from __future__ import annotations

from functools import lru_cache

import numpy as np
import pandas as pd

from agente10k import config, datos

MODELO_EMBEDDINGS = "BAAI/bge-small-en-v1.5"
PREFIJO_CONSULTA_BGE = "Represent this sentence for searching relevant passages: "


def _leer_indice():
    """Lee el índice sin importar FAISS al cargar el módulo."""
    import faiss

    return faiss.read_index(str(config.INDICE / "corpus.faiss"))


def _leer_metadatos() -> pd.DataFrame:
    """Lee los metadatos cuya fila i corresponde al vector i."""
    return pd.read_parquet(config.INDICE / "chunks_meta.parquet")


def _crear_codificador():
    """Crea el codificador una sola vez y solo cuando se hace una búsqueda."""
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(MODELO_EMBEDDINGS)


@lru_cache(maxsize=1)
def _cargar_recursos():
    """Carga y valida índice, metadatos y codificador una sola vez."""
    datos.verificar_corpus()
    indice = _leer_indice()
    metadatos = _leer_metadatos()

    if indice.ntotal != len(metadatos):
        raise RuntimeError(
            "Índice y metadatos desalineados: "
            f"{indice.ntotal} vectores frente a {len(metadatos)} filas."
        )

    columnas = {"chunk_id", "ticker", "fiscal_year", "item", "texto"}
    ausentes = columnas.difference(metadatos.columns)
    if ausentes:
        raise RuntimeError(
            "Faltan columnas obligatorias en chunks_meta.parquet: "
            + ", ".join(sorted(ausentes))
        )

    return indice, metadatos, _crear_codificador()


def _normalizar_item(item: str | None) -> str | None:
    """Convierte, por ejemplo, ``Item 1a`` en ``1A``."""
    if item is None:
        return None
    normalizado = str(item).strip()
    if normalizado.lower().startswith("item"):
        normalizado = normalizado[4:].strip()
    return normalizado.upper() or None


def buscar_denso(query: str, ticker: str | None = None, fiscal_year: int | None = None,
                 item: str | None = None, k: int = 5) -> list[dict]:
    """Paso 0: devuelve los k fragmentos más parecidos del índice FAISS.

    El índice contiene vectores normalizados, por lo que su producto interno
    es la similitud coseno. El prefijo BGE se añade únicamente a la consulta.
    Los filtros se aplican después de ordenar todo el índice, tal como define
    el baseline entregado en clase.
    """
    if not isinstance(query, str) or not query.strip():
        raise ValueError("query debe ser un texto no vacío")
    if isinstance(k, bool) or not isinstance(k, int):
        raise TypeError("k debe ser un entero")
    if k < 1:
        raise ValueError("k debe ser mayor o igual que 1")

    ticker_normalizado = str(ticker).strip().upper() if ticker is not None else None
    fy_normalizado = int(fiscal_year) if fiscal_year is not None else None
    item_normalizado = _normalizar_item(item)

    indice, metadatos, codificador = _cargar_recursos()
    consulta = PREFIJO_CONSULTA_BGE + query.strip()
    vector = codificador.encode(
        [consulta],
        normalize_embeddings=True,
        convert_to_numpy=True,
    )
    vector = np.asarray(vector, dtype="float32")

    puntuaciones, posiciones = indice.search(vector, indice.ntotal)
    resultados: list[dict] = []

    for puntuacion, posicion in zip(puntuaciones[0], posiciones[0]):
        if posicion < 0:
            continue
        fila = metadatos.iloc[int(posicion)]
        if ticker_normalizado is not None and str(fila["ticker"]).upper() != ticker_normalizado:
            continue
        if fy_normalizado is not None and int(fila["fiscal_year"]) != fy_normalizado:
            continue
        if item_normalizado is not None and str(fila["item"]).upper() != item_normalizado:
            continue

        resultado = fila.to_dict()
        resultado["puntuacion"] = float(puntuacion)
        resultados.append(resultado)
        if len(resultados) == k:
            break

    return resultados


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
