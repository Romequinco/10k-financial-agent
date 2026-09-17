"""Pruebas exploratorias en inglés del apartado 6 del notebook 05.

Ejecutan búsquedas locales nuevas, con las consultas manuales del experimento
del 17 de septiembre. No llaman al LLM ni escriben resultados oficiales.
"""
from __future__ import annotations

import json
import re
import time

import pandas as pd

from . import config, evaluacion, retrieval


_EXPERIMENTO = config.RESULTADOS / "experimentos" / "ingles_20260917"
_STOP = set("""according to its what does say about of by in from a an the how did
and is that between two with or for on at as it this these those fiscal year years
fy2024 fy2025 2024 2025 report describe indicate explain management regards regarding
states statements financial total""".split())
_EMPRESAS = set("microsoft msft nvidia nvda apple aapl amazon amzn alphabet google googl meta".split())
_ALIAS = {
    "MSFT": ("MSFT", "Microsoft"), "NVDA": ("NVDA", "NVIDIA"),
    "AAPL": ("AAPL", "Apple"), "AMZN": ("AMZN", "Amazon"),
    "GOOGL": ("GOOGL", "GOOG", "Alphabet", "Google"), "META": ("META", "Facebook"),
}
_VARIANTES = {
    "limpieza_densa": ("Denso + limpieza general", "denso", "Empresa y FY extraídos de la pregunta"),
    "bm25_breve": ("BM25 + consulta breve", "bm25", "Empresa, FY e item del golden (oráculo)"),
    "denso_reformulado": ("Denso + consulta reformulada", "denso", "Empresa, FY e item del golden (oráculo)"),
}


def limpiar_consulta(consulta: str) -> str:
    """La misma lista de exclusión para todas las preguntas; ninguna regla por id."""
    return " ".join(t for t in re.findall(r"[a-z0-9]+", consulta.lower())
                    if t not in _STOP | _EMPRESAS and t != "10")


def extraer_filtros(pregunta: str) -> dict:
    """Alias de empresa y año explícito; en comparativas, toma el FY más reciente."""
    empresas = [ticker for ticker, aliases in _ALIAS.items()
                if any(re.search(r"\b" + re.escape(a) + r"\b", pregunta, re.IGNORECASE)
                       for a in aliases)]
    ejercicios = [int(fy) for fy in re.findall(r"(?<!\d)(20\d{2})(?!\d)", pregunta)]
    return {"ticker": empresas[0] if len(empresas) == 1 else None,
            "fiscal_year": max(ejercicios) if ejercicios else None}


def probar_variante(variante: str) -> dict:
    """Recalcula controles, variante y detalle por pregunta; no lee rankings previos.

    El control con el mismo backend y filtros permite aislar el efecto de cambiar
    la consulta. Se añade el denso literal sin filtros como referencia común.
    El golden interviene en la recuperación solo en las variantes oráculo.
    """
    if variante not in _VARIANTES:
        raise ValueError(f"Variante desconocida: {variante}. Opciones: {list(_VARIANTES)}")
    nombre, motor, etiqueta_filtros = _VARIANTES[variante]
    golden = evaluacion.cargar_golden(config.GOLDEN / "golden_propio.jsonl")
    preguntas = [p for p in golden if p.get("ancla_texto")]
    consultas = json.loads((_EXPERIMENTO / "consultas.json").read_text(encoding="utf-8"))
    protocolo = json.loads((_EXPERIMENTO / "protocolo.json").read_text(encoding="utf-8"))
    originales = {p["id"]: p["pregunta"] for p in protocolo["golden"] if p.get("ancla_texto")}
    if {p["id"]: p["pregunta"] for p in preguntas} != originales or set(consultas) != set(originales):
        raise ValueError("Las traducciones manuales no corresponden al golden actual; revísalas antes de medir.")

    resumen, rankings, entradas = [], {}, []
    for p in preguntas:
        literal, breve, reformulada = consultas[p["id"]]
        filtros = (extraer_filtros(p["pregunta"]) if variante == "limpieza_densa"
                   else evaluacion.filtros_oraculo(p))
        consulta = {"limpieza_densa": limpiar_consulta(literal), "bm25_breve": breve,
                    "denso_reformulado": reformulada}[variante]
        entradas.append({"id": p["id"], "consulta_literal": literal,
                         "consulta_prueba": consulta, **filtros})

    controles = [("Denso literal sin filtros", "denso", False, False)]
    if motor == "bm25":
        controles.append(("Denso literal con los mismos filtros", "denso", True, False))
    controles.extend([("Consulta literal: mismo backend y filtros", motor, True, False),
                      (nombre, motor, True, True)])
    for etiqueta, backend, filtrar, cambiar_consulta in controles:
        filas = []
        buscar = retrieval.buscar_denso if backend == "denso" else retrieval.buscar_bm25
        for entrada in entradas:
            consulta = entrada["consulta_prueba" if cambiar_consulta else "consulta_literal"]
            filtros = ({k: entrada[k] for k in ("ticker", "fiscal_year", "item") if k in entrada}
                       if filtrar else {})
            inicio = time.perf_counter()
            docs = buscar(consulta, k=20, **filtros)
            filas.append({"id": entrada["id"], "ranking": [d["chunk_id"] for d in docs],
                          "ms": 1000 * (time.perf_counter() - inicio)})
        rankings[etiqueta] = filas
        metricas = evaluacion.resumir_retrieval(filas, preguntas)
        resumen.append({"prueba": etiqueta, "backend": backend,
                        "filtros": etiqueta_filtros if filtrar else "Ninguno",
                        **{k: metricas[k] for k in ("aciertos@5", "recall@5", "aciertos@10", "mrr@10")}})

    antes = {d["id"]: d["rango"] for d in evaluacion.detalle_retrieval(rankings[controles[-2][0]], preguntas)}
    despues = {d["id"]: d["rango"] for d in evaluacion.detalle_retrieval(rankings[nombre], preguntas)}
    detalle = pd.DataFrame([{**entrada, "rango_literal": antes[entrada["id"]],
                             "rango_prueba": despues[entrada["id"]],
                             "acierto@5": despues[entrada["id"]] is not None and despues[entrada["id"]] <= 5}
                            for entrada in entradas])
    return {"resumen": pd.DataFrame(resumen), "detalle": detalle, "rankings": rankings}
