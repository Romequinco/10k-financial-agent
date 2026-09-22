"""Línea de comandos: evalúa un fichero de preguntas sin tocar código.

    python -m agente10k golden/golden_propio.jsonl --etiqueta candidato_07 --sistema candidato_07
    python -m agente10k ciegas.jsonl --etiqueta ciegas          # el día 24 (docs/13 §8)

`--sistema final` (el valor por defecto) monta retrieval mejorado + los guardrails del 06 y gasta API real; si
`middleware_final()` no diera una pila válida, fallaría con un mensaje claro antes de crear ningún artefacto. El
baseline congelado se re-puntúa con `evaluadores.repuntuar`, no volviendo a lanzar esta orden.
"""
from __future__ import annotations

import argparse
import sys

COLUMNAS_VISTA = ("id", "familia", "acierto", "a", "b", "c", "abstiene", "verificacion",
                  "sr_cifra_xbrl", "a_existe", "a_vista", "latencia_s", "tokens", "n_llamadas")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m agente10k",
                                     description="Ejecuta y evalúa el agente sobre un JSONL de preguntas.")
    parser.add_argument("ruta_jsonl", help="fichero JSONL con las preguntas")
    parser.add_argument("--etiqueta", help="carpeta de salida en resultados/ (por defecto, el sistema)")
    parser.add_argument("--sistema", choices=["baseline", "candidato_07", "final"],
                        default="final")
    parser.add_argument("--sin-juez", action="store_true",
                        help="no crear el juez: extractivas y comparativas quedan sin evaluar (parcial)")
    args = parser.parse_args(argv)

    from agente10k.agente import SistemaFinalNoDisponible
    from agente10k.evaluacion import evaluar

    try:
        tabla = evaluar(args.ruta_jsonl, etiqueta=args.etiqueta, sistema=args.sistema,
                        con_juez=not args.sin_juez)
    except SistemaFinalNoDisponible as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    columnas = [c for c in COLUMNAS_VISTA if c in tabla.columns]
    print(tabla[columnas].to_string(index=False))
    if tabla.attrs.get("aviso"):
        print(f"\nAVISO: {tabla.attrs['aviso']}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
