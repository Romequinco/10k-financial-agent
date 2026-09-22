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
import threading
import time
import unicodedata
from typing import Literal

import numpy as np
import pandas as pd

from agente10k import config, datos
from agente10k.normalizacion import ALIAS, normalizar_ticker
from pydantic import BaseModel, Field, field_validator

MODELO_EMBEDDINGS = config.MODELO_EMBEDDINGS
PREFIJO_CONSULTA_BGE = "Represent this sentence for searching relevant passages: "

# Serializa la carga de recursos: precalentar() puede correr en un hilo mientras llega la primera
# búsqueda, y sin este cerrojo ambos cargarían torch y BGE a la vez.
_BLOQUEO = threading.RLock()


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


def _recursos():
    """``_cargar_recursos`` bajo cerrojo (la primera llamada tarda ~15 s por torch)."""
    with _BLOQUEO:
        return _cargar_recursos()


def _normalizar_item(item: str | None) -> str | None:
    """Convierte, por ejemplo, ``Item 1a`` en ``1A``."""
    if item is None:
        return None
    normalizado = str(item).strip()
    if normalizado.lower().startswith("item"):
        normalizado = normalizado[4:].strip()
    return normalizado.upper() or None


_FILAS: dict[int, tuple] = {}   # id(DataFrame) -> (DataFrame, datos derivados)


def _filas(metadatos: pd.DataFrame) -> dict:
    """Diccionarios y columnas de filtro por fila, calculados una vez por DataFrame.

    Sustituye ``metadatos.iloc[i].to_dict()`` por consulta (1.749 filas, ~130 ms) por copias
    superficiales de diccionarios ya construidos (<1 ms). La búsqueda densa y la léxica leen el mismo
    parquet por separado (dos DataFrame iguales), por eso hay varias entradas; se guarda el propio
    DataFrame para que su id no se reutilice, y se acota para no acumular los de las pruebas.
    """
    entrada = _FILAS.get(id(metadatos))
    if entrada is None or entrada[0] is not metadatos:
        if len(_FILAS) >= 4:
            _FILAS.clear()
        entrada = (metadatos, {
            "registros": metadatos.to_dict("records"),
            "tickers": np.array([str(t).upper() for t in metadatos["ticker"]], dtype=object),
            "ejercicios": metadatos["fiscal_year"].to_numpy().astype("int64"),
            "items": np.array([str(i).upper() for i in metadatos["item"]], dtype=object),
        })
        _FILAS[id(metadatos)] = entrada
    return entrada[1]


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

    indice, metadatos, codificador = _recursos()
    consulta = PREFIJO_CONSULTA_BGE + query.strip()
    vector = codificador.encode(
        [consulta],
        normalize_embeddings=True,
        convert_to_numpy=True,
    )
    vector = np.asarray(vector, dtype="float32")

    # La búsqueda FAISS exacta cuesta ~0,2 ms; el orden (y los empates) es el del baseline. Lo caro era
    # recorrer el ranking con iloc/to_dict, así que los filtros se aplican con máscaras numpy sobre el
    # mismo orden y solo se construyen los diccionarios de los k resultados.
    puntuaciones, posiciones = indice.search(vector, indice.ntotal)
    posiciones, puntuaciones = np.asarray(posiciones[0]), np.asarray(puntuaciones[0])
    filas = _filas(metadatos)
    seguras = np.where(posiciones >= 0, posiciones, 0)
    admitidas = posiciones >= 0
    if ticker_normalizado is not None:
        admitidas &= filas["tickers"][seguras] == ticker_normalizado
    if fy_normalizado is not None:
        admitidas &= filas["ejercicios"][seguras] == fy_normalizado
    if item_normalizado is not None:
        admitidas &= filas["items"][seguras] == item_normalizado

    resultados: list[dict] = []
    for j in np.flatnonzero(admitidas)[:k]:
        resultado = dict(filas["registros"][int(posiciones[j])])
        resultado["puntuacion"] = float(puntuaciones[j])
        resultados.append(resultado)
    return resultados


def buscar_bm25(query: str, ticker: str | None = None, fiscal_year: int | None = None,
                item: str | None = None, k: int = 5) -> list[dict]:
    """Búsqueda léxica BM25 sobre los mismos fragmentos (docs/11 §6)."""
    _validar_busqueda(query, k)
    cand = candidatos(ticker, fiscal_year, item)
    with _BLOQUEO:
        bm25 = _cargar_bm25()
    scores = np.asarray(bm25.get_batch_scores(tokenizar(query), cand.tolist()))
    orden = np.argsort(-scores, kind="stable")
    registros = _filas(_leer_metadatos_cache())["registros"]
    return [dict(registros[int(cand[i])], puntuacion=float(scores[i]))
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
           item: str | None = None, k: int = 5, modo: str = "final", *,
           item_blando: bool = False, relajar: tuple[str, ...] = ()) -> list[dict]:
    """Baseline denso o híbrido final. No llama a un LLM ni reescribe la consulta.

    En modo final ``fiscal_year`` e ``item`` pueden ser listas (filtros inferidos de la pregunta) y
    admiten dos opciones que solo activa la herramienta cuando el modelo no fijó el filtro:
    ``item_blando`` (RRF entre la búsqueda con item y sin item) y ``relajar`` (filtros que se pueden
    soltar, en orden item -> fy, si quedan menos de k resultados).
    """
    if modo == "baseline":
        return buscar_denso(query, ticker, fiscal_year, item, k)
    if modo != "final":
        raise ValueError("modo debe ser 'baseline' o 'final'")
    return buscar_final(query, ticker, fiscal_year, item, k, item_blando=item_blando, relajar=relajar)


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
    ejercicios = _como_lista(fiscal_year, int)
    if ejercicios:
        mascara &= np.isin(meta["fiscal_year"].to_numpy(), ejercicios)
    items = _como_lista(item, lambda i: "8" if _normalizar_item(i) == "15" else _normalizar_item(i))
    if items:
        mascara &= np.isin(meta["item"].to_numpy(), items)
    return np.flatnonzero(mascara)


def _como_lista(valor, convertir=lambda x: x) -> list:
    """Admite un valor suelto, una lista/tupla/conjunto o None (lista vacía)."""
    if valor is None:
        return []
    if isinstance(valor, (list, tuple, set, frozenset)):
        return [convertir(v) for v in valor]
    return [convertir(valor)]


# Acotada: cada entrada guarda 1.749 diccionarios (~0,6 MB); con 512 entradas eran ~0,3 GB en una
# evaluación larga. Una búsqueda de la herramienta reutiliza la misma consulta como mucho ~6 veces
# (ejercicios x con/sin item), así que 16 sobran.
@lru_cache(maxsize=16)
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
    permitidos = set(meta["chunk_id"].to_numpy()[candidatos(ticker, fiscal_year, item)])
    if not permitidos:
        return []
    listas, documentos = [], {}
    for q in consultas:
        densos = [d for d in _ranking_denso_completo(q) if d["chunk_id"] in permitidos]
        listas.append([d["chunk_id"] for d in densos[:config.RETRIEVAL_N_CAND]])
        for d in densos:
            documentos.setdefault(d["chunk_id"], d)   # referencia; se copia solo lo que se devuelve
        if usar_bm25:
            lexicos = buscar_bm25(q, ticker, fiscal_year, item, config.RETRIEVAL_N_CAND)
            listas.append([d["chunk_id"] for d in lexicos])
    ids = fusionar_rrf(listas, config.RETRIEVAL_K_RRF)[:k]
    return [dict(documentos[cid]) for cid in ids]


def _hibrido_blando(consulta: str, ticker, ejercicios: list[int], items: list[str],
                    n: int, item_blando: bool) -> list[dict]:
    """Híbrido con los ejercicios juntos; con ``item_blando``, RRF entre "con item" y "sin item".

    Así los pasajes de la sección probable suben, pero uno claramente mejor de otra sección sigue
    pudiendo aparecer (un item mal deducido no deja la respuesta fuera).
    """
    lista = buscar_hibrido([consulta], ticker, ejercicios or None, items or None, n)
    if not (item_blando and items):
        return lista
    sin_item = buscar_hibrido([consulta], ticker, ejercicios or None, None, n)
    documentos = {d["chunk_id"]: d for d in sin_item + lista}
    ids = fusionar_rrf([[d["chunk_id"] for d in lista], [d["chunk_id"] for d in sin_item]],
                       config.RETRIEVAL_K_RRF)[:n]
    return [documentos[i] for i in ids]


def buscar_final(query: str, ticker=None, fiscal_year=None, item=None, k: int = 5, *,
                 item_blando: bool = False, relajar: tuple[str, ...] = ()) -> list[dict]:
    """Híbrido (denso + BM25 + RRF) con filtros que admiten listas, item blando y relajación.

    - ``fiscal_year`` / ``item`` pueden ser listas: el filtro admite cualquiera de sus valores y el
      ranking es único (medido: con ticker y ambos ejercicios, el top-5 de una comparativa ya
      contiene los dos ejercicios).
    - ``item_blando``: RRF de "con item" y "sin item" (el item inferido orienta, no excluye).
    - ``relajar``: si quedan menos de k resultados se completan, en este orden, soltando el item y
      después también el ejercicio (nunca la empresa). Esos resultados llevan ``relajado`` = etapa.
    Determinista y sin llamadas al LLM. Sin opciones equivale a ``buscar_hibrido``.
    """
    _validar_busqueda(query, k)
    ejercicios = _como_lista(fiscal_year, int)
    items = [i for i in _como_lista(item, _normalizar_item) if i]
    if not item_blando and not relajar:
        return buscar_hibrido([query], ticker, ejercicios or None, items or None, k)
    n = max(config.RETRIEVAL_N_CAND, k)
    resultados = _hibrido_blando(query, ticker, ejercicios, items, n, item_blando)[:k]
    vistos = {d["chunk_id"] for d in resultados}
    for etapa, ejercicios_e in (("item", ejercicios), ("fy", [])):
        if len(resultados) >= k or etapa not in relajar:
            continue
        if (etapa == "item" and not items) or (etapa == "fy" and not ejercicios):
            continue
        for doc in _hibrido_blando(query, ticker, ejercicios_e, [], n, False):
            if len(resultados) >= k:
                break
            if doc["chunk_id"] not in vistos:
                vistos.add(doc["chunk_id"])
                resultados.append(dict(doc, relajado=etapa))
    return resultados


def precalentar() -> None:
    """Carga BGE, FAISS y BM25 y ejecuta una búsqueda de calentamiento. Idempotente y segura entre hilos.

    El arranque en frío (import de torch ~14 s + BGE) es el mayor coste de la primera búsqueda;
    llamarla al empezar una evaluación (p. ej. en un hilo) lo oculta detrás de la primera llamada al LLM.
    """
    global _PRECALENTADO
    with _BLOQUEO:
        _cargar_recursos()
        _leer_metadatos_cache()
        _cargar_bm25()
        if _PRECALENTADO:
            return
        buscar_final("revenue growth drivers", "NVDA", 2025, "7", 3, item_blando=True, relajar=("item", "fy"))
        _PRECALENTADO = True


_PRECALENTADO = False


REGLAS_CONSULTA ="""Write short ENGLISH queries using 10-K wording.
Put company, fiscal year and section in filters, not in the query text.
Use fiscal year, not filing year. Sections: 1A risks, 7 MD&A, 7A market risk, 8 financial statements.
Compare fiscal years by searching each year separately."""
INSTRUCCIONES_BUSQUEDA = """Turn the question into a search request, not an answer.
Return exactly ONE Busqueda tool call containing all 1-3 queries and filters.
Never call Busqueda separately for each query or fiscal year.
Include ticker, fiscal_years and item explicitly. Extract company and fiscal years
from the question, even when they also appear in the queries.
Infer the section from the question: risks 1A, management discussion 7,
market/foreign exchange exposure 7A, financial statements and notes 8.
Leave a filter empty only when it cannot be determined from the question.
Preserve the intent: explanations, risks and comparability must remain in the
queries; do not turn a request for an explanation into a search for numbers alone.
If two fiscal years are compared, include both in fiscal_years.
""" + REGLAS_CONSULTA

VERSION_REESCRITURA = 2
MAX_INTENTOS_REESCRITURA = 2
ERRORES_PROVEEDOR_NO_REINTENTABLES = {
    "TooManyRequestsResponseError", "PaymentRequiredResponseError", "UnauthorizedResponseError",
}


def filtros_explicitos(pregunta: str) -> dict:
    """Extrae solo entidades explícitas de la pregunta, sin consultar el golden.

    Conserva ambos FY. Una empresa o sección ambigua no se impone al modelo.
    """
    aliases = {**{t: t for t in ("NVDA", "MSFT", "AAPL", "GOOGL", "META", "AMZN")}, **ALIAS}
    tickers = {ticker for alias, ticker in aliases.items()
               if re.search(r"\b" + re.escape(alias) + r"\b", pregunta, re.IGNORECASE)}
    years = sorted({int(y) for y in re.findall(r"(?<!\d)(202[45])(?!\d)", pregunta)})
    items = {i.upper() for i in re.findall(r"\b(?:item|secci[oó]n)\s+(1A|7A|7|8|15)\b",
                                          pregunta, re.IGNORECASE)}
    items = {"8" if i == "15" else i for i in items}
    filtros = {}
    if len(tickers) == 1:
        filtros["ticker"] = next(iter(tickers))
    if years:
        filtros["fiscal_years"] = years
    if len(items) == 1:
        filtros["item"] = next(iter(items))
    return filtros


# --- Inferencia de filtros para las búsquedas del agente -------------------------------------------
# Medido con las consultas reales del agente (resultados/candidato_07): nunca pasó fiscal_year ni item
# (0/31 llamadas) y solo a veces el ticker; inferirlos de la pregunta sube el MRR de las anclas. Son reglas
# generales de vocabulario 10-K y de nombres de empresa, sin ids ni preguntas concretas del golden.

_NOMBRES_EMPRESA = {
    **{t: t for t in ("NVDA", "MSFT", "AAPL", "GOOGL", "META", "AMZN")}, **ALIAS,
    "META PLATFORMS": "META", "AMAZON.COM": "AMZN", "AMAZON WEB SERVICES": "AMZN", "AWS": "AMZN",
    "AZURE": "MSFT", "IPHONE": "AAPL", "YOUTUBE": "GOOGL", "INSTAGRAM": "META", "WHATSAPP": "META",
}
_RE_EMPRESA = {
    alias: re.compile(r"(?<![A-Za-z])" + (r"(?:META|Meta)" if alias == "META" else re.escape(alias))
                      + r"(?![A-Za-z])", 0 if alias == "META" else re.IGNORECASE)
    for alias in _NOMBRES_EMPRESA
}   # "meta" en minúscula es la palabra española, no la empresa
_RE_FY = re.compile(r"(?<![\w.])(?:FY|F\.Y\.)\s*'?\s*(?:20)?(2[45])(?!\d)", re.IGNORECASE)
_RE_ANIO = re.compile(r"(?<![\d,.$])(202[45])(?!\d)")
# Rango abreviado «2024/25», «2024-25», «FY24/25»: el segundo ejercicio no tiene 4 cifras y, sin esto,
# el filtro (duro) de ejercicio dejaría fuera la evidencia de FY2025.
_RE_RANGO = re.compile(r"(?<![\w.$,])(?:FY\s*'?(?:20)?|20)(2[45])\s*[/–—-]\s*(?:FY\s*)?(?:20)?(2[45])(?!\d)",
                       re.IGNORECASE)
_RE_ITEM_EXPLICITO = re.compile(r"\b(?:item|seccion|section|apartado)\s+(1a|7a|7|8|15)\b")

_ITEM_7A = (r"tipos? de cambio|divisa|moneda extranjera|foreign (?:currency|exchange)|exchange rate|"
            r"tipos? de interes|interest rate|riesgo de mercado|market risk|sensibilidad|value.at.risk|\bvar\b|"
            r"materias primas|commodit|cobertura|hedg|derivad|riesgo de credito|credit risk|contraparte|"
            r"counterparty|precio de (?:las |sus )?(?:acciones|inversiones)|equity (?:price|investments)|"
            r"renta variable")
_ITEM_1A = (r"riesgo|risk|amenaza|incertidumbre|litigio|legal proceedings|lawsuit|demanda judicial|regulaci|"
            r"regulator|antimonopolio|antitrust|competencia|ciberseguridad|cyber|dependen|depender|dependencia|"
            r"proveedor")
_ITEM_8 = (r"estados financieros|financial statements|\bnotas?\b|notes? to|arrendamiento|lease|"
           r"obligaciones contractuales|compromisos|politicas? contables?|criterios? contables?|impuesto|"
           r"deuda|pasivo|balance|cuenta de resultados|beneficio por accion|\beps\b|split|division de acciones|"
           r"adquisici|deterioro|goodwill|fondo de comercio|provisi|partida|segmentos? (?:contable|de informaci)|"
           r"restringid|escrow|comparab")
_ITEM_7 = (r"direccion|management|md&a|discusion|explica|evoluci|crecimiento|ingresos|ventas|resultados|"
           r"gasto|coste|costo|margen|liquidez|flujo de caja|capital|inversion|estrategia|segmento|aument|"
           r"disminu|variacion")


def _plegar(texto: str) -> str:
    """Minúsculas y sin acentos, para que las reglas no dependan de tildes."""
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower()


def _items_de(pregunta: str) -> tuple[str, ...]:
    t = _plegar(pregunta)
    explicitos = {"8" if i == "15" else i.upper() for i in _RE_ITEM_EXPLICITO.findall(t)}
    if len(explicitos) == 1:
        return (next(iter(explicitos)),)
    if re.search(_ITEM_7A, t):
        return ("1A", "7A") if re.search(r"factor|riesgo[s]? (?:declar|regul)", t) else ("7A", "7")
    if re.search(r"\bfactores? de riesgo|riesgo|risk", t) and not re.search(r"evoluci|ingresos|flujo", t):
        return ("1A",)
    if re.search(_ITEM_8, t):
        return ("8", "7") if re.search(_ITEM_7, t) else ("8",)
    if re.search(_ITEM_7, t):
        return ("7", "8")
    return ("1A",) if re.search(_ITEM_1A, t) else ()   # litigios, regulación, ciberseguridad... sin "riesgo"


def inferir_filtros(pregunta: str) -> dict:
    """Ticker, ejercicios e items probables de una pregunta en español o inglés.

    Devuelve ``{"ticker": str | None, "fiscal_years": tuple[int, ...], "items": tuple[str, ...]}``.
    Solo se afirma lo que la pregunta permite: ticker si nombra exactamente una empresa, ejercicios si
    escribe 2024/2025 o FY24/FY25, y los items por vocabulario (el primero es el más probable; la
    herramienta los usa como filtro blando). Un dato ambiguo queda vacío.
    """
    texto = str(pregunta or "")
    empresas = {_NOMBRES_EMPRESA[alias] for alias, patron in _RE_EMPRESA.items() if patron.search(texto)}
    ejercicios = {2000 + int(y) for y in _RE_FY.findall(texto)} | {int(y) for y in _RE_ANIO.findall(texto)}
    ejercicios |= {2000 + int(y) for par in _RE_RANGO.findall(texto) for y in par}
    return {"ticker": next(iter(empresas)) if len(empresas) == 1 else None,
            "fiscal_years": tuple(sorted(ejercicios)), "items": _items_de(texto)}


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
    return hashlib.sha256(json.dumps([VERSION_REESCRITURA, modelo_id, config.TEMPERATURA, protocolo, pregunta],
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
    if clave in cache and not cache[clave].get("fallo"):
        return cache[clave]
    if not permitir_api:
        raise ReescrituraPendiente("Reescritura pendiente: ejecuta esta celda con EJECUTAR = True.")
    if reescritor is None:
        reescritor = crear_reescritor(config.crear_modelo(modelo_id))
    from langchain_core.callbacks import get_usage_metadata_callback
    inicio, error = time.perf_counter(), None
    explicitos = filtros_explicitos(pregunta)
    busqueda = Busqueda(consultas=[pregunta], **explicitos)
    mensajes, errores, original, ajustes = [], [], None, {}
    entrada_modelo = pregunta + "\nExplicit filters to preserve: " + json.dumps(explicitos)
    with get_usage_metadata_callback() as cb:
        for intento in range(1, MAX_INTENTOS_REESCRITURA + 1):
            try:
                salida = reescritor.invoke({"messages": [{"role": "user", "content": entrada_modelo}]},
                                          config={"recursion_limit": 8})
                mensajes.extend(salida.get("messages", []))
                original = Busqueda.model_validate(salida.get("structured_response")).model_dump()
                ajustes = {k: v for k, v in explicitos.items() if original[k] != v}
                busqueda = Busqueda.model_validate(original | explicitos)
                error = None
                break
            except Exception as exc:
                error = type(exc).__name__
                errores.append(error)  # No persistir mensajes que puedan contener credenciales.
                if getattr(exc, "ai_message", None) is not None:
                    mensajes.append(exc.ai_message)
                if error in ERRORES_PROVEEDOR_NO_REINTENTABLES:
                    break  # No agotar la cuota repitiendo inmediatamente una petición rechazada.
                entrada_modelo = (pregunta + "\nExplicit filters to preserve: " + json.dumps(explicitos)
                                  + "\nThe previous attempt failed. Return exactly ONE Busqueda call. "
                                  "Put all queries in consultas and all fiscal years in fiscal_years.")
    costes = [getattr(m, "response_metadata", {}).get("cost") for m in mensajes
              if getattr(m, "type", None) == "ai"]
    coste = sum(float(c) for c in costes) if costes and all(c is not None for c in costes) else None
    entrada = {"pregunta": pregunta, "modelo": modelo_id, "busqueda": busqueda.model_dump(),
               "fallo": error is not None, "error": error,
               "intentos": intento, "errores_intentos": errores,
               "busqueda_llm": original, "filtros_explicitos": explicitos, "ajustes_filtros": ajustes,
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
