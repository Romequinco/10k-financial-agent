"""Búsqueda sobre los fragmentos del corpus (guía en docs/11; teoría en docs/04).

Paso 0 (baseline): búsqueda densa con bge-small y el índice FAISS, con el prefijo solo en la consulta.
Mejoras que hay que medir con recall@k tras cada una (R08): filtro por metadatos, BM25 + denso con
RRF y reescritura de la consulta con el LLM (docs/11 §2: un cambio cada vez).
"""
from __future__ import annotations

from functools import lru_cache
import hashlib
import json
from pathlib import Path
import re
import time
from typing import Literal

import numpy as np
import pandas as pd

from agente10k import config, datos
from agente10k.normalizacion import normalizar_ticker
from pydantic import BaseModel, Field, field_validator

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
    _validar_busqueda(query, k)
    cand = candidatos(ticker, fiscal_year, item)
    scores = np.asarray(_cargar_bm25().get_batch_scores(tokenizar(query), cand.tolist()))
    orden = np.argsort(-scores, kind="stable")
    return [dict(_leer_metadatos_cache().iloc[int(cand[i])], puntuacion=float(scores[i]))
            for i in orden[scores[orden] > 0][:k]]


def fusionar_rrf(rankings: list[list[str]], k_rrf: int = 60) -> list[str]:
    """Reciprocal Rank Fusion de varias listas de chunk_id (docs/11 §6)."""
    if k_rrf < 0:
        raise ValueError("k_rrf debe ser no negativo")
    puntuaciones = {}
    for ranking in rankings:
        for rango, cid in enumerate(dict.fromkeys(ranking), start=1):
            puntuaciones[cid] = puntuaciones.get(cid, 0.0) + 1 / (k_rrf + rango)
    return sorted(puntuaciones, key=puntuaciones.get, reverse=True)


def reescribir_consulta(pregunta: str, permitir_api: bool = False) -> list[str]:
    """Lee la caché; solo llama al modelo si se habilita expresamente."""
    return reescribir(pregunta, permitir_api=permitir_api)["busqueda"]["consultas"]


def buscar(query: str, ticker: str | None = None, fiscal_year: int | None = None,
           item: str | None = None, k: int = 5, modo: str = "final") -> list[dict]:
    """Baseline denso o híbrido final. No llama a un LLM ni reescribe la consulta."""
    if modo == "baseline":
        return buscar_denso(query, ticker, fiscal_year, item, k)
    if modo != "final":
        raise ValueError("modo debe ser 'baseline' o 'final'")
    return buscar_hibrido([query], ticker, fiscal_year, item, k)


def _validar_busqueda(query: str, k: int) -> None:
    if not isinstance(query, str) or not query.strip():
        raise ValueError("query debe ser un texto no vacío")
    if isinstance(k, bool) or not isinstance(k, int):
        raise TypeError("k debe ser un entero")
    if k < 1:
        raise ValueError("k debe ser mayor o igual que 1")


def tokenizar(texto: str) -> list[str]:
    return re.findall(config.RETRIEVAL_TOKENIZER, texto.lower())


@lru_cache(maxsize=1)
def _leer_metadatos_cache() -> pd.DataFrame:
    datos.verificar_corpus()
    return _leer_metadatos()


@lru_cache(maxsize=1)
def _cargar_bm25():
    from rank_bm25 import BM25Okapi
    return BM25Okapi([tokenizar(t) for t in _leer_metadatos_cache()["texto"]],
                     k1=config.BM25_K1, b=config.BM25_B, epsilon=config.BM25_EPSILON)


def candidatos(ticker=None, fiscal_year=None, item=None) -> np.ndarray:
    """Filtra antes del top-N; BM25 conserva el IDF del corpus completo."""
    meta = _leer_metadatos_cache()
    mascara = np.ones(len(meta), dtype=bool)
    if ticker is not None:
        mascara &= meta["ticker"].to_numpy() == normalizar_ticker(ticker)
    if fiscal_year is not None:
        mascara &= meta["fiscal_year"].to_numpy() == int(fiscal_year)
    if item is not None:
        it = _normalizar_item(item)
        mascara &= meta["item"].to_numpy() == ("8" if it == "15" else it)
    return np.flatnonzero(mascara)


@lru_cache(maxsize=512)
def _ranking_denso_completo(query: str) -> tuple[dict, ...]:
    # Reutiliza exactamente el orden FAISS del baseline, incluidos los empates.
    return tuple(buscar_denso(query, k=len(_leer_metadatos_cache())))


def buscar_hibrido(consultas: list[str], ticker=None, fiscal_year=None, item=None,
                   k: int = 5, usar_bm25: bool = True) -> list[dict]:
    """Pre-filtro, top-20 por señal y consulta, RRF y top-k. Sin llamadas al LLM."""
    if not consultas:
        raise ValueError("Hace falta al menos una consulta")
    for q in consultas:
        _validar_busqueda(q, k)
    meta = _leer_metadatos_cache()
    permitidos = set(meta.iloc[candidatos(ticker, fiscal_year, item)]["chunk_id"])
    if not permitidos:
        return []
    listas, documentos = [], {}
    for q in consultas:
        densos = [d for d in _ranking_denso_completo(q) if d["chunk_id"] in permitidos]
        listas.append([d["chunk_id"] for d in densos[:config.RETRIEVAL_N_CAND]])
        for d in densos:
            documentos.setdefault(d["chunk_id"], dict(d))
        if usar_bm25:
            lexicos = buscar_bm25(q, ticker, fiscal_year, item, config.RETRIEVAL_N_CAND)
            listas.append([d["chunk_id"] for d in lexicos])
    ids = fusionar_rrf(listas, config.RETRIEVAL_K_RRF)[:k]
    return [documentos[cid] for cid in ids]


REGLAS_CONSULTA = """Write short ENGLISH queries using 10-K wording.
Put company, fiscal year and section in filters, not in the query text.
Use fiscal year, not filing year. Sections: 1A risks, 7 MD&A, 7A market risk, 8 financial statements.
Compare fiscal years by searching each year separately."""
INSTRUCCIONES_BUSQUEDA = """Turn the question into a search request, not an answer.
Return 1-3 queries and the applicable filters. Leave unknown filters empty.
If two fiscal years are compared, include both in fiscal_years.
""" + REGLAS_CONSULTA


class Busqueda(BaseModel):
    consultas: list[str] = Field(min_length=1, max_length=3)
    ticker: Literal["NVDA", "MSFT", "AAPL", "GOOGL", "META", "AMZN"] | None = None
    fiscal_years: list[Literal[2024, 2025]] = Field(default_factory=list, max_length=2)
    item: Literal["1A", "7", "7A", "8"] | None = None

    @field_validator("consultas")
    @classmethod
    def consultas_no_vacias(cls, valor):
        if any(not q.strip() for q in valor):
            raise ValueError("Las consultas no pueden estar vacías")
        return list(dict.fromkeys(q.strip() for q in valor))


def crear_reescritor(modelo):
    """Recibe una instancia ya configurada; no crea clientes al importar el módulo."""
    from langchain.agents import create_agent
    from langchain.agents.structured_output import ToolStrategy
    return create_agent(model=modelo, tools=[], system_prompt=INSTRUCCIONES_BUSQUEDA,
                        response_format=ToolStrategy(Busqueda, handle_errors=False))


def _clave_reescritura(pregunta: str, modelo_id: str) -> str:
    protocolo = INSTRUCCIONES_BUSQUEDA + json.dumps(Busqueda.model_json_schema(), sort_keys=True)
    return hashlib.sha256(json.dumps([modelo_id, config.TEMPERATURA, protocolo, pregunta],
                                    ensure_ascii=False).encode()).hexdigest()


class ReescrituraPendiente(RuntimeError):
    """No hay caché y no se ha autorizado el acceso a la API."""


def reescribir(pregunta: str, permitir_api: bool = False, ruta_cache: Path | None = None,
              modelo_id: str | None = None, reescritor=None) -> dict:
    """Caché por modelo, pregunta, prompt y esquema. API desactivada por defecto.

    Los fallos se guardan sin el texto de la excepción (puede contener credenciales).
    Se usa la pregunta original como fallback, conservando el fallo en las métricas.
    """
    _validar_busqueda(pregunta, 1)
    ruta = Path(ruta_cache) if ruta_cache is not None else config.CACHE_REESCRITURAS
    modelo_id = modelo_id or config.MODELO_ID
    clave = _clave_reescritura(pregunta, modelo_id)
    cache = json.loads(ruta.read_text(encoding="utf-8")) if ruta.is_file() else {}
    if clave in cache:
        return cache[clave]
    if not permitir_api:
        raise ReescrituraPendiente("Reescritura pendiente: ejecuta esta celda con EJECUTAR = True.")
    if reescritor is None:
        reescritor = crear_reescritor(config.crear_modelo(modelo_id))
    from langchain_core.callbacks import get_usage_metadata_callback
    inicio, salida, error = time.perf_counter(), {}, None
    with get_usage_metadata_callback() as cb:
        try:
            salida = reescritor.invoke({"messages": [{"role": "user", "content": pregunta}]},
                                      config={"recursion_limit": 8})
            busqueda = Busqueda.model_validate(salida.get("structured_response"))
        except Exception as exc:
            error = type(exc).__name__
            busqueda = Busqueda(consultas=[pregunta])
    mensajes = salida.get("messages", [])
    costes = [getattr(m, "response_metadata", {}).get("cost") for m in mensajes
              if getattr(m, "type", None) == "ai"]
    coste = sum(float(c) for c in costes) if costes and all(c is not None for c in costes) else None
    entrada = {"pregunta": pregunta, "modelo": modelo_id, "busqueda": busqueda.model_dump(),
               "fallo": error is not None, "error": error,
               "uso": {m: dict(u) for m, u in cb.usage_metadata.items()},
               "ms": round(1000 * (time.perf_counter() - inicio), 2), "usd": coste}
    cache[clave] = entrada
    ruta.parent.mkdir(parents=True, exist_ok=True)
    temporal = ruta.with_suffix(".tmp")
    temporal.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
    temporal.replace(ruta)
    return entrada


def buscar_reescrita(busqueda: dict, k: int = 5, usar_bm25: bool = True) -> list[dict]:
    b = Busqueda.model_validate(busqueda)
    fys = sorted(set(b.fiscal_years), reverse=True) or [None]
    resultados = [buscar_hibrido(b.consultas, b.ticker, fy, b.item,
                                 config.RETRIEVAL_N_CAND, usar_bm25) for fy in fys]
    documentos = {d["chunk_id"]: d for lista in resultados for d in lista}
    ids = fusionar_rrf([[d["chunk_id"] for d in lista] for lista in resultados],
                      config.RETRIEVAL_K_RRF)[:k]
    return [documentos[cid] for cid in ids]
