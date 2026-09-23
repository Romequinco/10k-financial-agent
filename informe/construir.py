r"""Monta la presentación: inserta figuras y tablas en la plantilla y produce el PDF.

    .venv\Scripts\python.exe informe/construir.py

Requiere Google Chrome instalado (se usa su modo sin ventana para imprimir a PDF).
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

AQUI = Path(__file__).resolve().parent
FIGS = AQUI / "figuras"
PLANTILLA = AQUI / "plantilla.html"
MONTADO = AQUI / "presentacion.html"
PDF = AQUI / "Presentacion_Grupo3_10K.pdf"

CHROME = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
]

D = json.loads((AQUI / "datos.json").read_text(encoding="utf-8"))

NOMBRE_TANDA = {
    "baseline": "baseline (histórico)",
    "candidato_07": "candidato (sin guardrails)",
    "baseline_nexn25pro": "baseline",
    "final": "final",
    "final_r2_t1": "final, repetición 1",
    "final_r2_t2": "final, repetición 2",
    "baseline_pago": "baseline",
    "baseline_pago_r2": "baseline, repetición",
    "final_pago": "final",
    "final_pago_r2": "final, repetición",
    "final_libre_actual": "final, modelo gratuito",
    "baseline_entregado": "baseline",
    "final_entregado": "final",
}

ORDEN = [
    ("Código entregado", ["baseline_entregado", "final_entregado"]),
    ("Ablación de proveedor", ["final_libre_actual", "baseline_pago", "baseline_pago_r2",
                               "final_pago", "final_pago_r2"]),
    ("Rondas anteriores", ["baseline_nexn25pro", "final", "final_r2_t1", "final_r2_t2",
                           "baseline", "candidato_07"]),
]

MODELO_CORTO = {
    "google/gemini-3.8-flash": "gemini-3.8-flash (pago)",
    "nex-agi/nex-n2.5-pro:free": "nex-n2.5-pro (gratuito)",
    "inclusionai/ling-3.0-flash-fin:free": "ling-3.0-flash (gratuito)",
}


def _num(v, dec=2, vacio="&mdash;"):
    if v is None:
        return vacio
    return format(round(v, dec), "." + str(dec) + "f").replace(".", ",")


def tabla_tandas() -> str:
    t = D["todas_las_tandas"]
    filas = []
    for titulo, etiquetas in ORDEN:
        filas.append(
            '<tr><td colspan="8" style="padding-top:9px;padding-bottom:2px;border:0;'
            'font-size:12px;letter-spacing:1.1px;text-transform:uppercase;'
            'color:#8d9aa8;font-weight:600">' + titulo + "</td></tr>"
        )
        for et in etiquetas:
            r = t[et]
            destacada = ' class="destacada"' if et.endswith("_entregado") else ""
            filas.append(
                "<tr" + destacada + ">"
                + "<td>" + NOMBRE_TANDA[et] + "</td>"
                + '<td style="text-align:left;font-size:12px;color:#69788a">'
                + MODELO_CORTO.get(r["modelo"], r["modelo"]) + "</td>"
                + "<td>" + "{:.0f} %".format(r["micro"] * 100) + "</td>"
                + "<td>" + r["familias"]["numerica"] + "</td>"
                + "<td>" + r["familias"]["extractiva"] + "</td>"
                + "<td>" + r["familias"]["comparativa"] + "</td>"
                + "<td>" + str(r["errores"]) + "</td>"
                + "<td>" + _num(r["llamadas"], 2) + "</td>"
                + "</tr>"
            )
    return (
        '<table class="mini apretada"><thead><tr>'
        "<th>Ejecución</th><th>Modelo del agente</th><th>Acierto</th><th>Num.</th>"
        "<th>Extr.</th><th>Comp.</th><th>Preguntas<br>perdidas</th><th>Llamadas<br>/preg.</th>"
        "</tr></thead><tbody>" + "".join(filas) + "</tbody></table>"
    )


def tabla_escalera() -> str:
    nombres = {
        "0_denso": "Búsqueda densa (punto de partida)",
        "1_filtro": "+ filtro de empresa, año y sección",
        "2_bm25": "+ BM25 combinado con la densa",
        "3_reescritura": "+ reescritura de la consulta",
        "d_solo_bm25": "Solo BM25 (diagnóstico)",
        "d_rw_oraculo": "Reescritura con la respuesta (techo)",
    }
    filas = []
    for p in D["escalera"]["pasos"]:
        diag = p["paso"].startswith("d_")
        estilo = ' style="color:#69788a;font-style:italic"' if diag else ""
        filas.append(
            "<tr" + estilo + ">"
            + '<td style="text-align:left">' + nombres.get(p["paso"], p["paso"]) + "</td>"
            + "<td>" + p["aciertos5"] + "</td>"
            + "<td>" + p["aciertos10"] + "</td>"
            + "<td>" + _num(p["mrr10"], 2) + "</td>"
            + "<td>" + "{:.0f} ms".format(p["ms_busqueda"]) + "</td>"
            + "</tr>"
        )
    return (
        '<table class="mini"><thead><tr><th>Paso</th><th>Acierto@5</th>'
        "<th>Acierto@10</th><th>MRR@10</th><th>Tiempo</th></tr></thead><tbody>"
        + "".join(filas) + "</tbody></table>"
    )


def montar() -> str:
    html = PLANTILLA.read_text(encoding="utf-8")

    # La hoja de estilo va incrustada: así el HTML montado es un único fichero
    # que se abre en cualquier sitio y Chrome no depende de rutas relativas.
    css = (AQUI / "estilos.css").read_text(encoding="utf-8")
    html = html.replace(
        '<link rel="stylesheet" href="estilos.css">',
        "<style>\n" + css + "\n</style>",
    )

    for svg in sorted(FIGS.glob("*.svg")):
        cuerpo = svg.read_text(encoding="utf-8")
        cuerpo = cuerpo[cuerpo.index("<svg"):]
        cuerpo = re.sub(r'(<svg[^>]*?)\swidth="[^"]*"', r"\1", cuerpo, count=1)
        cuerpo = re.sub(r'(<svg[^>]*?)\sheight="[^"]*"', r"\1", cuerpo, count=1)
        html = html.replace("<!--FIG:" + svg.stem + "-->", cuerpo)

    html = html.replace("<!--TABLA:tandas-->", tabla_tandas())
    html = html.replace("<!--TABLA:escalera-->", tabla_escalera())

    rf = D["sistemas"]["final"]["resumen"]
    valores = {
        "commit_actual": D["commit_actual"],
        "commit_medido": rf["commit"],
        "fecha_medicion": rf["fecha"][:10].replace("-", "/"),
    }
    for clave, valor in valores.items():
        html = html.replace("<!--D:" + clave + "-->", str(valor))

    restantes = re.findall(r"<!--(?:FIG|TABLA|D):([a-z0-9_]+)-->", html)
    if restantes:
        raise SystemExit("huecos sin rellenar: " + ", ".join(restantes))
    return html


def a_pdf() -> None:
    chrome = next((c for c in CHROME if Path(c).exists()), None)
    if chrome is None:
        raise SystemExit("no encuentro Chrome; instala Chrome o exporta el HTML a mano")
    if PDF.exists():
        PDF.unlink()
    subprocess.run(
        [chrome, "--headless=new", "--disable-gpu", "--no-sandbox",
         "--no-pdf-header-footer", "--virtual-time-budget=10000",
         "--print-to-pdf=" + str(PDF), MONTADO.as_uri()],
        check=True, capture_output=True, timeout=180,
    )
    if not PDF.exists():
        raise SystemExit("Chrome no genero el PDF")


if __name__ == "__main__":
    MONTADO.write_text(montar(), encoding="utf-8")
    print("html montado:", MONTADO.name)
    a_pdf()
    print("pdf:", PDF.name, "(" + str(round(PDF.stat().st_size / 1024)) + " KB)")
