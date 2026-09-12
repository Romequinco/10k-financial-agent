"""Lo que no se puede cambiar (enunciado §7, docs/01 §3): lo usan las preguntas ciegas del día 24."""
import inspect

from agente10k import agente, config, evaluacion, herramientas

HERRAMIENTAS = {
    "list_available": [],
    "get_xbrl_fact": ["ticker", "fiscal_year", "concept"],
    "search_filings": ["query", "ticker", "fiscal_year", "item", "k"],
    "read_section": ["ticker", "fiscal_year", "item"],
}
CAMPOS = ["respuesta", "cifra", "unidad", "ticker", "ejercicio", "fuente", "cita", "chunk_id"]


def test_herramientas_del_contrato():
    for nombre, params in HERRAMIENTAS.items():
        herramienta = getattr(herramientas, nombre)
        assert herramienta.name == nombre
        # Se pueden añadir parámetros con valor por defecto al final, no cambiar los existentes.
        assert list(inspect.signature(herramienta.func).parameters)[:len(params)] == params


def test_valores_por_defecto_de_search_filings():
    firma = inspect.signature(herramientas.search_filings.func).parameters
    assert [firma[p].default for p in ("ticker", "fiscal_year", "item", "k")] == [None, None, None, 5]


def test_campos_de_respuesta_financiera():
    assert list(agente.RespuestaFinanciera.model_fields)[:8] == CAMPOS


def test_responder_y_evaluar():
    assert list(inspect.signature(agente.responder).parameters)[0] == "pregunta"
    assert list(inspect.signature(evaluacion.evaluar).parameters)[0] == "ruta_jsonl"


def test_rutas_del_repo():
    assert (config.CORPUS / "chunks.jsonl").is_file()
    assert (config.INDICE / "corpus.faiss").is_file()
