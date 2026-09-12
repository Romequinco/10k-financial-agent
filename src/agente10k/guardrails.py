"""Guardrails del sistema final (guía en docs/09): límite de llamadas (R04) y verificación de cifras
contra XBRL que devuelve el desajuste al modelo (R05)."""
from __future__ import annotations


def middleware_final() -> list:
    """Pila de middleware del sistema final: límites de llamadas (ToolCallLimitMiddleware y
    ModelCallLimitMiddleware) y verificador XBRL (docs/09 §2 y §5)."""
    raise NotImplementedError("TODO · docs/09 §2 y §5")


def extraer_cifras(texto: str) -> list[float]:
    """Cifras que afirma una respuesta, normalizadas a unidades (docs/09 §4)."""
    raise NotImplementedError("TODO · docs/09 §4")


def verificar_cifras(respuesta, trayectoria: list[dict]) -> list[str]:
    """Desajustes entre las cifras de la respuesta y XBRL; lista vacía si todo cuadra (docs/09 §5–§6)."""
    raise NotImplementedError("TODO · docs/09 §5")
