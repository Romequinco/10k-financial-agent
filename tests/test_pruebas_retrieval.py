"""Comparación local con filtros de la pregunta y sección oráculo opcional."""
import json

import pandas as pd
import pytest

from agente10k import config, evaluacion, pruebas_retrieval, retrieval


@pytest.fixture
def experimento(tmp_path, monkeypatch):
    pregunta = {
        "id": "p1", "pregunta": "Ingresos de Microsoft entre 2024 y 2025",
        "ticker": "MSFT", "fiscal_year": 2025, "item_esperado": "7",
        "ancla_texto": "revenue growth drivers",
    }
    consultas = ["How did Microsoft revenue evolve in 2025?", "revenue growth",
                 "revenue increased reasons"]
    (tmp_path / "consultas.json").write_text(json.dumps({"p1": consultas}), encoding="utf-8")
    (tmp_path / "protocolo.json").write_text(json.dumps({"golden": [pregunta]}), encoding="utf-8")
    monkeypatch.setattr(pruebas_retrieval, "_EXPERIMENTO", tmp_path)
    monkeypatch.setattr(evaluacion, "cargar_golden", lambda _: [pregunta])
    meta = pd.DataFrame([
        {"chunk_id": str(i), "ticker": "MSFT", "fiscal_year": 2025,
         "item": "8" if i < 5 else "7",
         "texto": "unrelated passage" if i < 5 else "revenue growth drivers"}
        for i in range(6)
    ])
    monkeypatch.setattr(retrieval, "_leer_metadatos_cache", lambda: meta)
    llamadas = []

    def buscador(motor):
        def buscar(query, k, **filtros):
            llamadas.append((motor, query, filtros))
            filas = meta.to_dict("records")
            return [f for f in filas if all(v is None or f[c] == v for c, v in filtros.items())][:k]
        return buscar

    monkeypatch.setattr(retrieval, "buscar_denso", buscador("denso"))
    monkeypatch.setattr(retrieval, "buscar_bm25", buscador("bm25"))

    def prohibido(*args, **kwargs):
        raise AssertionError("Estas pruebas no deben usar API ni credenciales")

    monkeypatch.setattr(config, "crear_modelo", prohibido)
    monkeypatch.setattr(config, "cargar_clave", prohibido)
    return pregunta, llamadas


@pytest.mark.parametrize("variante", ["limpieza_densa", "bm25_breve", "denso_reformulado"])
def test_item_cambia_solo_la_seccion_y_se_mide_por_separado(experimento, variante):
    _, llamadas = experimento
    sin_item = pruebas_retrieval.probar_variante(variante)
    llamadas_sin = list(llamadas)
    llamadas.clear()
    con_item = pruebas_retrieval.probar_variante(variante, usar_item=True)

    assert len(llamadas_sin) == len(llamadas)
    for (motor, query, filtros_sin), (motor_con, query_con, filtros_con) in zip(llamadas_sin, llamadas):
        assert (motor, query) == (motor_con, query_con)
        assert "item" not in filtros_sin
        if filtros_sin:
            assert filtros_sin == {"ticker": "MSFT", "fiscal_year": 2025}
            assert filtros_con == {**filtros_sin, "item": "7"}
        else:
            assert filtros_con == {}  # La referencia sin filtros sigue siendo común.
    assert sin_item["resumen"].iloc[-1]["aciertos@5"] == "0/1"
    assert con_item["resumen"].iloc[-1]["aciertos@5"] == "1/1"
    assert sin_item["detalle"].iloc[0]["rango_prueba"] == 6
    assert con_item["detalle"].iloc[0]["rango_prueba"] == 1
    assert sin_item["detalle"]["item"].isna().all()
    assert con_item["detalle"]["item"].tolist() == ["7"]
    assert sin_item["resumen"].iloc[-1]["escenario"] == "Sin item"
    assert con_item["resumen"].iloc[-1]["escenario"] == "Con item del golden"


@pytest.mark.parametrize("variante", ["limpieza_densa", "bm25_breve", "denso_reformulado"])
def test_empresa_y_ejercicio_nunca_se_toman_del_golden(experimento, variante):
    pregunta, llamadas = experimento
    # Metadatos deliberadamente contradictorios: no deben llegar al buscador.
    pregunta.update(ticker="NVDA", fiscal_year=2024)
    for usar_item in (False, True):
        pruebas_retrieval.probar_variante(variante, usar_item=usar_item)
    for _, _, filtros in llamadas:
        if filtros:
            assert filtros["ticker"] == "MSFT"
            assert filtros["fiscal_year"] == 2025
