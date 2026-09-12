"""Rutas y parámetros comunes del proyecto.

Todas las rutas salen de la raíz del repo (la carpeta con pyproject.toml), así que funcionan igual
desde notebooks/, tests/ o la raíz, en local y en Colab. Nunca usar rutas relativas al cwd.
"""
from __future__ import annotations

import os
from pathlib import Path


def _buscar_raiz() -> Path:
    for carpeta in Path(__file__).resolve().parents:
        if (carpeta / "pyproject.toml").is_file():
            return carpeta
    raise RuntimeError("No encuentro la raíz del repo (la carpeta con pyproject.toml).")


RAIZ = _buscar_raiz()
DATA = RAIZ / "data"
CORPUS = DATA / "corpus"
INDICE = CORPUS / "indice"
GOLDEN = RAIZ / "golden"
RESULTADOS = RAIZ / "resultados"

# Modelo fijo para todo lo que se evalúa: baseline y final con el mismo (docs/01 §4, D01).
MODELO_ID = "openrouter:google/gemini-3.8-flash"
TEMPERATURA = 0


def cargar_clave() -> bool:
    """Deja OPENROUTER_API_KEY en el entorno (desde el entorno o desde .env) y devuelve si hay clave."""
    if os.environ.get("OPENROUTER_API_KEY"):
        return True
    env = RAIZ / ".env"
    if env.is_file():
        for linea in env.read_text(encoding="utf-8").splitlines():
            clave, _, valor = linea.partition("=")
            if clave.strip() == "OPENROUTER_API_KEY" and valor.strip():
                os.environ["OPENROUTER_API_KEY"] = valor.strip()
                return True
    return False


def crear_modelo():
    """Modelo del agente con temperature=0. Pasar esta INSTANCIA a create_agent (docs/01 §5, fallo 9)."""
    from langchain.chat_models import init_chat_model

    return init_chat_model(MODELO_ID, temperature=TEMPERATURA)
