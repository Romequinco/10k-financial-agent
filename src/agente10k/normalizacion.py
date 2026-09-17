"""Normalización de texto y cifras. Copiado de docs/16 §3.2-3.3 y docs/09 §4.

UNA sola definición de normalizar() y cifra_ok() en todo el proyecto (D07):
el middleware XBRL de R05 y el evaluador (b) de R09 usan estas mismas.
"""
from __future__ import annotations

import math
import re
import unicodedata

_TRAD = str.maketrans({"’": "'", "‘": "'", "“": '"', "”": '"', "–": "-", "—": "-"})

ALIAS = {"GOOG": "GOOGL", "ALPHABET": "GOOGL", "GOOGLE": "GOOGL", "FACEBOOK": "META",
         "NVIDIA": "NVDA", "MICROSOFT": "MSFT", "APPLE": "AAPL", "AMAZON": "AMZN"}

# "billones" (10^12) queda fuera a propósito: es el falso amigo de "billion".
ESCALA = [("miles de millones", 1e9), ("mil millones", 1e9), ("billion", 1e9),
          ("millones", 1e6), ("million", 1e6), ("miles", 1e3), ("thousand", 1e3)]


def normalizar(t: str | None) -> str:
    """Minúsculas, comillas tipográficas unificadas y espacios colapsados."""
    t = unicodedata.normalize("NFKC", t or "").translate(_TRAD).lower()
    return re.sub(r"\s+", " ", t).strip()          # colapsa \t y \n de las tablas


def normalizar_ticker(t) -> str:
    """La misma que usan las herramientas: admite alias y mayúsculas sueltas."""
    t = str(t or "").strip().upper()
    return ALIAS.get(t, t)


def _tokens(t: str) -> list[str]:
    return re.findall(r"\w+|[^\w\s]", normalizar(t))   # la puntuación, token aparte


def cobertura(frag: str, fuente: str, n: int = 4) -> float:
    """Fracción de n-gramas contiguos de `frag` presentes en `fuente`."""
    f, s = _tokens(frag), _tokens(fuente)
    if len(f) < n:
        return float(bool(f) and " ".join(f) in " ".join(s))
    vistos = set(zip(*(s[i:] for i in range(n))))
    grams = list(zip(*(f[i:] for i in range(n))))
    return sum(g in vistos for g in grams) / len(grams)


def cifra_ok(cifra, unidad, verdad, unidad_xbrl) -> dict:
    """Tolerancia documentada: USD 0,5 % relativo; USD/shares 0,005 absoluto.

    Hueco = acierto si cifra is None. Los desajustes de escala se etiquetan
    aparte de los de valor, para poder contarlos en la presentación.
    """
    if verdad is None:
        return {"ok": cifra is None, "motivo": "hueco"}
    if cifra is None:
        return {"ok": False, "motivo": "sin_cifra"}
    v = float(cifra) * next((f for clave, f in ESCALA if clave in normalizar(unidad)), 1.0)
    tol = ({"rel_tol": 0.0, "abs_tol": 0.005} if unidad_xbrl == "USD/shares"   # BPA: al céntimo
           else {"rel_tol": 0.005, "abs_tol": 0.0})                            # USD: 0,5 %
    if math.isclose(v, verdad, **tol):
        return {"ok": True}
    esc = next((e for e in (-9, -6, -3, 3, 6, 9) if math.isclose(v * 10**e, verdad, **tol)), None)
    return {"ok": False, "motivo": f"error_escala 1e{esc}" if esc else "fuera_de_tolerancia"}