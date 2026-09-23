"""Manifest, sistema `final`, reanudación y legacy: todo offline con dobles del agente."""
from __future__ import annotations

import json
import time

import pandas as pd
import pytest

from agente10k import agente, config, evaluacion, evaluadores, guardrails

ESTADO_A = {"commit": "aaaaaaa", "dirty": False, "diff_sha256": "0" * 64}
ESTADO_B = {"commit": "bbbbbbb", "dirty": True, "diff_sha256": "f" * 64}

PREGUNTAS = [
    {"id": "t1", "pregunta": "¿Cuál fue el beneficio bruto de NVDA en FY2024?", "familia": "numerica",
     "ticker": "NVDA", "fiscal_year": 2024, "cifra_esperada": 44301000000.0, "unidad": "USD",
     "concept_xbrl": "GrossProfit", "herramienta_esperada": ["get_xbrl_fact"]},
    {"id": "t2", "pregunta": "¿Cuál fue el pasivo de NVDA en FY2025?", "familia": "numerica",
     "ticker": "NVDA", "fiscal_year": 2025, "cifra_esperada": 32274000000.0, "unidad": "USD",
     "concept_xbrl": "Liabilities", "herramienta_esperada": ["get_xbrl_fact"]},
    {"id": "t3", "pregunta": "¿Y el de MSFT en FY2025?", "familia": "numerica",
     "ticker": "MSFT", "fiscal_year": 2025, "cifra_esperada": 1.0, "unidad": "USD",
     "concept_xbrl": None, "herramienta_esperada": ["get_xbrl_fact"]},
]


@pytest.fixture
def entorno(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "RESULTADOS", tmp_path / "resultados")
    monkeypatch.setattr(evaluadores, "_estado_git", lambda: dict(ESTADO_A))
    golden = tmp_path / "golden.jsonl"
    golden.write_text("".join(json.dumps(p) + "\n" for p in PREGUNTAS), encoding="utf-8")
    return golden


class Corte(BaseException):
    """Simula un Ctrl+C: no es Exception, así que ejecutar_golden no lo captura."""


def _respuesta(pregunta):
    return {"respuesta": {"respuesta": "x", "cifra": 1.0, "unidad": "USD", "fuente": "xbrl"},
            "tool_calls": [{"name": "get_xbrl_fact", "args": {}}], "observaciones": [],
            "latencia_s": 1.5, "uso_mensajes": {"input_tokens": 10, "output_tokens": 5,
                                                "total_tokens": 15},
            "usd_openrouter": None, "modelo_real": config.MODELO_ID, "n_llamadas": 1,
            "llamadas_modelo": 2, "error": None}


# ------------------------------------------------------------- validar_manifest
def test_manifest_solo_bloquea_lo_que_cambia_el_resultado():
    base = {"version": 1, "golden_sha256": "g", "sistema": "baseline", "modelo": "m", "limite": None,
            "retrieval": {"backend": "denso"}, **ESTADO_A}
    assert evaluadores.validar_manifest(base, {**base, **ESTADO_B}) == []      # commit/dirty/diff: no bloquean
    assert evaluadores.avisos_manifest(base, {**base, **ESTADO_B})             # pero avisan
    for campo, valor in (("golden_sha256", "otro"), ("sistema", "final"), ("modelo", "otro"),
                         ("limite", 3), ("retrieval", {"backend": "hibrido"})):
        assert evaluadores.validar_manifest(base, {**base, campo: valor}) == [campo]


# ------------------------------------------------ evaluar reutiliza sin API
def test_evaluar_reutiliza_predicciones_con_manifest_sin_api(entorno, monkeypatch):
    """Antes de este cambio el test daba por bueno un predicciones.jsonl SIN manifest: eso es
    justo lo que evaluar() rechaza (legacy). Se reutiliza cuando hay manifest compatible."""
    destino = config.RESULTADOS / "candidato_07"
    destino.mkdir(parents=True)
    (destino / "predicciones.jsonl").write_text(json.dumps({"id": "t1"}) + "\n", encoding="utf-8")
    manifest = evaluadores.manifest_ejecucion(entorno, "candidato_07")
    (destino / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setattr(evaluadores, "ejecutar_golden",
                        lambda *a, **k: pytest.fail("no debe ejecutar la API si ya hay predicciones"))
    monkeypatch.setattr(evaluadores, "puntuar", lambda etiqueta: pd.DataFrame({"id": [etiqueta]}))

    tabla = evaluacion.evaluar(entorno, etiqueta="candidato_07", sistema="candidato_07")

    assert tabla.iloc[0]["id"] == "candidato_07"
    assert tabla.attrs["aviso"] is None


def test_evaluar_con_otro_commit_reutiliza_y_avisa(entorno, monkeypatch):
    destino = config.RESULTADOS / "candidato_07"
    destino.mkdir(parents=True)
    (destino / "predicciones.jsonl").write_text(json.dumps({"id": "t1"}) + "\n", encoding="utf-8")
    manifest = evaluadores.manifest_ejecucion(entorno, "candidato_07")
    (destino / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setattr(evaluadores, "_estado_git", lambda: dict(ESTADO_B))       # el árbol cambió
    monkeypatch.setattr(evaluadores, "puntuar", lambda etiqueta: pd.DataFrame({"id": [etiqueta]}))

    with pytest.warns(UserWarning, match="otro estado del código"):
        tabla = evaluacion.evaluar(entorno, etiqueta="candidato_07", sistema="candidato_07")

    assert "commit" in tabla.attrs["aviso"]


def test_evaluar_rechaza_otro_golden_o_sistema(entorno, monkeypatch, tmp_path):
    destino = config.RESULTADOS / "x"
    destino.mkdir(parents=True)
    (destino / "predicciones.jsonl").write_text("{}\n", encoding="utf-8")
    (destino / "manifest.json").write_text(
        json.dumps(evaluadores.manifest_ejecucion(entorno, "candidato_07")), encoding="utf-8")
    otro = tmp_path / "otro.jsonl"
    otro.write_text(json.dumps(PREGUNTAS[0]) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="golden_sha256"):
        evaluacion.evaluar(otro, etiqueta="x", sistema="candidato_07")
    with pytest.raises(ValueError, match="sistema"):
        evaluacion.evaluar(entorno, etiqueta="x", sistema="baseline")


def test_evaluar_rechaza_predicciones_legacy_sin_manifest_y_apunta_a_bendecir(entorno):
    destino = config.RESULTADOS / "baseline"
    destino.mkdir(parents=True)
    (destino / "predicciones.jsonl").write_text("{}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="bendecir_legacy"):
        evaluacion.evaluar(entorno, etiqueta="baseline", sistema="baseline")


# ------------------------------------------------------------ sistema `final`
def test_final_falla_antes_de_crear_artefactos_si_faltan_guardrails(entorno, monkeypatch):
    def sin_06():
        raise NotImplementedError("TODO")

    monkeypatch.setattr(guardrails, "middleware_final", sin_06)
    monkeypatch.setattr(agente, "ejecutar", lambda *a, **k: pytest.fail("no debe llamar al agente"))

    with pytest.raises(agente.SistemaFinalNoDisponible):
        evaluacion.evaluar(entorno, etiqueta="final", sistema="final")
    with pytest.raises(agente.SistemaFinalNoDisponible):
        evaluadores.ejecutar_golden(entorno, "final", sistema="final")

    assert not (config.RESULTADOS / "final").exists()
    assert not config.RESULTADOS.exists() or not any(config.RESULTADOS.iterdir())


def test_final_se_deja_montar_cuando_hay_pila_de_guardrails(entorno, monkeypatch):
    """La validación no depende del estado actual: con una pila real, ejecuta normalmente."""
    monkeypatch.setattr(guardrails, "middleware_final", lambda: [object()])
    monkeypatch.setattr(agente, "ejecutar", lambda pregunta, sistema, modelo=None: _respuesta(pregunta))

    ruta = evaluadores.ejecutar_golden(entorno, "final", sistema="final")

    assert ruta == config.RESULTADOS / "final" / "predicciones.jsonl"
    assert json.loads((ruta.parent / "manifest.json").read_text())["sistema"] == "final"


def test_cli_devuelve_error_explicito_con_final_no_disponible(entorno, monkeypatch, capsys):
    from agente10k.__main__ import main

    def no_disponible(*a, **k):
        raise agente.SistemaFinalNoDisponible("falta el 06")

    monkeypatch.setattr(evaluacion, "evaluar", no_disponible)
    assert main([str(entorno), "--sistema", "final"]) == 2
    assert "falta el 06" in capsys.readouterr().err


def test_cli_imprime_la_tabla_y_el_aviso(entorno, monkeypatch, capsys):
    from agente10k.__main__ import main

    tabla = pd.DataFrame({"id": ["t1"], "familia": ["numerica"], "acierto": [True], "extra": [1]})
    tabla.attrs["aviso"] = "resultado PARCIAL"
    monkeypatch.setattr(evaluacion, "evaluar", lambda *a, **k: tabla)
    assert main([str(entorno), "--sistema", "candidato_07", "--sin-juez"]) == 0
    salida = capsys.readouterr()
    assert "t1" in salida.out and "extra" not in salida.out and "PARCIAL" in salida.err


def test_sistema_desconocido_falla_antes_de_ejecutar(entorno):
    with pytest.raises(ValueError, match="Sistema desconocido"):
        evaluadores.ejecutar_golden(entorno, "x", sistema="basline")
    assert not config.RESULTADOS.exists()


# ------------------------------------------------- persistencia y reanudación
def test_persistencia_fila_a_fila_y_reanudacion_por_id(entorno, monkeypatch):
    ejecutadas = []

    def cortando(pregunta, sistema, modelo=None):
        ejecutadas.append(pregunta)
        if len(ejecutadas) == 2:
            raise Corte()
        return _respuesta(pregunta)

    monkeypatch.setattr(agente, "ejecutar", cortando)
    with pytest.raises(Corte):
        evaluadores.ejecutar_golden(entorno, "b", sistema="baseline")

    destino = config.RESULTADOS / "b"
    parcial = evaluadores._leer_jsonl(destino / evaluadores.ARCHIVO_PARCIAL)
    assert [f["id"] for f in parcial] == ["t1"]                    # lo hecho no se perdió
    assert not (destino / "predicciones.jsonl").exists()           # y no se publica a medias

    ejecutadas.clear()
    monkeypatch.setattr(agente, "ejecutar", lambda pregunta, sistema, modelo=None:
                        ejecutadas.append(pregunta) or _respuesta(pregunta))
    ruta = evaluadores.ejecutar_golden(entorno, "b", sistema="baseline")

    assert ejecutadas == [PREGUNTAS[1]["pregunta"], PREGUNTAS[2]["pregunta"]]   # t1 no se repite
    assert [f["id"] for f in evaluadores._leer_jsonl(ruta)] == ["t1", "t2", "t3"]
    assert not (destino / evaluadores.ARCHIVO_PARCIAL).exists()
    assert not (destino / evaluadores.MANIFEST_PARCIAL).exists()
    assert (destino / "manifest.json").is_file()


def test_reanudar_valida_el_manifest(entorno, monkeypatch):
    def cortando(pregunta, sistema, modelo=None):
        raise Corte()

    monkeypatch.setattr(agente, "ejecutar", cortando)
    with pytest.raises(Corte):
        evaluadores.ejecutar_golden(entorno, "b", sistema="baseline")
    monkeypatch.setattr(agente, "ejecutar", lambda *a, **k: pytest.fail("no debe ejecutar"))

    with pytest.raises(ValueError, match="sistema"):
        evaluadores.ejecutar_golden(entorno, "b", sistema="candidato_07")
    with pytest.raises(ValueError, match="limite"):
        evaluadores.ejecutar_golden(entorno, "b", sistema="baseline", limite=2)


def test_reanudar_reintenta_filas_con_error_y_mide_latencia_de_los_errores(entorno, monkeypatch):
    def rota(pregunta, sistema, modelo=None):
        time.sleep(0.01)
        raise RuntimeError("red muerta")

    monkeypatch.setattr(agente, "ejecutar", rota)
    ruta = evaluadores.ejecutar_golden(entorno, "e", sistema="baseline")
    filas = evaluadores._leer_jsonl(ruta)
    assert all(f["error"] and f["latencia_s"] >= 0.01 for f in filas)   # no 0.0

    # Tanda parcial con una fila con error y otra buena: la mala se reintenta al reanudar.
    destino = config.RESULTADOS / "r"
    destino.mkdir(parents=True)
    manifest = evaluadores.manifest_ejecucion(entorno, "baseline")
    (destino / evaluadores.MANIFEST_PARCIAL).write_text(json.dumps(manifest), encoding="utf-8")
    bueno = {"id": "t1", "golden": PREGUNTAS[0], "respuesta": {}, "error": None, "latencia_s": 1.0}
    malo = {"id": "t2", "golden": PREGUNTAS[1], "respuesta": {}, "error": "boom", "latencia_s": 1.0}
    evaluadores._escribir_jsonl(destino / evaluadores.ARCHIVO_PARCIAL, [bueno, malo])
    pedidas = []
    monkeypatch.setattr(agente, "ejecutar", lambda pregunta, sistema, modelo=None:
                        pedidas.append(pregunta) or _respuesta(pregunta))
    evaluadores.ejecutar_golden(entorno, "r", sistema="baseline")
    assert pedidas == [PREGUNTAS[1]["pregunta"], PREGUNTAS[2]["pregunta"]]


def test_solo_se_reintenta_el_fallo_de_infraestructura_y_sigue_contando(entorno, monkeypatch):
    monkeypatch.setattr(evaluadores, "ESPERA_REINTENTO_FILA_S", 0)
    intentos = {}

    def proveedor_caprichoso(pregunta, sistema, modelo=None):
        n = intentos[pregunta] = intentos.get(pregunta, 0) + 1
        if pregunta == PREGUNTAS[0]["pregunta"] and n == 1:
            return {"respuesta": {}, "error": "PlazoAgotado: plazo de 300 s agotado"}   # se reintenta
        if pregunta == PREGUNTAS[1]["pregunta"]:
            return {"respuesta": {}, "error": "sin structured_response"}                # NO se reintenta
        return _respuesta(pregunta)

    monkeypatch.setattr(agente, "ejecutar", proveedor_caprichoso)
    filas = {f["id"]: f for f in evaluadores._leer_jsonl(
        evaluadores.ejecutar_golden(entorno, "reint", sistema="baseline"))}

    assert intentos[PREGUNTAS[0]["pregunta"]] == 2 and not filas["t1"]["error"]  # el plazo se reintentó
    assert intentos[PREGUNTAS[1]["pregunta"]] == 1                               # la mala respuesta, no
    assert filas["t2"]["error"] == "sin structured_response"                     # y sigue en la tabla
    assert len(filas) == len(PREGUNTAS)                                          # nadie sale del denominador


def test_el_reintento_se_rinde_y_la_fila_queda_como_fallo(entorno, monkeypatch):
    monkeypatch.setattr(evaluadores, "ESPERA_REINTENTO_FILA_S", 0)
    llamadas = []
    monkeypatch.setattr(agente, "ejecutar", lambda pregunta, sistema, modelo=None:
                        llamadas.append(pregunta) or {"respuesta": {}, "error": "429 rate limit"})
    filas = evaluadores._leer_jsonl(evaluadores.ejecutar_golden(entorno, "rendido", sistema="baseline"))
    assert len(llamadas) == evaluadores.INTENTOS_FILA * len(PREGUNTAS)
    assert len(filas) == len(PREGUNTAS) and all(f["error"] for f in filas)


def test_una_tanda_completa_anterior_sobrevive_a_un_corte(entorno, monkeypatch):
    destino = config.RESULTADOS / "c"
    destino.mkdir(parents=True)
    (destino / "predicciones.jsonl").write_text('{"id": "viejo"}\n', encoding="utf-8")

    def cortando(pregunta, sistema, modelo=None):
        raise Corte()

    monkeypatch.setattr(agente, "ejecutar", cortando)
    with pytest.raises(Corte):
        evaluadores.ejecutar_golden(entorno, "c", sistema="baseline", reanudar=False)

    assert (destino / "predicciones.jsonl").read_text(encoding="utf-8") == '{"id": "viejo"}\n'


def test_se_guardan_llamadas_al_modelo_y_tokens(entorno, monkeypatch):
    monkeypatch.setattr(agente, "ejecutar", lambda pregunta, sistema, modelo=None: _respuesta(pregunta))
    fila = evaluadores._leer_jsonl(evaluadores.ejecutar_golden(entorno, "m", sistema="baseline"))[0]
    assert fila["llamadas_modelo"] == 2 and fila["uso_mensajes"]["total_tokens"] == 15


# ---------------------------------------------------------- bendecir_legacy
def _legacy(entorno, etiqueta="baseline"):
    destino = config.RESULTADOS / etiqueta
    destino.mkdir(parents=True)
    filas = [{"id": p["id"], "golden": p, "respuesta": {}, "tool_calls": [], "observaciones": [],
              "modelo_real": config.MODELO_ID.removeprefix("openrouter:")} for p in PREGUNTAS]
    evaluadores._escribir_jsonl(destino / "predicciones.jsonl", filas)
    (destino / "resumen.json").write_text(json.dumps({"commit": "bb24fb4"}), encoding="utf-8")
    return destino


def test_bendecir_legacy_solo_escribe_manifest_y_luego_evaluar_reutiliza(entorno, monkeypatch):
    destino = _legacy(entorno)
    antes = {f.name: f.read_bytes() for f in destino.iterdir()}

    ruta = evaluadores.bendecir_legacy("baseline", entorno, "baseline")

    despues = {f.name: f.read_bytes() for f in destino.iterdir()}
    assert set(despues) - set(antes) == {"manifest.json"}
    assert all(despues[k] == v for k, v in antes.items())              # nada más se tocó
    manifest = json.loads(ruta.read_text(encoding="utf-8"))
    assert manifest["legacy"] is True and manifest["commit"] == "bb24fb4"

    monkeypatch.setattr(evaluadores, "ejecutar_golden", lambda *a, **k: pytest.fail("API"))
    monkeypatch.setattr(evaluadores, "puntuar", lambda etiqueta: pd.DataFrame({"id": [etiqueta]}))
    with pytest.warns(UserWarning, match="legacy"):
        evaluacion.evaluar(entorno, etiqueta="baseline", sistema="baseline")


def test_bendecir_legacy_no_sobrescribe_ni_bendice_otro_golden(entorno, tmp_path):
    _legacy(entorno)
    otro = tmp_path / "otro.jsonl"
    otro.write_text(json.dumps(PREGUNTAS[0]) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="no coincide"):
        evaluadores.bendecir_legacy("baseline", otro, "baseline")
    evaluadores.bendecir_legacy("baseline", entorno, "baseline")
    with pytest.raises(FileExistsError):
        evaluadores.bendecir_legacy("baseline", entorno, "baseline")


def test_bendecir_legacy_rechaza_modelo_distinto(entorno):
    destino = _legacy(entorno)
    filas = evaluadores._leer_jsonl(destino / "predicciones.jsonl")
    for f in filas:
        f["modelo_real"] = "otro/modelo"
    evaluadores._escribir_jsonl(destino / "predicciones.jsonl", filas)
    with pytest.raises(ValueError, match="modelo real"):
        evaluadores.bendecir_legacy("baseline", entorno, "baseline")


def test_ejecutar_golden_no_sobrescribe_un_baseline_congelado(entorno, monkeypatch):
    destino = config.RESULTADOS / "baseline_huecos"
    destino.mkdir(parents=True)
    (destino / "predicciones.jsonl").write_text("CONGELADO\n", encoding="utf-8")
    monkeypatch.setattr(agente, "ejecutar", lambda *a, **k: pytest.fail("no debe llamar al agente"))
    with pytest.raises(FileExistsError, match="congelado"):
        evaluadores.ejecutar_golden(entorno, "baseline_huecos", sistema="baseline")
    assert (destino / "predicciones.jsonl").read_text(encoding="utf-8") == "CONGELADO\n"
    assert sorted(p.name for p in destino.iterdir()) == ["predicciones.jsonl"]


def test_evaluar_avisa_si_hay_filas_con_error_o_fallos_del_juez(entorno, monkeypatch):
    destino = config.RESULTADOS / "candidato_07"
    destino.mkdir(parents=True)
    (destino / "predicciones.jsonl").write_text(json.dumps({"id": "t1"}) + "\n", encoding="utf-8")
    (destino / "manifest.json").write_text(
        json.dumps(evaluadores.manifest_ejecucion(entorno, "candidato_07")), encoding="utf-8")

    def puntuar(etiqueta, **kwargs):
        (destino / "resumen.json").write_text(json.dumps(
            {"n": 20, "errores": 10, "juez_fallos_filas": 2, "micro": 0.2}), encoding="utf-8")
        return pd.DataFrame({"id": ["t1"]})

    monkeypatch.setattr(evaluadores, "puntuar", puntuar)
    with pytest.warns(UserWarning, match="10 de 20 filas terminaron con error"):
        tabla = evaluacion.evaluar(entorno, etiqueta="candidato_07", sistema="candidato_07", con_juez=False)
    assert "El juez falló en 2 filas" in tabla.attrs["aviso"]
