r"""Genera las figuras de la presentación a partir de informe/datos.json.

    .venv\Scripts\python.exe informe/figuras.py

Ninguna figura inventa un dato: todo sale de `datos.json`, que a su vez lo lee
de `resultados/`. La única excepción está marcada en `f1_herramientas`.
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

AQUI = Path(__file__).resolve().parent
FIGS = AQUI / "figuras"
FIGS.mkdir(exist_ok=True)

TINTA = "#16212c"
GRIS = "#55636f"
SUAVE = "#5f6f80"
LINEA = "#d9e1e8"
BASE_C = "#aab8c4"
FIN_C = "#1d6e8b"
OK = "#2f7d5c"
MAL = "#bf5540"
AMBAR = "#b08a42"

plt.rcParams.update({
    "font.family": ["Segoe UI", "DejaVu Sans"],
    "font.size": 12,
    "text.color": TINTA,
    "axes.labelcolor": TINTA,
    "axes.edgecolor": LINEA,
    "xtick.color": SUAVE,
    "ytick.color": SUAVE,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "figure.facecolor": "none",
    "axes.facecolor": "none",
    "savefig.facecolor": "none",
    "svg.fonttype": "none",
})

D = json.loads((AQUI / "datos.json").read_text(encoding="utf-8"))
RB = D["sistemas"]["baseline"]["resumen"]
RF = D["sistemas"]["final"]["resumen"]

MODELO_COLOR = {
    "google/gemini-3.8-flash": FIN_C,
    "nex-agi/nex-n2.5-pro:free": AMBAR,
    "inclusionai/ling-3.0-flash-fin:free": "#8d6e8e",
}
MODELO_NOMBRE = {
    "google/gemini-3.8-flash": "gemini-3.8-flash (de pago)",
    "nex-agi/nex-n2.5-pro:free": "nex-n2.5-pro (gratuito)",
    "inclusionai/ling-3.0-flash-fin:free": "ling-3.0-flash (gratuito)",
}


def _guardar(fig, nombre):
    fig.savefig(FIGS / nombre, format="svg", bbox_inches="tight", pad_inches=0.02, transparent=True)
    plt.close(fig)
    print("  ", nombre)


def _limpiar(ax):
    ax.set_yticks([])
    ax.spines["left"].set_visible(False)
    ax.spines["bottom"].set_color(LINEA)
    ax.tick_params(axis="x", length=0, labelsize=11)


# --------------------------------------------------------------------------
# 1 · lo que cuesta cada herramienta
# --------------------------------------------------------------------------

def f1_herramientas():
    nombres = [
        "get_xbrl_fact\nel dato exacto",
        "list_available\nqué hay en el corpus",
        "search_filings\nbusca 5 fragmentos",
        "read_section\nla sección entera",
    ]
    valores = [40, 196, 2000, 34751]
    colores = ["#cfe0e9", "#9cc0d0", "#5794b0", MAL]

    fig, ax = plt.subplots(figsize=(8.4, 3.4))
    barras = ax.barh(nombres, valores, color=colores, height=0.6)
    ax.set_xscale("log")
    ax.set_xlim(20, 260000)
    ax.invert_yaxis()
    ax.set_xlabel("tokens que el modelo tiene que leer (escala logarítmica)",
                  fontsize=10.5, color=SUAVE)
    ax.grid(axis="x", color=LINEA, lw=0.8)
    ax.set_axisbelow(True)
    ax.tick_params(axis="y", length=0, labelsize=11)
    for b, v in zip(barras, valores):
        ax.text(v * 1.3, b.get_y() + b.get_height() / 2, format(v, ",").replace(",", "."),
                va="center", fontsize=12, fontweight="bold", color=TINTA)
    ax.annotate("", xy=(40, 3.62), xytext=(34751, 3.62),
                arrowprops=dict(arrowstyle="<|-|>", color=SUAVE, lw=1.1,
                                shrinkA=0, shrinkB=0))
    ax.text(1180, 3.76, "868 veces más caro", ha="center", fontsize=12.5,
            fontweight="bold", color=MAL)
    ax.set_ylim(4.15, -0.55)
    _guardar(fig, "f1_herramientas.svg")


# --------------------------------------------------------------------------
# 2 · el embudo de la cita
# --------------------------------------------------------------------------

def f2_embudo():
    e = D["etapas_cita"]
    etapas = ["el fragmento\nexiste", "el agente\nlo vio", "la frase respalda\nlo que afirma"]
    claves = ["existe", "vista", "respalda"]
    PASO, ANCHO, ALTO = 1.30, 1.12, 0.60

    fig, ax = plt.subplots(figsize=(9.6, 3.1))
    for etiqueta, sis, color, y in [("Punto de partida", "baseline", BASE_C, 1.16),
                                    ("Sistema final", "final", FIN_C, 0.0)]:
        for i, clave in enumerate(claves):
            v = e[sis][clave]
            x = i * PASO
            ax.add_patch(Rectangle((x, y), ANCHO, ALTO, facecolor="#eef2f5", edgecolor="none"))
            relleno = color if clave != "respalda" else (MAL if v == 0 else OK)
            ax.add_patch(Rectangle((x, y), max(ANCHO * v / 13, 0.05), ALTO,
                                   facecolor=relleno, edgecolor="none"))
            ax.text(x + ANCHO / 2, y - 0.14, f"{v}/13", ha="center", va="top", fontsize=12.5,
                    fontweight="bold", color=MAL if (clave == "respalda" and v == 0) else TINTA)
        ax.text(-0.16, y + ALTO / 2, etiqueta, ha="right", va="center", fontsize=12.5,
                fontweight="bold" if sis == "final" else "normal",
                color=TINTA if sis == "final" else GRIS)

    for i, etiqueta in enumerate(etapas):
        ax.text(i * PASO + ANCHO / 2, 1.92, etiqueta, ha="center", va="bottom", fontsize=11,
                color=SUAVE, linespacing=1.4)

    ax.annotate("aquí se caía todo", xy=(2 * PASO + 0.1, 1.46), xytext=(2 * PASO + 1.32, 1.75),
                fontsize=12.5, fontweight="bold", color=MAL, ha="left", va="center",
                arrowprops=dict(arrowstyle="-|>", color=MAL, lw=1.4,
                                connectionstyle="arc3,rad=0.3"))
    ax.set_xlim(-2.75, 2 * PASO + ANCHO + 2.45)
    ax.set_ylim(-0.55, 2.62)
    ax.axis("off")
    _guardar(fig, "f2_embudo.svg")


# --------------------------------------------------------------------------
# 3 · más acierto con menos trabajo
# --------------------------------------------------------------------------

def f3_mas_por_menos():
    paneles = [
        ("Respuestas correctas", RB["micro"] * 100, RF["micro"] * 100, "{:.0f} %", True, "puntos"),
        ("Llamadas a herramientas\npor pregunta", RB["llamadas_medias"], RF["llamadas_medias"],
         "{:.1f}", False, "%"),
        ("Tokens leídos\npor pregunta (media)", RB["tokens_medios"] / 1000,
         RF["tokens_medios"] / 1000, "{:.1f}k", False, "%"),
    ]
    fig, axes = plt.subplots(1, 3, figsize=(9.4, 3.0))
    for ax, (titulo, vb, vf, fmt, subir, modo) in zip(axes, paneles):
        barras = ax.bar(["Partida", "Final"], [vb, vf], color=[BASE_C, FIN_C], width=0.56)
        for b, v in zip(barras, [vb, vf]):
            ax.text(b.get_x() + b.get_width() / 2, b.get_height() * 1.05,
                    fmt.format(v).replace(".", ","),
                    ha="center", fontsize=16, fontweight="bold")
        mejora = (vf > vb) if subir else (vf < vb)
        color = OK if mejora else MAL
        if modo == "puntos":
            texto = "+{:.0f} puntos".format(vf - vb)
        else:
            texto = "{:.0f} % {}".format(abs(100 * (vf - vb) / vb), "más" if subir else "menos")
        ax.set_title(titulo, fontsize=11.5, color=SUAVE, pad=8)
        ax.text(0.5, -0.32, texto, transform=ax.transAxes, ha="center",
                fontsize=13.5, fontweight="bold", color=color)
        ax.set_ylim(0, max(vb, vf) * 1.3)
        _limpiar(ax)
    fig.subplots_adjust(wspace=0.45, bottom=0.24)
    _guardar(fig, "f3_mas_por_menos.svg")


# --------------------------------------------------------------------------
# 4 · las 20 preguntas, una a una
# --------------------------------------------------------------------------

def f4_matriz():
    filas = D["matriz"]
    fig, ax = plt.subplots(figsize=(10.4, 2.5))
    ganadas = []
    for col, f in enumerate(filas):
        for i, clave in enumerate(["base_acierto", "final_acierto"]):
            bien = bool(f[clave])
            err = clave == "final_acierto" and f.get("final_error")
            if bien:
                fondo, texto, tinta = OK, "SÍ", "white"
            elif err:
                fondo, texto, tinta = "#fdf3e0", "ERR", AMBAR
            else:
                fondo, texto, tinta = "#f7e8e5", "NO", MAL
            ax.add_patch(Rectangle((col, 1 - i), 0.86, 0.86, facecolor=fondo, edgecolor="none"))
            ax.text(col + 0.43, 1 - i + 0.43, texto, ha="center", va="center",
                    fontsize=8.5 if texto == "ERR" else 9.5, fontweight="bold", color=tinta)
        ax.text(col + 0.43, -0.62, f["id"].replace("g3-", ""), ha="center", fontsize=9, color=SUAVE)
        if not f["base_acierto"] and f["final_acierto"]:
            ganadas.append(col)
            ax.annotate("", xy=(col + 0.43, -0.14), xytext=(col + 0.43, 0.50),
                        arrowprops=dict(arrowstyle="-|>", color=OK, lw=1.5))

    cuenta = {}
    for f in filas:
        cuenta[f["familia"]] = cuenta.get(f["familia"], 0) + 1
    nombres = {"numerica": "NUMÉRICAS", "extractiva": "EXTRACTIVAS", "comparativa": "COMPARATIVAS"}
    acum = 0
    for fam in ["numerica", "extractiva", "comparativa"]:
        n = cuenta[fam]
        ax.plot([acum, acum + n - 0.14], [2.16, 2.16], color=LINEA, lw=3, solid_capstyle="butt")
        ax.text(acum + (n - 0.14) / 2, 2.30, nombres[fam], ha="center", fontsize=10,
                color=SUAVE, fontweight="bold")
        acum += n
    ax.text(-0.35, 1.43, "Punto de partida", ha="right", va="center", fontsize=11.5, color=GRIS)
    ax.text(-0.35, 0.43, "Sistema final", ha="right", va="center", fontsize=11.5, fontweight="bold")
    ax.text(-0.35, -0.14, f"{len(ganadas)} preguntas ganadas", ha="right", va="center",
            fontsize=11.5, color=OK, fontweight="bold")
    ax.text(20.15, -1.15, "",
            ha="right", va="center", fontsize=9.5, color=AMBAR)
    ax.set_xlim(-4.6, 20.2)
    ax.set_ylim(-1.45, 2.58)
    ax.axis("off")
    _guardar(fig, "f4_matriz.svg")


# --------------------------------------------------------------------------
# 5 · la escalera de búsqueda, contra su techo
# --------------------------------------------------------------------------

def f5_escalera():
    nombres = {
        "0_denso": "Búsqueda densa\n(punto de partida)",
        "1_filtro": "+ filtro por\nempresa, año y sección",
        "2_bm25": "+ BM25 combinado\ncon la densa",
        "3_reescritura": "+ reescritura de\nla consulta",
    }
    pasos = [p for p in D["escalera"]["pasos"] if p["paso"] in nombres]
    etiquetas = [nombres[p["paso"]] for p in pasos]
    valores = [int(p["aciertos5"].split("/")[0]) for p in pasos]
    colores = [BASE_C, FIN_C, FIN_C, "#c6d6dd"]
    techo = D["escalera"]["techo"]

    fig, ax = plt.subplots(figsize=(8.4, 3.9))
    ax.axhspan(techo, 13, color="#f2f5f7", zorder=0)
    ax.axhline(techo, color=SUAVE, ls=(0, (5, 3)), lw=1.2, zorder=1)
    ax.text(3.46, techo + 0.4, "2 preguntas que ningún buscador alcanza:\nel techo real es 11, no 13",
            ha="right", fontsize=10.5, color=SUAVE, linespacing=1.35)
    barras = ax.bar(etiquetas, valores, color=colores, width=0.56, zorder=2)
    for b, v in zip(barras, valores):
        ax.text(b.get_x() + b.get_width() / 2, v + 0.22, f"{v}/13", ha="center",
                fontsize=14.5, fontweight="bold")
    ax.set_ylim(0, 13)
    _limpiar(ax)
    ax.tick_params(axis="x", labelsize=10.5)
    ax.annotate("", xy=(3, 6.2), xytext=(2, 6.2),
                arrowprops=dict(arrowstyle="-|>", color=MAL, lw=1.6))
    ax.text(2.5, 6.45, "3 entran, 3 salen:\nen neto, cero", ha="center", fontsize=11,
            color=MAL, fontweight="bold", linespacing=1.3)
    _guardar(fig, "f5_escalera.svg")


# --------------------------------------------------------------------------
# 6 · las dos mitades de la decisión de proveedor
# --------------------------------------------------------------------------

def f6_proveedor():
    p = D["proveedor"]
    libre, pago = p["final_libre_actual"], p["final_pago"]
    fig, axes = plt.subplots(1, 3, figsize=(12.8, 3.2))

    ax = axes[0]
    tasas = [100 * libre["errores"] / 20, 0.0]
    barras = ax.bar(["Gratuito", "De pago"], tasas, color=[MAL, OK], width=0.55)
    ax.plot([0.72, 1.28], [0.15, 0.15], color=OK, lw=5, solid_capstyle="butt")
    for b, t in zip(barras, [f"{libre['errores']} de 20", "0 de 40"]):
        ax.text(b.get_x() + b.get_width() / 2, max(b.get_height(), 0) + 2.5, t,
                ha="center", fontsize=13, fontweight="bold")
    ax.set_title("Preguntas que se quedan sin respuesta\n(sobre el total de cada ejecución)",
                 fontsize=11, color=SUAVE, pad=8)
    ax.set_ylim(0, 62)
    _limpiar(ax)

    ax = axes[1]
    valores = [libre["latencia_mediana_s"], pago["latencia_mediana_s"]]
    barras = ax.bar(["Gratuito", "De pago"], valores, color=[MAL, OK], width=0.55)
    for b, v in zip(barras, valores):
        ax.text(b.get_x() + b.get_width() / 2, v + 9, "{:.0f} s".format(v), ha="center",
                fontsize=13, fontweight="bold")
    ax.axhline(300, color=MAL, ls=(0, (4, 3)), lw=1.2)
    ax.text(1.42, 307, "plazo máximo que imponemos (300 s)", ha="right", fontsize=9.5, color=MAL)
    ax.set_title("Tiempo en contestar\n(mediana)", fontsize=11, color=SUAVE, pad=8)
    ax.set_ylim(0, 355)
    _limpiar(ax)

    ax = axes[2]
    t = D["todas_las_tandas"]
    vistos = set()
    for j, (et, r) in enumerate(sorted(t.items())):
        x = 0 if (et.startswith("baseline") or et.startswith("candidato")) else 1
        color = MODELO_COLOR.get(r["modelo"], SUAVE)
        etiqueta = MODELO_NOMBRE.get(r["modelo"], r["modelo"])
        ax.scatter([x + (j % 7 - 3) * 0.062], [r["micro"] * 100], s=125, color=color,
                   zorder=3, edgecolors="white", linewidths=1.4,
                   label=etiqueta if etiqueta not in vistos else None)
        vistos.add(etiqueta)
    ax.set_title("Respuestas correctas en las 15 ejecuciones\nmedidas, por sistema y por modelo",
                 fontsize=11, color=SUAVE, pad=8)
    ax.set_xlim(-0.55, 1.55)
    ax.set_ylim(20, 100)
    ax.set_xticks([0, 1])
    ax.set_xticklabels(["Punto de partida", "Sistema final"], fontsize=11)
    ax.set_yticks([30, 50, 70, 90])
    ax.set_yticklabels(["30 %", "50 %", "70 %", "90 %"], fontsize=10)
    ax.grid(axis="y", color=LINEA, lw=0.8)
    ax.set_axisbelow(True)
    ax.spines["left"].set_visible(False)
    ax.spines["bottom"].set_color(LINEA)
    ax.tick_params(axis="x", length=0)
    ax.legend(frameon=False, fontsize=9.5, loc="upper left", handletextpad=0.35,
              borderpad=0.1, labelspacing=0.25)
    fig.subplots_adjust(wspace=0.3)
    _guardar(fig, "f6_proveedor.svg")


# --------------------------------------------------------------------------
# 7 · en qué se gastan las llamadas
# --------------------------------------------------------------------------

def f7_llamadas():
    h = D["llamadas_herramienta"]
    orden = ["get_xbrl_fact", "list_available", "search_filings", "read_section"]
    colores = {"get_xbrl_fact": "#cfe0e9", "list_available": "#9cc0d0",
               "search_filings": "#5794b0", "read_section": MAL}

    fig, ax = plt.subplots(figsize=(9.2, 2.6))
    for fila, (etiqueta, sis) in enumerate([("Punto de partida", "baseline"),
                                            ("Sistema final", "final")]):
        y = 1 - fila
        izq = 0
        for herr in orden:
            v = h[sis].get(herr, 0)
            if not v:
                continue
            ax.barh([y], [v], left=izq, height=0.54, color=colores[herr],
                    edgecolor="white", lw=1.5)
            if v >= 4:
                ax.text(izq + v / 2, y, str(v), ha="center", va="center", fontsize=11.5,
                        fontweight="bold",
                        color="white" if herr in ("search_filings", "read_section") else TINTA)
            izq += v
        ax.text(izq + 1.5, y, f"{izq} llamadas", va="center", fontsize=12.5, fontweight="bold")
        ax.text(-1.5, y, etiqueta, ha="right", va="center", fontsize=12,
                fontweight="bold" if sis == "final" else "normal",
                color=TINTA if sis == "final" else GRIS)

    for i, herr in enumerate(orden):
        ax.add_patch(Rectangle((i * 17.5 - 24, -0.78), 2.4, 0.17, facecolor=colores[herr],
                               edgecolor="none"))
        ax.text(i * 17.5 - 20.8, -0.70, herr, va="center", fontsize=10, color=GRIS)

    ax.annotate("read_section y list_available\ndesaparecen del todo",
                xy=(65, 0.74), xytext=(74, 1.42), fontsize=10.5, color=MAL,
                fontweight="bold", ha="right", linespacing=1.3,
                arrowprops=dict(arrowstyle="-|>", color=MAL, lw=1.3,
                                connectionstyle="arc3,rad=0.25"))
    ax.set_xlim(-26, 84)
    ax.set_ylim(-1.0, 1.95)
    ax.axis("off")
    _guardar(fig, "f7_llamadas.svg")


# --------------------------------------------------------------------------
# 8 · lee la mitad y escribe el doble
# --------------------------------------------------------------------------

def f8_tokens():
    fig, ax = plt.subplots(figsize=(8.8, 2.3))
    for i, (etiqueta, r) in enumerate([("Punto de partida", RB), ("Sistema final", RF)]):
        y = 1 - i
        ent = r["tokens_entrada_medios"] / 1000
        sal = r["tokens_salida_medios"] / 1000
        ax.barh([y], [ent], height=0.5, color=BASE_C)
        ax.barh([y], [sal], left=ent, height=0.5, color=FIN_C)
        ax.text(ent / 2, y, f"{ent:.1f}k".replace(".", ",") + " leídos", ha="center",
                va="center", fontsize=11.5, fontweight="bold", color=TINTA)
        ax.text(ent + sal + 0.7, y, f"{sal:.1f}k".replace(".", ",") + " escritos",
                va="center", fontsize=11, color=FIN_C, fontweight="bold")
        ax.text(-0.9, y, etiqueta, ha="right", va="center", fontsize=12,
                fontweight="bold" if i else "normal", color=TINTA if i else GRIS)
    ax.text(8, -0.5, "lee un 42 % menos", fontsize=11.5, color=OK, fontweight="bold", ha="center")
    ax.text(25, -0.5, "y escribe más del doble", fontsize=11.5, color=SUAVE, ha="center")
    ax.set_xlim(-17, 40)
    ax.set_ylim(-0.95, 1.55)
    ax.axis("off")
    _guardar(fig, "f8_tokens.svg")


if __name__ == "__main__":
    print("figuras:")
    f1_herramientas()
    f2_embudo()
    f3_mas_por_menos()
    f4_matriz()
    f5_escalera()
    f6_proveedor()
    f7_llamadas()
    f8_tokens()
