"""Compilador de Compiscript por línea de comandos (alternativa al IDE).

Uso (desde la carpeta ``Proyecto 3``)::

    python src/compilar.py examples/mips_herencia.cps                 # crea examples/mips_herencia.asm
    python src/compilar.py programa.cps -o salida.asm                 # elige el archivo de salida
    python src/compilar.py programa.cps --tac                         # también guarda el .tac
    python src/compilar.py programa.cps --ejecutar                    # además lo ejecuta en MARS
    python src/compilar.py programa.cps --ejecutar --arbol            # y muestra el árbol de activación
    python src/compilar.py programa.cps --sin-optimizar               # sin optimización por mirilla

Si el programa tiene errores léxicos, sintácticos o semánticos los muestra
todos y no genera TAC ni ensamblador (código de salida 1).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from activation_tree import build_activation_tree, render_activation_tree, strip_trace  # noqa: E402
from compiler import compile_source  # noqa: E402
from mars_runner import mars_available, run_mars, unavailable_reason  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compila un programa Compiscript a MIPS (MARS).")
    parser.add_argument("archivo", type=Path, help="programa .cps")
    parser.add_argument("-o", "--salida", type=Path, help="archivo .asm (por defecto, junto al .cps)")
    parser.add_argument("--tac", action="store_true", help="guarda también el código intermedio (.tac)")
    parser.add_argument("--sin-optimizar", action="store_true", help="no aplica la optimización por mirilla")
    parser.add_argument("--ejecutar", action="store_true", help="ejecuta el .asm en MARS")
    parser.add_argument("--arbol", action="store_true", help="con --ejecutar: muestra el árbol de activación")
    args = parser.parse_args(argv)

    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")

    source = args.archivo.read_text(encoding="utf-8")
    result = compile_source(source, optimize=not args.sin_optimizar)
    if result.diagnostics:
        print(f"{len(result.diagnostics)} error(es); no se generó código:", file=sys.stderr)
        for diagnostic in result.diagnostics:
            print(f"  [{diagnostic.kind}] línea {diagnostic.line}:{diagnostic.column} {diagnostic.description}",
                  file=sys.stderr)
        return 1

    output = args.salida or args.archivo.with_suffix(".asm")
    output.write_text(result.mips.text, encoding="utf-8")
    mips = result.mips
    print(f"MIPS guardado en {output} ({mips.instruction_count} instrucciones; "
          f"{mips.raw_instruction_count - mips.instruction_count} eliminadas por mirilla)")
    if args.tac:
        tac_path = output.with_suffix(".tac")
        tac_path.write_text(result.tac.render() + "\n", encoding="utf-8")
        print(f"TAC guardado en {tac_path}")

    if not args.ejecutar:
        return 0
    if not mars_available():
        print(unavailable_reason(), file=sys.stderr)
        return 1
    program = result.mips
    if args.arbol:
        program = compile_source(source, trace=True, optimize=not args.sin_optimizar).mips
    run = run_mars(program.text)
    print("---- salida de MARS ----")
    print(strip_trace(run.output + "\n").rstrip("\n") if args.arbol else run.output)
    if run.problem:
        print(run.problem, file=sys.stderr)
    if args.arbol:
        print("---- árbol de activación ----")
        print(render_activation_tree(build_activation_tree(run.output + "\n", strict=False)))
    return 0 if run.ok else 1


if __name__ == "__main__":
    sys.exit(main())
