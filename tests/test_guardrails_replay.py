"""Replays offline de los guardrails sobre las trazas guardadas (baseline y candidato_07, sin LLM ni red).

Cada fila de ``predicciones.jsonl`` se reconstruye como historial de mensajes (llamadas reales del modelo,
resultado determinista de get_xbrl_fact y observaciones numeradas como las vería el modelo) y se pasa por
el revisor SIN reintentos: es el peor caso, el que se daría si el modelo no corrigiera nada. Después se
re-puntúa con ``evaluadores.puntuar_fila`` vigente.

Qué demuestran: las invenciones se detectan, no hay falsos positivos sobre las respuestas buenas y la cita
que resolvería un modelo que eligiera bien los ids pasa la etapa 1 del evaluador (existe y fue vista). Qué NO
demuestran: que el modelo real elija bien los ids (eso solo se sabe con la API).
"""
import json
from pathlib import Path

import pytest
from langchain.messages import AIMessage, ToolMessage

from agente10k import config
from agente10k import guardrails as g
from agente10k.agente import RespuestaFinanciera
from agente10k.evaluadores import etapa1_cita, puntuar_fila
from agente10k.herramientas import get_xbrl_fact
from agente10k.normalizacion import cobertura, normalizar

CAMPOS = set(RespuestaFinanciera.model_fields)


def _filas(etiqueta: str) -> list[dict]:
    ruta = Path(config.RESULTADOS) / etiqueta / "predicciones.jsonl"
    if not ruta.is_file():
        pytest.skip(f"sin trazas guardadas de {etiqueta}")
    return [json.loads(x) for x in ruta.read_text(encoding="utf-8").splitlines() if x.strip()]


def _mensajes(fila: dict) -> list:
    """Historial equivalente al de la ejecución original, con las observaciones numeradas."""
    msgs, obs = [], list(fila.get("observaciones") or [])
    for llamada in fila["tool_calls"]:
        msgs.append(AIMessage(content="", tool_calls=[{"name": llamada["name"], "args": llamada["args"],
                                                       "id": llamada["id"]}]))
        if llamada["name"] == "get_xbrl_fact":
            msgs.append(ToolMessage(content=str(get_xbrl_fact.invoke(llamada["args"])), tool_call_id=llamada["id"],
                                    name="get_xbrl_fact"))
        elif llamada["name"] in g.TOOLS_TEXTO and obs:
            o = obs.pop(0)
            msgs.append(ToolMessage(content=g.numerar(o["content"], o["name"], g.siguiente_id(msgs)),
                                    tool_call_id=llamada["id"], name=o["name"], artifact=o["content"]))
    return msgs


def _respuesta(fila: dict, **cambios) -> RespuestaFinanciera:
    return RespuestaFinanciera(**({k: v for k, v in fila["respuesta"].items() if k in CAMPOS} | cambios))


def _revisar(fila: dict, **cambios):
    """(respuesta nueva, guard) sin reintentos; la fila re-puntuada con el evaluador vigente."""
    upd = g.GuardrailsFinal(max_reintentos=0).revisar({"messages": _mensajes(fila)}, _respuesta(fila, **cambios))
    nueva = upd["structured_response"]
    fila_nueva = dict(fila, respuesta=nueva.model_dump())
    return nueva, upd["guard"], puntuar_fila(fila, juez=None, estricto=False), puntuar_fila(fila_nueva, juez=None, estricto=False)


ETIQUETAS = ["baseline", "candidato_07"]


# ------------------------------------------------------------------ 0 falsos positivos bloqueantes
@pytest.mark.parametrize("etiqueta", ETIQUETAS)
def test_las_siete_numericas_correctas_siguen_siendo_aciertos(etiqueta):
    numericas = [f for f in _filas(etiqueta) if f["golden"]["familia"] == "numerica"]
    assert len(numericas) == 7
    for fila in numericas:
        nueva, guard, antes, despues = _revisar(fila)
        assert antes["acierto"] is True and despues["acierto"] is True, fila["id"]
        assert nueva.cifra == fila["respuesta"]["cifra"] and nueva.fuente == "xbrl", fila["id"]
        assert not guard["degradada"] and not guard["problemas"], (fila["id"], guard["problemas"])


@pytest.mark.parametrize("etiqueta", ETIQUETAS)
def test_comparativas_con_cifra_correcta_no_pierden_la_cifra(etiqueta):
    """La cifra buena de una comparativa nunca se degrada; las mal orientadas o vacías se recuperan del ledger."""
    for fila in (f for f in _filas(etiqueta) if f["golden"]["familia"] == "comparativa"):
        if fila.get("error"):
            continue                                            # g3-014 (candidato): sin structured_response
        nueva, guard, antes, despues = _revisar(fila)
        if antes["b"] is True:
            assert despues["b"] is True, (fila["id"], guard["problemas"])
        assert despues["c"] == antes["c"]                       # la trayectoria no se toca
        assert not any(c.startswith("cifra_de_dato_no_reportado") for c, _ in guard["problemas"]), fila["id"]


def test_baseline_cifras_de_comparativas_se_recuperan_del_ledger():
    """g3-018 (cifra vacía con fuente xbrl) y g3-020 (cifra y cifra_base invertidas) pasan a (b) correcto."""
    filas = {f["id"]: f for f in _filas("baseline")}
    _, guard, antes, despues = _revisar(filas["g3-018"])
    assert antes["b"] is False and despues["b"] is True
    assert {c for c, _ in guard["reparaciones"]} >= {"cifra_rellenada", "cifra_base_rellenada"}
    nueva, guard, antes, despues = _revisar(filas["g3-020"])
    assert antes["b"] is False and despues["b"] is True
    assert (nueva.cifra, nueva.ejercicio, nueva.cifra_base, nueva.ejercicio_base) == (2.97, 2025, 12.05, 2024)
    assert "orientacion_invertida" in {c for c, _ in guard["reparaciones"]}


# ------------------------------------------------------------------ invenciones detectadas
@pytest.mark.parametrize("etiqueta", ["baseline_huecos", "candidato_07_huecos"])
def test_huecos_con_cifras_derivadas_o_sumadas_se_degradan_y_puntuan_como_acierto(etiqueta):
    """h001/h002/h004/h005 (338.924, 81,66 %, 59,65 %...): fuente ninguna, sin cifra ni importes, sin reintento."""
    filas = _filas(etiqueta)
    inventadas = [f for f in filas if f["respuesta"]["cifra"] is not None]
    assert inventadas, "la traza debe conservar al menos una cifra inventada"
    for fila in filas:
        nueva, guard, antes, despues = _revisar(fila)
        assert despues["acierto"] is True, (fila["id"], nueva.respuesta)
        assert (nueva.fuente, nueva.cifra, nueva.cifra_base) == ("ninguna", None, None), fila["id"]
        assert g.extraer_cifras(nueva.respuesta) == []
        if fila["respuesta"]["cifra"] is not None:
            assert antes["acierto"] is False and guard["hueco"] is True
            assert any(c == "cifra_de_dato_no_reportado" for c, _ in guard["problemas"]), fila["id"]
            assert guard["reintentos"] == 0                     # ahorra la segunda vuelta: el dato no existe
            assert nueva.respuesta.startswith("No reportado en XBRL para ")


def test_huecos_del_candidato_los_cuatro_inventados_pasan_de_fallar_a_acertar():
    filas = {f["id"]: f for f in _filas("candidato_07_huecos")}
    for pid in ("g3-h001", "g3-h002", "g3-h004", "g3-h005"):
        _, _, antes, despues = _revisar(filas[pid])
        assert antes["acierto"] is False and despues["acierto"] is True, pid
    for pid in ("g3-h003", "g3-h006"):                          # las abstenciones correctas no se tocan
        _, guard, antes, despues = _revisar(filas[pid])
        assert antes["acierto"] is True and despues["acierto"] is True and not guard["degradada"], pid


def test_g3_010_concepto_inventado_y_cifras_sin_xbrl():
    fila = {f["id"]: f for f in _filas("candidato_07")}["g3-010"]
    assert fila["respuesta"]["concept_xbrl"] == "ForeignExchangeRateRisk" and fila["respuesta"]["cifra"] == 538.0
    nueva, guard, _, _ = _revisar(fila)
    assert nueva.concept_xbrl is None and nueva.cifra is None and nueva.cifra_base is None
    reparaciones = {c for c, _ in guard["reparaciones"]}
    assert {"concepto_anulado", "cifra_no_xbrl_anulada"} <= reparaciones
    assert nueva.fuente != "xbrl"


@pytest.mark.parametrize("etiqueta", ETIQUETAS)
def test_fuente_incoherente_con_la_trayectoria_queda_derivada_de_la_evidencia(etiqueta):
    """Antes: 8/20 (baseline) y 9/20 (candidato) con fuente incoherente. Ahora la fuente sale de la evidencia."""
    incoherentes_antes = incoherentes_despues = 0
    for fila in _filas(etiqueta):
        if fila.get("error"):
            continue
        nueva, guard, antes, despues = _revisar(fila)
        incoherentes_antes += antes["coherencia_fuente"] is False
        incoherentes_despues += despues["coherencia_fuente"] is False
        assert nueva.fuente == g.derivar_fuente(nueva.model_dump()), fila["id"]
    assert incoherentes_antes > 0 and incoherentes_despues == 0


def test_el_reintento_se_pide_solo_cuando_solo_el_modelo_puede_arreglarlo():
    """Con reintento disponible, las respuestas buenas y los huecos NO gastan una segunda vuelta."""
    mw = g.GuardrailsFinal(max_reintentos=1)
    for etiqueta in ("candidato_07", "candidato_07_huecos"):
        for fila in _filas(etiqueta):
            if fila.get("error"):
                continue
            upd = mw.revisar({"messages": _mensajes(fila)}, _respuesta(fila))
            pide = upd.get("jump_to") == "model"
            if fila["golden"]["familia"] == "numerica" or fila["id"].startswith("g3-h"):
                assert not pide, fila["id"]


# ------------------------------------------------------------------ la cita resuelta pasa la etapa 1 del evaluador
def _ids_para(fila: dict, msgs: list):
    """SOLO EN EL TEST: simula que el modelo eligiera la frase visible más parecida al ancla del golden."""
    idx = g.indice_frases(msgs)
    if not idx:
        return None
    return max(idx.values(), key=lambda f: cobertura(fila["golden"]["ancla_texto"], f.texto)).id


@pytest.mark.parametrize("etiqueta", ETIQUETAS)
def test_cita_resuelta_de_frase_ids_es_literal_existente_y_vista(etiqueta):
    filas = [f for f in _filas(etiqueta) if f["golden"]["familia"] in ("extractiva", "comparativa")]
    ancla_vista = [f for f in filas if normalizar(f["golden"]["ancla_texto"]) in normalizar(
        " ".join(o["content"] for o in f["observaciones"]))]
    assert len(ancla_vista) >= 8, "el ancla debe haberse visto en la mayoría (10/13 en lo medido)"
    for fila in ancla_vista:
        msgs = _mensajes(fila)
        ident = _ids_para(fila, msgs)
        fuente = "texto" if fila["golden"]["familia"] == "extractiva" else "ambas"
        upd = g.GuardrailsFinal(max_reintentos=0).revisar(
            {"messages": msgs}, _respuesta(fila, cita=None, chunk_id=None, frase_ids=[ident], fuente=fuente))
        nueva = upd["structured_response"]
        e1 = etapa1_cita(nueva.model_dump(), fila["golden"], fila["observaciones"])
        assert e1["a_cita"] and e1["a_existe"] and e1["a_vista"], (fila["id"], nueva.cita)
        assert e1["a_chunk_id_ok"], fila["id"]
        assert e1["a_cita_ancla"] >= 0.6, (fila["id"], e1["a_cita_ancla"])      # y es el pasaje del ancla
        assert all(len(p.split()) <= g.MAX_PALABRAS_PIEZA for p in nueva.cita.split(" [...] "))
        assert nueva.fuente in ("texto", "ambas")


@pytest.mark.parametrize("etiqueta", ETIQUETAS)
def test_numeracion_y_original_son_reversibles_sobre_las_trazas(etiqueta):
    """La numeración no parte anclas: cada frase numerada es literal del texto que se guarda en observaciones."""
    for fila in _filas(etiqueta):
        msgs = _mensajes(fila)
        original = normalizar(" ".join(o["content"] for o in fila.get("observaciones") or []))
        assert all(normalizar(f.texto) in original for f in g.indice_frases(msgs).values()), fila["id"]
        guardadas = g.observaciones_texto(msgs)
        assert [o["content"] for o in guardadas] == [o["content"] for o in fila.get("observaciones") or []]


def _golden(nombre: str) -> list[dict]:
    ruta = Path(config.GOLDEN) / nombre
    if not ruta.is_file():
        pytest.skip(f"sin {nombre}")
    return [json.loads(x) for x in ruta.read_text(encoding="utf-8").splitlines() if x.strip()]


def test_camino_rapido_solo_se_activa_en_las_numericas_de_una_cifra_y_en_los_huecos_simples():
    """Comprobación de que la heurística es conservadora: no corta extractivas ni comparativas."""
    def corta(p):
        h_ticker, h_fy = p["ticker"], p["fiscal_year"]
        concepto = p.get("concept_xbrl") or "GrossProfit"
        return (g.ticker_coherente(p["pregunta"], h_ticker) and g.ejercicio_coherente(p["pregunta"], h_fy)
                and g.concepto_coherente(p["pregunta"], concepto))

    propio = _golden("golden_propio.jsonl")
    for p in propio:
        if p["familia"] == "numerica":
            assert corta(p), p["id"]
        else:
            assert not corta(p), p["id"]                       # extractivas y comparativas siempre pasan por el modelo
    for p in _golden("golden_huecos.jsonl"):
        h_ok = g.ticker_coherente(p["pregunta"], p["ticker"]) and g.ejercicio_coherente(p["pregunta"], p["fiscal_year"]) \
            and g.concepto_coherente(p["pregunta"], p.get("concept_xbrl") or "GrossProfit", permitir_derivadas=True)
        assert h_ok or p["ticker"] not in g._EMPRESAS, p["id"]   # fuera de corpus (TSLA): nunca


def test_cita_del_modelo_sin_frase_ids_tambien_se_verifica_contra_las_observaciones():
    """Candidato g3-008: la cita del modelo (literal) se conserva; se le completa el chunk_id correcto."""
    fila = {f["id"]: f for f in _filas("candidato_07")}["g3-008"]
    assert fila["respuesta"]["cita"]
    nueva, guard, antes, despues = _revisar(fila)
    assert nueva.cita == fila["respuesta"]["cita"] and nueva.fuente == "texto"
    assert antes["a_existe"] and despues["a_existe"] and despues["a_vista"]
