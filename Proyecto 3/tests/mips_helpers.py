"""Auxiliares de las pruebas de Persona 3 (control de flujo, objetos,
excepciones, mirilla e integración).

A diferencia de ``mips_doubles.py`` (dobles de prueba de Persona 1), aquí
se usa el compilador real completo: ``compile_source`` genera el TAC y el
MIPS con los traductores de las tres personas, y el programa se ejecuta en
MARS. Las pruebas que necesitan MARS se omiten si no hay Java o
``tools/Mars*.jar``.
"""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
for folder in (PROJECT / "src", PROJECT / "tests"):
    if str(folder) not in sys.path:
        sys.path.insert(0, str(folder))

from compiler import compile_source  # noqa: E402
from mars_runner import mars_available, run_mars  # noqa: E402
from mips_doubles import TinyMips  # noqa: E402
from mips_doubles import run_mars as run_mars_with_registers  # noqa: E402

EXAMPLES = PROJECT / "examples"
EXPECTED = EXAMPLES / "salidas"
STACK_TOP = TinyMips.STACK_TOP

needs_mars = unittest.skipUnless(mars_available(), "MARS no disponible: se necesita Java y tools/Mars*.jar")


def compile_mips(source: str, **options):
    """Compila y exige que no haya diagnósticos."""
    result = compile_source(source, **options)
    assert not result.diagnostics, result.diagnostics
    assert result.mips is not None
    return result


def mips_lines(source: str, **options) -> list[str]:
    return compile_mips(source, **options).mips.lines


def instructions(lines: list[str]) -> list[str]:
    """Sólo las instrucciones (sin comentarios ni etiquetas)."""
    out = []
    for line in lines:
        code = line.split("#", 1)[0].strip()
        if code and not code.endswith(":") and not code.startswith(".") and not re.match(r"^[\w.$]+:\s", code):
            out.append(code)
    return out


def execute(source: str, **options) -> str:
    """Salida del programa en MARS."""
    result = compile_mips(source, **options)
    run = run_mars(result.mips.text)
    assert run.ok, run.problem
    return run.output


class MarsTestCase(unittest.TestCase):
    def assert_runs(self, source: str, expected: str, *, balanced: bool = True, **options) -> None:
        """Ejecuta ``source`` en MARS (con y sin mirilla), compara la salida
        y, si ``balanced``, que ``$sp`` y ``$fp`` terminen en el tope de la
        pila (ningún marco ni manejador quedó sin liberar)."""
        for optimize in (True, False):
            with self.subTest(optimize=optimize):
                result = compile_mips(source, optimize=optimize, **options)
                run = run_mars_with_registers(result.mips.lines)
                self.assertEqual(run.returncode, 0, (run.output, run.stderr))
                self.assertEqual(run.output, expected)
                if balanced:
                    self.assertEqual(run.registers, {"$sp": STACK_TOP, "$fp": STACK_TOP})
