"""Contratos offline de evaluación para el candidato del notebook 07."""
from __future__ import annotations

import json

import pandas as pd
import pytest

from agente10k import config, evaluacion, evaluadores


def _guardar_json(ruta, valor):
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(valor), encoding="utf-8")


def _guardar_jsonl(ruta, filas):
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text("".join(json.dumps(f) + "\n" for f in filas), encoding="utf-8")


def _resumen(etiqueta, *, micro, recall, latencia, llamadas, errores=0, abstenciones=0):
    return {
        "etiqueta": etiqueta,
        "n": 4,
        "familias": {
            "numerica": "1/1", "extractiva": "1/1",
            "comparativa": "1/2", "hueco": "—",
        },
        "micro": micro,
        "macro": micro,
        "recall@5": recall,
        "usd_medio": None,
        "tokens_medios": 1000 if etiqueta == "baseline" else 900,
        "latencia_media_s": latencia,
        "latencia_mediana_s": latencia - 0.1,
        "llamadas_medias": llamadas,
        "errores": errores,
        "abstenciones_indebidas": abstenciones,
    }


def test_evaluar_no_degrada_candidato_a_baseline(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "RESULTADOS", tmp_path)
    llamadas = []

    def ejecutar(ruta, etiqueta, sistema):
        llamadas.append((ruta, etiqueta, sistema))

    monkeypatch.setattr(evaluadores, "ejecutar_golden", ejecutar)
    monkeypatch.setattr(evaluadores, "puntuar", lambda etiqueta: pd.DataFrame({"id": [etiqueta]}))

    tabla = evaluacion.evaluar("golden.jsonl", etiqueta="prueba", sistema="candidato_07")

    assert llamadas == [("golden.jsonl", "prueba", "candidato_07")]
    assert tabla.iloc[0]["id"] == "prueba"


def test_evaluar_rechaza_sistema_desconocido(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "RESULTADOS", tmp_path)
    with pytest.raises(ValueError, match="Sistema desconocido"):
        evaluacion.evaluar("golden.jsonl", sistema="basline")


def test_evaluar_reutiliza_predicciones_sin_api(tmp_path, monkeypatch):
    # evaluar() solo reutiliza predicciones con un manifest.json compatible (las anteriores al
    # manifest son «legacy» y se rechazan hasta evaluadores.bendecir_legacy): se crea uno real.
    monkeypatch.setattr(config, "RESULTADOS", tmp_path)
    golden = tmp_path / "golden.jsonl"
    _guardar_jsonl(golden, [{"id": "p1", "pregunta": "¿?"}])
    pred = tmp_path / "candidato_07" / "predicciones.jsonl"
    _guardar_jsonl(pred, [{"id": "p1"}])
    _guardar_json(pred.with_name("manifest.json"),
                  evaluadores.manifest_ejecucion(golden, "candidato_07"))
    monkeypatch.setattr(
        evaluadores, "ejecutar_golden",
        lambda *args, **kwargs: pytest.fail("no debe ejecutar la API si ya hay predicciones"),
    )
    monkeypatch.setattr(evaluadores, "puntuar", lambda etiqueta: pd.DataFrame({"id": [etiqueta]}))

    evaluacion.evaluar(golden, etiqueta="candidato_07", sistema="candidato_07")


def test_fachadas_de_evaluadores_reutilizan_la_implementacion(monkeypatch):
    pregunta = {"id": "p1"}
    fila = {"respuesta": {"cifra": 10}, "tool_calls": [{"name": "x"}]}
    monkeypatch.setattr(evaluadores, "evaluar_cifra", lambda resp, p: {"b": resp["cifra"] == 10})
    monkeypatch.setattr(
        evaluadores, "evaluar_trayectoria",
        lambda calls, p, resp: {"c": calls[0]["name"] == "x"},
    )
    monkeypatch.setattr(evaluadores, "puntuar_fila", lambda f, juez, estricto: {"a": None})

    assert evaluacion.evaluar_cifra(fila, pregunta) is True
    assert evaluacion.evaluar_trayectoria(fila, pregunta) is True
    assert evaluacion.evaluar_cita(fila, pregunta) is None
    assert evaluacion.evaluar_cita({"a": True}, pregunta) is True


def test_tabla_comparativa_incluye_metricas_y_marca_mejores(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "RESULTADOS", tmp_path)
    _guardar_json(
        tmp_path / "baseline" / "resumen.json",
        _resumen("baseline", micro=0.5, recall=0.2, latencia=10, llamadas=4,
                 errores=1, abstenciones=1),
    )
    _guardar_json(
        tmp_path / "candidato_07" / "resumen.json",
        _resumen("candidato_07", micro=0.75, recall=0.6, latencia=8, llamadas=3),
    )
    _guardar_jsonl(
        tmp_path / "baseline" / "puntuaciones.jsonl",
        [{"recall_agente": False}, {"recall_agente": True}],
    )
    _guardar_jsonl(
        tmp_path / "candidato_07" / "puntuaciones.jsonl",
        [{"recall_agente": True}, {"recall_agente": True}],
    )

    tabla = evaluacion.tabla_comparativa(("baseline", "candidato_07", "final"))

    assert list(tabla["sistema"]) == ["baseline", "candidato_07", "final"]
    assert bool(tabla.loc[2, "disponible"]) is False
    assert pd.isna(tabla.loc[2, "micro"])
    assert tabla.loc[0, "numerica"] == "1/1"
    assert tabla.loc[0, "recall_agente"] == 0.5
    assert bool(tabla.loc[1, "mejor_micro"]) is True
    assert bool(tabla.loc[1, "mejor_recall@5"]) is True
    assert bool(tabla.loc[1, "mejor_latencia_media_s"]) is True
    assert bool(tabla.loc[1, "mejor_errores"]) is True
    assert bool(tabla.loc[0, "mejor_micro"]) is False
    assert "recall@5" in tabla.attrs["nota_recall"]


def test_tabla_no_remarca_si_solo_hay_un_resultado(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "RESULTADOS", tmp_path)
    _guardar_json(
        tmp_path / "baseline" / "resumen.json",
        _resumen("baseline", micro=0.5, recall=0.2, latencia=10, llamadas=4),
    )

    tabla = evaluacion.tabla_comparativa(("baseline", "final"))

    assert not bool(tabla.loc[0, "mejor_micro"])
    assert not bool(tabla.loc[1, "mejor_micro"])


def test_tabla_rechaza_etiquetas_repetidas():
    with pytest.raises(ValueError, match="únicas"):
        evaluacion.tabla_comparativa(("baseline", "baseline"))


# ------------------------------------------------------ tabla del enunciado §5 (R11)
def _resumen_con_modelo(etiqueta, modelo, **kw):
    return {**_resumen(etiqueta, **kw), "modelo": modelo}


def test_tabla_r11_trae_las_columnas_del_enunciado_y_marca_el_mejor(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "RESULTADOS", tmp_path)
    _guardar_json(tmp_path / "base" / "resumen.json",
                  _resumen_con_modelo("base", "m1", micro=0.5, recall=0.2, latencia=10, llamadas=4))
    _guardar_json(tmp_path / "fin" / "resumen.json",
                  _resumen_con_modelo("fin", "m1", micro=0.75, recall=0.6, latencia=8, llamadas=3))

    tabla = evaluacion.tabla_r11(("base", "fin"))

    # El enunciado §5 exige coste y latencia COMO COLUMNAS, no como nota al pie.
    for columna in ("numérica", "extractiva", "comparativa", "hueco", "micro", "recall@5",
                    "coste USD/pregunta", "latencia media (s)", "llamadas/pregunta"):
        assert columna in tabla.columns
    fila_fin = tabla[tabla["sistema"] == "fin"].iloc[0]
    fila_base = tabla[tabla["sistema"] == "base"].iloc[0]
    assert fila_fin["micro"].endswith("*") and not fila_base["micro"].endswith("*")
    assert fila_fin["latencia media (s)"].endswith("*")      # menos latencia es mejor
    assert "*" in tabla.attrs["nota"]


def test_tabla_r11_no_marca_ganador_si_las_filas_son_de_modelos_distintos(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "RESULTADOS", tmp_path)
    _guardar_json(tmp_path / "base" / "resumen.json",
                  _resumen_con_modelo("base", "modelo-viejo", micro=0.5, recall=0.2, latencia=10, llamadas=4))
    _guardar_json(tmp_path / "fin" / "resumen.json",
                  _resumen_con_modelo("fin", "modelo-nuevo", micro=0.75, recall=0.6, latencia=8, llamadas=3))

    with pytest.warns(UserWarning, match="no usan el mismo modelo"):
        tabla = evaluacion.tabla_r11(("base", "fin"))

    assert not any("*" in str(v) for v in tabla.drop(columns=["sistema", "modelo"]).values.ravel())

def test_manifest_bm25_rechaza_resultados_del_hibrido(tmp_path):
    golden = tmp_path / "golden.jsonl"
    golden.write_text("", encoding="utf-8")
    actual = evaluadores.manifest_ejecucion(golden, "final")
    assert actual["retrieval"] == {
        "backend": "bm25", "consulta": "palabras_clave_ingles_agente", "item": False,
    }
    anterior = dict(actual, retrieval={"backend": "hibrido_sin_reescritura", "paso_aislado": "2_bm25"})
    assert evaluadores.validar_manifest(anterior, actual)
