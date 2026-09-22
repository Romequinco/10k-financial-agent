"""Golden set, los tres evaluadores, evaluar() y tablas (guías en docs/10, docs/12 y docs/13).

Estado: el golden set (cargar, guardar, validar) está implementado desde el
notebook 03. Los tres evaluadores, evaluar(), recall_at_k y las tablas llegan
en el 04 y el 05.
"""
from __future__ import annotations

import json
import hashlib
import math
import time
import warnings
from pathlib import Path

import pandas as pd

from . import config, datos, retrieval
from .normalizacion import normalizar, normalizar_ticker

CAMPOS = {
    "id", "pregunta", "familia", "ticker", "fiscal_year", "respuesta_esperada",
    "cifra_esperada", "unidad", "concept_xbrl", "item_esperado", "ancla_texto",
    "ancla_inicio", "ancla_fin", "chunk_id_esperado", "herramienta_esperada", "autor",
}
FAMILIAS = {"extractiva", "numerica", "comparativa"}
ITEMS = {"1A", "7", "7A", "8"}
HERRAMIENTAS = {"list_available", "get_xbrl_fact", "search_filings", "read_section"}
MAX_PALABRAS_ANCLA = 40
RETRIEVAL_ARTEFACTO_SELECCIONADO = "5976eb180c38"


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
    from . import evaluadores

    if "a" in fila:
        return fila["a"]
    # El respaldo semántico requiere juez. Esta fachada mantiene el contrato
    # público y reutiliza la única implementación, sin inventar un veredicto.
    return evaluadores.puntuar_fila(
        _fila_evaluable(fila, pregunta), juez=None, estricto=True
    ).get("a")


def evaluar_cifra(fila: dict, pregunta: dict) -> bool | None:
    """Evaluador (b): la cifra coincide con XBRL dentro de la tolerancia documentada (docs/12 §3)."""
    from . import evaluadores

    if "b" in fila:
        return fila["b"]
    return evaluadores.evaluar_cifra(_respuesta(fila), pregunta).get("b")


def evaluar_trayectoria(fila: dict, pregunta: dict) -> bool | None:
    """Evaluador (c): la trayectoria pasó por la herramienta esperada (docs/12 §4)."""
    from . import evaluadores

    if "c" in fila:
        return fila["c"]
    resp = _respuesta(fila)
    return evaluadores.evaluar_trayectoria(
        fila.get("tool_calls") or [], pregunta, resp
    ).get("c")


def _respuesta(fila: dict) -> dict:
    """Admite tanto una predicción persistida como una respuesta plana."""
    resp = fila.get("respuesta", fila)
    if hasattr(resp, "model_dump"):
        return resp.model_dump()
    return dict(resp or {})


def _fila_evaluable(fila: dict, pregunta: dict) -> dict:
    """Normaliza la entrada de las fachadas al formato de ``puntuar_fila``."""
    if "golden" in fila and "respuesta" in fila:
        return fila
    return {
        "id": fila.get("id", pregunta.get("id")),
        "golden": pregunta,
        "respuesta": _respuesta(fila),
        "tool_calls": fila.get("tool_calls") or [],
        "observaciones": fila.get("observaciones") or [],
    }


def recall_at_k(rankings: list[dict], preguntas: list[dict], k: int = 5) -> float:
    """Fracción de preguntas con ancla cuya frase aparece en algún fragmento del top-k (docs/11 §4)."""
    if isinstance(k, bool) or not isinstance(k, int) or k < 1:
        raise ValueError("k debe ser un entero positivo")
    detalle = detalle_retrieval(rankings, preguntas)
    return sum(d["rango"] is not None and d["rango"] <= k for d in detalle) / len(detalle)


def evaluar(ruta_jsonl: str | Path, etiqueta: str | None = None, sistema: str = "final",
            juez=None, con_juez: bool = True) -> pd.DataFrame:
    """CONTRATO (R10): ejecuta el agente sobre cada pregunta, guarda resultados/<etiqueta>/
    (predicciones.jsonl y resumen.json) y devuelve una fila por pregunta con los tres evaluadores,
    coste, latencia y llamadas (docs/12 §8).

    Ejecutar y puntuar están separados: si ya existe predicciones.jsonl para esa
    etiqueta, se repuntúa sin volver a llamar al modelo. Se reutilizan si coinciden el hash
    del golden, el sistema, el modelo, el límite y el retrieval del manifest; commit, árbol sucio
    y huella del diff solo dan un aviso. Predicciones sin manifest (legacy) no se reutilizan
    hasta `evaluadores.bendecir_legacy`. Una tanda cortada se reanuda por id (ejecutar_golden).

    Juez (docs/12 §8): sin `juez`, se crea uno con `evaluadores.crear_juez()` (modelo de
    AGENTE10K_MODELO_JUEZ o el del agente) cuando hay extractivas o comparativas que puntuar.
    Si no se puede crear (sin clave o sin red) no se falla: se avisa, esas filas quedan sin
    evaluar y el resumen sale `parcial` con `micro`/`macro` en None (nunca un 1.0 inflado).
    `con_juez=False` lo pide expresamente. El aviso queda en `tabla.attrs["aviso"]`.

    Sistema `final`: falla con SistemaFinalNoDisponible mientras falte el 06, antes de crear
    ningún artefacto.
    """
    from . import config, evaluadores

    etiqueta = etiqueta or sistema
    if sistema not in evaluadores.SISTEMAS:
        raise ValueError(f"Sistema desconocido: {sistema!r}. Opciones: {sorted(evaluadores.SISTEMAS)}")
    predicciones = config.RESULTADOS / etiqueta / "predicciones.jsonl"
    avisos: list[str] = []
    if predicciones.is_file():
        ruta_manifest = predicciones.with_name("manifest.json")
        if not ruta_manifest.is_file():
            raise ValueError(
                f"La etiqueta {etiqueta!r} contiene predicciones legacy sin manifest.json; "
                "no se pueden reutilizar de forma reproducible. Usa una etiqueta nueva o, si "
                "son de este golden y sistema, escribe solo su manifest con "
                "evaluadores.bendecir_legacy(etiqueta, ruta_jsonl, sistema)."
            )
        manifest = _leer_json_si_existe(ruta_manifest)
        esperado = evaluadores.manifest_ejecucion(ruta_jsonl, sistema)
        if diferencias := evaluadores.validar_manifest(manifest, esperado):
            raise ValueError(
                f"La etiqueta {etiqueta!r} no es compatible con esta ejecución "
                f"({', '.join(diferencias)}). Usa una etiqueta nueva."
            )
        if informativas := evaluadores.avisos_manifest(manifest, esperado):
            avisos.append("Se reutilizan predicciones de otro estado del código ("
                          + "; ".join(informativas) + ").")
    else:
        # Nunca degradar silenciosamente candidato/final a baseline: se valida el sistema
        # ANTES de ejecutar; si no puede montarse, falla sin crear ningún artefacto.
        evaluadores.validar_sistema(sistema)
        evaluadores.ejecutar_golden(ruta_jsonl, etiqueta=etiqueta, sistema=sistema)

    if juez is None and con_juez and evaluadores.necesita_juez(_leer_jsonl_si_existe(predicciones)):
        try:
            juez = evaluadores.crear_juez()
        except Exception as exc:                         # sin clave, sin red, paquete ausente
            avisos.append(f"No se pudo crear el juez ({type(exc).__name__}: {exc}): las "
                          "extractivas y comparativas quedan sin evaluar.")
    tabla = evaluadores.puntuar(etiqueta, **({"juez": juez} if juez is not None else {}))
    resumen = _leer_json_si_existe(config.RESULTADOS / etiqueta / "resumen.json")
    if resumen.get("parcial"):
        avisos.append(f"Resultado PARCIAL: {resumen.get('n_no_evaluables')} preguntas no evaluables; "
                      "micro/macro no se publican (cota inferior "
                      f"{resumen.get('micro_cota_inferior')}, sobre evaluables {resumen.get('micro_parcial')}).")
    if resumen.get("errores"):
        avisos.append(f"{resumen['errores']} de {resumen.get('n')} filas terminaron con error (429, red, "
                      "recursión...) y cuentan como fallo: micro/macro no son comparables hasta repetir esas "
                      "filas (evaluar reutiliza las predicciones guardadas; usa otra etiqueta).")
    if resumen.get("juez_fallos_filas"):
        avisos.append(f"El juez falló en {resumen['juez_fallos_filas']} filas (cuentan como fallo); "
                      "re-puntúa con el juez disponible para reintentarlas.")
    for aviso in avisos:
        warnings.warn(aviso, stacklevel=2)
    tabla.attrs["aviso"] = " ".join(avisos) if avisos else None
    tabla.attrs["resumen"] = resumen
    return tabla


def tabla_comparativa(etiquetas: tuple[str, ...] = ("baseline", "final")) -> pd.DataFrame:
    """Tabla R11: aciertos por familia, recall@k, coste medio, latencia media y llamadas por
    pregunta, con el mejor valor remarcado (docs/13 §5).

    Devuelve métricas numéricas (aptas para gráficos/cálculos), los recuentos
    ``k/n`` por familia y columnas booleanas ``mejor_*``. Una etiqueta todavía
    no ejecutada produce una fila ``disponible=False`` en vez de confundirse con
    ceros. El recall principal es el aislado ``recall@5`` guardado en el resumen;
    ``recall_agente`` se presenta aparte y nunca lo sustituye.
    """
    if isinstance(etiquetas, str):
        etiquetas = (etiquetas,)
    if not etiquetas:
        return pd.DataFrame()
    if len(set(etiquetas)) != len(etiquetas):
        raise ValueError("Las etiquetas de la comparación deben ser únicas")

    filas = [_fila_comparativa(etiqueta) for etiqueta in etiquetas]
    tabla = pd.DataFrame(filas)
    direcciones = {
        "tasa_numerica": "max", "tasa_extractiva": "max",
        "tasa_comparativa": "max", "tasa_hueco": "max",
        "micro": "max", "macro": "max", "recall@5": "max",
        "recall_agente": "max", "usd_medio": "min",
        "tokens_medios": "min", "tokens_mediana": "min", "tokens_p90": "min",
        "tokens_entrada_medios": "min", "tokens_salida_medios": "min",
        "latencia_media_s": "min", "latencia_mediana_s": "min", "latencia_p90_s": "min",
        "llamadas_medias": "min", "llamadas_modelo_medias": "min", "errores": "min",
        "abstenciones_indebidas": "min",
    }
    for metrica, direccion in direcciones.items():
        valores = pd.to_numeric(tabla[metrica], errors="coerce")
        validos = valores[tabla["disponible"] & valores.notna()]
        col = f"mejor_{metrica}"
        tabla[col] = False
        # No se remarca un único resultado: aún no existe comparación.
        if len(validos) >= 2:
            mejor = validos.max() if direccion == "max" else validos.min()
            tabla.loc[validos.index, col] = validos.map(
                lambda valor: math.isclose(valor, mejor, rel_tol=1e-9, abs_tol=1e-12)
            )
    tabla.attrs["direccion_metricas"] = direcciones
    tabla.attrs["nota_recall"] = (
        "recall@5 es la medida aislada persistida; recall_agente es el diagnóstico "
        "sobre los fragmentos observados durante la ejecución."
    )
    return tabla


def _ratio_kn(valor) -> float | None:
    if isinstance(valor, str) and "/" in valor:
        try:
            k, n = (int(x) for x in valor.split("/", 1))
        except ValueError:
            return None
        return k / n if n else None
    if isinstance(valor, (int, float)) and not isinstance(valor, bool):
        return float(valor)
    return None


def _leer_json_si_existe(ruta: Path) -> dict:
    if not ruta.is_file():
        return {}
    valor = json.loads(ruta.read_text(encoding="utf-8"))
    if not isinstance(valor, dict):
        raise ValueError(f"Se esperaba un objeto JSON en {ruta}")
    return valor


def _leer_jsonl_si_existe(ruta: Path) -> list[dict]:
    if not ruta.is_file():
        return []
    return [json.loads(linea) for linea in ruta.read_text(encoding="utf-8").splitlines()
            if linea.strip()]


def _media_booleana(filas: list[dict], clave: str) -> float | None:
    valores = [fila[clave] for fila in filas if isinstance(fila.get(clave), bool)]
    return sum(valores) / len(valores) if valores else None


def _config_retrieval_compatible(configuracion: dict) -> bool:
    """La configuración aislada corresponde al híbrido que usa el runtime."""
    esperada = {
        "embeddings": retrieval.MODELO_EMBEDDINGS,
        "prefijo": retrieval.PREFIJO_CONSULTA_BGE,
        "n_cand": config.RETRIEVAL_N_CAND,
        "k_rrf": config.RETRIEVAL_K_RRF,
        "pesos": [1, 1],
        "bm25": [config.BM25_K1, config.BM25_B, config.BM25_EPSILON],
        "tokenizer": config.RETRIEVAL_TOKENIZER,
    }
    return all(configuracion.get(k) == v for k, v in esperada.items())


def _recall_aislado(etiqueta: str, directorio: Path,
                    predicciones: list[dict]) -> dict:
    """Recall R11 con paso y procedencia explícitos; nunca infiere otro paso."""
    manifest = _leer_json_si_existe(directorio / "manifest.json")
    sistema = manifest.get("sistema")
    paso = (manifest.get("retrieval") or {}).get("paso_aislado")
    if not paso:  # compatibilidad de lectura para resultados legacy conocidos
        if etiqueta == "baseline":
            sistema, paso = "baseline", "0_denso"
        elif etiqueta == "candidato_07":
            sistema, paso = "candidato_07", "2_bm25"
        else:
            return {}

    raiz = config.RESULTADOS_RETRIEVAL / RETRIEVAL_ARTEFACTO_SELECCIONADO
    configuracion = _leer_json_si_existe(raiz / "configuracion.json")
    resumen = _leer_json_si_existe(raiz / "resumen.json")
    if not configuracion or not resumen.get("completo"):
        return {}
    golden_resultado = [f.get("golden") for f in predicciones if f.get("golden")]
    if not golden_resultado or golden_resultado != configuracion.get("golden"):
        return {}
    if sistema in {"candidato_07", "final"} and not _config_retrieval_compatible(configuracion):
        return {"recall_paso": paso, "recall_config_compatible": False}
    fila = next((p for p in resumen.get("pasos", []) if p.get("paso") == paso), None)
    if not fila:
        return {}
    return {
        "recall@5": fila.get("recall@5"),
        "recall_aciertos@5": fila.get("aciertos@5"),
        "recall_paso": paso,
        "recall_config_compatible": True,
        "recall_procedencia": str((raiz / "resumen.json").relative_to(config.RAIZ).as_posix()),
    }


def _fila_comparativa(etiqueta: str) -> dict:
    from . import evaluadores

    directorio = config.RESULTADOS / etiqueta
    resumen = _leer_json_si_existe(directorio / "resumen.json")
    disponible = bool(resumen)
    puntuaciones = _leer_jsonl_si_existe(directorio / "puntuaciones.jsonl")
    predicciones = _leer_jsonl_si_existe(directorio / "predicciones.jsonl")
    familias = resumen.get("familias") or {}
    recall = _recall_aislado(etiqueta, directorio, predicciones) if disponible else {}
    fila = {
        "sistema": etiqueta, "disponible": disponible,
        "n": resumen.get("n"),
        "numerica": familias.get("numerica", "—"),
        "extractiva": familias.get("extractiva", "—"),
        "comparativa": familias.get("comparativa", "—"),
        "hueco": familias.get("hueco", "—"),
        "tasa_numerica": _ratio_kn(familias.get("numerica")),
        "tasa_extractiva": _ratio_kn(familias.get("extractiva")),
        "tasa_comparativa": _ratio_kn(familias.get("comparativa")),
        "tasa_hueco": _ratio_kn(familias.get("hueco")),
        "micro": resumen.get("micro"), "macro": resumen.get("macro"),
        "recall@5": recall.get("recall@5", resumen.get("recall@5")),
        "recall_aciertos@5": recall.get("recall_aciertos@5"),
        "recall_paso": recall.get("recall_paso"),
        "recall_config_compatible": recall.get("recall_config_compatible"),
        "recall_procedencia": recall.get("recall_procedencia"),
        "recall_agente": (resumen.get("recall_agente")
                           if "recall_agente" in resumen
                           else _media_booleana(puntuaciones, "recall_agente")),
        "usd_medio": resumen.get("usd_medio"),
        "errores": resumen.get("errores"),
        "abstenciones_indebidas": resumen.get("abstenciones_indebidas"),
        "parcial": resumen.get("parcial"), "micro_parcial": resumen.get("micro_parcial"),
        "verificacion_sin_referencia": (resumen.get("sin_referencia") or {}).get("verificacion"),
    }
    # Latencia, tokens y llamadas: el resumen manda; si es anterior a la mediana, el p90 o los
    # tokens de entrada/salida, se derivan de las predicciones con la misma función.
    derivadas = evaluadores.metricas_operativas(predicciones) if predicciones else {}
    for clave in ("tokens_medios", "tokens_mediana", "tokens_p90", "tokens_entrada_medios",
                  "tokens_salida_medios", "latencia_media_s", "latencia_mediana_s",
                  "latencia_p90_s", "llamadas_medias", "llamadas_modelo_medias"):
        valor = resumen.get(clave)
        fila[clave] = valor if valor is not None else derivadas.get(clave)
    return fila


def textos_retrieval() -> dict[str, str]:
    meta = retrieval._leer_metadatos_cache()
    return dict(zip(meta["chunk_id"], meta["texto"].map(normalizar)))


def _relevantes(pregunta: dict, textos: dict[str, str]) -> set[str]:
    """Ancla literal en la empresa, FY y sección esperados, aunque se repita en otros informes."""
    ancla = normalizar(pregunta["ancla_texto"])
    meta = retrieval._leer_metadatos_cache()
    posiciones = retrieval.candidatos(pregunta.get("ticker"), pregunta.get("fiscal_year"),
                                      pregunta.get("item_esperado"))
    permitidos = set(meta.iloc[posiciones]["chunk_id"])
    return {cid for cid, texto in textos.items() if cid in permitidos and ancla and ancla in texto}


def detalle_retrieval(rankings: list[dict], preguntas: list[dict]) -> list[dict]:
    """Una fila por pregunta con ancla; un ranking ausente cuenta como fallo."""
    textos = textos_retrieval()
    filas = {f["id"]: f for f in rankings}
    if len(filas) != len(rankings):
        raise ValueError("Hay ids repetidos en los rankings")
    detalle = []
    for p in preguntas:
        if not p.get("ancla_texto"):
            continue
        relevantes = _relevantes(p, textos)
        ranking = filas.get(p["id"], {}).get("ranking", [])
        if len(ranking) != len(set(ranking)) or any(cid not in textos for cid in ranking):
            raise ValueError(f"Ranking inválido: {p['id']}")
        rango = next((i for i, cid in enumerate(ranking, 1) if cid in relevantes), None)
        detalle.append({"id": p["id"], "item": p["item_esperado"], "rango": rango,
                        "n_relevantes": len(relevantes), "presente": p["id"] in filas})
    if not detalle:
        raise ValueError("No hay preguntas con ancla para medir retrieval")
    return detalle


def resumir_retrieval(rankings: list[dict], preguntas: list[dict]) -> dict:
    detalle = detalle_retrieval(rankings, preguntas)
    n = len(detalle)
    res = {"n": n, "no_indexables": sum(d["n_relevantes"] == 0 for d in detalle),
           "mrr@10": sum(1 / d["rango"] for d in detalle if d["rango"] and d["rango"] <= 10) / n,
           "ms_busqueda": sum(f["ms"] for f in rankings) / n,
           "ms_reescritura": sum(f.get("reescritura", {}).get("ms", 0) for f in rankings) / n,
           "fallos_reescritura": sum(f.get("reescritura", {}).get("fallo", False) for f in rankings),
           "reintentos_reescritura": sum(max(0, f.get("reescritura", {}).get("intentos", 1) - 1)
                                          for f in rankings)}
    costes = [f["reescritura"].get("usd") for f in rankings if "reescritura" in f]
    res["usd_reescritura"] = (sum(costes) / n if costes and all(c is not None for c in costes)
                              else (None if costes else 0.0))
    for k in (1, 3, 5, 10):
        hits = sum(d["rango"] is not None and d["rango"] <= k for d in detalle)
        res[f"aciertos@{k}"] = f"{hits}/{n}"
        res[f"recall@{k}"] = hits / n
    return res


def _guardar_json(ruta: Path, valor) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(valor, ensure_ascii=False, indent=2), encoding="utf-8")


def _guardar_jsonl(ruta: Path, filas: list[dict]) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text("".join(json.dumps(f, ensure_ascii=False) + "\n" for f in filas), encoding="utf-8")


def preparar_retrieval(preguntas: list[dict], directorio: Path | None = None) -> Path:
    """Fija el protocolo y separa experimentos con datos/código/modelos distintos."""
    problemas = validar_golden(preguntas)
    if problemas:
        raise ValueError("Golden inválido: " + "; ".join(problemas))
    textos = textos_retrieval()
    no_indexables = [p["id"] for p in preguntas if p.get("ancla_texto") and not _relevantes(p, textos)]
    if no_indexables:
        raise ValueError(f"Anclas que no caben en el índice: {no_indexables}")
    from importlib.metadata import version
    protocolo = {"golden": preguntas, "modelo": config.MODELO_ID, "temperatura": config.TEMPERATURA,
                 "embeddings": retrieval.MODELO_EMBEDDINGS, "prefijo": retrieval.PREFIJO_CONSULTA_BGE,
                 "n_cand": config.RETRIEVAL_N_CAND, "k_rrf": config.RETRIEVAL_K_RRF,
                 "pesos": [1, 1], "bm25": [config.BM25_K1, config.BM25_B, config.BM25_EPSILON],
                 "tokenizer": config.RETRIEVAL_TOKENIZER, "prompt": retrieval.INSTRUCCIONES_BUSQUEDA,
                 "metrica": "ancla_normalizada_con_ticker_fy_item",
                 "filtros_paso3": "LLM corregido con entidades explícitas de la pregunta; sin golden",
                 "versiones": {n: version(n) for n in ("faiss-cpu", "sentence-transformers", "rank-bm25", "langchain")}}
    archivos = [config.INDICE / "corpus.faiss", config.INDICE / "chunks_meta.parquet",
                Path(retrieval.__file__), Path(__file__), Path(__file__).with_name("normalizacion.py")]
    protocolo["sha256"] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in archivos}
    huella = hashlib.sha256(json.dumps(protocolo, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    raiz = Path(directorio) if directorio is not None else config.RESULTADOS_RETRIEVAL
    destino = raiz / huella[:12]
    _guardar_json(destino / "configuracion.json", protocolo | {"huella": huella})
    return destino


def filtros_oraculo(p: dict) -> dict:
    return {"ticker": p["ticker"], "fiscal_year": p["fiscal_year"], "item": p["item_esperado"]}


def diagnosticar_filtros(busqueda: dict, p: dict) -> dict:
    fys = set(busqueda.get("fiscal_years") or [])
    esperados = {int(p["fiscal_year"])}
    if p["familia"] == "comparativa":
        esperados.add(int(p.get("fiscal_year_base") or (2024 if p["fiscal_year"] == 2025 else 2025)))
    valores = {"ticker": busqueda.get("ticker"), "fiscal_years": list(fys), "item": busqueda.get("item")}
    correctos = {"ticker": normalizar_ticker(valores["ticker"]) == p["ticker"],
                 "fiscal_years": fys == esperados, "item": retrieval._normalizar_item(valores["item"]) == p["item_esperado"]}
    return {campo: "ausente" if not valor else "ok" if correctos[campo] else "erroneo"
            for campo, valor in valores.items()}


PASOS_RETRIEVAL = ("0_denso", "1_filtro", "2_bm25", "3_reescritura", "d_solo_bm25", "d_rw_oraculo")


def medir_retrieval(preguntas: list[dict], paso: str, directorio: Path,
                   permitir_api: bool = False, reutilizar: bool = True,
                   ruta_cache: Path | None = None) -> list[dict]:
    """Mide un paso. La ausencia de caché LLM nunca produce un falso resultado final."""
    if paso not in PASOS_RETRIEVAL:
        raise ValueError(f"Paso desconocido: {paso}")
    directorio = Path(directorio)
    # Evita mezclar resultados si el golden o la configuración cambian entre celdas.
    if preparar_retrieval(preguntas, directorio.parent) != directorio:
        raise ValueError("El experimento ha cambiado: vuelve a ejecutar desde la primera celda")
    ruta = directorio / f"rankings_{paso}.jsonl"
    con_ancla = [p for p in preguntas if p.get("ancla_texto")]
    if reutilizar and ruta.is_file():
        guardados = cargar_golden(ruta)
        if [f["id"] for f in guardados] != [p["id"] for p in con_ancla]:
            raise ValueError("Los rankings guardados no corresponden a las preguntas")
        detalle_retrieval(guardados, preguntas)
        if not any(f.get("reescritura", {}).get("fallo") for f in guardados):
            return guardados
        if not permitir_api:
            raise retrieval.ReescrituraPendiente(
                "Los rankings contienen reescrituras fallidas. Activa EJECUTAR para reintentarlas.")
    reescrituras = {}
    if paso in ("3_reescritura", "d_rw_oraculo"):
        for p in con_ancla:
            reescrituras[p["id"]] = retrieval.reescribir(p["pregunta"], permitir_api, ruta_cache)
            fallo = reescrituras[p["id"]].get("error")
            if fallo in retrieval.ERRORES_PROVEEDOR_NO_REINTENTABLES:
                raise retrieval.ReescrituraPendiente(
                    f"Reescritura detenida en {p['id']}: {fallo}. "
                    "Revisa disponibilidad/cuota y vuelve a ejecutar con EJECUTAR=True. "
                    "Las reescrituras correctas ya están en caché; no se publican rankings parciales.")
    # Carga de recursos fuera del cronómetro; no mezcla tiempo de arranque y búsqueda.
    retrieval._cargar_recursos()
    retrieval._cargar_bm25()
    retrieval._ranking_denso_completo.cache_clear()
    filas = []
    for p in con_ancla:
        inicio = time.perf_counter()
        kw = filtros_oraculo(p)
        if paso == "0_denso":
            docs = retrieval.buscar_hibrido([p["pregunta"]], k=20, usar_bm25=False)
        elif paso == "1_filtro":
            docs = retrieval.buscar_hibrido([p["pregunta"]], k=20, usar_bm25=False, **kw)
        elif paso == "2_bm25":
            docs = retrieval.buscar_hibrido([p["pregunta"]], k=20, **kw)
        elif paso == "d_solo_bm25":
            docs = retrieval.buscar_bm25(p["pregunta"], k=20, **kw)
        elif paso == "3_reescritura":
            docs = retrieval.buscar_reescrita(reescrituras[p["id"]]["busqueda"], k=20)
        else:
            docs = retrieval.buscar_hibrido(reescrituras[p["id"]]["busqueda"]["consultas"], k=20, **kw)
        fila = {"id": p["id"], "item": p["item_esperado"], "familia": p["familia"],
                "ms": round(1000 * (time.perf_counter() - inicio), 3),
                "ranking": [d["chunk_id"] for d in docs]}
        if p["id"] in reescrituras:
            fila["reescritura"] = reescrituras[p["id"]]
            fila["filtros"] = diagnosticar_filtros(fila["reescritura"]["busqueda"], p)
            if fila["reescritura"].get("busqueda_llm") is not None:
                fila["filtros_llm"] = diagnosticar_filtros(fila["reescritura"]["busqueda_llm"], p)
        filas.append(fila)
    _guardar_jsonl(ruta, filas)
    return filas


def techos_retrieval(preguntas: list[dict]) -> list[dict]:
    """El techo híbrido es la unión de candidatos, antes de recortar la fusión."""
    textos, filas = textos_retrieval(), []
    meta = retrieval._leer_metadatos_cache()
    for p in preguntas:
        if not p.get("ancla_texto"):
            continue
        kw, rel = filtros_oraculo(p), _relevantes(p, textos)
        ids = set(meta.iloc[retrieval.candidatos(**kw)]["chunk_id"])
        d = {x["chunk_id"] for x in retrieval.buscar_hibrido([p["pregunta"]], k=20, usar_bm25=False, **kw)}
        b = {x["chunk_id"] for x in retrieval.buscar_bm25(p["pregunta"], k=20, **kw)}
        filas.append({"id": p["id"], "item": p["item_esperado"], "n_candidatos": len(ids),
                      "aleatorio@5": min(1, 5 / len(ids)) if ids else 0,
                      "techo_filtro": bool(rel & ids), "hit_denso@20": bool(rel & d),
                      "hit_bm25@20": bool(rel & b), "techo_hibrido": bool(rel & (d | b))})
    return filas


def exportar_retrieval(preguntas: list[dict], directorio: Path) -> dict[str, pd.DataFrame]:
    """Regenera tablas desde rankings, sin búsqueda ni llamadas al modelo. Sin Markdown."""
    tablas, por_item, filtros, detalles, pasos = [], [], [], [], {}
    for paso in PASOS_RETRIEVAL:
        ruta = directorio / f"rankings_{paso}.jsonl"
        if not ruta.is_file():
            continue
        filas = cargar_golden(ruta)
        pasos[paso] = filas
        tablas.append({"paso": paso, **resumir_retrieval(filas, preguntas)})
        detalle = detalle_retrieval(filas, preguntas)
        detalles.extend({"paso": paso, **d} for d in detalle)
        for item in sorted({d["item"] for d in detalle}):
            grupo = [d for d in detalle if d["item"] == item]
            hits = sum(d["rango"] is not None and d["rango"] <= 5 for d in grupo)
            por_item.append({"paso": paso, "item": item, "aciertos@5": f"{hits}/{len(grupo)}",
                             "recall@5": hits / len(grupo)})
        if paso == "3_reescritura":
            for campo in ("ticker", "fiscal_years", "item"):
                for estado in ("ok", "ausente", "erroneo"):
                    n = sum(f["filtros"][campo] == estado for f in filas)
                    filtros.append({"campo": campo, "estado": estado, "n": n, "porcentaje": 100 * n / len(filas)})
    cambios = []
    for anterior, posterior in zip(PASOS_RETRIEVAL[:3], PASOS_RETRIEVAL[1:4]):
        if anterior not in pasos or posterior not in pasos:
            continue
        antes = {d["id"]: d for d in detalle_retrieval(pasos[anterior], preguntas)}
        for d in detalle_retrieval(pasos[posterior], preguntas):
            a = antes[d["id"]]["rango"]
            b = d["rango"]
            delta = int(b is not None and b <= 5) - int(a is not None and a <= 5)
            cambios.append({"antes": anterior, "despues": posterior, "id": d["id"],
                            "rango_antes": a, "rango_despues": b,
                            "cambio": {1: "ganada", -1: "perdida", 0: "igual"}[delta]})
    resultado = {"escalera": pd.DataFrame(tablas), "por_item": pd.DataFrame(por_item),
                 "filtros": pd.DataFrame(filtros), "detalle": pd.DataFrame(detalles),
                 "cambios": pd.DataFrame(cambios)}
    for nombre, df in resultado.items():
        df.to_csv(directorio / f"{nombre}.csv", index=False)
    fallos = sum(f.get("reescritura", {}).get("fallo", False) for f in pasos.get("3_reescritura", []))
    _guardar_json(directorio / "resumen.json", {"completo": all(p in pasos for p in PASOS_RETRIEVAL[:4]) and not fallos,
                    "fallos_reescritura": fallos,
                    "pendientes": [p for p in PASOS_RETRIEVAL if p not in pasos], "pasos": tablas})
    return resultado


def diagnosticar_retrieval_agente(predicciones: list[dict], preguntas: list[dict]) -> pd.DataFrame:
    """Lee trayectorias existentes; jamás ejecuta el agente para obtenerlas."""
    por_id = {p["id"]: p for p in preguntas if p.get("ancla_texto")}
    filas = []
    for pred in predicciones:
        p = por_id.get(pred.get("id"))
        if p is None:
            continue
        obs = [o for o in pred.get("observaciones", []) if o.get("name") == "search_filings"]
        # Cada fragmento/observación se comprueba por separado, sin crear anclas al concatenar.
        hit = any(normalizar(p["ancla_texto"]) in normalizar(o.get("content", "")) for o in obs)
        llamadas = [t for t in pred.get("tool_calls", []) if t.get("name") == "search_filings"]
        if not llamadas:
            filas.append({"id": p["id"], "recall_agente": hit if "observaciones" in pred else None,
                          "llamada": None})
        for i, llamada in enumerate(llamadas, 1):
            a = llamada.get("args", {})
            try:
                fy = int(a["fiscal_year"]) if a.get("fiscal_year") is not None else None
            except (TypeError, ValueError):
                fy = -1
            estados = diagnosticar_filtros({**a, "fiscal_years": [fy] if fy is not None else []}, p)
            if fy is not None and fy in {p["fiscal_year"], p.get("fiscal_year_base")}:
                estados["fiscal_years"] = "ok"
            filas.append({"id": p["id"], "llamada": i,
                          "recall_agente": hit if "observaciones" in pred else None, **estados})
    return pd.DataFrame(filas)
