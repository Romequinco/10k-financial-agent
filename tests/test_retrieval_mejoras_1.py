"""Mejoras del retrieval sin red, sin API y sin cargar BGE ni torch (codificador falso).

Cubre: equivalencia exacta de la búsqueda densa rápida con el bucle original, caché acotada, filtros con
listas, ``buscar_final`` (item blando, relajación), inferencia de filtros, ``precalentar`` y HF offline.
"""
import subprocess
import sys

import numpy as np
import pandas as pd
import pytest

from agente10k import config, retrieval


@pytest.fixture(autouse=True)
def limpiar_caches():
    retrieval._ranking_denso_completo.cache_clear()
    retrieval._cargar_bm25.cache_clear()
    retrieval._FILAS.clear()
    yield
    retrieval._ranking_denso_completo.cache_clear()
    retrieval._cargar_bm25.cache_clear()
    retrieval._FILAS.clear()


# --- búsqueda densa rápida == bucle original sobre el índice y los metadatos reales -------------------

class CodificadorDeCorpus:
    """Devuelve como 'consulta' el vector de un fragmento real, con ruido determinista."""

    def __init__(self, indice, fila, semilla):
        vector = indice.reconstruct(fila).astype("float64")
        vector = vector + np.random.default_rng(semilla).normal(0, 0.05, vector.shape)
        self.vector = (vector / np.linalg.norm(vector))[None, :]

    def encode(self, textos, **opciones):
        return self.vector


def referencia_original(indice, metadatos, vector, ticker, fiscal_year, item, k):
    """El bucle iloc/to_dict que había antes de la optimización (misma semántica)."""
    puntuaciones, posiciones = indice.search(vector, indice.ntotal)
    salida = []
    for puntuacion, posicion in zip(puntuaciones[0], posiciones[0]):
        if posicion < 0:
            continue
        fila = metadatos.iloc[int(posicion)]
        if ticker is not None and str(fila["ticker"]).upper() != ticker:
            continue
        if fiscal_year is not None and int(fila["fiscal_year"]) != fiscal_year:
            continue
        if item is not None and str(fila["item"]).upper() != item:
            continue
        resultado = fila.to_dict()
        resultado["puntuacion"] = float(puntuacion)
        salida.append(resultado)
        if len(salida) == k:
            break
    return salida


@pytest.mark.parametrize("filtros", [
    {}, {"ticker": "NVDA"}, {"ticker": "msft", "fiscal_year": 2025}, {"fiscal_year": 2024, "item": "Item 7"},
    {"ticker": "AAPL", "fiscal_year": 2025, "item": "1a"}, {"item": "8"},
])
def test_busqueda_densa_rapida_identica_al_bucle_original(monkeypatch, filtros):
    indice, metadatos = retrieval._leer_indice(), retrieval._leer_metadatos()
    codificador = CodificadorDeCorpus(indice, 17, semilla=3)
    monkeypatch.setattr(retrieval, "_cargar_recursos", lambda: (indice, metadatos, codificador))
    for k in (1, 5, 10, len(metadatos)):
        rapido = retrieval.buscar_denso("cualquier consulta", k=k, **filtros)
        esperado = referencia_original(
            indice, metadatos, np.asarray(codificador.vector, dtype="float32"),
            filtros["ticker"].upper() if "ticker" in filtros else None, filtros.get("fiscal_year"),
            retrieval._normalizar_item(filtros.get("item")), k)
        assert rapido == esperado
        assert all(isinstance(r["fiscal_year"], int) for r in rapido)


def test_ranking_denso_acotado_y_sin_fuga(monkeypatch):
    # Cada entrada guarda todos los fragmentos; con 512 entradas eran ~0,3 GB en una evaluación larga.
    assert retrieval._ranking_denso_completo.cache_info().maxsize <= 32
    llamadas = []
    monkeypatch.setattr(retrieval, "_leer_metadatos_cache", lambda: pd.DataFrame({"chunk_id": ["a", "b"]}))
    monkeypatch.setattr(retrieval, "buscar_denso", lambda q, k: llamadas.append(q) or [{"chunk_id": q}])
    for i in range(60):
        retrieval._ranking_denso_completo(f"consulta {i}")
    assert retrieval._ranking_denso_completo.cache_info().currsize <= 32
    retrieval._ranking_denso_completo("consulta 59")   # la más reciente sigue en caché
    assert len(llamadas) == 60


def test_filas_se_construyen_una_vez_por_dataframe(monkeypatch):
    meta = pd.DataFrame([{"chunk_id": "a", "ticker": "NVDA", "fiscal_year": 2025, "item": "7", "texto": "x"}])
    otra = meta.copy()
    contador = []
    original = pd.DataFrame.to_dict
    monkeypatch.setattr(pd.DataFrame, "to_dict", lambda self, *a, **kw: contador.append(1) or original(self, *a, **kw))
    for _ in range(3):   # la densa y la léxica alternan dos DataFrame iguales: no deben invalidarse entre sí
        retrieval._filas(meta)
        retrieval._filas(otra)
    assert len(contador) == 2


# --- corpus falso para la lógica de filtros y fusión ---------------------------------------------------

@pytest.fixture
def corpus(monkeypatch):
    filas = [
        ("a", "MSFT", 2025, "1A", "supply chain risk factors"), ("b", "MSFT", 2025, "7", "cloud demand growth"),
        ("c", "MSFT", 2024, "7", "cloud demand growth prior"), ("d", "MSFT", 2025, "8", "lease obligations"),
        ("e", "NVDA", 2025, "7", "data center revenue growth"), ("f", "NVDA", 2024, "7", "gaming revenue"),
        ("g", "NVDA", 2025, "7A", "interest rate risk"), ("h", "NVDA", 2025, "8", "revenue recognition"),
    ]
    meta = pd.DataFrame([{"chunk_id": c, "ticker": t, "fiscal_year": y, "item": i, "texto": x}
                         for c, t, y, i, x in filas])
    monkeypatch.setattr(retrieval, "_leer_metadatos_cache", lambda: meta)
    monkeypatch.setattr(retrieval, "_cargar_recursos", lambda: None)
    # Ranking denso falso y fijo: orden alfabético inverso (h primero).
    monkeypatch.setattr(retrieval, "buscar_denso", lambda q, k=None, **kw: [
        dict(r, puntuacion=1 - i / 10) for i, r in enumerate(meta.iloc[::-1].to_dict("records"))])
    return meta


def ids(resultados):
    return [d["chunk_id"] for d in resultados]


def test_candidatos_admite_listas_de_ejercicios_e_items(corpus):
    assert list(retrieval.candidatos("NVDA", [2024, 2025], ["7", "7A"])) == [4, 5, 6]
    assert list(retrieval.candidatos(None, 2025, "Item 7")) == [1, 4]
    assert list(retrieval.candidatos("nvidia", None, None)) == [4, 5, 6, 7]
    assert list(retrieval.candidatos(None, [], [])) == list(range(8))      # lista vacía = sin filtro


def test_buscar_final_sin_opciones_equivale_a_buscar_hibrido(corpus):
    assert retrieval.buscar_final("cloud", "MSFT", 2025, "7", 5) == retrieval.buscar_hibrido(
        ["cloud"], "MSFT", 2025, "7", 5)


def test_buscar_final_seleccionado_es_bm25_sin_item_ni_relajacion(corpus, monkeypatch):
    monkeypatch.setattr(retrieval, "buscar_denso", lambda *a, **kw: pytest.fail("No debe usar denso"))
    esperado = retrieval.buscar_bm25("cloud", "MSFT", 2025, k=5)
    assert ids(esperado) == ["b"]
    assert retrieval.buscar("cloud", "MSFT", 2025, "1A", 5,
                            item_blando=True, relajar=("item", "fy")) == esperado
    assert retrieval.buscar("cloud", "MSFT", [2024, 2025]) == retrieval.buscar_bm25(
        "cloud", "MSFT", [2024, 2025])
    assert retrieval.buscar("cloud", "MSFT", 2023) == []


def test_varios_ejercicios_forman_un_solo_ranking(corpus):
    resultado = retrieval.buscar_final("revenue growth", "NVDA", [2024, 2025], None, 10, item_blando=True)
    assert set(ids(resultado)) == {"e", "f", "g", "h"} and len(ids(resultado)) == 4
    assert {d["fiscal_year"] for d in resultado} == {2024, 2025}


def test_item_blando_sube_la_seccion_probable_sin_excluir_las_demas(corpus):
    duro = retrieval.buscar_final("revenue", "NVDA", 2025, ["7A"], 5, relajar=())
    assert ids(duro) == ["g"]
    blando = retrieval.buscar_final("interest rate risk", "NVDA", 2025, ["7A"], 5, item_blando=True)
    assert ids(blando)[0] == "g"                      # la sección probable va primero...
    assert set(ids(blando)) == {"e", "g", "h"}        # ...y las otras siguen disponibles


def test_relajacion_item_y_luego_ejercicio_marca_lo_relajado(corpus):
    # MSFT 2024 item 1A no tiene nada: primero se suelta el item, luego el ejercicio.
    r = retrieval.buscar_final("cloud", "MSFT", [2024], ["1A"], 4, relajar=("item", "fy"))
    assert ids(r)[0] == "c" and [d.get("relajado") for d in r] == ["item", "fy", "fy", "fy"]
    assert len(r) == 4 and {d["ticker"] for d in r} == {"MSFT"}            # la empresa nunca se relaja
    assert len({d["chunk_id"] for d in r}) == 4                             # sin repetidos
    sin_relajar = retrieval.buscar_final("cloud", "MSFT", [2024], ["1A"], 4, relajar=())
    assert sin_relajar == []                                               # lo explícito no se relaja solo


def test_relajar_solo_las_etapas_pedidas(corpus):
    solo_item = retrieval.buscar_final("cloud", "MSFT", [2024], ["1A"], 4, relajar=("item",))
    assert {d["fiscal_year"] for d in solo_item} == {2024} and {d.get("relajado") for d in solo_item} == {"item"}
    assert [d["chunk_id"] for d in solo_item] == ["c"]                     # solo hay un fragmento MSFT 2024


def test_buscar_es_determinista(corpus):
    primero = retrieval.buscar_final("cloud growth", "MSFT", [2024, 2025], ["7", "8"], 5, item_blando=True,
                                     relajar=("item", "fy"))
    retrieval._ranking_denso_completo.cache_clear()
    assert retrieval.buscar_final("cloud growth", "MSFT", [2024, 2025], ["7", "8"], 5, item_blando=True,
                                  relajar=("item", "fy")) == primero


def test_buscar_final_valida_entradas(corpus):
    with pytest.raises(ValueError, match="query"):
        retrieval.buscar_final("  ")
    with pytest.raises(TypeError, match="k"):
        retrieval.buscar_final("x", k=2.5)
    with pytest.raises(ValueError, match="modo"):
        retrieval.buscar("x", modo="otro")


# --- inferencia de filtros ------------------------------------------------------------------------------

@pytest.mark.parametrize("pregunta, esperado", [
    ("¿Qué riesgos de ciberseguridad menciona Meta en FY2025?", ("META", (2025,), ("1A",))),
    ("Compara los gastos de Microsoft entre FY2024 y 2025 y explica las razones", ("MSFT", (2024, 2025), ("7", "8"))),
    ("How does Alphabet manage foreign exchange risk in fiscal 2024?", ("GOOGL", (2024,), ("7A", "7"))),
    ("¿Qué política contable sigue Apple para reconocer ingresos, según las notas?", ("AAPL", (), ("8", "7"))),
    ("Ventas de AWS en FY25 según el item 7A", ("AMZN", (2025,), ("7A",))),
    ("Explica el margen de NVIDIA en el ejercicio FY 2024", ("NVDA", (2024,), ("7", "8"))),
    ("Riesgos de Facebook e Instagram", ("META", (), ("1A",))),
])
def test_inferir_filtros(pregunta, esperado):
    r = retrieval.inferir_filtros(pregunta)
    assert (r["ticker"], r["fiscal_years"], r["items"]) == esperado


@pytest.mark.parametrize("pregunta", [
    "Apple risks FY24/25", "Apple 2024/25 revenue", "Apple fiscal 2024-25 results", "ingresos de Apple 2024–25",
    "Apple FY2024/FY25", "Apple 2024 y 2025",
])
def test_inferir_rango_abreviado_incluye_ambos_ejercicios(pregunta):
    assert retrieval.inferir_filtros(pregunta)["fiscal_years"] == (2024, 2025)


def test_inferir_rango_no_confunde_fechas_ni_otros_anios():
    assert retrieval.inferir_filtros("quarter ended 2024-06")["fiscal_years"] == (2024,)
    assert retrieval.inferir_filtros("plan 2025-26")["fiscal_years"] == (2025,)
    assert retrieval.inferir_filtros("el 24/25 de mayo")["fiscal_years"] == ()


def test_inferir_no_afirma_lo_que_es_ambiguo():
    r = retrieval.inferir_filtros("Compara Apple y Microsoft")
    assert r == {"ticker": None, "fiscal_years": (), "items": ()}
    # "meta" en minúscula es la palabra española; 25 y 24 sueltos no son ejercicios; 2023 no está en el corpus.
    r = retrieval.inferir_filtros("Una meta de crecimiento del 25 % en 24 meses desde 2023")
    assert r["ticker"] is None and r["fiscal_years"] == ()
    assert retrieval.inferir_filtros("") == {"ticker": None, "fiscal_years": (), "items": ()}
    assert retrieval.inferir_filtros(None)["ticker"] is None


def test_inferir_nunca_inventa_tickers_ni_ejercicios_fuera_del_corpus():
    for pregunta in ("¿Qué dice Tesla en 2023?", "Riesgos de Oracle FY2026", "quarter ended 2024-06"):
        r = retrieval.inferir_filtros(pregunta)
        assert r["ticker"] is None and set(r["fiscal_years"]) <= {2024, 2025}


def test_filtros_explicitos_previos_no_cambian():
    assert retrieval.filtros_explicitos("Riesgos de NVIDIA FY2025") == {"ticker": "NVDA", "fiscal_years": [2025]}


# --- precalentar ---------------------------------------------------------------------------------------

def test_precalentar_es_idempotente_y_solo_carga_bm25(monkeypatch):
    llamadas = []
    monkeypatch.setattr(retrieval, "_PRECALENTADO", False)
    monkeypatch.setattr(retrieval, "_cargar_recursos", lambda: pytest.fail("No debe cargar embeddings"))
    monkeypatch.setattr(retrieval, "_cargar_bm25", lambda: llamadas.append(1))
    retrieval.precalentar()
    retrieval.precalentar()
    assert llamadas == [1]


def test_precalentar_desde_varios_hilos_carga_una_vez(monkeypatch):
    import threading
    import time
    cargas = []
    monkeypatch.setattr(retrieval, "_PRECALENTADO", False)
    monkeypatch.setattr(retrieval, "_cargar_recursos", lambda: pytest.fail("No debe cargar embeddings"))
    monkeypatch.setattr(retrieval, "_cargar_bm25", lambda: (time.sleep(0.05), cargas.append(1)))
    hilos = [threading.Thread(target=retrieval.precalentar) for _ in range(4)]
    [h.start() for h in hilos]
    [h.join() for h in hilos]
    assert cargas == [1]


# --- HF offline por defecto cuando BGE ya está en caché -----------------------------------------------

def crear_cache_hf(raiz, completo=True):
    snap = raiz / "models--BAAI--bge-small-en-v1.5" / "snapshots" / "abc123"
    snap.mkdir(parents=True)
    (snap / "config.json").write_text("{}")
    if completo:
        (snap / "modules.json").write_text("[]")


def test_modelo_en_cache_hf(tmp_path, monkeypatch):
    monkeypatch.setenv("HF_HUB_CACHE", str(tmp_path))
    assert not config._modelo_en_cache_hf(config.MODELO_EMBEDDINGS)
    crear_cache_hf(tmp_path, completo=False)
    assert not config._modelo_en_cache_hf(config.MODELO_EMBEDDINGS)         # descarga a medias: no se fuerza
    (tmp_path / "models--BAAI--bge-small-en-v1.5" / "snapshots" / "abc123" / "modules.json").write_text("[]")
    assert config._modelo_en_cache_hf(config.MODELO_EMBEDDINGS)
    assert not config._modelo_en_cache_hf("otro/modelo")


def _importar_config(entorno):
    codigo = "import os, agente10k.config; print(os.environ.get('HF_HUB_OFFLINE'))"
    import os
    entorno = {**{k: v for k, v in os.environ.items() if k != "HF_HUB_OFFLINE"}, **entorno}
    salida = subprocess.run([sys.executable, "-c", codigo], env=entorno, capture_output=True, text=True, timeout=60)
    assert salida.returncode == 0, salida.stderr
    return salida.stdout.strip()


def test_hf_offline_solo_si_esta_en_cache_y_sin_pisar_al_usuario(tmp_path):
    con_cache, sin_cache = tmp_path / "cache_completa", tmp_path / "cache_vacia"   # "con" es un nombre reservado en Windows
    crear_cache_hf(con_cache)
    sin_cache.mkdir()
    assert _importar_config({"HF_HUB_CACHE": str(con_cache), "PYTHONPATH": str(config.RAIZ / "src")}) == "1"
    assert _importar_config({"HF_HUB_CACHE": str(sin_cache), "PYTHONPATH": str(config.RAIZ / "src")}) == "None"
    assert _importar_config({"HF_HUB_CACHE": str(con_cache), "HF_HUB_OFFLINE": "0",
                             "PYTHONPATH": str(config.RAIZ / "src")}) == "0"
