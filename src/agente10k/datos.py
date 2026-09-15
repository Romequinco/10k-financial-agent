"""Carga y validación del corpus 10-K distribuido con la práctica."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

import pandas as pd
from pandas.api.types import is_bool_dtype, is_integer_dtype, is_numeric_dtype

from agente10k import config


_ARCHIVOS_CORPUS = ("secciones.jsonl", "chunks.jsonl", "xbrl_facts.parquet")
_ARCHIVOS_REQUERIDOS = (
    *_ARCHIVOS_CORPUS,
    "MANIFEST.md",
    "indice/MANIFEST.md",
    "indice/corpus.faiss",
    "indice/chunks_meta.parquet",
)


def _sha256(ruta: Path) -> str:
    """Calcula la huella SHA-256 de un fichero sin alterar sus bytes."""
    huella = hashlib.sha256()
    with ruta.open("rb") as fichero:
        for bloque in iter(lambda: fichero.read(1 << 20), b""):
            huella.update(bloque)
    return huella.hexdigest()


def _leer_jsonl(ruta: Path) -> pd.DataFrame:
    """Lee JSONL línea a línea para conservar identificadores como texto."""
    registros: list[dict] = []
    try:
        with ruta.open(encoding="utf-8") as fichero:
            for numero, linea in enumerate(fichero, start=1):
                if not linea.strip():
                    continue
                try:
                    registros.append(json.loads(linea))
                except json.JSONDecodeError as error:
                    raise ValueError(f"JSON inválido en {ruta}, línea {numero}: {error.msg}") from error
    except FileNotFoundError:
        raise FileNotFoundError(f"No existe el fichero del corpus: {ruta}") from None
    return pd.DataFrame(registros)


def _exigir_columnas(datos: pd.DataFrame, columnas: set[str], nombre: str) -> None:
    ausentes = sorted(columnas - set(datos.columns))
    if ausentes:
        raise RuntimeError(f"{nombre} no tiene las columnas obligatorias: {', '.join(ausentes)}")


def _exigir_cik_texto(datos: pd.DataFrame, nombre: str) -> None:
    if not datos["cik"].map(lambda valor: isinstance(valor, str)).all():
        raise RuntimeError(f"{nombre}: cik debe cargarse como texto para conservar los ceros iniciales")
    if not datos["cik"].str.fullmatch(r"\d{10}").all():
        raise RuntimeError(f"{nombre}: hay valores cik que no tienen diez dígitos")


def _huella_del_manifiesto(manifiesto: str, nombre: str) -> str:
    """Extrae la huella asociada al fichero, no una coincidencia incidental."""
    patron = rf"^\| `{re.escape(nombre)}` \|.*?`([0-9a-f]{{64}})`"
    coincidencia = re.search(patron, manifiesto, flags=re.MULTILINE)
    if not coincidencia:
        raise RuntimeError(f"data/corpus/MANIFEST.md no declara una huella para {nombre}")
    return coincidencia.group(1)


def _validar_universo(datos: pd.DataFrame, nombre: str) -> None:
    if set(datos["ticker"]) != {"NVDA", "MSFT", "AAPL", "GOOGL", "META", "AMZN"}:
        raise RuntimeError(f"{nombre}: el conjunto de empresas no coincide con el corpus de la práctica")
    if set(datos["fiscal_year"]) != {2024, 2025}:
        raise RuntimeError(f"{nombre}: los ejercicios deben ser FY2024 y FY2025")
    if not is_integer_dtype(datos["fiscal_year"]):
        raise RuntimeError(f"{nombre}: fiscal_year debe ser entero")


def verificar_corpus() -> None:
    """Valida archivos, hashes y alineación entre los chunks y el índice FAISS."""
    corpus = config.CORPUS
    for relativa in _ARCHIVOS_REQUERIDOS:
        ruta = corpus / relativa
        if not ruta.is_file():
            raise FileNotFoundError(f"Falta un archivo necesario del corpus: {ruta}")

    manifiesto_corpus = (corpus / "MANIFEST.md").read_text(encoding="utf-8")
    huellas = {nombre: _sha256(corpus / nombre) for nombre in _ARCHIVOS_CORPUS}
    for nombre, huella in huellas.items():
        if huella != _huella_del_manifiesto(manifiesto_corpus, nombre):
            raise RuntimeError(
                f"La huella SHA-256 de {nombre} no coincide con data/corpus/MANIFEST.md"
            )

    manifiesto_indice = (corpus / "indice" / "MANIFEST.md").read_text(encoding="utf-8")
    coincidencia_indice = re.search(
        r"^\| SHA-256 de `chunks\.jsonl` \| `([0-9a-f]{64})` \|",
        manifiesto_indice,
        flags=re.MULTILINE,
    )
    if not coincidencia_indice or huellas["chunks.jsonl"] != coincidencia_indice.group(1):
        raise RuntimeError(
            "La huella SHA-256 de chunks.jsonl no coincide con indice/MANIFEST.md; "
            "el índice FAISS y sus metadatos podrían estar desalineados"
        )


def cargar_secciones() -> pd.DataFrame:
    """Carga el texto íntegro de las 48 secciones, una por empresa, FY e item."""
    columnas = {
        "ticker", "empresa", "cik", "fiscal_year", "item", "titulo", "texto",
        "n_tokens", "url_origen", "accession", "item_origen",
    }
    secciones = _leer_jsonl(config.CORPUS / "secciones.jsonl")
    _exigir_columnas(secciones, columnas, "secciones.jsonl")
    if len(secciones) != 48:
        raise RuntimeError(f"secciones.jsonl debe tener 48 filas, no {len(secciones)}")
    if secciones.duplicated(["ticker", "fiscal_year", "item"]).any():
        raise RuntimeError("secciones.jsonl contiene claves (ticker, fiscal_year, item) duplicadas")
    _validar_universo(secciones, "secciones.jsonl")
    if set(secciones["item"]) != {"1A", "7", "7A", "8"}:
        raise RuntimeError("secciones.jsonl no contiene exactamente los items 1A, 7, 7A y 8")
    _exigir_cik_texto(secciones, "secciones.jsonl")
    if not is_integer_dtype(secciones["n_tokens"]) or (secciones["n_tokens"] <= 0).any():
        raise RuntimeError("secciones.jsonl: n_tokens debe contener enteros positivos")
    return secciones.sort_values(["ticker", "fiscal_year", "item"]).reset_index(drop=True)


def cargar_chunks() -> pd.DataFrame:
    """Carga los 1.749 fragmentos y conserva sus identificadores y offsets."""
    columnas = {
        "chunk_id", "ticker", "fiscal_year", "item", "posicion", "texto",
        "n_tokens", "contiene_tabla", "inicio_car", "fin_car",
    }
    chunks = _leer_jsonl(config.CORPUS / "chunks.jsonl")
    _exigir_columnas(chunks, columnas, "chunks.jsonl")
    if len(chunks) != 1749:
        raise RuntimeError(f"chunks.jsonl debe tener 1.749 filas, no {len(chunks)}")
    if chunks["chunk_id"].duplicated().any():
        raise RuntimeError("chunks.jsonl contiene chunk_id duplicados")
    _validar_universo(chunks, "chunks.jsonl")
    if set(chunks["item"]) != {"1A", "7", "7A", "8"}:
        raise RuntimeError("chunks.jsonl no contiene exactamente los items 1A, 7, 7A y 8")
    for columna in ("posicion", "n_tokens", "inicio_car", "fin_car"):
        if not is_integer_dtype(chunks[columna]):
            raise RuntimeError(f"chunks.jsonl: {columna} debe ser entero")
    if (chunks["posicion"] < 0).any() or (chunks["n_tokens"] <= 0).any():
        raise RuntimeError("chunks.jsonl contiene posiciones negativas o recuentos de tokens no positivos")
    if (chunks["inicio_car"] < 0).any() or (chunks["fin_car"] <= chunks["inicio_car"]).any():
        raise RuntimeError("chunks.jsonl contiene offsets de caracteres inválidos")
    if not is_bool_dtype(chunks["contiene_tabla"]):
        raise RuntimeError("chunks.jsonl: contiene_tabla debe ser booleano")
    return chunks.sort_values(["ticker", "fiscal_year", "item", "posicion"]).reset_index(drop=True)


def cargar_xbrl() -> pd.DataFrame:
    """Carga los 135 hechos XBRL sin escalar ni redondear sus valores."""
    ruta = config.CORPUS / "xbrl_facts.parquet"
    if not ruta.is_file():
        raise FileNotFoundError(f"No existe el fichero del corpus: {ruta}")
    xbrl = pd.read_parquet(ruta)
    columnas = {"ticker", "cik", "fiscal_year", "concept", "value", "unit", "period_end", "form"}
    _exigir_columnas(xbrl, columnas, "xbrl_facts.parquet")
    if len(xbrl) != 135:
        raise RuntimeError(f"xbrl_facts.parquet debe tener 135 filas, no {len(xbrl)}")
    if xbrl.duplicated(["ticker", "fiscal_year", "concept"]).any():
        raise RuntimeError("xbrl_facts.parquet contiene claves (ticker, fiscal_year, concept) duplicadas")
    _validar_universo(xbrl, "xbrl_facts.parquet")
    _exigir_cik_texto(xbrl, "xbrl_facts.parquet")
    if not is_numeric_dtype(xbrl["value"]) or xbrl["value"].isna().any():
        raise RuntimeError("xbrl_facts.parquet: value debe contener números no nulos")
    if set(xbrl["unit"]) != {"USD", "USD/shares"}:
        raise RuntimeError("xbrl_facts.parquet contiene unidades distintas de USD y USD/shares")
    if set(xbrl["form"]) != {"10-K"}:
        raise RuntimeError("xbrl_facts.parquet contiene formularios distintos de 10-K")
    if xbrl["concept"].nunique() != 13:
        raise RuntimeError("xbrl_facts.parquet debe contener 13 conceptos XBRL")
    return xbrl.sort_values(["ticker", "fiscal_year", "concept"]).reset_index(drop=True)
