"""Carga del corpus de data/corpus y comprobación de integridad (docs/02 §3, §7 y §8; data/README.md)."""
from __future__ import annotations

import pandas as pd

from agente10k import config


def verificar_corpus() -> None:
    """Comprueba el SHA-256 de chunks.jsonl contra los dos MANIFEST y lanza si no cuadra (docs/02 §8)."""
    raise NotImplementedError("TODO · docs/02 §8 y data/README.md")


def cargar_secciones() -> pd.DataFrame:
    """secciones.jsonl: texto íntegro por (ticker, fiscal_year, item). Lo usa read_section (docs/02 §3)."""
    raise NotImplementedError("TODO · docs/02 §7")


def cargar_chunks() -> pd.DataFrame:
    """chunks.jsonl: los 1.749 fragmentos con su chunk_id. Lo usan search_filings y recall@k (docs/02 §3)."""
    raise NotImplementedError("TODO · docs/02 §7")


def cargar_xbrl() -> pd.DataFrame:
    """xbrl_facts.parquet: 135 hechos, la fuente autorizada de cualquier cifra (docs/02 §5)."""
    raise NotImplementedError("TODO · docs/02 §7")
