"""Pruebas unitarias del retrieval denso baseline, sin descargar modelos."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from agente10k import retrieval


class IndiceFalso:
    def __init__(self, puntuaciones, posiciones):
        self._puntuaciones = np.asarray([puntuaciones], dtype="float32")
        self._posiciones = np.asarray([posiciones], dtype="int64")
        self.ntotal = len(posiciones)
        self.ultima_consulta = None
        self.ultimo_k = None

    def search(self, consulta, k):
        self.ultima_consulta = consulta
        self.ultimo_k = k
        return self._puntuaciones, self._posiciones


class CodificadorFalso:
    def __init__(self):
        self.textos = None
        self.opciones = None

    def encode(self, textos, **opciones):
        self.textos = textos
        self.opciones = opciones
        return np.array([[1, 2, 3]], dtype="float64")


@pytest.fixture(autouse=True)
def limpiar_cache():
    retrieval._cargar_recursos.cache_clear()
    yield
    retrieval._cargar_recursos.cache_clear()


@pytest.fixture
def metadatos():
    return pd.DataFrame(
        [
            {"chunk_id": "NVDA-2024-7-0000", "ticker": "NVDA", "fiscal_year": 2024,
             "item": "7", "texto": "NVIDIA 2024"},
            {"chunk_id": "MSFT-2025-1A-0001", "ticker": "MSFT", "fiscal_year": 2025,
             "item": "1A", "texto": "Microsoft riesgo"},
            {"chunk_id": "MSFT-2025-1A-0002", "ticker": "MSFT", "fiscal_year": 2025,
             "item": "1A", "texto": "Microsoft IA"},
            {"chunk_id": "MSFT-2024-1A-0003", "ticker": "MSFT", "fiscal_year": 2024,
             "item": "1A", "texto": "Microsoft 2024"},
        ]
    )


def preparar_busqueda(monkeypatch, metadatos):
    indice = IndiceFalso([0.95, 0.80, 0.70, 0.60], [2, 0, 3, 1])
    codificador = CodificadorFalso()
    monkeypatch.setattr(
        retrieval,
        "_cargar_recursos",
        lambda: (indice, metadatos, codificador),
    )
    return indice, codificador


def test_prefijo_normalizacion_y_tipo_del_vector(monkeypatch, metadatos):
    indice, codificador = preparar_busqueda(monkeypatch, metadatos)

    resultados = retrieval.buscar_denso("  artificial intelligence  ", k=2)

    assert codificador.textos == [
        retrieval.PREFIJO_CONSULTA_BGE + "artificial intelligence"
    ]
    assert codificador.opciones == {
        "normalize_embeddings": True,
        "convert_to_numpy": True,
    }
    assert indice.ultima_consulta.dtype == np.float32
    assert indice.ultimo_k == indice.ntotal
    assert [r["chunk_id"] for r in resultados] == [
        "MSFT-2025-1A-0002",
        "NVDA-2024-7-0000",
    ]
    assert resultados[0]["puntuacion"] == pytest.approx(0.95)


def test_filtros_se_aplican_sobre_el_ranking_completo(monkeypatch, metadatos):
    indice, _ = preparar_busqueda(monkeypatch, metadatos)

    resultados = retrieval.buscar_denso(
        "AI risk",
        ticker=" msft ",
        fiscal_year="2025",
        item="Item 1a",
        k=2,
    )

    assert indice.ultimo_k == 4
    assert [r["chunk_id"] for r in resultados] == [
        "MSFT-2025-1A-0002",
        "MSFT-2025-1A-0001",
    ]
    assert [r["puntuacion"] for r in resultados] == pytest.approx([0.95, 0.60])


def test_filtros_sin_coincidencias_devuelven_lista_vacia(monkeypatch, metadatos):
    preparar_busqueda(monkeypatch, metadatos)

    assert retrieval.buscar_denso("risk", ticker="AAPL") == []


@pytest.mark.parametrize("query", ["", "   ", None])
def test_query_debe_contener_texto(query):
    with pytest.raises(ValueError, match="query"):
        retrieval.buscar_denso(query)


@pytest.mark.parametrize(
    ("k", "error"),
    [(0, ValueError), (-1, ValueError), (1.5, TypeError), (True, TypeError)],
)
def test_k_debe_ser_entero_positivo(k, error):
    with pytest.raises(error, match="k"):
        retrieval.buscar_denso("risk", k=k)


def test_normalizar_item():
    assert retrieval._normalizar_item(" Item 1a ") == "1A"
    assert retrieval._normalizar_item("7a") == "7A"
    assert retrieval._normalizar_item(None) is None
    assert retrieval._normalizar_item("   ") is None


def test_cargar_recursos_valida_alineacion_y_columnas(monkeypatch, metadatos):
    indice = IndiceFalso([0.9, 0.8, 0.7], [0, 1, 2])
    monkeypatch.setattr(retrieval.datos, "verificar_corpus", lambda: None)
    monkeypatch.setattr(retrieval, "_leer_indice", lambda: indice)
    monkeypatch.setattr(retrieval, "_leer_metadatos", lambda: metadatos)
    monkeypatch.setattr(retrieval, "_crear_codificador", CodificadorFalso)

    with pytest.raises(RuntimeError, match="desalineados"):
        retrieval._cargar_recursos()

    retrieval._cargar_recursos.cache_clear()
    indice.ntotal = len(metadatos)
    sin_texto = metadatos.drop(columns="texto")
    monkeypatch.setattr(retrieval, "_leer_metadatos", lambda: sin_texto)
    with pytest.raises(RuntimeError, match="texto"):
        retrieval._cargar_recursos()


def test_recursos_se_cargan_una_sola_vez(monkeypatch, metadatos):
    llamadas = {"integridad": 0, "indice": 0, "meta": 0, "modelo": 0}
    indice = IndiceFalso([0.9, 0.8, 0.7, 0.6], [0, 1, 2, 3])

    def contar(nombre, valor):
        def funcion():
            llamadas[nombre] += 1
            return valor
        return funcion

    monkeypatch.setattr(retrieval.datos, "verificar_corpus", contar("integridad", None))
    monkeypatch.setattr(retrieval, "_leer_indice", contar("indice", indice))
    monkeypatch.setattr(retrieval, "_leer_metadatos", contar("meta", metadatos))
    monkeypatch.setattr(retrieval, "_crear_codificador", contar("modelo", CodificadorFalso()))

    primero = retrieval._cargar_recursos()
    segundo = retrieval._cargar_recursos()

    assert primero is segundo
    assert llamadas == {"integridad": 1, "indice": 1, "meta": 1, "modelo": 1}
