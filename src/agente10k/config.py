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


MODELO_EMBEDDINGS = "BAAI/bge-small-en-v1.5"


def _modelo_en_cache_hf(modelo: str) -> bool:
    """True si el modelo de Hugging Face ya está descargado y completo en la caché local."""
    hub = os.environ.get("HF_HUB_CACHE") or os.environ.get("HUGGINGFACE_HUB_CACHE")
    if not hub:
        base = os.environ.get("HF_HOME") or (Path.home() / ".cache" / "huggingface")
        hub = Path(base) / "hub"
    instantaneas = Path(hub) / ("models--" + modelo.replace("/", "--")) / "snapshots"
    try:
        return any((carpeta / "config.json").exists() and (carpeta / "modules.json").exists()
                   for carpeta in instantaneas.iterdir())
    except OSError:
        return False


# Con el modelo BGE ya en caché, evita los intentos de red de huggingface_hub (cada carga espera a los
# reintentos si no hay conexión). Si no está en caché no se fuerza: la primera ejecución debe poder descargarlo.
# Debe fijarse antes de importar huggingface_hub, por eso vive aquí; setdefault respeta lo que ya haya.
if _modelo_en_cache_hf(MODELO_EMBEDDINGS):
    os.environ.setdefault("HF_HUB_OFFLINE", "1")

RAIZ = _buscar_raiz()
DATA = RAIZ / "data"
# Permite usar el corpus montado fuera del repo (por ejemplo, en Colab) sin
# cambiar código. En local conserva la ruta versionada del proyecto.
CORPUS = Path(os.environ.get("AGENTE10K_CORPUS", DATA / "corpus")).expanduser().resolve()
INDICE = CORPUS / "indice"
GOLDEN = RAIZ / "golden"
RESULTADOS = RAIZ / "resultados"

# Modelo fijo para todo lo que se evalúa: baseline y final con el mismo (docs/01 §4, D01).
# Gratuito, elegido tras el banco de 12 modelos `:free` de la ronda 2: los demás o no devuelven
# salida estructurada, o el proveedor responde 429, o tardan minutos por pregunta. El baseline
# histórico de `resultados/baseline/` se midió con ling-3.0-flash-fin y se conserva sin tocar;
# la comparación con el mismo modelo vive en `resultados/baseline_nexn25pro/`.
# AGENTE10K_MODELO permite fijar otro modelo antes de iniciar el kernel.
MODELO_ID = os.environ.get("AGENTE10K_MODELO", "openrouter:nex-agi/nex-n2.5-pro:free")
TEMPERATURA = 0
TIMEOUT_OPENROUTER_MS = int(os.environ.get("AGENTE10K_TIMEOUT_MS", "30000"))

# Notebook 05: constantes del experimento, fijadas antes de medir.
RETRIEVAL_N_CAND = 20
RETRIEVAL_K_RRF = 60
BM25_K1 = 1.5
BM25_B = 0.75
BM25_EPSILON = 0.25
RETRIEVAL_TOKENIZER = r"[a-z0-9]+"
RESULTADOS_RETRIEVAL = RESULTADOS / "retrieval"
CACHE_REESCRITURAS = RESULTADOS / "cache" / "reescrituras.json"


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
        # utf-8-sig también acepta el UTF-8 normal y elimina la marca BOM que
        # algunos editores de Windows añaden al principio de .env.
        for linea in env.read_text(encoding="utf-8-sig").splitlines():
            clave, _, valor = linea.partition("=")
            if clave.strip() == "OPENROUTER_API_KEY" and valor.strip():
                os.environ["OPENROUTER_API_KEY"] = valor.strip()
                return True
    return False


def _id_openrouter(modelo: str) -> str:
    """Quita el prefijo de LangChain para el parámetro ``model`` de OpenRouter."""
    return modelo.removeprefix("openrouter:")


def _cliente_openrouter():
    """Crea un cliente que no hereda proxies ajenos al proyecto.

    Algunos entornos de notebook inyectan ``HTTP_PROXY`` hacia un puerto local
    inexistente. ``trust_env=False`` mantiene TLS y evita que esa variable
    externa bloquee las llamadas reales a OpenRouter.
    """
    if not cargar_clave():
        raise RuntimeError("Falta OPENROUTER_API_KEY en el entorno o en .env.")
    import httpx
    import openrouter

    return openrouter.OpenRouter(
        api_key=os.environ["OPENROUTER_API_KEY"],
        client=httpx.Client(trust_env=False, timeout=TIMEOUT_OPENROUTER_MS / 1000),
        async_client=httpx.AsyncClient(trust_env=False, timeout=TIMEOUT_OPENROUTER_MS / 1000),
        timeout_ms=TIMEOUT_OPENROUTER_MS,
    )


def crear_modelo(modelo: str | None = None, fallbacks: list[str] | tuple[str, ...] | None = None):
    """Crea una instancia a temperatura cero.

    Para OpenRouter crea un cliente explícito que no hereda proxies del proceso.
    Con una lista, ``models`` ordena el failover técnico del proveedor.
    """
    principal = modelo or MODELO_ID
    suplentes = tuple(fallbacks or ())
    if not principal.startswith("openrouter:"):
        from langchain.chat_models import init_chat_model
        return init_chat_model(principal, temperature=TEMPERATURA)

    # ``models`` es el parámetro nativo de OpenRouter y debe contener *todo* el
    # orden de preferencia, incluido el principal. ``model`` se conserva como
    # identificador principal para LangChain; OpenRouter recibe la lista completa
    # para poder hacer failover ante rate limit o indisponibilidad.
    if any(not item.startswith("openrouter:") for item in suplentes):
        raise ValueError("La cascada de disponibilidad solo admite ids 'openrouter:...'.")
    from langchain_openrouter import ChatOpenRouter
    kwargs = {}
    if suplentes:
        kwargs["model_kwargs"] = {"models": [_id_openrouter(item) for item in (principal, *suplentes)]}
    # Ajustes opcionales, iguales para baseline y final cuando se comparan (D01): esfuerzo de razonamiento del
    # modelo (menos tokens ocultos y menor latencia), tope de salida y reintentos ante 429/5xx del proveedor.
    if os.environ.get("AGENTE10K_REASONING"):
        kwargs["reasoning"] = {"effort": os.environ["AGENTE10K_REASONING"]}
    if os.environ.get("AGENTE10K_MAX_TOKENS"):
        kwargs["max_tokens"] = int(os.environ["AGENTE10K_MAX_TOKENS"])
    return ChatOpenRouter(
        model=_id_openrouter(principal), temperature=TEMPERATURA,
        client=_cliente_openrouter(), timeout=TIMEOUT_OPENROUTER_MS,
        # 1 y no 2: el peor caso se multiplica (reintentos del cliente x vueltas del grafo x
        # reintentos por pregunta) y en la medición de la ronda 2 no llegó a dispararse ninguno
        # (60 de 60 peticiones fueron 200). Basta con cubrir un corte puntual.
        max_retries=int(os.environ.get("AGENTE10K_MAX_RETRIES", "1")), **kwargs,
    )
