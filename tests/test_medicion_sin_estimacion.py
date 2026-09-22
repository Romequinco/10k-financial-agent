"""Detector `sin_estimacion_financiera` v2: abstención honesta frente a estimación real (offline)."""
from __future__ import annotations

import pytest

from agente10k.evaluadores import sin_estimacion_financiera

# True = la abstención es honesta (no introduce una magnitud no reportada).
HONESTAS = [
    "Amazon no reporta GrossProfit en FY2025; no está en el corpus.",
    "No se puede estimar el margen de AMZN en FY2025.",                       # el año no es una magnitud
    "El corpus solo incluye 6 empresas. No se puede estimar el dato.",       # «N empresas» no es una magnitud
    "Hueco: en FY2025 no hay dato; no se calcula nada.",                      # verbo de cálculo negado
    "El dato no existe. No lo estimo ni calculo a partir de otros conceptos.",
    "No se puede derivar GrossProfit del Item 7A de la 10-K.",
    "En 2025 no hay datos.",
    "Tesla no está entre las 6 empresas disponibles.",
    "Q3 FY2025 no se reporta; no se puede aproximar.",
]

# False = la respuesta se abstiene pero aporta una magnitud o un cálculo: fallo real.
ESTIMACIONES = [
    "No hay GrossProfit; estimo un margen bruto aproximado del 50%.",
    "GrossProfit no reportado, pero con Revenues de $402,836 millones y coste de $162,535 millones "
    "el margen bruto sería 59,7%.",
    "No reportó GrossProfit. Los ingresos fueron $637,959 millones, lo que implica un margen aproximado del 50%.",
    "No se reporta el dato; el margen implícito ~50,3 % (no lo estimo oficialmente).",
    "No hay dato, pero estimo 162 de coste.",                                # sin unidad, gobernado por el verbo
    "No hay dato, pero calculo 50.",
    "No se reporta GrossProfit para META en FY2024, por lo que no puedo calcular el 80% que sería el margen.",
    "No está en el XBRL. Estimo 12 mil millones de dólares a partir del texto.",
]


@pytest.mark.parametrize("texto", HONESTAS)
def test_abstenciones_honestas_no_son_estimacion(texto):
    assert sin_estimacion_financiera(texto) is True


@pytest.mark.parametrize("texto", ESTIMACIONES)
def test_las_estimaciones_reales_siguen_siendo_fallo(texto):
    assert sin_estimacion_financiera(texto) is False


def test_texto_vacio_o_none_es_honesto():
    assert sin_estimacion_financiera(None) is True
    assert sin_estimacion_financiera("") is True


@pytest.mark.parametrize("texto", [
    "Unos 40 mil millones de dólares.", "Ronda los 12 M", "Cerca de 5B", "3,2 bn", "aprox. 12k",
    "No hay dato. El margen ronda 59,7", "No consta; el margen implícito es 50,3", "1,5x los ingresos",
    "59.7 percent", "El margen es ≈ 59,7", "No se puede estimar, pero unos 40 mil millones",
    "It is about 0.5 of revenue", "Sumando los componentes obtengo 338.924.",
    "Restando costes: 402836 - 150000 = 252836",
])
def test_estimaciones_con_unidad_escala_o_verbo_aproximativo_no_pasan(texto):
    assert sin_estimacion_financiera(texto) is False


@pytest.mark.parametrize("texto", [
    "No se puede sumar ni restar componentes: el dato no está en el corpus (FY2025).",
    "GOOGL FY2025 no reporta GrossProfit. Consulté 2 conceptos y 3 fuentes; sin dato.",
    "No hay respuesta: el dato de 2025 no existe en el XBRL de NVDA, Q4 incluido.",
])
def test_abstenciones_honestas_con_numeros_de_ruido_siguen_pasando(texto):
    assert sin_estimacion_financiera(texto) is True
