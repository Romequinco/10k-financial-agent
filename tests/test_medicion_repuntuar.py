"""Re-puntuación sin API de artefactos guardados; no toca los originales (offline)."""
from __future__ import annotations

import hashlib
import json
import shutil

import pytest

from agente10k import config, evaluadores

BASELINE_HUECOS = config.RESULTADOS / "baseline_huecos"
requiere_baseline_huecos = pytest.mark.skipif(
    not (BASELINE_HUECOS / "predicciones.jsonl").is_file(),
    reason="no está el artefacto baseline_huecos")


def _huellas(carpeta):
    return {f.name: hashlib.sha256(f.read_bytes()).hexdigest() for f in carpeta.iterdir()}


@requiere_baseline_huecos
def test_repuntuar_huecos_da_2_de_6_y_no_toca_el_original():
    """baseline_huecos guardó 3/6 antes de que existiera `sin_estimacion`; hoy son 2/6.

    g3-h005 se abstiene pero calcula «un margen bruto aproximado del 59,7 %» a partir de ingresos
    y costes: estima un dato no reportado. Este test fija la discrepancia (baseline* está
    congelado y no se regenera).
    """
    antes = _huellas(BASELINE_HUECOS)

    tabla, resumen = evaluadores.repuntuar("baseline_huecos")

    assert resumen["familias"]["hueco"] == "2/6"
    guardado = json.loads((BASELINE_HUECOS / "resumen.json").read_text(encoding="utf-8"))
    assert guardado["familias"]["hueco"] == "3/6"                  # lo guardado no cambia
    fallo = tabla[tabla["id"] == "g3-h005"].iloc[0]
    assert bool(fallo["abstiene"]) and not bool(fallo["sin_estimacion"]) and not fallo["acierto"]
    assert _huellas(BASELINE_HUECOS) == antes                      # nada escrito, ni hoy ni antes


@requiere_baseline_huecos
def test_repuntuar_guardar_en_escribe_en_otra_etiqueta(tmp_path, monkeypatch):
    origen = tmp_path / "origen"
    shutil.copytree(BASELINE_HUECOS, origen)
    monkeypatch.setattr(config, "RESULTADOS", tmp_path)

    evaluadores.repuntuar("origen", guardar_en="nueva")

    resumen = json.loads((tmp_path / "nueva" / "resumen.json").read_text(encoding="utf-8"))
    assert resumen["repuntuado_de"] == "origen" and resumen["familias"]["hueco"] == "2/6"
    assert (tmp_path / "nueva" / "puntuaciones.jsonl").is_file()
    assert not (tmp_path / "nueva" / "predicciones.jsonl").exists()
    with pytest.raises(ValueError, match="distinta"):
        evaluadores.repuntuar("origen", guardar_en="origen")
