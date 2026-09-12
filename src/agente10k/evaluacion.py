"""Golden set, los tres evaluadores, evaluar() y tablas (guías en docs/10, docs/12 y docs/13)."""
from __future__ import annotations

from pathlib import Path

import pandas as pd


def cargar_golden(ruta: str | Path) -> list[dict]:
    """Lee un JSONL de preguntas (golden propio o ciegas) sin exigir nada (docs/12 §2)."""
    raise NotImplementedError("TODO · docs/12 §2")


def validar_golden(preguntas: list[dict], exigir_20: bool = True) -> list[str]:
    """Problemas del golden set, uno por línea; lista vacía = correcto. Mismas reglas que el
    validador de clase (docs/10 §8, docs/01 §3)."""
    raise NotImplementedError("TODO · docs/10 §8")


def evaluar_cita(fila: dict, pregunta: dict) -> bool | None:
    """Evaluador (a): la cita existe en el corpus y respalda lo que se afirma (docs/12 §5–§6)."""
    raise NotImplementedError("TODO · docs/12 §5")


def evaluar_cifra(fila: dict, pregunta: dict) -> bool | None:
    """Evaluador (b): la cifra coincide con XBRL dentro de la tolerancia documentada (docs/12 §3)."""
    raise NotImplementedError("TODO · docs/12 §3")


def evaluar_trayectoria(fila: dict, pregunta: dict) -> bool | None:
    """Evaluador (c): la trayectoria pasó por la herramienta esperada (docs/12 §4)."""
    raise NotImplementedError("TODO · docs/12 §4")


def recall_at_k(rankings: list[dict], preguntas: list[dict], k: int = 5) -> float:
    """Fracción de preguntas con ancla cuya frase aparece en algún fragmento del top-k (docs/11 §4)."""
    raise NotImplementedError("TODO · docs/11 §4")


def evaluar(ruta_jsonl: str | Path, etiqueta: str | None = None, sistema: str = "final") -> pd.DataFrame:
    """CONTRATO (R10): ejecuta el agente sobre cada pregunta, guarda resultados/<etiqueta>/
    (predicciones.jsonl y resumen.json) y devuelve una fila por pregunta con los tres evaluadores,
    coste, latencia y llamadas (docs/12 §8)."""
    raise NotImplementedError("TODO · docs/12 §8")


def tabla_comparativa(etiquetas: tuple[str, ...] = ("baseline", "final")) -> pd.DataFrame:
    """Tabla R11: aciertos por familia, recall@k, coste medio, latencia media y llamadas por
    pregunta, con el mejor valor remarcado (docs/13 §5)."""
    raise NotImplementedError("TODO · docs/13 §5")
