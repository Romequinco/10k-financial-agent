"""Línea de comandos: evalúa un fichero de preguntas sin tocar código.

    python -m agente10k golden/golden_propio.jsonl --etiqueta baseline --sistema baseline
    python -m agente10k ciegas.jsonl --etiqueta ciegas          # el día 24 (docs/13 §8)
"""
from __future__ import annotations

import argparse


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m agente10k",
                                     description="Ejecuta y evalúa el agente sobre un JSONL de preguntas.")
    parser.add_argument("ruta_jsonl", help="fichero JSONL con las preguntas")
    parser.add_argument("--etiqueta", help="carpeta de salida en resultados/ (por defecto, el sistema)")
    parser.add_argument("--sistema", choices=["baseline", "final"], default="final")
    args = parser.parse_args(argv)

    from agente10k.evaluacion import evaluar

    print(evaluar(args.ruta_jsonl, etiqueta=args.etiqueta, sistema=args.sistema))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
