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
# Permite usar el corpus montado fuera del repo (por ejemplo, en Colab) sin
# cambiar código. En local conserva la ruta versionada del proyecto.
CORPUS = Path(os.environ.get("AGENTE10K_CORPUS", DATA / "corpus")).expanduser().resolve()
INDICE = CORPUS / "indice"
GOLDEN = RAIZ / "golden"
RESULTADOS = RAIZ / "resultados"

# Modelo fijo para todo lo que se evalúa: baseline y final con el mismo (docs/01 §4, D01).
# La variable existe para experimentos reproducibles, no para cambiar de modelo a mitad
# de una evaluación.
MODELO_ID = os.environ.get("AGENTE10K_MODELO", "openrouter:google/gemini-3.8-flash")
TEMPERATURA = 0


def _lista_modelos(valor: str | None, predeterminado: tuple[str, ...]) -> tuple[str, ...]:
    """Convierte una lista separada por comas en ids, descartando entradas vacías."""
    modelos = tuple(item.strip() for item in (valor or "").split(",") if item.strip())
    return modelos or predeterminado


# La cascada es una opción de disponibilidad para desarrollo: OpenRouter intenta el
# primero y solo pasa al siguiente ante un fallo técnico. Si no se configura, se
# comporta como un único modelo y por tanto no altera el baseline evaluable.
CASCADA_MODELOS = _lista_modelos(os.environ.get("AGENTE10K_CASCADA"), (MODELO_ID,))


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


def _id_openrouter(modelo: str) -> str:
    """Quita el prefijo de LangChain para el parámetro ``model`` de OpenRouter."""
    return modelo.removeprefix("openrouter:")


def crear_modelo(modelo: str | None = None, fallbacks: list[str] | tuple[str, ...] | None = None):
    """Crea una instancia a temperatura cero.

    Sin ``fallbacks`` conserva ``init_chat_model`` para el baseline. Con una
    lista, usa el campo ``models`` de la API de OpenRouter: el primer id es el
    principal y los restantes se intentan solo si OpenRouter no puede servirlo.
    Esta ruta se reserva para desarrollo; el baseline oficial no la utiliza.
    """
    from langchain.chat_models import init_chat_model

    principal = modelo or MODELO_ID
    suplentes = tuple(fallbacks or ())
    if not suplentes:
        return init_chat_model(principal, temperature=TEMPERATURA)

    # ``models`` es el parámetro nativo de OpenRouter. ChatOpenRouter lo expone
    # mediante model_kwargs; así no se fuerza un parámetro ajeno a otros providers.
    if not principal.startswith("openrouter:") or any(not item.startswith("openrouter:") for item in suplentes):
        raise ValueError("La cascada de disponibilidad solo admite ids 'openrouter:...'.")
    from langchain_openrouter import ChatOpenRouter

    return ChatOpenRouter(
        model=_id_openrouter(principal), temperature=TEMPERATURA,
        model_kwargs={"models": [_id_openrouter(item) for item in suplentes]},
    )
