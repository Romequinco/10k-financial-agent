"""Puntuación: micro parcial sin juez, modo sin_referencia, banderas, juez y métricas (offline)."""
from __future__ import annotations

import json
import math

import pandas as pd
import pytest

from agente10k import config, evaluacion, evaluadores
from agente10k.evaluadores import (Juez, Veredicto, acierto, banderas_diagnosticas, es_hueco,
                                   metricas_operativas, puntuar_fila, resumen_aciertos)

ANCLA = "AWS sales increased 20% in 2025, compared to the prior year."
NUMERICA = {"id": "n1", "pregunta": "¿Beneficio bruto de NVDA FY2024?", "familia": "numerica",
            "ticker": "NVDA", "fiscal_year": 2024, "cifra_esperada": 44301000000.0, "unidad": "USD",
            "concept_xbrl": "GrossProfit", "herramienta_esperada": ["get_xbrl_fact"],
            "respuesta_esperada": "44.301 millones"}
EXTRACTIVA = {"id": "x1", "pregunta": "¿Cómo crecieron las ventas de AWS?", "familia": "extractiva",
              "ticker": "AMZN", "fiscal_year": 2025, "cifra_esperada": None, "unidad": None,
              "concept_xbrl": None, "item_esperado": "7", "ancla_texto": ANCLA,
              "respuesta_esperada": "Un 20 %", "herramienta_esperada": ["search_filings"]}
XBRL_OK = [{"name": "get_xbrl_fact", "args": {"ticker": "NVDA", "fiscal_year": 2024, "concept": "GrossProfit"}}]
BUSQUEDA = [{"name": "search_filings", "args": {"query": "AWS"}}]


def fila(p, resp, llamadas=(), obs=(), **extra):
    return {"id": p["id"], "golden": p, "respuesta": resp, "tool_calls": list(llamadas),
            "observaciones": list(obs), **extra}


def resp_extractiva(**kw):
    return {"respuesta": "AWS creció un 20 %.", "fuente": "texto", "cita": ANCLA, "ticker": "AMZN",
            "ejercicio": 2025, "chunk_id": None, **kw}


OBS_ANCLA = [{"name": "search_filings", "content": f"[AMZN-2025-7-0001] {ANCLA}"}]


class JuezFalso:
    modelo_id = "fake"

    def __init__(self, respalda=True, correcta=True):
        self._r, self._c, self.llamadas_respalda, self.llamadas_correcta = respalda, correcta, 0, 0
        self.llamadas, self.fallos, self.uso = 0, 0, {}

    def guardar(self):
        pass

    def respalda(self, cita, respuesta):
        self.llamadas_respalda += 1
        return self._r

    def correcta(self, *a):
        self.llamadas_correcta += 1
        return self._c


# --------------------------------------------------- micro parcial (punto 1)
def test_sin_juez_las_extractivas_no_evaluables_dejan_el_micro_parcial():
    punt = [puntuar_fila(fila(NUMERICA, {"cifra": 44301e6, "unidad": "USD", "fuente": "xbrl"}, XBRL_OK)),
            puntuar_fila(fila(EXTRACTIVA, resp_extractiva(), BUSQUEDA, OBS_ANCLA))]
    assert punt[0]["acierto"] is True and punt[1]["acierto"] is None

    r = resumen_aciertos(punt)

    assert r["parcial"] is True and r["n_no_evaluables"] == 1
    assert r["micro"] is None and r["macro"] is None                # nunca el 1.0 engañoso
    assert r["micro_parcial"] == 1.0 and r["micro_cota_inferior"] == 0.5
    assert r["familias"]["extractiva"] == "—"


def test_con_todo_evaluable_el_resumen_no_es_parcial():
    punt = [puntuar_fila(fila(NUMERICA, {"cifra": 44301e6, "unidad": "USD", "fuente": "xbrl"}, XBRL_OK))]
    r = resumen_aciertos(punt)
    assert r["parcial"] is False and r["micro"] == 1.0 and r["micro_cota_inferior"] is None


def _preparar_predicciones(tmp_path, monkeypatch, filas, sistema="candidato_07"):
    monkeypatch.setattr(config, "RESULTADOS", tmp_path / "res")
    monkeypatch.setattr(evaluadores, "_estado_git",
                        lambda: {"commit": "c", "dirty": False, "diff_sha256": "d"})
    golden = tmp_path / "g.jsonl"
    golden.write_text("".join(json.dumps(f["golden"]) + "\n" for f in filas), encoding="utf-8")
    destino = config.RESULTADOS / sistema
    evaluadores._escribir_jsonl(destino / "predicciones.jsonl", filas)
    (destino / "manifest.json").write_text(
        json.dumps(evaluadores.manifest_ejecucion(golden, sistema)), encoding="utf-8")
    return golden


def _filas_mixtas():
    return [fila(NUMERICA, {"cifra": 44301e6, "unidad": "USD", "fuente": "xbrl"}, XBRL_OK,
                 latencia_s=2.0, uso_mensajes={"total_tokens": 10}, n_llamadas=1),
            fila(EXTRACTIVA, resp_extractiva(), BUSQUEDA, OBS_ANCLA,
                 latencia_s=4.0, uso_mensajes={"total_tokens": 30}, n_llamadas=1)]


def test_evaluar_crea_el_juez_por_defecto_y_lo_usa(tmp_path, monkeypatch):
    golden = _preparar_predicciones(tmp_path, monkeypatch, _filas_mixtas())
    juez = JuezFalso()
    creados = []
    monkeypatch.setattr(evaluadores, "crear_juez", lambda *a, **k: creados.append(1) or juez)

    tabla = evaluacion.evaluar(golden, etiqueta="candidato_07", sistema="candidato_07")

    assert creados == [1] and juez.llamadas_respalda == 1
    resumen = json.loads((config.RESULTADOS / "candidato_07" / "resumen.json").read_text(encoding="utf-8"))
    assert resumen["con_juez"] is True and resumen["parcial"] is False and resumen["micro"] == 1.0
    assert tabla.attrs["aviso"] is None


def test_evaluar_sin_poder_crear_el_juez_avisa_y_marca_parcial(tmp_path, monkeypatch):
    golden = _preparar_predicciones(tmp_path, monkeypatch, _filas_mixtas())

    def sin_clave(*a, **k):
        raise RuntimeError("Falta OPENROUTER_API_KEY")

    monkeypatch.setattr(evaluadores, "crear_juez", sin_clave)

    with pytest.warns(UserWarning) as avisos:
        tabla = evaluacion.evaluar(golden, etiqueta="candidato_07", sistema="candidato_07")

    texto = " ".join(str(a.message) for a in avisos)
    assert "No se pudo crear el juez" in texto and "PARCIAL" in texto
    resumen = json.loads((config.RESULTADOS / "candidato_07" / "resumen.json").read_text(encoding="utf-8"))
    assert resumen["parcial"] is True and resumen["micro"] is None       # no 1.0
    assert resumen["micro_parcial"] == 1.0 and resumen["micro_cota_inferior"] == 0.5
    assert tabla.attrs["resumen"]["parcial"] is True
    fila_ext = tabla[tabla["id"] == "x1"].iloc[0]
    assert fila_ext["acierto"] is None or pd.isna(fila_ext["acierto"])


def test_con_juez_false_no_intenta_crearlo(tmp_path, monkeypatch):
    golden = _preparar_predicciones(tmp_path, monkeypatch, _filas_mixtas())
    monkeypatch.setattr(evaluadores, "crear_juez",
                        lambda *a, **k: pytest.fail("no debe crearse con con_juez=False"))
    with pytest.warns(UserWarning, match="PARCIAL"):
        evaluacion.evaluar(golden, etiqueta="candidato_07", sistema="candidato_07", con_juez=False)


def test_evaluar_no_crea_juez_si_solo_hay_numericas(tmp_path, monkeypatch):
    filas = [_filas_mixtas()[0]]
    golden = _preparar_predicciones(tmp_path, monkeypatch, filas)
    monkeypatch.setattr(evaluadores, "crear_juez", lambda *a, **k: pytest.fail("sobra el juez"))
    tabla = evaluacion.evaluar(golden, etiqueta="candidato_07", sistema="candidato_07")
    assert tabla.attrs["aviso"] is None and tabla.attrs["resumen"]["micro"] == 1.0


# ---------------------------------------------------------- juez (punto 11)
def test_no_se_llama_al_juez_si_la_trayectoria_ya_falla():
    juez = JuezFalso()
    s = puntuar_fila(fila(EXTRACTIVA, resp_extractiva(), [], OBS_ANCLA), juez=juez)   # sin search_filings
    assert s["c"] is False and s["acierto"] is False and s["juez_omitido"] is True
    assert juez.llamadas_respalda == 0 and juez.llamadas_correcta == 0


def test_sin_juez_una_trayectoria_fallida_ya_es_fallo_conocido():
    s = puntuar_fila(fila(EXTRACTIVA, resp_extractiva(), [], OBS_ANCLA))
    assert s["c"] is False and s["acierto"] is False


def test_un_fallo_del_juez_se_marca_y_no_pasa_desapercibido():
    juez = JuezFalso(respalda=None)                                   # el parseo del juez falló
    s = puntuar_fila(fila(EXTRACTIVA, resp_extractiva(), BUSQUEDA, OBS_ANCLA), juez=juez)
    assert s["juez_fallo"] is True and s["a"] is False and s["acierto"] is False
    assert evaluadores._puntuar_filas(
        "x", [fila(EXTRACTIVA, resp_extractiva(), BUSQUEDA, OBS_ANCLA)], juez, True
    )[1]["juez_fallos_filas"] == 1


def test_un_fallo_en_correcta_tambien_marca_juez_fallo():
    s = puntuar_fila(fila(EXTRACTIVA, resp_extractiva(), BUSQUEDA, OBS_ANCLA),
                     juez=JuezFalso(respalda=True, correcta=None))
    assert s["juez_fallo"] is True and s["acierto"] is False


class _Agente:
    def invoke(self, *a, **k):
        return {"structured_response": Veredicto(razonamiento="x", etiquetas=["supported"])}


def _juez_sin_modelo(tmp_path):
    j = Juez.__new__(Juez)                     # sin crear_agente ni red
    j.modelo_id, j.ruta, j.cache = "m", tmp_path / "juez.json", {}
    j.agentes = {"respaldo": _Agente(), "correccion": _Agente()}
    j.llamadas, j.fallos, j.uso = 0, 0, {}
    return j


class _AgenteIntermitente:
    """Falla las `fallos_previos` primeras veces y después responde bien."""

    def __init__(self, fallos_previos: int):
        self.fallos_previos, self.invocaciones = fallos_previos, 0

    def invoke(self, *a, **k):
        self.invocaciones += 1
        if self.invocaciones <= self.fallos_previos:
            raise RuntimeError("corte transitorio del proveedor")
        return {"structured_response": Veredicto(razonamiento="x", etiquetas=["supported"])}


def test_el_juez_reintenta_un_veredicto_perdido_y_lo_cachea(tmp_path, monkeypatch):
    monkeypatch.setattr(evaluadores, "ESPERA_JUEZ_S", 0)
    j = _juez_sin_modelo(tmp_path)
    j.agentes["respaldo"] = _AgenteIntermitente(fallos_previos=1)      # cae una vez, luego responde
    assert j._preguntar("respaldo", "t") is not None                   # antes habría devuelto None
    assert j.llamadas == 2 and j.fallos == 0 and len(j.cache) == 1


def test_el_juez_se_rinde_tras_agotar_los_intentos_y_no_cachea_el_fallo(tmp_path, monkeypatch):
    monkeypatch.setattr(evaluadores, "ESPERA_JUEZ_S", 0)
    j = _juez_sin_modelo(tmp_path)
    j.agentes["respaldo"] = _AgenteIntermitente(fallos_previos=99)
    assert j._preguntar("respaldo", "t") is None                       # sigue contando como fallo
    assert j.llamadas == evaluadores.INTENTOS_JUEZ and j.fallos == 1 and j.cache == {}


def test_la_cache_del_juez_depende_del_hash_del_prompt(tmp_path, monkeypatch):
    j = _juez_sin_modelo(tmp_path)
    j._preguntar("respaldo", "t")
    j._preguntar("respaldo", "t")                                    # misma clave: caché
    assert j.llamadas == 1 and len(j.cache) == 1
    monkeypatch.setattr(evaluadores, "PROMPT_RESPALDO", evaluadores.PROMPT_RESPALDO + " Sé breve.")
    j._preguntar("respaldo", "t")                                    # prompt distinto: otra clave
    assert j.llamadas == 2 and len(j.cache) == 2
    assert Juez.huella_prompt("respaldo") != Juez.huella_prompt("correccion")


# ------------------------------------------------------ es_hueco (punto 8)
def test_numerica_con_concepto_existente_y_sin_cifra_no_es_hueco():
    p = {**NUMERICA, "cifra_esperada": None}
    assert es_hueco(p) is False                                      # el concepto SÍ está en XBRL
    s = puntuar_fila(fila(p, {"cifra": 44301e6, "unidad": "USD", "fuente": "xbrl"}, XBRL_OK))
    assert s["familia"] == "numerica" and s["b"] is True and s["acierto"] is True


def test_numerica_sin_concepto_ni_cifra_sigue_siendo_hueco():
    assert es_hueco({"familia": "numerica", "ticker": "NVDA", "fiscal_year": 2024,
                     "respuesta_esperada": "No está."}) is True
    assert es_hueco({**NUMERICA, "cifra_esperada": None, "concept_xbrl": "NoExiste"}) is True


# --------------------------------------------------- sin_referencia (punto 8)
CIEGA_NUM = {"id": "c1", "pregunta": "¿Beneficio bruto de NVIDIA en FY2024?", "familia": "numerica",
             "ticker": "NVDA", "fiscal_year": 2024}
CIEGA_EXT = {"id": "c2", "pregunta": "¿Cómo crecieron las ventas de AWS?", "familia": "extractiva",
             "ticker": "AMZN", "fiscal_year": 2025}


def test_ciega_numerica_se_verifica_contra_xbrl_sin_inventar_referencia():
    ok = puntuar_fila(fila(CIEGA_NUM, {"cifra": 44301e6, "unidad": "USD", "fuente": "xbrl",
                                        "ticker": "NVDA", "ejercicio": 2024,
                                        "concept_xbrl": "GrossProfit"}, XBRL_OK))
    assert ok["familia"] == "sin_referencia" and ok["acierto"] is None
    assert ok["b"] is None and ok["c"] is None                        # trayectoria: no se adivina
    assert ok["sr_cifra_xbrl"] is True and ok["verificacion"] is True
    assert ok["abstencion_indebida"] is False

    mal = puntuar_fila(fila(CIEGA_NUM, {"cifra": 99e9, "unidad": "USD", "fuente": "xbrl",
                                         "ticker": "NVDA", "ejercicio": 2024,
                                         "concept_xbrl": "GrossProfit"}, XBRL_OK))
    assert mal["sr_cifra_xbrl"] is False and mal["verificacion"] is False


def test_ciega_infiere_el_concepto_de_la_trayectoria_solo_si_es_unico():
    resp = {"cifra": 44301e6, "unidad": "USD", "fuente": "xbrl", "ticker": "NVDA", "ejercicio": 2024}
    s = puntuar_fila(fila(CIEGA_NUM, resp, XBRL_OK))
    assert s["sr_concepto"] == "GrossProfit" and s["sr_concepto_origen"] == "trayectoria"
    dos = XBRL_OK + [{"name": "get_xbrl_fact", "args": {"ticker": "NVDA", "fiscal_year": 2024,
                                                        "concept": "Revenues"}}]
    s = puntuar_fila(fila(CIEGA_NUM, resp, dos))
    assert s["sr_cifra_xbrl"] is None and s["sr_motivo"] == "sin_concepto"


def test_ciega_sin_cifra_no_verifica_ni_penaliza():
    s = puntuar_fila(fila(CIEGA_NUM, {"cifra": None, "fuente": "ninguna"}, XBRL_OK))
    assert s["sr_cifra_xbrl"] is None and s["abstiene"] is True and s["abstencion_indebida"] is False
    assert s["acierto"] is None


def test_ciega_extractiva_comprueba_cita_vista_y_coherencia():
    bueno = puntuar_fila(fila(CIEGA_EXT, resp_extractiva(), BUSQUEDA, OBS_ANCLA))
    assert bueno["a_existe"] and bueno["a_vista"] and bueno["coherencia_fuente"] is True
    assert bueno["verificacion"] is True and bueno["acierto"] is None
    inventada = puntuar_fila(fila(CIEGA_EXT, resp_extractiva(cita="Esta frase no existe en el 10-K de nadie."),
                                  BUSQUEDA, OBS_ANCLA))
    assert inventada["a_existe"] is False and inventada["verificacion"] is False
    incoherente = puntuar_fila(fila(CIEGA_EXT, resp_extractiva(fuente="xbrl", cita=None), [], []))
    assert incoherente["coherencia_fuente"] is False and incoherente["verificacion"] is False


def test_evaluar_de_ciegas_devuelve_tabla_util_y_resumen(tmp_path, monkeypatch):
    filas = [fila(CIEGA_NUM, {"cifra": 44301e6, "unidad": "USD", "fuente": "xbrl", "ticker": "NVDA",
                              "ejercicio": 2024, "concept_xbrl": "GrossProfit"}, XBRL_OK,
                  latencia_s=2.0, uso_mensajes={"total_tokens": 10}, n_llamadas=1),
             fila(CIEGA_EXT, resp_extractiva(), BUSQUEDA, OBS_ANCLA, latencia_s=3.0,
                  uso_mensajes={"total_tokens": 20}, n_llamadas=1)]
    golden = _preparar_predicciones(tmp_path, monkeypatch, filas)
    monkeypatch.setattr(evaluadores, "crear_juez", lambda *a, **k: pytest.fail("no hay nada que juzgar"))

    tabla = evaluacion.evaluar(golden, etiqueta="candidato_07", sistema="candidato_07")

    assert list(tabla["familia"]) == ["sin_referencia", "sin_referencia"]
    assert list(tabla["verificacion"]) == [True, True] and "sr_cifra_xbrl" in tabla.columns
    resumen = tabla.attrs["resumen"]
    assert resumen["sin_referencia"]["n"] == 2 and resumen["sin_referencia"]["verificacion"] == "2/2"
    assert resumen["parcial"] is False and resumen["n_no_evaluables"] == 0
    assert resumen["latencia_media_s"] == 2.5


# ------------------------------------------------- banderas diagnósticas (10)
def test_banderas_no_cambian_el_acierto_pero_marcan_laxitudes():
    resp = resp_extractiva(cita="Cuatro palabras nada más", ticker="MSFT", ejercicio=2024)
    s = puntuar_fila(fila(EXTRACTIVA, resp, BUSQUEDA, OBS_ANCLA))
    assert s["diag_cita_corta"] is True
    assert s["diag_ticker_distinto"] is True and s["diag_ejercicio_distinto"] is True
    assert acierto({**s, "a": True, "correcta_ok": True, "c": True}) is True      # la nota ni se mira


def test_banderas_de_comparativa_y_chunks():
    p = {"id": "k", "familia": "comparativa", "ticker": "NVDA", "fiscal_year": 2025,
         "cifra_esperada": 1.0, "concept_xbrl": "Revenues"}
    b = banderas_diagnosticas({"ticker": "NVDA", "ejercicio": 2025, "cifra_base": None,
                               "chunk_id": "NVDA-2024-7-0001",
                               "cita": "una frase suficientemente larga para pasar"}, p)
    assert b["diag_cifra_base_ausente"] is True and b["diag_cita_corta"] is False
    assert b["diag_chunk_otro_ejercicio"] is False      # 2024 es el ejercicio base permitido
    otro = banderas_diagnosticas({"ticker": "NVDA", "ejercicio": 2025, "cifra_base": 3.0,
                                  "chunk_id": "AAPL-2023-7-0001"}, p)
    assert otro["diag_cifra_base_ausente"] is False and otro["diag_chunk_inexistente"] is True
    assert otro["diag_chunk_otro_ejercicio"] is True and otro["diag_chunk_otra_empresa"] is True
    sin = banderas_diagnosticas({}, p)
    assert sin["diag_chunk_inexistente"] is None and sin["diag_cita_corta"] is None


# -------------------------------------------------- métricas operativas (7)
def test_metricas_operativas_mediana_p90_tokens_y_llamadas():
    filas = [{"latencia_s": float(x), "error": None, "n_llamadas": 1, "llamadas_modelo": 2,
              "uso_mensajes": {"input_tokens": 10 * x, "output_tokens": x, "total_tokens": 11 * x}}
             for x in range(1, 11)]
    filas.append({"latencia_s": 0.0, "error": "boom", "n_llamadas": 0, "uso_mensajes": {}})   # sin cronometrar

    m = metricas_operativas(filas)

    assert m["latencia_media_s"] == 5.5 and m["latencia_mediana_s"] == 5.5
    assert math.isclose(m["latencia_p90_s"], 9.1)                     # interpolación lineal
    assert m["tokens_medios"] == 60.5 and m["tokens_mediana"] == 60.5
    assert math.isclose(m["tokens_p90"], 100.1)
    assert m["tokens_entrada_medios"] == 55 and m["tokens_salida_medios"] == 5.5
    assert m["llamadas_modelo_medias"] == 2 and math.isclose(m["llamadas_medias"], 10 / 11)


def test_metricas_sin_filas_o_sin_datos_son_none():
    assert all(v is None for v in metricas_operativas([]).values())


def test_tabla_deriva_mediana_y_p90_de_un_resumen_antiguo(tmp_path, monkeypatch):
    """El baseline no guardó la mediana: la tabla la calcula desde predicciones.jsonl."""
    monkeypatch.setattr(config, "RESULTADOS", tmp_path)
    destino = tmp_path / "viejo"
    destino.mkdir()
    (destino / "resumen.json").write_text(json.dumps(
        {"n": 3, "familias": {}, "micro": 0.5, "latencia_media_s": 99.0}), encoding="utf-8")
    evaluadores._escribir_jsonl(destino / "predicciones.jsonl", [
        {"id": str(i), "latencia_s": float(i), "n_llamadas": 1,
         "uso_mensajes": {"input_tokens": 8, "output_tokens": 2, "total_tokens": 10}}
        for i in (1, 2, 3)])

    fila_t = evaluacion.tabla_comparativa(("viejo",)).iloc[0]

    assert fila_t["latencia_media_s"] == 99.0                          # lo guardado manda
    assert fila_t["latencia_mediana_s"] == 2.0 and math.isclose(fila_t["latencia_p90_s"], 2.8)
    assert fila_t["tokens_mediana"] == 10 and fila_t["tokens_entrada_medios"] == 8
    assert pd.notna(fila_t["tokens_p90"]) and pd.isna(fila_t["llamadas_modelo_medias"])
