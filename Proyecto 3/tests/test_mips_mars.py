"""Pruebas en el simulador MARS: funciones, parámetros, recursividad,
funciones anidadas y restauración de ``$sp``/``$fp``.

Se ejecutan sólo si hay Java instalado y un ``tools/Mars*.jar`` (por ejemplo
``Mars4_5.jar``); si no, se omiten. Las instrucciones que no son de Persona 1
las traduce el doble de prueba de ``mips_doubles.py`` hasta que estén las de
Persona 2 y 3."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "src"))
sys.path.insert(0, str(PROJECT / "tests"))

from activation_tree import build_activation_tree, render_activation_tree, strip_trace  # noqa: E402
from mips_doubles import TinyMips, Translation, mars_command, run_mars  # noqa: E402

PROGRAMS = {
    "parámetros y retorno": (
        "function suma(a: integer, b: integer): integer { return a + b; }\n"
        "print(suma(2, 3));\nprint(suma(-4, 1));",
        [5, -3],
    ),
    "llamadas anidadas y consecutivas": (
        "function doble(x: integer): integer { return x * 2; }\n"
        "function inc(x: integer): integer { return x + 1; }\n"
        "print(doble(inc(doble(3))));\nprint(inc(1));\nprint(inc(2));",
        [14, 2, 3],
    ),
    "más de cuatro parámetros": (
        "function mezcla(a: integer, b: integer, c: integer, d: integer, e: integer, f: integer): integer {\n"
        "  return a - b + c - d + e - f;\n}\nprint(mezcla(100, 1, 20, 3, 40, 5));",
        [151],
    ),
    "recursión": (
        "function factorial(n: integer): integer { if (n <= 1) { return 1; } return n * factorial(n - 1); }\n"
        "function fib(n: integer): integer { if (n < 2) { return n; } return fib(n - 1) + fib(n - 2); }\n"
        "print(factorial(10));\nprint(fib(15));",
        [3628800, 610],
    ),
    "recursión mutua": (
        "function esPar(n: integer): boolean { if (n == 0) { return true; } return esImpar(n - 1); }\n"
        "function esImpar(n: integer): boolean { if (n == 0) { return false; } return esPar(n - 1); }\n"
        "if (esPar(10)) { print(1); } else { print(0); }\nif (esPar(7)) { print(1); } else { print(0); }",
        [1, 0],
    ),
    "funciones anidadas": (
        "function externo(x: integer): integer {\n"
        "  let y: integer = 1;\n"
        "  function primero(): integer { return x; }\n"
        "  function segundo(): integer { return primero() + y; }\n"
        "  function medio(): integer {\n"
        "    function interno(): integer { return segundo() + x; }\n"
        "    return interno();\n"
        "  }\n"
        "  return medio() + segundo();\n"
        "}\nprint(externo(3));\nprint(externo(5));",
        [11, 17],
    ),
}


def printed_numbers(output: str) -> list[int]:
    return [int(line) for line in output.split()]


@unittest.skipUnless(mars_command(), "MARS no disponible: se necesita Java y tools/Mars*.jar")
class MarsTests(unittest.TestCase):
    def test_programs(self) -> None:
        for name, (source, expected) in PROGRAMS.items():
            with self.subTest(programa=name):
                result = run_mars(Translation(source, run_others=True).program())
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(printed_numbers(result.output), expected)
                self.assertEqual(result.registers.get("$sp"), TinyMips.STACK_TOP)
                self.assertEqual(result.registers.get("$fp"), TinyMips.STACK_TOP)

    def test_activation_tree_from_mars(self) -> None:
        source = PROGRAMS["recursión"][0].split("print")[0] + "print(factorial(3));"
        result = run_mars(Translation(source, run_others=True, trace=True).program())
        self.assertEqual(result.returncode, 0, result.stderr)
        root = build_activation_tree(result.output + "\n")
        self.assertEqual(
            render_activation_tree(root),
            "main\n└── factorial(3)\n    └── factorial(2)\n        └── factorial(1)",
        )
        self.assertEqual(printed_numbers(strip_trace(result.output + "\n")), [6])


class SameProgramsInTinyMipsTests(unittest.TestCase):
    """Los mismos programas en el simulador de prueba (siempre se ejecutan)."""

    def test_programs(self) -> None:
        for name, (source, expected) in PROGRAMS.items():
            with self.subTest(programa=name):
                machine = TinyMips(Translation(source, run_others=True).program()).run()
                self.assertEqual(machine.output, expected)
                self.assertEqual(machine.get("$sp"), TinyMips.STACK_TOP)


if __name__ == "__main__":
    unittest.main()
