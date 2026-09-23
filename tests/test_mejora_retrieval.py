"""Notebook 05: pruebas sin API, sin clave y sin descargar modelos."""
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from langchain.messages import AIMessage

from agente10k import config, evaluacion, herramientas, retrieval


@pytest.fixture(autouse=True)
def sin_api(monkeypatch):
    def prohibido(*args, **kwargs):
        raise AssertionError("Las pruebas del 05 no pueden crear clientes ni leer claves")
    monkeypatch.setattr(config, "crear_modelo", prohibido)
    monkeypatch.setattr(config, "cargar_clave", prohibido)
    retrieval._ranking_denso_completo.cache_clear()
    retrieval._cargar_bm25.cache_clear()
    yield
    retrieval._ranking_denso_completo.cache_clear()
    retrieval._cargar_bm25.cache_clear()


@pytest.fixture
def corpus(monkeypatch):
    meta = pd.DataFrame([
        {"chunk_id": "a", "ticker": "MSFT", "fiscal_year": 2025, "item": "7", "texto": "revenue growth"},
        {"chunk_id": "b", "ticker": "MSFT", "fiscal_year": 2024, "item": "7", "texto": "cloud demand"},
        {"chunk_id": "c", "ticker": "NVDA", "fiscal_year": 2025, "item": "7", "texto": "supply risk"},
        {"chunk_id": "d", "ticker": "NVDA", "fiscal_year": 2024, "item": "8", "texto": "lease obligations"},
    ])
    monkeypatch.setattr(retrieval, "_leer_metadatos_cache", lambda: meta)
    monkeypatch.setattr(retrieval, "_cargar_recursos", lambda: None)
    monkeypatch.setattr(retrieval, "buscar_denso", lambda *a, **kw: [
        dict(r, puntuacion=1 - i / 10) for i, r in enumerate(meta.iloc[::-1].to_dict("records"))])
    return meta


def test_prefiltro_antes_del_recorte_y_orden_baseline(corpus, monkeypatch):
    monkeypatch.setattr(config, "RETRIEVAL_N_CAND", 1)
    resultado = retrieval.buscar_hibrido(["revenue"], "MSFT", 2025, "7", usar_bm25=False)
    assert [d["chunk_id"] for d in resultado] == ["a"]
    monkeypatch.setattr(config, "RETRIEVAL_N_CAND", 20)
    assert [d["chunk_id"] for d in retrieval.buscar_hibrido(["x"], usar_bm25=False)] == ["d", "c", "b", "a"]


def test_bm25_global_sin_ceros_ni_filtro_contaminando_idf(corpus):
    globales = retrieval.buscar_bm25("REVENUE", k=20)
    filtrados = retrieval.buscar_bm25("revenue", "MSFT", 2025, "7", 20)
    assert globales == filtrados
    assert [d["chunk_id"] for d in filtrados] == ["a"]
    assert retrieval.buscar_bm25("palabras inexistentes") == []
    assert retrieval.buscar_bm25("revenue", "NVDA") == []


def test_rrf_premia_consenso_y_no_duplicados():
    assert retrieval.fusionar_rrf([["a", "b", "c"], ["d", "e", "c"]])[0] == "c"
    assert retrieval.fusionar_rrf([["a", "a", "b"], ["b"]])[0] == "b"
    assert retrieval.fusionar_rrf([["a", "b", "c"]]) == ["a", "b", "c"]


def test_reescritura_no_crea_cliente_en_modo_offline(tmp_path):
    with pytest.raises(retrieval.ReescrituraPendiente):
        retrieval.reescribir("pregunta", ruta_cache=tmp_path / "cache.json")


def test_cache_y_fallo_sin_filtrar_secretos(tmp_path, monkeypatch):
    class Falso:
        llamadas = 0
        def invoke(self, entrada, config):
            self.llamadas += 1
            return {"structured_response": {"consultas": ["revenue growth"], "ticker": "MSFT"},
                    "messages": [AIMessage(content="", response_metadata={"cost": 0.0})]}
    falso, ruta = Falso(), tmp_path / "cache.json"
    primera = retrieval.reescribir("pregunta", True, ruta, "modelo-prueba", falso)
    segunda = retrieval.reescribir("pregunta", False, ruta, "modelo-prueba")
    assert primera == segunda and falso.llamadas == 1
    assert primera["usd"] == 0.0 and not primera["fallo"]
    with pytest.raises(retrieval.ReescrituraPendiente):
        retrieval.reescribir("pregunta", False, ruta, "otro-modelo")
    monkeypatch.setattr(retrieval, "INSTRUCCIONES_BUSQUEDA", "Otro prompt")
    with pytest.raises(retrieval.ReescrituraPendiente):
        retrieval.reescribir("pregunta", False, ruta, "modelo-prueba")

    class Roto:
        def invoke(self, *args, **kwargs):
            raise RuntimeError("secreto-no-publicable")
    fallo = retrieval.reescribir("otra pregunta", True, ruta, "modelo-prueba", Roto())
    assert fallo["fallo"] and fallo["busqueda"]["consultas"] == ["otra pregunta"]
    assert "secreto-no-publicable" not in ruta.read_text(encoding="utf-8")


def test_reescritor_real_con_modelo_falso_y_estructura(tmp_path):
    from langchain_core.language_models.fake_chat_models import GenericFakeChatModel

    class ModeloFalso(GenericFakeChatModel):
        def bind_tools(self, tools, **kwargs):
            return self

    modelo = ModeloFalso(messages=iter([AIMessage(content="", tool_calls=[{
        "name": "Busqueda", "id": "busqueda-1",
        "args": {"consultas": ["cloud demand"], "ticker": "MSFT", "fiscal_years": [2024, 2025], "item": "7"},
    }])]))
    reescritor = retrieval.crear_reescritor(modelo)
    resultado = retrieval.reescribir("compara", True, tmp_path / "cache.json", "falso", reescritor)
    assert not resultado["fallo"]
    assert resultado["busqueda"]["fiscal_years"] == [2024, 2025]
    assert resultado["usd"] is None


def test_multiquery_comparativa_busca_ambos_ejercicios(corpus):
    b = {"consultas": ["revenue", "cloud"], "ticker": "MSFT", "fiscal_years": [2024, 2025], "item": "7"}
    assert [d["chunk_id"] for d in retrieval.buscar_reescrita(b)] == ["a", "b"]


def test_recall_normalizado_mrr_y_ausentes(corpus):
    preguntas = [
        {"id": "p1", "ancla_texto": "Revenue\t GROWTH", "item_esperado": "7"},
        {"id": "p2", "ancla_texto": "cloud demand", "item_esperado": "7"},
        {"id": "p3", "ancla_texto": None},
    ]
    rankings = [{"id": "p1", "ranking": ["c", "a"], "ms": 10}]
    assert evaluacion.recall_at_k(rankings, preguntas, 1) == 0
    assert evaluacion.recall_at_k(rankings, preguntas, 5) == 0.5
    assert evaluacion.resumir_retrieval(rankings, preguntas)["mrr@10"] == 0.25
    with pytest.raises(ValueError, match="repetidos"):
        evaluacion.recall_at_k(rankings * 2, preguntas)


def test_filtros_llm_ausentes_erroneos_y_comparativa():
    p = {"ticker": "MSFT", "familia": "comparativa", "fiscal_year": 2025, "fiscal_year_base": 2024, "item_esperado": "7"}
    estados = evaluacion.diagnosticar_filtros({"ticker": "Microsoft", "fiscal_years": [2025], "item": None}, p)
    assert estados == {"ticker": "ok", "fiscal_years": "erroneo", "item": "ausente"}


def test_tool_final_preserva_baseline_y_contrato(monkeypatch):
    llamadas = []
    def buscar(*args, **kwargs):
        llamadas.append(kwargs)
        return [{"chunk_id": "a", "ticker": "MSFT", "fiscal_year": 2025,
                 "item": "7", "texto": "revenue growth", "puntuacion": 0.4}]
    monkeypatch.setattr(retrieval, "buscar", buscar)
    herramienta = herramientas.crear_search_filings()
    assert herramienta.name == "search_filings"
    assert herramienta.args == herramientas.search_filings.args
    assert retrieval.REGLAS_BM25 in herramienta.description
    assert herramientas.TOOLS[2] is herramientas.search_filings
    texto = herramienta.invoke({"query": "revenue", "ticker": "microsoft", "fiscal_year": 2025, "item": "7"})
    assert "[a]" in texto and "revenue growth" in texto
    assert llamadas[0]["modo"] == "final" and llamadas[0]["ticker"] == "MSFT"


def test_experimento_reutilizacion_y_tablas_sin_modelo(corpus, tmp_path, monkeypatch):
    monkeypatch.setattr(evaluacion, "validar_golden", lambda p: [])
    golden = [{"id": "p1", "pregunta": "revenue", "ancla_texto": "revenue growth",
               "familia": "extractiva", "ticker": "MSFT", "fiscal_year": 2025, "item_esperado": "7"}]
    directorio = evaluacion.preparar_retrieval(golden, tmp_path)
    for paso in ("0_denso", "1_filtro", "2_bm25", "d_solo_bm25"):
        evaluacion.medir_retrieval(golden, paso, directorio)
    tablas = evaluacion.exportar_retrieval(golden, directorio)
    assert len(tablas["escalera"]) == 4
    assert "3_reescritura" in json.loads((directorio / "resumen.json").read_text())["pendientes"]
    monkeypatch.setattr(retrieval, "buscar_hibrido", lambda *a, **kw: pytest.fail("No debe buscar de nuevo"))
    assert evaluacion.medir_retrieval(golden, "0_denso", directorio)
    assert evaluacion.exportar_retrieval(golden, directorio)["escalera"].equals(tablas["escalera"])
    with pytest.raises(retrieval.ReescrituraPendiente):
        evaluacion.medir_retrieval(golden, "3_reescritura", directorio, ruta_cache=tmp_path / "cache.json")
    assert not (directorio / "rankings_3_reescritura.jsonl").exists()
    cambiado = [{**golden[0], "pregunta": "otra"}]
    with pytest.raises(ValueError, match="experimento ha cambiado"):
        evaluacion.medir_retrieval(cambiado, "0_denso", directorio)


def test_notebook_solo_codigo_sin_todos():
    nb = json.loads((config.RAIZ / "notebooks/05_mejora_retrieval.ipynb").read_text(encoding="utf-8"))
    for i, cell in enumerate(nb["cells"]):
        if cell["cell_type"] == "code":
            source = "".join(cell["source"])
            compile(source, f"celda-{i}", "exec")
            assert "# TODO" not in source


def test_escalera_completa_con_reescritura_simulada(corpus, tmp_path, monkeypatch):
    monkeypatch.setattr(evaluacion, "validar_golden", lambda p: [])
    golden = [{"id": "p1", "pregunta": "ingresos", "ancla_texto": "revenue growth",
               "familia": "extractiva", "ticker": "MSFT", "fiscal_year": 2025, "item_esperado": "7"}]
    class Falso:
        def invoke(self, *args, **kwargs):
            return {"structured_response": {"consultas": ["revenue growth"], "ticker": "MSFT",
                                             "fiscal_years": [2025], "item": "7"}}
    cache = tmp_path / "cache.json"
    retrieval.reescribir("ingresos", True, cache, reescritor=Falso())
    directorio = evaluacion.preparar_retrieval(golden, tmp_path)
    for paso in evaluacion.PASOS_RETRIEVAL:
        evaluacion.medir_retrieval(golden, paso, directorio, ruta_cache=cache)
    tablas = evaluacion.exportar_retrieval(golden, directorio)
    assert json.loads((directorio / "resumen.json").read_text())["completo"]
    assert len(tablas["escalera"]) == 6
    assert sum(tablas["filtros"].query("estado == 'ok'")["n"]) == 3
    assert tablas["escalera"].query("paso == '3_reescritura'")["recall@5"].iloc[0] == 1
    assert evaluacion.techos_retrieval(golden)[0]["techo_filtro"]


def test_filtro_ausente_agente_y_anclas_no_se_concatenan():
    p = {"id": "p1", "ticker": "MSFT", "familia": "extractiva", "fiscal_year": 2025,
         "item_esperado": "7", "ancla_texto": "revenue growth"}
    pred = {"id": "p1", "tool_calls": [{"name": "search_filings", "args": {"query": "revenue"}}],
            "observaciones": [{"name": "search_filings", "content": "revenue"},
                              {"name": "search_filings", "content": "growth"}]}
    tabla = evaluacion.diagnosticar_retrieval_agente([pred], [p])
    assert tabla.iloc[0]["fiscal_years"] == "ausente"
    assert not tabla.iloc[0]["recall_agente"]


def test_reescritura_recupera_multiple_salida_y_preserva_filtros(tmp_path):
    from langchain_core.language_models.fake_chat_models import GenericFakeChatModel

    class ModeloFalso(GenericFakeChatModel):
        def bind_tools(self, tools, **kwargs):
            return self

    llamadas = [{"name": "Busqueda", "id": f"q-{fy}", "args": {
        "consultas": ["revenue growth"], "ticker": "NVDA", "fiscal_years": [fy], "item": "7",
    }} for fy in (2024, 2025)]
    corregida = {"name": "Busqueda", "id": "unica", "args": {
        "consultas": ["revenue growth drivers"], "ticker": "MSFT", "item": "8",
    }}
    modelo = ModeloFalso(messages=iter([
        AIMessage(content="", tool_calls=llamadas), AIMessage(content="", tool_calls=[corregida]),
    ]))
    resultado = retrieval.reescribir(
        "Compara NVIDIA FY2024 y FY2025, Item 7", True, tmp_path / "cache.json", "falso",
        retrieval.crear_reescritor(modelo),
    )
    assert not resultado["fallo"] and resultado["intentos"] == 2
    assert resultado["errores_intentos"] == ["MultipleStructuredOutputsError"]
    assert resultado["busqueda"] == {
        "consultas": ["revenue growth drivers"], "ticker": "NVDA", "fiscal_years": [2024, 2025], "item": "7",
    }
    assert resultado["busqueda_llm"]["ticker"] == "MSFT"


def test_fallo_acotado_con_filtros_y_cache_reintentable(tmp_path):
    class Roto:
        llamadas = 0
        def invoke(self, *args, **kwargs):
            self.llamadas += 1
            raise RuntimeError("secreto-no-publicable")

    pregunta, ruta, roto = "Riesgos de Apple FY2024, Item 1A", tmp_path / "cache.json", Roto()
    fallo = retrieval.reescribir(pregunta, True, ruta, "falso", roto)
    assert roto.llamadas == 2 and fallo["fallo"]
    assert fallo["busqueda"] == {
        "consultas": [pregunta], "ticker": "AAPL", "fiscal_years": [2024], "item": "1A",
    }
    with pytest.raises(retrieval.ReescrituraPendiente):
        retrieval.reescribir(pregunta, False, ruta, "falso")

    class Recuperado:
        llamadas = 0
        def invoke(self, *args, **kwargs):
            self.llamadas += 1
            return {"structured_response": {"consultas": ["business risks"]}}

    recuperado = Recuperado()
    ok = retrieval.reescribir(pregunta, True, ruta, "falso", recuperado)
    assert not ok["fallo"] and recuperado.llamadas == 1
    assert retrieval.reescribir(pregunta, False, ruta, "falso") == ok
    assert "secreto-no-publicable" not in ruta.read_text(encoding="utf-8")


def test_filtros_explicitos_no_inventa_seccion_ni_elige_entre_empresas():
    assert retrieval.filtros_explicitos("Compara Google y Microsoft FY2024 y FY2025") == {
        "fiscal_years": [2024, 2025],
    }
    assert retrieval.filtros_explicitos("Riesgos de NVIDIA FY2025") == {
        "ticker": "NVDA", "fiscal_years": [2025],
    }
    assert retrieval.filtros_explicitos("riesgos de proveedores") == {}


def test_recall_rechaza_ancla_de_otro_ejercicio_empresa_o_seccion(monkeypatch):
    meta = pd.DataFrame([
        {"chunk_id": cid, "ticker": ticker, "fiscal_year": fy, "item": item, "texto": "same anchor"}
        for cid, ticker, fy, item in [
            ("otro_fy", "AAPL", 2024, "8"), ("otra_empresa", "MSFT", 2025, "8"),
            ("otro_item", "AAPL", 2025, "7"), ("correcto", "AAPL", 2025, "8"),
        ]
    ])
    monkeypatch.setattr(retrieval, "_leer_metadatos_cache", lambda: meta)
    p = {"id": "p1", "ticker": "AAPL", "fiscal_year": 2025,
         "item_esperado": "8", "ancla_texto": "same anchor"}
    ranking = [{"id": "p1", "ranking": list(meta["chunk_id"]), "ms": 0}]
    assert evaluacion.recall_at_k(ranking, [p], 3) == 0
    assert evaluacion.recall_at_k(ranking, [p], 4) == 1
    assert evaluacion.detalle_retrieval(ranking, [p])[0]["n_relevantes"] == 1


def test_rankings_fallidos_no_impiden_reintentar_reescritura(corpus, tmp_path, monkeypatch):
    monkeypatch.setattr(evaluacion, "validar_golden", lambda p: [])
    golden = [{"id": "p1", "pregunta": "MSFT FY2025 Item 7 revenue", "ancla_texto": "revenue growth",
               "familia": "extractiva", "ticker": "MSFT", "fiscal_year": 2025, "item_esperado": "7"}]
    directorio = evaluacion.preparar_retrieval(golden, tmp_path)
    cache = tmp_path / "cache.json"

    class Roto:
        def invoke(self, *args, **kwargs):
            raise RuntimeError("fallo")

    retrieval.reescribir(golden[0]["pregunta"], True, cache, reescritor=Roto())
    fallida = {"id": "p1", "ranking": ["a"], "ms": 0, "reescritura": {"fallo": True}}
    evaluacion.guardar_golden([fallida], directorio / "rankings_3_reescritura.jsonl")
    with pytest.raises(retrieval.ReescrituraPendiente):
        evaluacion.medir_retrieval(golden, "3_reescritura", directorio, ruta_cache=cache)

    class Recuperado:
        def invoke(self, *args, **kwargs):
            return {"structured_response": {"consultas": ["revenue growth"]}}

    monkeypatch.setattr(retrieval, "crear_reescritor", lambda modelo: Recuperado())
    monkeypatch.setattr(config, "crear_modelo", lambda *a: object())
    filas = evaluacion.medir_retrieval(golden, "3_reescritura", directorio, permitir_api=True, ruta_cache=cache)
    assert not filas[0]["reescritura"]["fallo"]
    assert filas[0]["ranking"] == ["a"]


def test_limite_proveedor_detiene_tanda_sin_rankings_parciales(corpus, tmp_path, monkeypatch):
    monkeypatch.setattr(evaluacion, "validar_golden", lambda p: [])
    golden = [{"id": pid, "pregunta": f"MSFT FY2025 Item 7 {pid}", "ancla_texto": "revenue growth",
               "familia": "extractiva", "ticker": "MSFT", "fiscal_year": 2025, "item_esperado": "7"}
              for pid in ("p1", "p2")]
    directorio = evaluacion.preparar_retrieval(golden, tmp_path)

    class TooManyRequestsResponseError(RuntimeError):
        pass

    class Limitado:
        llamadas = 0
        def invoke(self, *args, **kwargs):
            self.llamadas += 1
            raise TooManyRequestsResponseError("no repetir inmediatamente")

    limitado = Limitado()
    monkeypatch.setattr(retrieval, "crear_reescritor", lambda modelo: limitado)
    monkeypatch.setattr(config, "crear_modelo", lambda *a: object())
    with pytest.raises(retrieval.ReescrituraPendiente, match="TooManyRequestsResponseError"):
        evaluacion.medir_retrieval(golden, "3_reescritura", directorio,
                                   permitir_api=True, ruta_cache=tmp_path / "cache.json")
    assert limitado.llamadas == 1
    assert not (directorio / "rankings_3_reescritura.jsonl").exists()
