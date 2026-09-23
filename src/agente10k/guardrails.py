"""Guardrails del sistema final (docs/09): límites de llamadas (R04), verificación determinista de
cifras contra XBRL (R05), cita por frase numerada y abstención honesta ante huecos (R14).

Todo es código determinista y sin LLM. El modelo sigue decidiendo qué herramientas llama: este módulo
solo FILTRA (límites, duplicados), REPARA (argumentos con marcado, escala, orientación, ticker),
VERIFICA (cifras y citas contra lo que devolvieron las herramientas) y DEGRADA con honestidad; nunca
invoca herramientas por su cuenta ni fabrica ``tool_calls``.

Piezas
- ``middleware_final()``: pila ``ToolCallLimit(8)`` + ``ToolCallLimit(read_section, 1)`` +
  ``ModelCallLimit(10, end)`` + :class:`GuardrailsFinal` (ganchos ``wrap_tool_call``, ``before_model``,
  ``after_model`` y ``after_agent``).
- Ledger XBRL (:func:`libro_hechos`): qué devolvió cada ``get_xbrl_fact`` de la ejecución.
- Verificador (:func:`verificar_xbrl`): cifra/cifra_base/ejercicio/unidad/ticker/concepto frente al ledger.
- Cita por frase (:func:`numerar`, :func:`resolver_cita`): el modelo ve ``⟨n⟩`` delante de cada frase y
  devuelve ``frase_ids``; el sistema rellena ``cita`` y ``chunk_id`` LITERALES.
- ``fuente`` se DERIVA de la evidencia verificada (:func:`derivar_fuente`).
"""
from __future__ import annotations

import copy
import functools
import os
import re
from dataclasses import dataclass, field
from typing import Any, NotRequired

from langchain.agents.middleware import (
    AgentMiddleware, AgentState, ModelCallLimitMiddleware, ToolCallLimitMiddleware, hook_config,
)
from langchain.messages import AIMessage, HumanMessage, ToolMessage

from agente10k import datos
from agente10k.normalizacion import ESCALA, cifra_ok, cobertura, normalizar, normalizar_ticker

# ------------------------------------------------------------------ constantes
NOMBRES_TOOLS = ("list_available", "get_xbrl_fact", "search_filings", "read_section")
TOOLS_TEXTO = ("search_filings", "read_section")
TICKERS = ("NVDA", "MSFT", "AAPL", "GOOGL", "META", "AMZN")
UNIDADES_OK = ("USD", "USD/shares")
NOMBRE_ESQUEMA = "RespuestaFinanciera"

RUN_LIMIT_TOOLS = 8              # R04: llamadas a herramientas por invocación
RUN_LIMIT_READ_SECTION = 1       # una sección entera cuesta hasta 35.000 tokens
RUN_LIMIT_MODELO = 10            # corte duro (exit_behavior="end")
# Tope de la cita que emite el AGENTE. El <= 40 palabras de R07 se refiere al ancla del golden
# (docs/00 §4.3), no a esta cita: recortar a 40 partía frases a media oración y el juez marcaba
# como no respaldado lo que el informe sí decía (g3-012: la cita acababa en "business, reputation,
# financial" y la respuesta afirmaba "...y resultados operativos"). Medido: la pieza más larga que
# genera el sistema son 114 palabras (una fila de tabla del MD&A), así que 120 cubre las tablas y
# sigue cortando una "frase" patológica.
MAX_PALABRAS_PIEZA = 120
MAX_PIEZAS_CITA = 3
UMBRAL_ENCAJE_CITA = 0.6         # cobertura 4-gramas para "reparar" una cita casi literal

MARCA = "[GUARDRAIL]"            # los reintentos dejan esta marca en el historial (1 por causa)
MARCA_ESQUEMA = f"{MARCA} esquema"
MARCA_CONTENIDO = f"{MARCA} contenido"
MSG_REPETIDA = ("Llamada repetida: ya tienes ese resultado más arriba. Responde con lo que tienes; "
                "si el dato no existe, fuente='ninguna'.")
# Un aviso sin contenido deja al modelo sin nada que citar y puede encerrarlo en un bucle: repitió
# nueve veces la misma búsqueda, agotó el límite y se rindió sin cita. Recordarle qué frases ya
# tiene numeradas le da la salida sin volver a gastar la herramienta ni reenviar el fragmento.
MSG_REPETIDA_CON_FRASES = (MSG_REPETIDA + " Las frases numeradas que ya tienes de esa misma llamada "
                           "van de ⟨{primera}⟩ a ⟨{ultima}⟩: elige frase_ids entre ellas y responde ahora.")
TEXTO_DEGRADADA = ("No he podido verificar la cifra contra los datos XBRL del 10-K, "
                   "así que prefiero no darla.")
TEXTO_SIN_EVIDENCIA = "No verificada: "
FALLBACK_TEXTO = "No se pudo completar la respuesta."

MARCA_FRASE = re.compile(r"⟨\d+⟩ ?")
_ELISION = re.compile(r"\s*(?:\[\.\.\.\]|\.\.\.|…)\s*")
_SEP_BLOQUES = "\n\n---\n\n"
_BLOQUE = re.compile(
    r"^\[([^\]\s]+)\] (\w+) FY(\d{4}) Item (\w+)(?: · [^\n]*)?\n", re.M)     # cabecera de un fragmento
_CAB_SEC = re.compile(r"^\[(\w+) FY(\d{4}) Item (\w+) · [^\]]*\][^\n]*\n\n")
_NOTA_HERRAMIENTA = re.compile(r"\n\n\((?:Filtros inferidos|con los filtros)[^\n]*\)\s*$")   # cola de search_filings
_FIN_FRASE = re.compile(r"(?<=[.!?;:])\s+(?=[A-Z0-9“\"(•\$])")

ETIQUETAS = {
    "Assets": "activos totales", "Liabilities": "pasivo total",
    "StockholdersEquity": "patrimonio neto",
    "CashAndCashEquivalentsAtCarryingValue": "caja y equivalentes",
    "NetIncomeLoss": "beneficio neto", "OperatingIncomeLoss": "resultado operativo",
    "GrossProfit": "beneficio bruto", "ResearchAndDevelopmentExpense": "gasto en I+D",
    "NetCashProvidedByUsedInOperatingActivities": "flujo de caja operativo",
    "EarningsPerShareBasic": "BPA básico", "EarningsPerShareDiluted": "BPA diluido",
    "Revenues": "ingresos totales",
    "RevenueFromContractWithCustomerExcludingAssessedTax": "ingresos totales",
}


# ------------------------------------------------------------------ accesos a datos (perezosos)
@functools.lru_cache(maxsize=1)
def _conceptos() -> frozenset[str]:
    return frozenset(str(c) for c in datos.cargar_xbrl()["concept"].unique())


@functools.lru_cache(maxsize=1)
def _chunks_por_seccion() -> dict[tuple[str, int, str], list[tuple[str, str]]]:
    salida: dict[tuple[str, int, str], list[tuple[str, str]]] = {}
    for r in datos.cargar_chunks().to_dict("records"):
        clave = (str(r["ticker"]), int(r["fiscal_year"]), str(r["item"]))
        salida.setdefault(clave, []).append((str(r["chunk_id"]), normalizar(r["texto"])))
    return salida


def _fy(x: Any) -> int | None:
    try:
        return int(x)
    except (TypeError, ValueError):
        return None


_TXT_VALOR = re.compile(r"^([A-Z][A-Z0-9.]*) FY(\d{4}) · (\w+) = ")             # get_xbrl_fact con valor
_TXT_HUECO = re.compile(r"^([A-Z][A-Z0-9.]*) no reportó '(\w+)' en FY(\d{4})")   # hueco o sugerencia


def _fy_arg(x: Any) -> int | None:
    """Ejercicio de un argumento de herramienta: 2024, '2024' o 'FY2024'."""
    v = _fy(x)
    if v is not None:
        return v
    m = re.search(r"(?<!\d)(20\d\d)(?!\d)", str(x or ""))
    return int(m.group(1)) if m else None


def _canon_concepto(c: Any) -> str:
    """Nombre XBRL exacto de un concepto pedido con alias (prefijo us-gaap:, minúsculas, español)."""
    c = str(c or "").strip()
    if not c or c in _conceptos():
        return c
    try:
        from agente10k import herramientas

        canon, _ = herramientas._resolver_concepto(c, sorted(_conceptos()))
        return canon or c
    except Exception:  # pragma: no cover - el ledger no debe romperse por el resolutor
        return c


def _texto(m: Any) -> str:
    """Texto plano de un mensaje (los bloques de contenido se aplanan)."""
    c = getattr(m, "content", "")
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        return " ".join(b.get("text", "") if isinstance(b, dict) else str(b) for b in c)
    return str(c or "")


# ------------------------------------------------------------------ argumentos corruptos y firmas
def sanear_args(args: dict) -> tuple[dict, bool]:
    """Repara argumentos con marcado filtrado por el proveedor.

    Caso real (baseline g3-011): ``ticker='AMZN", "fiscal_year": 2025, "item": "7"}}]</think>...'``.
    Se conserva el primer token válido y se recuperan ticker/fiscal_year/item/k incrustados.
    """
    out, tocado, extra = dict(args or {}), False, {}
    for k, v in list((args or {}).items()):
        if isinstance(v, str) and k != "query" and re.search(r"[\"<>{}]|</?\w+_?\w*>", v):
            limpio = re.match(r"\s*([A-Za-z0-9.]+)", v)
            out[k] = limpio.group(1) if limpio else v
            tocado = True
            for kk, vv in re.findall(r"\"(fiscal_year|item|k|ticker|concept)\"\s*:\s*\"?([A-Za-z0-9.]+)", v):
                extra.setdefault(kk, vv)
    for kk, vv in extra.items():
        if kk not in out or out[kk] in (None, ""):
            out[kk] = int(vv) if kk in ("fiscal_year", "k") and vv.isdigit() else vv
    for kk in ("fiscal_year", "k"):
        if tocado and isinstance(out.get(kk), str) and out[kk].isdigit():
            out[kk] = int(out[kk])
    return out, tocado


def firma(tc: dict) -> tuple:
    """Firma normalizada de una llamada (mayúsculas, espacios y tipos): detecta duplicados."""
    a, _ = sanear_args(tc.get("args") or {})
    if "ticker" in a:
        a["ticker"] = normalizar_ticker(a["ticker"])
    if "query" in a:
        a["query"] = re.sub(r"\s+", " ", str(a["query"]).lower()).strip()
    for k in ("fiscal_year", "k"):
        if k in a:
            a[k] = _fy(a[k]) if _fy(a[k]) is not None else a[k]
    if "item" in a and isinstance(a["item"], str):
        a["item"] = a["item"].upper().removeprefix("ITEM").strip().rstrip(".")
    return tc.get("name"), tuple(sorted((k, str(v)) for k, v in a.items() if v is not None))


# ------------------------------------------------------------------ ledger de get_xbrl_fact
@dataclass
class Hecho:
    """Lo que devolvió UNA llamada a get_xbrl_fact."""

    ticker: str | None
    fy: int | None
    concept: str
    status: str           # valor | hueco | sugerencia | error | bloqueada | omitida
    valor: float | None = None
    unidad: str | None = None
    texto: str = ""


def _estado_desde_parquet(ticker, fy, concepto):
    r = datos.valor_xbrl(ticker, fy, concepto) if ticker and fy else None
    if r is not None:
        return "valor", r[0], r[1]
    if ticker in TICKERS and fy in (2024, 2025) and concepto in _conceptos():
        return "hueco", None, None
    return "error", None, None


def libro_hechos(mensajes: list) -> list[Hecho]:
    """Un :class:`Hecho` por cada get_xbrl_fact de la ejecución.

    El VALOR sale siempre del parquet por los argumentos (el texto del ToolMessage puede cambiar entre
    versiones); el ToolMessage decide el ESTADO (valor, hueco, sugerencia, bloqueada por límite...).
    Sin ToolMessage (el modelo respondió en el mismo mensaje) se decide por el parquet.
    """
    resultados = {m.tool_call_id: _texto(m) for m in mensajes if isinstance(m, ToolMessage)}
    salida: list[Hecho] = []
    for m in mensajes:
        if not isinstance(m, AIMessage):
            continue
        for tc in m.tool_calls or []:
            if tc.get("name") != "get_xbrl_fact":
                continue
            a, _ = sanear_args(tc.get("args") or {})
            t = normalizar_ticker(a.get("ticker")) or None
            fy, c = _fy_arg(a.get("fiscal_year")), _canon_concepto(a.get("concept", ""))
            txt = resultados.get(tc.get("id"))
            # La herramienta acepta alias ('us-gaap:GrossProfit', 'beneficio bruto', 'FY2024'): su respuesta
            # dice qué (ticker, ejercicio, concepto) resolvió; el ledger usa esa clave canónica.
            canon = (_TXT_VALOR.match(txt) or _TXT_HUECO.match(txt)) if txt else None
            if canon is not None:
                if canon.re is _TXT_VALOR:
                    t, fy, c = canon.group(1), int(canon.group(2)), canon.group(3)
                else:
                    t, c, fy = canon.group(1), canon.group(2), int(canon.group(3))
            if txt is None:
                st, v, u = _estado_desde_parquet(t, fy, c)
            elif txt.startswith("Llamada repetida"):
                st, v, u = "omitida", None, None
            elif "limit exceeded" in txt.lower() or "limit reached" in txt.lower():
                st, v, u = "bloqueada", None, None
            elif "Valor sin escalar" in txt:
                r = datos.valor_xbrl(t, fy, c)
                st, v, u = ("valor", r[0], r[1]) if r else ("error", None, None)
            elif "no reportó" in txt and "Vuelve a llamar" in txt:
                st, v, u = "sugerencia", None, None
            elif "no reportó" in txt or txt.startswith("No hay datos"):
                st, v, u = "hueco", None, None
            else:
                st, v, u = "error", None, None
            salida.append(Hecho(t, fy, c, st, v, u, txt or ""))
    return salida


# ------------------------------------------------------------------ frases numeradas
def trocear(texto: str) -> list[str]:
    """Divide en frases: párrafos/viñetas y cortes tras . ! ? ; : seguidos de mayúscula o cifra."""
    frases: list[str] = []
    for par in re.split(r"\n\s*\n|\n(?=[•·-])", texto):
        par = re.sub(r"\s*\n\s*", " ", par).strip()
        if par:
            frases += [f.strip() for f in _FIN_FRASE.split(par) if f.strip()]
    return frases


def siguiente_id(mensajes: list) -> int:
    mx = 0
    for m in mensajes:
        if isinstance(m, ToolMessage):
            for n in re.findall(r"⟨(\d+)⟩", _texto(m)):
                mx = max(mx, int(n))
    return mx + 1


def _marcar_cuerpo(cuerpo: str, n: int) -> tuple[str, int]:
    salida = []
    for par in cuerpo.split("\n\n"):
        frases = trocear(par)
        if len(frases) <= 1 and len(par.split()) < 6:
            salida.append(par)
            continue
        piezas = []
        for f in frases:
            if len(f.split()) >= 6:
                piezas.append(f"⟨{n}⟩ {f}")
                n += 1
            else:
                piezas.append(f)
        salida.append(" ".join(piezas))
    return "\n\n".join(salida), n


def numerar(contenido: str, nombre: str, desde: int = 1) -> str:
    """Antepone ``⟨n⟩`` a cada frase de >= 6 palabras de una observación de search_filings/read_section.

    Se numera solo lo que ve el modelo: el sistema guarda el original SIN marcas (``artifact``).
    """
    n = desde
    if nombre == "search_filings":
        nota = _NOTA_HERRAMIENTA.search(contenido)      # metadatos de la herramienta: no son texto del informe
        cola = contenido[nota.start():] if nota else ""
        contenido = contenido[:nota.start()] if nota else contenido
        partes, pos = [], 0
        for m in _BLOQUE.finditer(contenido):
            fin = contenido.find(_SEP_BLOQUES, m.end())
            fin = len(contenido) if fin == -1 else fin
            cuerpo, n = _marcar_cuerpo(contenido[m.end():fin], n)
            partes.append(contenido[pos:m.end()] + cuerpo)
            pos = fin
        return "".join(partes) + contenido[pos:] + cola
    m = _CAB_SEC.match(contenido)
    if not m:
        return contenido
    cuerpo, _ = _marcar_cuerpo(contenido[m.end():], n)
    return contenido[:m.end()] + cuerpo


def quitar_marcas(texto: str) -> str:
    return MARCA_FRASE.sub("", texto or "")


def original(m: ToolMessage) -> str:
    """Texto de la observación tal como lo devolvió la herramienta (sin marcas ⟨n⟩)."""
    art = getattr(m, "artifact", None)
    return art if isinstance(art, str) else quitar_marcas(_texto(m))


@dataclass
class Frase:
    id: int
    texto: str
    chunk_id: str | None
    ticker: str | None
    fy: int | None
    item: str | None


def _chunk_de(pieza_norm: str, ticker, fy, item) -> str | None:
    chunks = _chunks_por_seccion().get((ticker, fy, item), [])
    cid = next((c for c, t in chunks if pieza_norm in t), None)
    if cid is None and len(pieza_norm) > 60:              # frase a caballo entre dos fragmentos
        cid = next((c for c, t in chunks if pieza_norm[:60] in t), None)
    return cid


_RE_FRASE_NUM = re.compile(r"⟨(\d+)⟩ (.+?)(?=\s⟨\d+⟩ |\n\n|$)", re.S)


def _aviso_repetida(mensajes: list) -> str:
    """Aviso de llamada repetida, recordando el rango de frases ya numeradas si lo hay."""
    ids = sorted(indice_frases(mensajes))
    if not ids:
        return MSG_REPETIDA
    return MSG_REPETIDA_CON_FRASES.format(primera=ids[0], ultima=ids[-1])


def indice_frases(mensajes: list) -> dict[int, Frase]:
    """id -> :class:`Frase`, reconstruido de las observaciones numeradas que vio el modelo."""
    idx: dict[int, Frase] = {}
    for m in mensajes:
        if not (isinstance(m, ToolMessage) and m.name in TOOLS_TEXTO):
            continue
        c = _texto(m)
        if m.name == "search_filings":
            for b in _BLOQUE.finditer(c):
                fin = c.find(_SEP_BLOQUES, b.end())
                cuerpo = c[b.end(): len(c) if fin == -1 else fin]
                for mm in _RE_FRASE_NUM.finditer(cuerpo):
                    idx[int(mm.group(1))] = Frase(int(mm.group(1)), re.sub(r"\s+", " ", mm.group(2)).strip(),
                                                  b.group(1), b.group(2), int(b.group(3)), b.group(4))
        else:
            h = _CAB_SEC.match(c)
            if not h:
                continue
            t, fy, it = h.group(1), int(h.group(2)), h.group(3)
            for mm in _RE_FRASE_NUM.finditer(c[h.end():]):
                f = re.sub(r"\s+", " ", mm.group(2)).strip()
                idx[int(mm.group(1))] = Frase(int(mm.group(1)), f, _chunk_de(normalizar(f), t, fy, it), t, fy, it)
    return idx


def observaciones_texto(mensajes: list) -> list[dict]:
    """Observaciones de search_filings/read_section SIN marcas (lo que ve el evaluador)."""
    return [{"name": m.name, "tool_call_id": m.tool_call_id, "content": original(m)}
            for m in mensajes if isinstance(m, ToolMessage) and m.name in TOOLS_TEXTO]


def _bloques_vistos(obs: list[dict]) -> list[tuple[str | None, str | None, int | None, str | None, str]]:
    """(chunk_id, ticker, fy, item, cuerpo normalizado) de cada fragmento o sección visto."""
    salida = []
    for o in obs:
        c = o.get("content", "")
        if o.get("name") == "search_filings":
            for b in _BLOQUE.finditer(c):
                fin = c.find(_SEP_BLOQUES, b.end())
                salida.append((b.group(1), b.group(2), int(b.group(3)), b.group(4),
                               normalizar(c[b.end(): len(c) if fin == -1 else fin])))
        else:
            h = _CAB_SEC.match(c)
            if h:
                salida.append((None, h.group(1), int(h.group(2)), h.group(3), normalizar(c[h.end():])))
    return salida


def _ubicar(pieza_norm: str, obs: list[dict]) -> tuple[str | None, str | None, int | None]:
    """(chunk_id, ticker, fy) del primer fragmento/sección visto que contiene la pieza."""
    for cid, t, fy, it, cuerpo in _bloques_vistos(obs):
        if pieza_norm in cuerpo:
            return cid or _chunk_de(pieza_norm, t, fy, it), t, fy
    return None, None, None


def recortar(frase: str, referencia: str = "", max_palabras: int = MAX_PALABRAS_PIEZA) -> str:
    """Ventana literal de <= max_palabras: la que más comparte con ``referencia`` (o el inicio)."""
    palabras = frase.split()
    if len(palabras) <= max_palabras:
        return frase
    ref = set(re.findall(r"\w+", normalizar(referencia)))
    mejor, mejor_i = -1, 0
    for i in range(0, len(palabras) - max_palabras + 1):
        p = sum(w in ref for w in re.findall(r"\w+", normalizar(" ".join(palabras[i:i + max_palabras]))))
        if p > mejor:
            mejor, mejor_i = p, i
    return " ".join(palabras[mejor_i:mejor_i + max_palabras])


def _pieza_literal(texto: str, referencia: str, vistas: str) -> str:
    """Pieza de cita lo más completa posible, garantizando que sigue siendo literal de lo visto.

    Con el tope amplio una "frase" puede haberse reconstruido cruzando dos fragmentos; en ese caso
    dejaría de existir en el corpus y el evaluador (a) la marcaría como inventada. Si la pieza larga
    no aparece literal en las observaciones, se retrocede a la ventana estrecha de 40 palabras.
    """
    pieza = recortar(texto, referencia)
    if not vistas or normalizar(pieza) in vistas:
        return pieza
    estrecha = recortar(texto, referencia, 40)
    # Si tampoco la ventana estrecha es literal, la cita está rota de todos modos: se conserva la
    # larga, que al menos le da al juez el contexto completo en lugar de un fragmento cortado.
    return estrecha if normalizar(estrecha) in vistas else pieza


# ------------------------------------------------------------------ importes de la prosa
_NUM = re.compile(r"(?<![\w.,])\$?\s?(\d{1,3}(?:[.,]\d{3})+(?:[.,]\d+)?|\d+(?:[.,]\d+)?)")
_ESC = re.compile(r"\s*(miles de millones|mil millones|billones|billions?|millones|mill[oó]n|millions?|bn\b|mm\b|m\b|b\b)")
_FACT = {"miles de millones": 1e9, "mil millones": 1e9, "billion": 1e9, "billions": 1e9, "bn": 1e9, "b": 1e9,
         "millones": 1e6, "millón": 1e6, "millon": 1e6, "million": 1e6, "millions": 1e6, "mm": 1e6, "m": 1e6,
         "billones": 1e12}


def _flt(s: str) -> float:
    if "," in s and "." in s:
        dec = "," if s.rfind(",") > s.rfind(".") else "."
        return float(s.replace("." if dec == "," else ",", "").replace(dec, "."))
    for sep in ",.":
        if sep in s:
            p = s.split(sep)
            if len(p) > 2 or (len(p[-1]) == 3 and p[0] != "0"):
                return float(s.replace(sep, ""))
            return float(s.replace(sep, "."))
    return float(s)


def importes_prosa(texto: str | None) -> list[dict]:
    """Importes en USD (con ``$`` o palabra de escala/USD) y porcentajes de la prosa; sin años."""
    t = (texto or "").replace("*", "")
    out = []
    for m in _NUM.finditer(t):
        num, despues = m.group(1), t[m.end():m.end() + 30].lower()
        antes = t[max(0, m.start() - 3):m.start()]
        try:
            if re.match(r"\s*(%|por ciento|puntos)", despues):
                out.append({"valor": _flt(num), "tipo": "%", "texto": m.group(0).strip()})
                continue
            esc = _ESC.match(despues)
            dolar = "$" in m.group(0) or "$" in antes
            if not (esc or dolar or re.match(r"\s*(usd|d[oó]lares)", despues)):
                continue
            if re.fullmatch(r"(19|20)\d\d", num) and not (esc or dolar):
                continue
            out.append({"valor": _flt(num) * (_FACT[esc.group(1)] if esc else 1.0), "tipo": "USD",
                        "texto": m.group(0).strip()})
        except (ValueError, KeyError):
            continue
    return out


def extraer_cifras(texto: str) -> list[float]:
    """Cifras en USD que afirma una respuesta, normalizadas a unidades (docs/09 §4). Los % no cuentan."""
    return [c["valor"] for c in importes_prosa(texto) if c["tipo"] == "USD"]


def _en_texto(valor: float, texto_norm: str) -> bool:
    """¿Aparece ``valor`` como literal (con 4 escalas posibles) en el texto normalizado?"""
    if not valor:
        return False
    for m in _NUM.finditer(texto_norm):
        try:
            x = _flt(m.group(1))
        except ValueError:
            continue
        if any(abs(x * f - valor) <= 1e-6 * abs(valor) for f in (1, 1e3, 1e6, 1e9)):
            return True
    return False


def _sin_estimacion(texto: str | None) -> bool:
    """Misma noción que el evaluador (d): sin magnitudes financieras ni cálculo de un dato no reportado."""
    try:
        from agente10k.evaluadores import sin_estimacion_financiera
        return bool(sin_estimacion_financiera(texto))
    except Exception:  # pragma: no cover - el evaluador no debe ser requisito de los guardrails
        return not importes_prosa(texto) and not re.search(
            r"\b(?:estim\w*|calcul\w*|aproxim\w*)\b", texto or "", re.I)


# ------------------------------------------------------------------ verificación XBRL
@dataclass
class Informe:
    resp: dict = field(default_factory=dict)
    problemas: list[tuple[str, str]] = field(default_factory=list)     # (código, detalle) -> no verificable
    modelo: list[str] = field(default_factory=list)                    # códigos que justifican un reintento
    reparaciones: list[tuple[str, str]] = field(default_factory=list)  # arreglos deterministas sin coste
    avisos: list[tuple[str, str]] = field(default_factory=list)        # informativos
    hueco: Hecho | None = None                                         # el hueco que invalida la respuesta


def _mas_cercano(valor, unidad, candidatos: list[Hecho]) -> Hecho | None:
    """El hecho cuyo valor (con la escala de ``unidad``) más se acerca a ``valor``; None si no hay candidatos.

    Sin esto, dos conceptos casi iguales (META FY2024: caja 43.889 y I+D 43.873 millones, 0,04 %) se resolvían
    por orden de consulta y una cifra correcta se «corregía» al hecho equivocado.
    """
    if not candidatos:
        return None
    f = next((f for clave, f in ESCALA if clave in normalizar(unidad)), 1.0)
    return min(candidatos, key=lambda h: abs(float(valor) * f - float(h.valor)))


def _hueco_representativo(huecos: list[Hecho], concepto: str | None) -> Hecho | None:
    if not huecos:
        return None
    return next((h for h in huecos if concepto and h.concept == concepto), huecos[-1] if concepto else huecos[0])


def verificar_xbrl(resp0: dict, hechos: list[Hecho], obs: list[dict]) -> Informe:
    """Contrasta cifra/cifra_base/ejercicio/unidad/ticker/concepto con el ledger. Determinista y sin LLM.

    Repara sin coste: ticker (alias/ausente), escala y unidad, orientación cifra<->cifra_base, cifra
    redondeada (se ajusta al valor exacto del ledger) y concepto. Marca como problema lo que solo el
    modelo puede resolver (valor distinto, ejercicio cruzado) o lo que obliga a abstenerse (hueco).
    """
    r = copy.deepcopy(resp0)
    inf = Informe(resp=r)
    P, R, A = inf.problemas, inf.reparaciones, inf.avisos
    valores = [h for h in hechos if h.status == "valor"]
    huecos = [h for h in hechos if h.status == "hueco"]
    soporte = normalizar(" ".join(o.get("content", "") for o in obs) + " " + quitar_marcas(r.get("cita") or ""))
    usa_texto = any(o.get("name") in TOOLS_TEXTO for o in obs)

    # ticker: alias o ausente
    if r.get("ticker"):
        nt = normalizar_ticker(r["ticker"])
        if nt != r["ticker"] and nt in TICKERS:
            R.append(("ticker_normalizado", f"{r['ticker']}->{nt}"))
            r["ticker"] = nt
    elif len({h.ticker for h in hechos if h.status in ("valor", "hueco")}) == 1:
        r["ticker"] = next(h.ticker for h in hechos if h.status in ("valor", "hueco"))
        R.append(("ticker_completado", r["ticker"]))

    # concepto que no existe en el corpus
    c = r.get("concept_xbrl")
    if c is not None and c not in _conceptos():
        A.append(("concepto_inventado", f"concept_xbrl='{c}' no existe en el corpus"))
        R.append(("concepto_anulado", str(c)))
        r["concept_xbrl"] = None

    # orientación declarada: cifra = ejercicio reciente
    e, eb = _fy(r.get("ejercicio")), _fy(r.get("ejercicio_base"))
    if e and eb and e < eb:
        r["ejercicio"], r["ejercicio_base"] = eb, e
        r["cifra"], r["cifra_base"] = r.get("cifra_base"), r.get("cifra")
        R.append(("orientacion_invertida", f"{e}<{eb}: intercambiadas"))

    def coincide(valor, fy=None, concepto=None):
        cand = [h for h in valores if fy is None or h.fy == fy]
        if concepto and any(h.concept == concepto for h in cand):
            cand = [h for h in cand if h.concept == concepto]
        return cand, [(h, cifra_ok(valor, r.get("unidad"), h.valor, h.unidad)) for h in cand]

    # orientación por el ledger: cifra coincide con el ejercicio anterior y cifra_base con el reciente
    if r.get("cifra") is not None and r.get("cifra_base") is not None and valores:
        a = [h for h in valores if cifra_ok(r["cifra"], r.get("unidad"), h.valor, h.unidad)["ok"]]
        b = [h for h in valores if cifra_ok(r["cifra_base"], r.get("unidad"), h.valor, h.unidad)["ok"]]
        if len(a) == 1 and len(b) == 1 and a[0].concept == b[0].concept and a[0].fy < b[0].fy:
            r["cifra"], r["cifra_base"] = r["cifra_base"], r["cifra"]
            r["ejercicio"], r["ejercicio_base"] = b[0].fy, a[0].fy
            R.append(("orientacion_invertida", f"ledger: FY{a[0].fy}<FY{b[0].fy}"))

    # cifra ausente pese a declarar xbrl/ambas: se rellena del ledger si es inequívoco
    if r.get("fuente") in ("xbrl", "ambas") and r.get("cifra") is None and valores:
        conceptos = {h.concept for h in valores}
        if r.get("concept_xbrl") in conceptos:
            conceptos = {r["concept_xbrl"]}
        if len(conceptos) == 1:
            hs = sorted({(h.fy, h.valor, h.unidad, h.concept) for h in valores if h.concept in conceptos},
                        key=lambda x: -x[0])
            if _sin_importes_sin_soporte(r, hechos, obs):       # la prosa no contradice al ledger
                r["cifra"], r["unidad"], r["ejercicio"], r["concept_xbrl"] = hs[0][1], hs[0][2], hs[0][0], hs[0][3]
                R.append(("cifra_rellenada", f"{hs[0][3]} FY{hs[0][0]}"))
                if len(hs) > 1 and r.get("cifra_base") is None:
                    r["cifra_base"], r["ejercicio_base"] = hs[1][1], hs[1][0]
                    R.append(("cifra_base_rellenada", f"FY{hs[1][0]}"))

    def contrastar(campo: str, fy_campo: str) -> None:
        valor, fy = r.get(campo), _fy(r.get(fy_campo))
        cand, res = coincide(valor, fy, r.get("concept_xbrl"))
        ok = _mas_cercano(valor, r.get("unidad"), [h for h, x in res if x["ok"]])
        if ok is None:                                               # error de escala: se corrige a mano
            esc = next((h for h, x in res if "error_escala" in x.get("motivo", "")), None)
            if esc is not None:
                R.append(("escala_corregida", f"{campo}: {valor}->{esc.valor:,.0f}"))
                ok = esc
        if ok is None:                                               # ¿otro hecho consultado?
            otros = [h for h in valores if cifra_ok(valor, r.get("unidad"), h.valor, h.unidad)["ok"]
                     and h not in cand]
            mismo_fy = [h for h in otros if fy is None or h.fy == fy]
            if mismo_fy:                                             # mismo ejercicio, otro concepto consultado
                ok = _mas_cercano(valor, r.get("unidad"), mismo_fy)
                R.append(("concepto_corregido", f"{r.get('concept_xbrl')}->{ok.concept}"))
                r["concept_xbrl"] = ok.concept
            elif otros:                                              # ejercicio cruzado: solo el modelo decide
                h = otros[0]
                P.append(("ejercicio_cruzado", f"{campo}={valor:,} es {h.concept} FY{h.fy}, no FY{fy}"))
                inf.modelo.append("ejercicio_cruzado")
                return
        if ok is not None:
            if r.get(campo) != ok.valor:
                R.append(("cifra_exacta", f"{campo}: {r.get(campo)}->{ok.valor}"))
            r[campo] = ok.valor
            if r.get("unidad") != ok.unidad:
                R.append(("unidad_normalizada", f"{r.get('unidad')}->{ok.unidad}"))
                r["unidad"] = ok.unidad
            if campo == "cifra" and (not r.get("concept_xbrl") or r["concept_xbrl"] != ok.concept):
                if r.get("concept_xbrl") and r["concept_xbrl"] not in {h.concept for h in valores}:
                    R.append(("concepto_corregido", f"{r['concept_xbrl']}->{ok.concept}"))
                r["concept_xbrl"] = ok.concept
            if r.get(fy_campo) is None:
                r[fy_campo] = ok.fy
                R.append(("ejercicio_completado", f"{fy_campo}={ok.fy}"))
            return
        # sin respaldo en el ledger
        if _en_texto(valor, soporte):
            A.append(("cifra_de_texto", f"{campo}={valor}: aparece en el texto, no en XBRL"))
            R.append(("cifra_no_xbrl_anulada", f"{campo}={valor}"))
            r[campo] = None
            return
        if huecos:
            P.append(("cifra_de_dato_no_reportado",
                      f"{campo}={valor}: get_xbrl_fact dijo 'no reportó' y la cifra no sale de XBRL"))
            inf.hueco = inf.hueco or _hueco_representativo(huecos, r.get("concept_xbrl"))
            return
        if not valores:
            if usa_texto:                                            # extractiva: no es una cifra XBRL
                R.append(("cifra_no_xbrl_anulada", f"{campo}={valor}: sin get_xbrl_fact"))
                r[campo] = None
                return
            P.append(("cifra_sin_get_xbrl_fact", f"{campo}={valor}: ningún get_xbrl_fact devolvió valor"))
            inf.modelo.append("cifra_sin_get_xbrl_fact")
            return
        P.append(("cifra_sin_respaldo", f"{campo}={valor:,} no coincide con "
                  + "; ".join(f"{h.concept} FY{h.fy}={h.valor:,.2f}" for h in cand[:3])))
        inf.modelo.append("cifra_sin_respaldo")

    if r.get("cifra") is not None:
        contrastar("cifra", "ejercicio")
    if r.get("cifra_base") is not None:
        contrastar("cifra_base", "ejercicio_base")
    if r.get("cifra_base") is None and r.get("ejercicio_base") is not None and r.get("cifra") is None:
        r["ejercicio_base"] = None

    # unidad válida cuando hay cifra
    if r.get("cifra") is not None and r.get("unidad") not in UNIDADES_OK and valores:
        h = next((x for x in valores if cifra_ok(r["cifra"], None, x.valor, x.unidad)["ok"]), None)
        if h:
            R.append(("unidad_normalizada", f"{r.get('unidad')}->{h.unidad}"))
            r["unidad"] = h.unidad

    # concepto declarado que la herramienta dijo 'no reportó' y sin valor propio
    cc = r.get("concept_xbrl")
    if cc and any(h.concept == cc for h in huecos) and not any(h.concept == cc for h in valores):
        if r.get("cifra") is not None or r.get("fuente") in ("xbrl", "ambas"):
            P.append(("concepto_no_reportado", f"{cc}: la herramienta dijo que no lo reportó"))
            inf.hueco = inf.hueco or _hueco_representativo(huecos, cc)
        else:
            r["concept_xbrl"] = None

    # ejercicio incoherente con el hecho que respalda la cifra (cifra ya verificada)
    if r.get("cifra") is not None and not P:
        fys = {h.fy for h in valores if cifra_ok(r["cifra"], r.get("unidad"), h.valor, h.unidad)["ok"]}
        if fys and _fy(r.get("ejercicio")) not in fys:
            R.append(("ejercicio_corregido", f"{r.get('ejercicio')}->{max(fys)}"))
            r["ejercicio"] = max(fys)

    # importes de la prosa sin respaldo (XBRL, cita u observaciones): informativo
    vals = [h.valor for h in valores]
    difs = [abs(a - b) for a in vals for b in vals if a != b]
    for imp in importes_prosa(r.get("respuesta")):
        if imp["tipo"] != "USD":
            continue
        v = imp["valor"]
        if any(abs(v - x) <= 0.005 * max(abs(x), 1) for x in vals + difs) or _en_texto(v, soporte):
            continue
        A.append(("importe_prosa_sin_respaldo", f"{imp['texto']} (= {v:,.0f})"))

    # hueco puro: solo 'no reportó', y la respuesta declara un dato XBRL que no existe
    if huecos and not valores and r.get("fuente") == "xbrl" and inf.hueco is None:
        P.append(("hueco_no_respetado", f"{huecos[0].concept}: 'no reportó' pero fuente='xbrl'"))
        inf.hueco = _hueco_representativo(huecos, r.get("concept_xbrl"))
    return inf


# ------------------------------------------------------------------ cita literal
def resolver_cita(r: dict, mensajes: list, obs: list[dict]) -> tuple[dict, list[tuple[str, str]], list[tuple[str, str]]]:
    """Resuelve ``frase_ids`` -> ``cita``/``chunk_id`` literales o verifica la cita textual del modelo.

    Devuelve (respuesta, problemas, reparaciones). Un problema aquí justifica un reintento: el modelo
    debe elegir frases visibles. La cita resultante SIEMPRE es literal de lo que vieron las herramientas.
    """
    r = dict(r)
    P: list[tuple[str, str]] = []
    R: list[tuple[str, str]] = []
    ids = [int(i) for i in (r.get("frase_ids") or []) if _fy(i) is not None]
    idx = indice_frases(mensajes)
    vistas = normalizar(" ".join(o.get("content", "") for o in obs))
    referencia = r.get("respuesta") or ""

    if ids:
        validos = [i for i in dict.fromkeys(ids) if i in idx]
        if validos:
            frases = [idx[i] for i in validos[:MAX_PIEZAS_CITA]]
            r["cita"] = " [...] ".join(_pieza_literal(f.texto, referencia, vistas) for f in frases)
            r["chunk_id"] = frases[0].chunk_id
            _alinear_ticker_ejercicio(r, frases[0], R)
            R.append(("cita_resuelta", f"frase_ids={validos[:MAX_PIEZAS_CITA]}"))
            return r, P, R
        P.append(("frase_inexistente", f"frase_ids={ids} no corresponden a frases numeradas visibles"))
        r["cita"] = r["chunk_id"] = None
        return r, P, R

    cita = quitar_marcas(r.get("cita") or "").strip()
    if not cita:
        r["cita"] = r["chunk_id"] = None
        return r, P, R
    piezas = [normalizar(x) for x in _ELISION.split(cita) if normalizar(x)]
    if piezas and all(x in vistas for x in piezas):
        cid, t, fy = _ubicar(piezas[0], obs)
        if cid and r.get("chunk_id") != cid:
            R.append(("chunk_id_corregido", f"{r.get('chunk_id')}->{cid}"))
            r["chunk_id"] = cid
        r["cita"] = cita
        return r, P, R
    mejor = max(idx.values(), key=lambda f: cobertura(cita, f.texto), default=None)
    if mejor is not None and cobertura(cita, mejor.texto) >= UMBRAL_ENCAJE_CITA:
        R.append(("cita_encajada", f"cobertura={cobertura(cita, mejor.texto):.2f}"))
        r["cita"], r["chunk_id"] = recortar(mejor.texto, referencia), mejor.chunk_id
        _alinear_ticker_ejercicio(r, mejor, R)
        return r, P, R
    P.append(("cita_no_literal", "la cita no aparece literalmente en ninguna observación visible"))
    r["cita"] = r["chunk_id"] = None
    return r, P, R


def _alinear_ticker_ejercicio(r: dict, f: Frase, R: list) -> None:
    """La cita fija dónde está la evidencia: completa ticker/ejercicio ausentes (y los corrige si no
    hay cifra, porque entonces no hay otra cosa a la que se refieran)."""
    sin_cifra = r.get("cifra") is None and r.get("cifra_base") is None
    if f.ticker and (not r.get("ticker") or (sin_cifra and normalizar_ticker(r["ticker"]) != f.ticker)):
        R.append(("ticker_de_la_cita", f"{r.get('ticker')}->{f.ticker}"))
        r["ticker"] = f.ticker
    if f.fy and (r.get("ejercicio") is None or (sin_cifra and _fy(r.get("ejercicio")) != f.fy)):
        R.append(("ejercicio_de_la_cita", f"{r.get('ejercicio')}->{f.fy}"))
        r["ejercicio"] = f.fy


# ------------------------------------------------------------------ fuente derivada, abstención y degradación
def derivar_fuente(r: dict) -> str:
    """``fuente`` según la evidencia verificada: cifra XBRL y/o cita literal (docs/09, d)."""
    xbrl, texto = r.get("cifra") is not None, bool((r.get("cita") or "").strip())
    return "ambas" if xbrl and texto else "xbrl" if xbrl else "texto" if texto else "ninguna"


def texto_hueco(h: Hecho | None) -> str:
    """Abstención de plantilla: sin importes ni verbos de estimación."""
    if h is None or not h.ticker and not h.fy:
        return "No reportado en el corpus: el dato solicitado no está en el corpus."
    ticker = h.ticker or "la empresa"
    fy = f" FY{h.fy}" if h.fy else ""
    return f"No reportado en XBRL para {ticker}{fy}: el dato no está en el corpus."


def abstencion(r: dict, h: Hecho | None) -> dict:
    """Respuesta de abstención honesta: fuente ninguna, sin cifras, sin cita."""
    d = dict(r)
    d.update(respuesta=texto_hueco(h), fuente="ninguna", cifra=None, cifra_base=None, unidad=None,
             concept_xbrl=None, ejercicio_base=None, cita=None, chunk_id=None, frase_ids=None)
    if h is not None:
        d["ticker"] = h.ticker or d.get("ticker")
        d["ejercicio"] = h.fy if h.fy else d.get("ejercicio")
    return d


def degradar(r: dict, motivo: str, hechos: list[Hecho], obs: list[dict]) -> dict:
    """Degradación honesta: quita lo no verificable (cifras, unidad, concepto) sin inventar nada.

    La prosa se sustituye por una frase que no afirma nada nuevo (era la que llevaba la cifra rechazada);
    la cita verificada, si la hay, se conserva y la fuente se deriva después de lo que quede.
    """
    d = dict(r)
    d.update(cifra=None, cifra_base=None, unidad=None, concept_xbrl=None, ejercicio_base=None,
             respuesta=TEXTO_DEGRADADA)
    return d


def limpiar_abstencion(r: dict, h: Hecho | None) -> tuple[dict, bool]:
    """fuente='ninguna': la prosa no puede traer importes ni estimaciones (R14)."""
    if r.get("fuente") != "ninguna":
        return r, False
    if r.get("cifra") is None and r.get("cifra_base") is None and _sin_estimacion(r.get("respuesta")) \
            and not [i for i in importes_prosa(r.get("respuesta")) if i["tipo"] == "USD"]:
        return r, False
    d = abstencion(r, h) if h is not None else dict(
        r, respuesta="El dato solicitado no figura en el corpus; no lo estimo.", cifra=None, cifra_base=None,
        unidad=None, concept_xbrl=None, ejercicio_base=None)
    return d, True


# ------------------------------------------------------------------ coherencia pregunta <-> herramienta
_EMPRESAS = {"NVDA": r"nvidia|nvda", "MSFT": r"microsoft|msft", "AAPL": r"apple|aapl",
             "GOOGL": r"alphabet|google|googl", "META": r"\bmeta\b|facebook", "AMZN": r"amazon|amzn"}
_LEXICO = {
    "Assets": r"activos?\b|total assets|\bassets\b",
    "Liabilities": r"pasivos?\b|liabilities",
    "StockholdersEquity": r"patrimonio|equity|fondos propios",
    "CashAndCashEquivalentsAtCarryingValue": r"\bcaja\b|efectivo y equivalentes|equivalentes de efectivo|\bcash\b",
    "NetIncomeLoss": r"beneficio neto|resultado neto|ganancia neta|utilidad neta|net income|ingreso neto|p[eé]rdida neta",
    "OperatingIncomeLoss": r"resultado operativo|beneficio operativo|ingreso operativo|utilidad operativa|operating income|resultado de explotaci[oó]n",
    "GrossProfit": r"beneficio bruto|utilidad bruta|resultado bruto|gross profit|margen bruto|gross margin",
    "ResearchAndDevelopmentExpense": r"i\s?\+\s?d\b|investigaci[oó]n y desarrollo|research and development|\br&d\b",
    "NetCashProvidedByUsedInOperatingActivities": r"flujo de caja operativo|flujo de efectivo operativo|flujos? de (?:caja|efectivo) (?:de|por|procedentes? de) (?:las )?(?:operaciones|actividades)|actividades de explotaci[oó]n|actividades operativas|operating cash",
    "EarningsPerShareBasic": r"por acci[oó]n|per share|\bbpa\b|\beps\b",
    "EarningsPerShareDiluted": r"por acci[oó]n|per share|\bbpa\b|\beps\b",
    "Revenues": r"ingresos|ventas|revenue|facturaci[oó]n|cifra de negocio",
    "RevenueFromContractWithCustomerExcludingAssessedTax": r"ingresos|ventas|revenue|facturaci[oó]n|cifra de negocio",
}
_DERIVADA = re.compile(r"m[aá]rgen|ratio|porcentaje|\d\s?%|crecimiento|variaci[oó]n|evoluci|compar|tasa\b|promedio|"
                       r"media\b|diferencia|cu[aá]nto m[aá]s|por ciento|por qu[eé]|explic|c[oó]mo|qu[eé] dice|"
                       r"riesgo|impacto|motivo|raz[oó]n|causa|tendencia|respecto|frente a|\by qu[eé]\b|suma|combinad|"
                       r"acumulad|crecid|cambi|crec(?:i|e)\w*|aument\w*|subi\w*|baj\w*|cay\w*|disminu\w*|mayor|menor|"
                       r"euros?|represent\w*|porcentual|relaci[oó]n|\bvs\b|versus|growth|increase|decrease|change|"
                       r"compare|percent|margin|ratio|why|how|explain", re.I)
# Magnitudes equivalentes entre sí (no cuentan como «otra magnitud» en la misma pregunta).
_GRUPO_LEXICO = {"EarningsPerShareBasic": "eps", "EarningsPerShareDiluted": "eps", "Revenues": "rev",
                 "RevenueFromContractWithCustomerExcludingAssessedTax": "rev"}


def _pide_otra_magnitud(q: str, concepto: str) -> bool:
    """¿Menciona la pregunta otra magnitud además de ``concepto``? (fuera de las palabras de la propia)."""
    grupo = _GRUPO_LEXICO.get(concepto, concepto)
    propios = [m.span() for m in re.finditer(_LEXICO[concepto], q)]
    for otro, pat in _LEXICO.items():
        if _GRUPO_LEXICO.get(otro, otro) == grupo:
            continue
        for m in re.finditer(pat, q):
            if not any(a <= m.start() and m.end() <= b for a, b in propios):
                return True
    return False


def pregunta_de(mensajes: list) -> str:
    for m in mensajes:
        if isinstance(m, HumanMessage) and MARCA not in _texto(m):
            return _texto(m)
    return ""


def concepto_coherente(pregunta: str, concepto: str, *, permitir_derivadas: bool = False) -> bool:
    """¿Pide la pregunta esa magnitud? Conservador: sin evidencia léxica clara, False."""
    q = normalizar(pregunta)
    if not permitir_derivadas and _DERIVADA.search(q):
        return False
    pat = _LEXICO.get(concepto)
    if not pat or not re.search(pat, q):
        return False
    if _pide_otra_magnitud(q, concepto):                 # «patrimonio y pasivo»: el modelo aún debe consultar la otra
        return False
    if concepto not in ("EarningsPerShareBasic", "EarningsPerShareDiluted") and re.search(r"por acci[oó]n|per share", q):
        return False
    if concepto == "EarningsPerShareBasic" and re.search(r"diluid", q):
        return False
    if concepto == "EarningsPerShareDiluted" and re.search(r"b[aá]sic", q):
        return False
    return True


def ticker_coherente(pregunta: str, ticker: str | None) -> bool:
    q = normalizar(pregunta)
    citadas = {t for t, pat in _EMPRESAS.items() if re.search(pat, q)}
    return len(citadas) == 1 and ticker in citadas


def ejercicio_coherente(pregunta: str, fy: int | None) -> bool:
    anos = {int(a) for a in re.findall(r"(?<!\d)(20\d\d)(?!\d)", pregunta or "")}
    return len(anos) == 1 and fy in anos


def _fmt_es(x: float, dec: int = 0) -> str:
    return f"{x:,.{dec}f}".replace(",", "\0").replace(".", ",").replace("\0", ".")


def formatear_valor(v: float, unidad: str | None) -> str:
    if unidad == "USD/shares":
        return f"{_fmt_es(v, 2)} USD por acción"
    if abs(v) >= 1e6 and abs(v) % 1e6 == 0:
        return f"{_fmt_es(v / 1e6)} millones de USD"
    return f"{_fmt_es(v)} USD"


# ------------------------------------------------------------------ middleware
class EstadoGuard(AgentState):
    guard: NotRequired[dict]


def _reintentos(mensajes: list, marca: str) -> int:
    return sum(isinstance(m, HumanMessage) and marca in _texto(m) for m in mensajes)


def _pidio_estructurada(ai: Any, nombre: str) -> bool:
    return isinstance(ai, AIMessage) and any(tc.get("name") == nombre for tc in ai.tool_calls or [])


def _pide_tools_reales(ai: Any) -> bool:
    return isinstance(ai, AIMessage) and any(tc.get("name") in NOMBRES_TOOLS for tc in ai.tool_calls or [])


def _ultimo_texto_modelo(mensajes: list) -> str:
    for m in reversed(mensajes):
        if isinstance(m, AIMessage) and _texto(m).strip():
            t = _texto(m).strip()
            if not re.match(r"(Tool call limit|Model call limit)", t, re.I):
                return t
    return ""


class GuardrailsFinal(AgentMiddleware):
    """Reparación de argumentos, numeración de frases, verificación XBRL/cita y salida garantizada."""

    state_schema = EstadoGuard

    def __init__(self, esquema: type | None = None, *, max_reintentos: int = 1, camino_rapido: bool = True,
                 numerar_frases: bool = True):
        super().__init__()
        self._esquema = esquema
        self.max_reintentos = max_reintentos
        self.camino_rapido = camino_rapido
        self.numerar_frases = numerar_frases

    @property
    def esquema(self) -> type:
        if self._esquema is None:                       # importación diferida: agente.py importa este módulo
            from agente10k.agente import RespuestaFinanciera
            self._esquema = RespuestaFinanciera
        return self._esquema

    def _nuevo(self, d: dict):
        campos = getattr(self.esquema, "model_fields", {})
        d = dict(d)
        for k in ("respuesta", "cita"):                 # el modelo puede copiar un ⟨n⟩ a la prosa o a la cita
            if isinstance(d.get(k), str):
                d[k] = quitar_marcas(d[k]).strip()
        return self.esquema(**{k: v for k, v in d.items() if k in campos})

    # ------------------------------------------------------------ herramientas: duplicados, args, numeración
    def wrap_tool_call(self, request, handler):
        tc = request.tool_call
        args, tocado = sanear_args(tc.get("args") or {})
        if tocado:
            tc = {**tc, "args": args}
            request = request.override(tool_call=tc)
        state = request.state
        mensajes = state.get("messages", []) if isinstance(state, dict) else getattr(state, "messages", [])
        respondidas = {m.tool_call_id for m in mensajes
                       if isinstance(m, ToolMessage) and not _texto(m).startswith("Llamada repetida")
                       and "limit exceeded" not in _texto(m).lower()}
        previas = {firma(t) for m in mensajes if isinstance(m, AIMessage) for t in (m.tool_calls or [])
                   if t.get("id") in respondidas and t.get("id") != tc.get("id")}
        if firma(tc) in previas:
            return ToolMessage(content=_aviso_repetida(mensajes), tool_call_id=tc["id"], name=tc["name"])
        res = handler(request)
        if (self.numerar_frases and isinstance(res, ToolMessage) and res.name in TOOLS_TEXTO
                and isinstance(res.content, str)):
            base = siguiente_id(mensajes)
            # llamadas paralelas: cada una arranca en un tramo distinto para que los ids no choquen
            ultimo = next((m for m in reversed(mensajes) if isinstance(m, AIMessage)), None)
            if ultimo is not None:
                pos = [t.get("id") for t in ultimo.tool_calls or [] if t.get("name") in TOOLS_TEXTO]
                if tc.get("id") in pos:
                    base += 5000 * pos.index(tc["id"])
            res = res.model_copy(update={"content": numerar(res.content, res.name, base),
                                         "artifact": res.content})
        return res

    # ------------------------------------------------------------ camino rápido (antes de la 2.ª llamada)
    @hook_config(can_jump_to=["end"])
    def before_model(self, state, runtime):
        if not self.camino_rapido or state.get("structured_response") is not None:
            return None
        mensajes = state["messages"]
        llamadas = [(m, tc) for m in mensajes if isinstance(m, AIMessage) for tc in m.tool_calls or []]
        if len(llamadas) != 1 or llamadas[0][1].get("name") != "get_xbrl_fact":
            return None
        if _reintentos(mensajes, MARCA) or not isinstance(mensajes[-1], ToolMessage):
            return None
        hechos = libro_hechos(mensajes)
        if len(hechos) != 1 or hechos[0].status not in ("valor", "hueco"):
            return None
        h, pregunta = hechos[0], pregunta_de(mensajes)
        if not (ticker_coherente(pregunta, h.ticker) and ejercicio_coherente(pregunta, h.fy)):
            return None
        if h.status == "valor":
            if not concepto_coherente(pregunta, h.concept):
                return None
            d = {"respuesta": (f"{h.ticker} FY{h.fy}: {ETIQUETAS.get(h.concept, h.concept)} = "
                               f"{formatear_valor(h.valor, h.unidad)} (concepto XBRL {h.concept})."),
                 "cifra": h.valor, "unidad": h.unidad, "ticker": h.ticker, "ejercicio": h.fy,
                 "fuente": "xbrl", "concept_xbrl": h.concept}
        else:
            if not concepto_coherente(pregunta, h.concept, permitir_derivadas=True):
                return None
            d = abstencion({"ticker": h.ticker, "ejercicio": h.fy}, h)
        guard = self._guard_base(state) | {"camino_rapido": True, "fuente_derivada": d["fuente"],
                                           "hueco": h.status == "hueco"}
        return {"structured_response": self._nuevo(d), "guard": guard, "jump_to": "end"}

    # ------------------------------------------------------------ verificación tras cada respuesta del modelo
    @hook_config(can_jump_to=["model"])
    def after_model(self, state, runtime):
        mensajes = state["messages"]
        # ToolStrategy añade un ToolMessage tras el AIMessage de la respuesta estructurada: se mira el último AIMessage
        ultimo = next((m for m in reversed(mensajes) if isinstance(m, AIMessage)), None)
        if ultimo is None:
            return None
        nombre = getattr(self._esquema, "__name__", NOMBRE_ESQUEMA)
        previa = state.get("structured_response")
        if _pide_tools_reales(ultimo):
            if _pidio_estructurada(ultimo, nombre) and previa is not None:
                # herramienta real + respuesta en el MISMO mensaje: el grafo ejecuta la herramienta y termina, así
                # que no hay segunda vuelta; se verifica igualmente (sin reintento) en lugar de dejarla pasar.
                return self._verificar(state, previa, reintentar=False)
            return None                    # las tools saneán sus argumentos; no se reescriben los tool_calls del modelo
        if _pidio_estructurada(ultimo, nombre):
            resp = previa                                   # respuesta fresca de esta vuelta
        elif not ultimo.tool_calls and previa is not None and _reintentos(mensajes, MARCA_CONTENIDO) >= 1:
            resp = previa                                   # texto plano tras el reintento: se usa la anterior
        else:
            resp = None
        if resp is None:
            if ultimo.tool_calls:
                return None
            # el modelo contestó en texto plano: 1 reintento pidiendo RespuestaFinanciera; luego, rescate
            guard = self._guard_base(state)
            if _reintentos(mensajes, MARCA_ESQUEMA) < 1:
                guard["reintentos_esquema"] = guard.get("reintentos_esquema", 0) + 1
                guard["causa"] = "sin_structured_response"
                msg = (f"{MARCA_ESQUEMA}: responde AHORA solo llamando a la herramienta {NOMBRE_ESQUEMA} "
                       "(respuesta breve, fuente, cifra si es XBRL, frase_ids si usas texto).")
                return {"messages": [HumanMessage(msg)], "jump_to": "model", "guard": guard}
            return {"structured_response": self._nuevo(self._rescatar(mensajes, guard)), "guard": guard}
        return self._verificar(state, resp)

    def _reparar_llamadas(self, ultimo: AIMessage) -> dict | None:
        """Sustituye (mismo id) el AIMessage cuyos argumentos traen marcado filtrado por el proveedor."""
        nuevas, cambio = [], 0
        for tc in ultimo.tool_calls or []:
            a, tocado = sanear_args(tc.get("args") or {}) if tc.get("name") in NOMBRES_TOOLS else (None, False)
            if tocado:
                cambio += 1
                nuevas.append({**tc, "args": a})
            else:
                nuevas.append(tc)
        if not cambio:
            return None
        return {"messages": [ultimo.model_copy(update={"tool_calls": nuevas})]}

    def _guard_base(self, state) -> dict:
        previo = state.get("guard") if isinstance(state, dict) else None
        base = {"reintentos": 0, "reintentos_esquema": 0, "degradada": False, "degradaciones": [],
                "reparaciones": [], "problemas": [], "avisos": [], "causa": None, "camino_rapido": False,
                "hueco": False}
        return base | (copy.deepcopy(previo) if isinstance(previo, dict) else {})

    def revisar(self, state, resp) -> dict:
        """Verifica una respuesta estructurada frente al estado (ledger + observaciones). Público para replays."""
        return self._verificar(state, resp)

    def _verificar(self, state, resp, reintentar: bool = True) -> dict:
        mensajes = state["messages"]
        guard = self._guard_base(state)
        d0 = resp.model_dump() if hasattr(resp, "model_dump") else dict(resp)
        declarada = d0.get("fuente")
        hechos, obs = libro_hechos(mensajes), observaciones_texto(mensajes)
        inf = verificar_xbrl(d0, hechos, obs)
        r = inf.resp
        r, p_cita, rep_cita = resolver_cita(r, mensajes, obs)
        reparaciones = inf.reparaciones + rep_cita
        problemas = inf.problemas + p_cita
        modelo = list(inf.modelo) + [c for c, _ in p_cita]
        valores = [h for h in hechos if h.status == "valor"]
        huecos = [h for h in hechos if h.status == "hueco"]
        usa_texto = bool(obs)

        # hueco: la herramienta dijo 'no reportó' y la respuesta afirma o deriva el dato -> abstención, sin reintento
        hueco = inf.hueco
        if hueco is None and huecos and not valores and declarada != "ninguna":
            # no se abstuvo: solo es válido un texto con cita literal y sin importes sin respaldo
            if not (r.get("cita") or "").strip() or not _sin_importes_sin_soporte(r, hechos, obs):
                hueco = _hueco_representativo(huecos, r.get("concept_xbrl"))
        if hueco is not None:
            guard["hueco"] = True
            guard["causa"] = "hueco_no_reportado"
            return self._cerrar(state, resp, abstencion(r, hueco), guard, declarada, reparaciones,
                                problemas, inf.avisos, hechos)

        # ¿falta evidencia? fuente declarada xbrl/texto sin cifra verificada ni cita: se pide una vez
        comparativa = r.get("cifra_base") is not None            # una comparativa también necesita su explicación citada
        falta_cita = (declarada in ("texto", "ambas") or (comparativa and usa_texto)) \
            and not (r.get("cita") or "").strip() and "cita_no_literal" not in modelo \
            and "frase_inexistente" not in modelo
        if falta_cita and usa_texto:
            modelo.append("cita_vacia")
            problemas.append(("cita_vacia", "fuente texto/ambas sin cita: elige frases visibles"))
        elif falta_cita and not usa_texto and r.get("cifra") is None:
            modelo.append("texto_sin_consulta")
            problemas.append(("texto_sin_consulta", "fuente texto sin haber consultado search_filings/read_section"))
        if declarada == "xbrl" and r.get("cifra") is None and not (r.get("cita") or "").strip():
            modelo.append("xbrl_sin_cifra")
            problemas.append(("xbrl_sin_cifra", "fuente xbrl sin cifra verificada" + (
                "; si es texto, elige frases visibles." if usa_texto else "; llama a get_xbrl_fact.")))

        if modelo and reintentar and _reintentos(mensajes, MARCA_CONTENIDO) < self.max_reintentos:
            guard["reintentos"] += 1
            guard["problemas"] = [list(p) for p in problemas]
            guard["causa"] = ",".join(dict.fromkeys(modelo))
            guard["reparaciones"] = [list(x) for x in reparaciones]
            return {"messages": [HumanMessage(self._mensaje_reintento(problemas, usa_texto))],
                    "jump_to": "model", "guard": guard}

        # sin más reintentos: lo no verificable se degrada
        if modelo:
            guard["degradada"] = True
            guard["degradaciones"] = list(dict.fromkeys(modelo))
            guard["causa"] = ",".join(dict.fromkeys(modelo))
            if any(c in modelo for c in ("cifra_sin_respaldo", "ejercicio_cruzado", "cifra_sin_get_xbrl_fact")):
                r = degradar(r, guard["causa"], hechos, obs)
        return self._cerrar(state, resp, r, guard, declarada, reparaciones, problemas, inf.avisos, hechos)

    @staticmethod
    def _mensaje_reintento(problemas: list, usa_texto: bool) -> str:
        cifras = [d for c, d in problemas if c in ("cifra_sin_respaldo", "ejercicio_cruzado", "cifra_sin_get_xbrl_fact")]
        citas = [d for c, d in problemas if c in ("cita_no_literal", "frase_inexistente", "cita_vacia",
                                                  "xbrl_sin_cifra", "texto_sin_consulta")]
        if not usa_texto and any(c == "xbrl_sin_cifra" for c, _ in problemas):
            citas = [d for c, d in problemas if c == "xbrl_sin_cifra"]
        partes = [MARCA_CONTENIDO + ":"]
        if cifras:
            partes.append("Desajuste XBRL: " + " ".join(cifras) + " Copia el valor exacto de get_xbrl_fact "
                          "(sin escalar, unidad 'USD' o 'USD/shares'; en comparativas cifra = ejercicio reciente y "
                          "cifra_base = el anterior) o llama a get_xbrl_fact con el concepto correcto. Si el dato "
                          "no existe: fuente='ninguna' y cifra=null. No estimes.")
        if citas:
            partes.append("Cita: " + " ".join(citas) + (
                " Devuelve frase_ids con los números ⟨n⟩ de las frases visibles que respaldan la respuesta "
                "(1-2 ids; en comparativas una frase por cifra) y no copies texto en cita." if usa_texto else
                " Llama a search_filings o responde con fuente='ninguna'."))
        return " ".join(partes)

    def _cerrar(self, state, resp, r: dict, guard: dict, declarada, reparaciones, problemas, avisos, hechos) -> dict:
        """Deriva la fuente, limpia abstenciones y devuelve la respuesta definitiva."""
        mensajes = state["messages"]
        obs = observaciones_texto(mensajes)
        h_hueco = _hueco_representativo([h for h in hechos if h.status == "hueco"], r.get("concept_xbrl"))
        r["fuente"] = derivar_fuente(r)
        if r["fuente"] == "ninguna" and declarada not in (None, "ninguna") and not guard.get("hueco"):
            if r.get("respuesta") and not r["respuesta"].startswith(TEXTO_SIN_EVIDENCIA) \
                    and r["respuesta"] != TEXTO_DEGRADADA:
                sin_resp = [i for i in importes_prosa(r["respuesta"]) if i["tipo"] == "USD"
                            and not _en_texto(i["valor"], normalizar(" ".join(o["content"] for o in obs)))
                            and not any(abs(i["valor"] - h.valor) <= 0.005 * max(abs(h.valor), 1)
                                        for h in hechos if h.status == "valor")]
                r["respuesta"] = TEXTO_DEGRADADA if sin_resp else TEXTO_SIN_EVIDENCIA + r["respuesta"]
            guard["degradada"] = True
            guard["degradaciones"] = list(dict.fromkeys(guard["degradaciones"] + ["sin_evidencia"]))
        limpiada = False
        if declarada in (None, "ninguna") or guard.get("hueco"):      # abstención declarada: sin importes ni estimaciones
            r, limpiada = limpiar_abstencion(r, h_hueco if r["fuente"] == "ninguna" else None)
        if limpiada:
            reparaciones = reparaciones + [("abstencion_limpiada", "sin importes ni estimaciones")]
        guard["reparaciones"] = [list(x) for x in reparaciones]
        guard["problemas"] = [list(p) for p in problemas]
        guard["avisos"] = [list(a) for a in avisos]
        guard["fuente_declarada"], guard["fuente_derivada"] = declarada, r["fuente"]
        guard["duplicadas"] = sum(isinstance(m, ToolMessage) and _texto(m).startswith("Llamada repetida")
                                  for m in mensajes)
        guard["limite_alcanzado"] = any(isinstance(m, ToolMessage) and "limit exceeded" in _texto(m).lower()
                                        for m in mensajes)
        return {"structured_response": self._nuevo(r), "guard": guard}

    # ------------------------------------------------------------ salida garantizada
    def _rescatar(self, mensajes: list, guard: dict) -> dict:
        """Sin structured_response: reutiliza el último texto del modelo y rellena campos desde el ledger."""
        texto = _ultimo_texto_modelo(mensajes)
        hechos = libro_hechos(mensajes)
        valores = [h for h in hechos if h.status == "valor"]
        huecos = [h for h in hechos if h.status == "hueco"]
        frases = re.split(r"(?<=[.!?])\s+", re.sub(r"\s+", " ", texto).strip())
        d: dict = {"respuesta": " ".join(frases[:3])[:600] or FALLBACK_TEXTO, "fuente": "ninguna"}
        conceptos = {h.concept for h in valores}
        if len(conceptos) == 1:
            hs = sorted({(h.fy, h.valor, h.unidad, h.concept, h.ticker) for h in valores}, key=lambda x: -x[0])
            d.update(cifra=hs[0][1], unidad=hs[0][2], ejercicio=hs[0][0], concept_xbrl=hs[0][3], ticker=hs[0][4])
            if len(hs) > 1:
                d.update(cifra_base=hs[1][1], ejercicio_base=hs[1][0])
        elif huecos and not valores:
            d = abstencion(d, _hueco_representativo(huecos, None))
        d["fuente"] = derivar_fuente(d)
        if d["fuente"] == "ninguna" and texto and not huecos:
            d["respuesta"] = TEXTO_SIN_EVIDENCIA + d["respuesta"]
        elif d["fuente"] == "xbrl" and texto:
            ok = all(any(abs(i["valor"] - h.valor) <= 0.005 * max(abs(h.valor), 1) for h in valores)
                     for i in importes_prosa(d["respuesta"]) if i["tipo"] == "USD")
            if not ok:
                d["respuesta"] = TEXTO_SIN_EVIDENCIA + d["respuesta"]
        guard.update(degradada=True, causa=guard.get("causa") or "sin_structured_response",
                     reparaciones=guard.get("reparaciones", []) + [["respuesta_rescatada", d["fuente"]]])
        guard["degradaciones"] = list(dict.fromkeys(guard.get("degradaciones", []) + ["sin_structured_response"]))
        guard["fuente_derivada"] = d["fuente"]
        return d

    def after_agent(self, state, runtime):
        """Red final: si el grafo terminó (p. ej. por ModelCallLimit) sin structured_response, se rescata algo."""
        if state.get("structured_response") is not None:
            return None
        mensajes = state["messages"]
        guard = self._guard_base(state)
        guard["causa"] = guard.get("causa") or "grafo_terminado_sin_respuesta"
        return {"structured_response": self._nuevo(self._rescatar(mensajes, guard)), "guard": guard}


def _sin_importes_sin_soporte(r: dict, hechos: list[Hecho], obs: list[dict]) -> bool:
    """True si TODOS los importes de la prosa tienen respaldo (ledger, diferencias, cita u observaciones)."""
    vals = [h.valor for h in hechos if h.status == "valor"]
    difs = [abs(a - b) for a in vals for b in vals if a != b]
    soporte = normalizar(" ".join(o.get("content", "") for o in obs) + " " + (r.get("cita") or ""))
    return all(any(abs(i["valor"] - x) <= 0.005 * max(abs(x), 1) for x in vals + difs) or _en_texto(i["valor"], soporte)
               for i in importes_prosa(r.get("respuesta")) if i["tipo"] == "USD")


# ------------------------------------------------------------------ API pública del contrato
def middleware_final(esquema: type | None = None, *, camino_rapido: bool | None = None) -> list:
    """Pila real y determinista del sistema final (docs/09 §2 y §5, D04).

    ``ToolCallLimit(8, continue)`` deja al modelo rendirse con fuente='ninguna'; ``read_section`` se limita
    a 1 llamada por pregunta; ``ModelCallLimit(10, end)`` es el corte duro y :class:`GuardrailsFinal`
    verifica, repara y garantiza ``structured_response``.

    ``camino_rapido`` (activado por defecto en el final; ``AGENTE10K_CAMINO_RAPIDO=0`` lo apaga para un
    ablation sin tocar código) permite omitir la segunda llamada al modelo en preguntas de una sola cifra.
    RIESGO: la prosa la escribe una plantilla, no el modelo, y depende de un léxico ES/EN por concepto
    (:data:`_LEXICO`); ante cualquier duda (concepto alternativo, sugerencia de la herramienta, magnitud
    derivada, comparativa, ticker o ejercicio ambiguos) NO corta y el modelo responde como siempre.
    El agente se cachea por sistema: tras cambiar la variable hay que llamar a ``limpiar_cache_agentes()``.
    """
    if camino_rapido is None:
        camino_rapido = os.environ.get("AGENTE10K_CAMINO_RAPIDO", "1").strip().lower() not in ("0", "false", "no")
    return [
        ToolCallLimitMiddleware(run_limit=RUN_LIMIT_TOOLS),
        ToolCallLimitMiddleware(tool_name="read_section", run_limit=RUN_LIMIT_READ_SECTION),
        ModelCallLimitMiddleware(run_limit=RUN_LIMIT_MODELO, exit_behavior="end"),
        GuardrailsFinal(esquema, camino_rapido=camino_rapido),
    ]


def rescatar_respuesta(mensajes: list, esquema: type | None = None):
    """(respuesta, guard) desde un estado sin structured_response (excepción del grafo o corte por límite).

    Reutiliza el último texto del modelo y rellena los campos desde el ledger XBRL; la fuente se deriva de la
    evidencia y la respuesta se marca «No verificada» cuando no hay nada que la respalde.
    """
    mw = GuardrailsFinal(esquema)
    guard = mw._guard_base({})
    return mw._nuevo(mw._rescatar(mensajes, guard)), guard


def revisar_sin_reintento(mensajes: list, respuesta, guard: dict | None = None, esquema: type | None = None):
    """(respuesta, guard) tras verificar una respuesta ya emitida SIN pedir otra vuelta al modelo.

    Para cuando el grafo terminó con una excepción (red, recursión) después de que el modelo respondiera: esa
    respuesta puede ser justo la que el verificador había rechazado, y no debe salir como si estuviera verificada.
    """
    mw = GuardrailsFinal(esquema)
    upd = mw._verificar({"messages": mensajes, "guard": guard or {}}, respuesta, reintentar=False)
    return upd["structured_response"], upd["guard"]


def verificar_cifras(respuesta, trayectoria: list[dict]) -> list[str]:
    """Desajustes entre las cifras de la respuesta y XBRL; lista vacía si todo cuadra (docs/09 §5–§6).

    ``trayectoria`` es la lista ``[{"name", "args", "id"}]`` de ``ejecutar()``; el valor de cada llamada
    sale del parquet por sus argumentos (no se reejecuta nada).
    """
    d = respuesta.model_dump() if hasattr(respuesta, "model_dump") else dict(respuesta)
    msgs = [AIMessage(content="", tool_calls=[
        {"name": t["name"], "args": t.get("args", {}), "id": t.get("id") or f"t{i}"}
        for i, t in enumerate(trayectoria) if t.get("name") == "get_xbrl_fact"])]
    inf = verificar_xbrl(d, libro_hechos(msgs), [])
    return [f"{codigo}: {detalle}" for codigo, detalle in inf.problemas]
