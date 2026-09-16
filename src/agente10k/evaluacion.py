"""Golden set, los tres evaluadores, evaluar() y tablas (guías en docs/10, docs/12 y docs/13).

Estado: el golden set (cargar, guardar, validar) está implementado desde el
notebook 03. Los tres evaluadores, evaluar(), recall_at_k y las tablas llegan
en el 04 y el 05.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from . import datos

CAMPOS = {
    "id", "pregunta", "familia", "ticker", "fiscal_year", "respuesta_esperada",
    "cifra_esperada", "unidad", "concept_xbrl", "item_esperado", "ancla_texto",
    "ancla_inicio", "ancla_fin", "chunk_id_esperado", "herramienta_esperada", "autor",
}
FAMILIAS = {"extractiva", "numerica", "comparativa"}
ITEMS = {"1A", "7", "7A", "8"}
HERRAMIENTAS = {"list_available", "get_xbrl_fact", "search_filings", "read_section"}
MAX_PALABRAS_ANCLA = 40


def cargar_golden(ruta: str | Path) -> list[dict]:
    """Lee un JSONL de preguntas (golden propio o ciegas) sin exigir nada (docs/12 §2)."""
    lineas = Path(ruta).read_text(encoding="utf-8").splitlines()
    return [json.loads(l) for l in lineas if l.strip()]


def guardar_golden(preguntas: list[dict], ruta: str | Path) -> Path:
    """Escribe el JSONL. Crea el directorio si hace falta."""
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    cuerpo = "\n".join(json.dumps(p, ensure_ascii=False) for p in preguntas)
    ruta.write_text(cuerpo + "\n", encoding="utf-8")
    return ruta


def validar_golden(preguntas: list[dict], exigir_20: bool = True,
                   esperar_ausencia: bool = False) -> list[str]:
    """Problemas del golden set, uno por línea; lista vacía = correcto. Mismas reglas que el
    validador de clase (docs/10 §8, docs/01 §3), más cuatro comprobaciones propias: que la
    cifra coincida con XBRL, que el ancla exista literal en la sección, que sus offsets
    cuadren y que las herramientas esperadas existan.

    esperar_ausencia: modo huecos. Invierte la comprobación XBRL (el concepto NO debe
        existir), exige cifra_esperada nula y admite tickers fuera del corpus.
    """
    secciones = datos.cargar_secciones()
    xbrl = datos.cargar_xbrl()
    tickers = set(secciones["ticker"])
    ejercicios = set(secciones["fiscal_year"].astype(int))
    problemas, vistos = [], set()

    for p in preguntas:
        pid = p.get("id", "(sin id)")
        if faltan := CAMPOS - set(p):
            problemas.append(f"{pid}: faltan campos {sorted(faltan)}")
            continue
        if p["id"] in vistos:
            problemas.append(f"{pid}: id repetido")
        vistos.add(p["id"])
        if p["familia"] not in FAMILIAS:
            problemas.append(f"{pid}: familia '{p['familia']}' no válida")
        if not esperar_ausencia:
            if p["ticker"] not in tickers:
                problemas.append(f"{pid}: {p['ticker']} no está en el corpus")
            if int(p["fiscal_year"]) not in ejercicios:
                problemas.append(f"{pid}: FY{p['fiscal_year']} no está en el corpus")

        concepto = p.get("concept_xbrl")
        if concepto:
            hay = xbrl[(xbrl["ticker"] == p["ticker"])
                       & (xbrl["fiscal_year"].astype(int) == int(p["fiscal_year"]))
                       & (xbrl["concept"] == concepto)]
        else:
            hay = xbrl.iloc[0:0]

        if esperar_ausencia:
            if p.get("cifra_esperada") is not None:
                problemas.append(f"{pid}: es un hueco, cifra_esperada debe ser null")
            if concepto and not hay.empty:
                problemas.append(f"{pid}: '{concepto}' SÍ está reportado; no es un hueco")
        elif p["familia"] in {"numerica", "comparativa"}:
            if p.get("cifra_esperada") is None:
                problemas.append(f"{pid}: numérica sin cifra_esperada")
            if concepto and hay.empty:
                problemas.append(
                    f"{pid}: {p['ticker']} no reporta '{concepto}' en FY{p['fiscal_year']}. "
                    "El concepto se mira en xbrl_facts.parquet, nunca por analogía.")
            elif concepto and p.get("cifra_esperada") is not None:
                valor = float(hay.iloc[0]["value"])
                esperada = float(p["cifra_esperada"])
                if abs(valor - esperada) > max(abs(valor) * 1e-9, 1e-6):
                    problemas.append(
                        f"{pid}: cifra_esperada ({esperada}) no coincide con XBRL ({valor})")

        if p["familia"] in {"extractiva", "comparativa"} and not esperar_ausencia:
            ancla = p.get("ancla_texto")
            item = p.get("item_esperado")
            if not ancla:
                problemas.append(f"{pid}: {p['familia']} sin ancla_texto")
            elif len(ancla.split()) > MAX_PALABRAS_ANCLA:
                problemas.append(
                    f"{pid}: ancla de {len(ancla.split())} palabras. Una frase. Así no "
                    "medís vuestro retrieval, medís vuestro tamaño de ventana.")
            if item not in ITEMS:
                problemas.append(f"{pid}: item_esperado '{item}' no es 1A, 7, 7A ni 8")
            elif ancla:
                fila = secciones[(secciones["ticker"] == p["ticker"])
                                 & (secciones["fiscal_year"].astype(int) == int(p["fiscal_year"]))
                                 & (secciones["item"] == item)]
                if fila.empty:
                    problemas.append(
                        f"{pid}: no existe {p['ticker']} FY{p['fiscal_year']} item {item}")
                else:
                    texto = fila.iloc[0]["texto"]
                    pos = texto.find(ancla)
                    if pos == -1:
                        problemas.append(
                            f"{pid}: el ancla no aparece literalmente en la sección")
                    elif (p.get("ancla_inicio"), p.get("ancla_fin")) != (pos, pos + len(ancla)):
                        problemas.append(
                            f"{pid}: offsets del ancla mal; deberían ser "
                            f"({pos}, {pos + len(ancla)})")

        herramientas = p.get("herramienta_esperada") or []
        if not herramientas:
            problemas.append(f"{pid}: sin herramienta_esperada")
        elif desconocidas := set(herramientas) - HERRAMIENTAS:
            problemas.append(f"{pid}: herramienta desconocida {sorted(desconocidas)}")

    if exigir_20:
        if len(preguntas) != 20:
            problemas.append(f"hacen falta 20 preguntas, hay {len(preguntas)}")
        n_comp = sum(p.get("familia") == "comparativa" for p in preguntas)
        if n_comp < 6:
            problemas.append(f"hacen falta 6 comparativas, hay {n_comp}")
    return problemas


def evaluar_cita(fila: dict, pregunta: dict) -> bool | None:
    """Evaluador (a): la cita existe en el corpus y respalda lo que se afirma (docs/12 §5–§6)."""
    raise NotImplementedError("TODO · docs/12 §5")


def evaluar_cifra(fila: dict, pregunta: dict) -> bool | None:
    """Evaluador (b): la cifra coincide con XBRL dentro de la tolerancia documentada (docs/12 §3)."""
    raise NotImplementedError("TODO · docs/12 §3")


def evaluar_trayectoria(fila: dict, pregunta: dict) -> bool | None:
    """Evaluador (c): la trayectoria pasó por la herramienta esperada (docs/12 §4)."""
    raise NotImplementedError("TODO · docs/12 §4")


def recall_at_k(rankings: list[dict], preguntas: list[dict], k: int = 5) -> float:
    """Fracción de preguntas con ancla cuya frase aparece en algún fragmento del top-k (docs/11 §4)."""
    raise NotImplementedError("TODO · docs/11 §4")


def evaluar(ruta_jsonl: str | Path, etiqueta: str | None = None, sistema: str = "final") -> pd.DataFrame:
    """CONTRATO (R10): ejecuta el agente sobre cada pregunta, guarda resultados/<etiqueta>/
    (predicciones.jsonl y resumen.json) y devuelve una fila por pregunta con los tres evaluadores,
    coste, latencia y llamadas (docs/12 §8)."""
    raise NotImplementedError("TODO · docs/12 §8")


def tabla_comparativa(etiquetas: tuple[str, ...] = ("baseline", "final")) -> pd.DataFrame:
    """Tabla R11: aciertos por familia, recall@k, coste medio, latencia media y llamadas por
    pregunta, con el mejor valor remarcado (docs/13 §5)."""
    raise NotImplementedError("TODO · docs/13 §5")
