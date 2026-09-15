"""Pruebas de integridad y contratos internos del corpus."""
from __future__ import annotations

import shutil

import pytest

from agente10k import datos


HASH_CHUNKS = "388ff3671742c2248e8f5cb1c75afbc786edfa0dc6f72a62d1fadf2310ec82b2"


def test_verificar_corpus_real():
    assert datos.verificar_corpus() is None
    assert datos._sha256(datos.config.CORPUS / "chunks.jsonl") == HASH_CHUNKS


def test_verificar_corpus_detecta_archivos_ausentes(tmp_path, monkeypatch):
    monkeypatch.setattr(datos.config, "CORPUS", tmp_path)
    with pytest.raises(FileNotFoundError, match="secciones.jsonl"):
        datos.verificar_corpus()


def test_verificar_corpus_detecta_corrupcion_y_desalineacion(tmp_path, monkeypatch):
    copia = tmp_path / "corpus"
    shutil.copytree(datos.config.CORPUS, copia)
    monkeypatch.setattr(datos.config, "CORPUS", copia)

    chunks = copia / "chunks.jsonl"
    original_chunks = chunks.read_bytes()
    chunks.write_bytes(original_chunks + b"\n")
    with pytest.raises(RuntimeError, match="chunks.jsonl.*MANIFEST"):
        datos.verificar_corpus()

    chunks.write_bytes(original_chunks)
    manifiesto_indice = copia / "indice" / "MANIFEST.md"
    manifiesto_indice.write_text(
        manifiesto_indice.read_text(encoding="utf-8").replace(HASH_CHUNKS, "0" * 64),
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match="desalineados"):
        datos.verificar_corpus()


def test_cargar_secciones_conserva_esquema_y_cobertura():
    secciones = datos.cargar_secciones()
    assert secciones.shape == (48, 11)
    assert not secciones.duplicated(["ticker", "fiscal_year", "item"]).any()
    assert set(secciones["ticker"]) == {"NVDA", "MSFT", "AAPL", "GOOGL", "META", "AMZN"}
    assert set(secciones["fiscal_year"]) == {2024, 2025}
    assert set(secciones["item"]) == {"1A", "7", "7A", "8"}
    assert secciones.loc[secciones["ticker"].eq("NVDA"), "cik"].iat[0] == "0001045810"


def test_item_8_de_nvda_procede_del_item_15():
    secciones = datos.cargar_secciones()
    excepciones = secciones.loc[
        secciones["item"].ne(secciones["item_origen"]),
        ["ticker", "fiscal_year", "item", "item_origen"],
    ].to_dict("records")
    assert excepciones == [
        {"ticker": "NVDA", "fiscal_year": 2024, "item": "8", "item_origen": "15"},
        {"ticker": "NVDA", "fiscal_year": 2025, "item": "8", "item_origen": "15"},
    ]


def test_chunks_conservan_ids_posiciones_y_offsets():
    secciones = datos.cargar_secciones().set_index(["ticker", "fiscal_year", "item"])
    chunks = datos.cargar_chunks()
    assert chunks.shape == (1749, 10)
    assert chunks["chunk_id"].is_unique
    assert chunks["contiene_tabla"].eq(chunks["texto"].str.contains("\t", regex=False)).all()

    for clave, grupo in chunks.groupby(["ticker", "fiscal_year", "item"], sort=False):
        assert grupo["posicion"].tolist() == list(range(len(grupo)))
        texto_completo = secciones.loc[clave, "texto"]
        for fila in grupo.itertuples(index=False):
            assert fila.texto == texto_completo[fila.inicio_car:fila.fin_car]


def test_cargar_xbrl_conserva_unidades_y_precision():
    xbrl = datos.cargar_xbrl()
    assert xbrl.shape == (135, 8)
    assert not xbrl.duplicated(["ticker", "fiscal_year", "concept"]).any()
    assert xbrl["unit"].value_counts().to_dict() == {"USD": 111, "USD/shares": 24}
    bpa = xbrl.query(
        "ticker == 'NVDA' and fiscal_year == 2025 and concept == 'EarningsPerShareBasic'"
    )["value"].iat[0]
    assert bpa == pytest.approx(2.97)


def test_xbrl_distingue_huecos_reales_de_conceptos_alternativos():
    xbrl = datos.cargar_xbrl()
    presentes = set(zip(xbrl["ticker"], xbrl["fiscal_year"], xbrl["concept"]))

    huecos = {
        *((ticker, fy, "GrossProfit") for ticker in ("AMZN", "GOOGL", "META") for fy in (2024, 2025)),
        *(("AMZN", fy, "Liabilities") for fy in (2024, 2025)),
        *(("AMZN", fy, "ResearchAndDevelopmentExpense") for fy in (2024, 2025)),
    }
    assert len(huecos) == 10
    assert presentes.isdisjoint(huecos)

    concepto_largo = "RevenueFromContractWithCustomerExcludingAssessedTax"
    for ticker in ("AAPL", "MSFT", "META", "AMZN"):
        for fy in (2024, 2025):
            assert (ticker, fy, concepto_largo) in presentes
            assert (ticker, fy, "Revenues") not in presentes
    for fy in (2024, 2025):
        assert ("NVDA", fy, "Revenues") in presentes
        assert ("NVDA", fy, concepto_largo) not in presentes
    assert ("GOOGL", 2024, "Revenues") in presentes
    assert ("GOOGL", 2024, concepto_largo) in presentes
    assert ("GOOGL", 2025, "Revenues") in presentes
    assert ("GOOGL", 2025, concepto_largo) not in presentes

    googl_2024 = xbrl.query(
        "ticker == 'GOOGL' and fiscal_year == 2024 and concept in ['Revenues', @concepto_largo]"
    )
    assert googl_2024["value"].nunique() == 1
