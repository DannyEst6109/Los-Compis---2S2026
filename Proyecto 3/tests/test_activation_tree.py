"""Pruebas de la traza de activaciones (``trace=True`` en
``mips_functions.py``) y del árbol de activación (``activation_tree.py``)."""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "src"))
sys.path.insert(0, str(PROJECT / "tests"))

from activation_tree import (  # noqa: E402
    ActivationTraceError,
    build_activation_tree,
    render_activation_tree,
    strip_trace,
)
from mips_doubles import TinyMips, Translation, run  # noqa: E402

FACTORIAL = """
function factorial(n: integer): integer {
  if (n <= 1) { return 1; }
  return n * factorial(n - 1);
}
"""

FIB = """
function fib(n: integer): integer {
  if (n < 2) { return n; }
  return fib(n - 1) + fib(n - 2);
}
"""


def traced_tree(source: str):
    _, machine = run(source, trace=True)
    return build_activation_tree(machine.text), machine


class TreeFromExecutionTests(unittest.TestCase):
    def test_recursion_is_a_chain(self) -> None:
        root, _ = traced_tree(FACTORIAL + "print(factorial(3));")
        self.assertEqual(
            render_activation_tree(root),
            "main\n"
            "└── factorial(3)\n"
            "    └── factorial(2)\n"
            "        └── factorial(1)",
        )
        self.assertEqual(root.depth, 3)

    def test_two_recursive_calls_form_a_binary_tree(self) -> None:
        root, _ = traced_tree(FIB + "print(fib(4));")
        self.assertEqual(root.count("fib"), 9)  # fib(4) se activa 9 veces
        fib4 = root.children[0]
        self.assertEqual([child.label for child in fib4.children], ["fib(3)", "fib(2)"])
        self.assertEqual([child.label for child in fib4.children[1].children], ["fib(1)", "fib(0)"])
        self.assertTrue(all(node.finished for node in root.walk()))

    def test_consecutive_calls_are_siblings(self) -> None:
        source = FACTORIAL + "print(factorial(1));\nprint(factorial(2));"
        root, _ = traced_tree(source)
        self.assertEqual([child.label for child in root.children], ["factorial(1)", "factorial(2)"])

    def test_nested_functions_and_boolean_arguments(self) -> None:
        source = """
function externo(x: integer, ok: boolean): integer {
  function interno(y: integer): integer { return x + y; }
  if (ok) { return interno(1) + interno(2); }
  return 0;
}
print(externo(10, true));
"""
        root, machine = traced_tree(source)
        self.assertEqual(
            render_activation_tree(root),
            "main\n"
            "└── externo(10, 1)\n"
            "    ├── interno(1)\n"
            "    └── interno(2)",
        )
        self.assertEqual(strip_trace(machine.text), "23\n")

    def test_trace_does_not_change_the_program(self) -> None:
        source = FIB + FACTORIAL + "print(fib(6));\nprint(factorial(5));"
        _, plain = run(source)
        _, traced = run(source, trace=True)
        # Sin las líneas de la traza, la salida es idéntica.
        self.assertEqual(strip_trace(traced.text), plain.text)
        self.assertEqual(traced.get("$sp"), TinyMips.STACK_TOP)
        self.assertEqual(traced.get("$fp"), TinyMips.STACK_TOP)

    def test_return_value_survives_the_exit_trace(self) -> None:
        root, machine = traced_tree(FACTORIAL + "print(factorial(6));")
        self.assertEqual(strip_trace(machine.text), "720\n")


class TraceCodeTests(unittest.TestCase):
    def test_no_trace_by_default(self) -> None:
        t = Translation(FACTORIAL + "print(factorial(3));")
        self.assertFalse(any(".asciiz" in line for line in t.translator.data_lines()))
        self.assertNotIn("syscall", t.functions["factorial"])

    def test_trace_strings_in_data(self) -> None:
        t = Translation(FACTORIAL + "print(factorial(3));", trace=True)
        data = t.translator.data_lines()
        self.assertIn('fn_factorial_entra: .asciiz "#>factorial"', data)
        self.assertIn('fn_factorial_sale: .asciiz "#<factorial\\n"', data)

    def test_this_is_not_printed_and_other_types_print_a_question_mark(self) -> None:
        source = """
class Caja {
  let v: integer;
  function guardar(k: integer, nombre: string, ok: boolean) { this.v = k; }
}
let c: Caja = new Caja();
c.guardar(1, "a", true);
"""
        lines = Translation(source, trace=True).functions["Caja.guardar"]
        start, end = lines.index("# traza: entrada"), lines.index("li $a0, 10")
        enter = lines[start:end]
        self.assertEqual(enter.count("li $a0, 32"), 3)  # un espacio por parámetro, sin this
        self.assertEqual(enter.count("li $a0, 63"), 1)  # «?» para la cadena
        self.assertNotIn("lw $a0, -16($fp)", enter)  # this está en -16($fp)

    def test_exit_trace_keeps_v0(self) -> None:
        lines = Translation(FACTORIAL + "print(factorial(3));", trace=True).functions["factorial"]
        exit_ = lines[lines.index("fn_factorial_fin:") + 1:lines.index("lw $ra, -4($fp)")]
        self.assertEqual(exit_[1], "move $v1, $v0")
        self.assertEqual(exit_[-1], "move $v0, $v1")

    def test_trace_labels_do_not_collide(self) -> None:
        source = "function f(): integer { return 1; }\nfunction f_entra(): integer { return 2; }\nprint(f() + f_entra());"
        t = Translation(source, trace=True)
        labels = [line.split(":")[0] for line in t.translator.data_lines() if ".asciiz" in line]
        functions = [frame.label for frame in t.model.frames.values()]
        self.assertEqual(len(set(labels) | set(functions)), len(labels) + len(functions))


class TraceParsingTests(unittest.TestCase):
    def test_trace_glued_to_program_output(self) -> None:
        root = build_activation_tree("5#>f 1\n7#<f\n")
        self.assertEqual(root.children[0].label, "f(1)")
        self.assertEqual(strip_trace("5#>f 1\n7#<f\n"), "57")

    def test_exit_without_enter(self) -> None:
        with self.assertRaises(ActivationTraceError):
            build_activation_tree("#<f\n")

    def test_exit_of_another_function(self) -> None:
        with self.assertRaises(ActivationTraceError):
            build_activation_tree("#>f\n#>g\n#<f\n")

    def test_unfinished_execution(self) -> None:
        trace = "#>f 1\n#>g\n"
        with self.assertRaises(ActivationTraceError):
            build_activation_tree(trace)
        root = build_activation_tree(trace, strict=False)
        self.assertFalse(root.finished)
        self.assertEqual(
            render_activation_tree(root),
            "main\n└── f(1)  (sin terminar)\n    └── g()  (sin terminar)",
        )

    def test_method_names_with_dots_and_dollars(self) -> None:
        root = build_activation_tree("#>Animal.$init\n#<Animal.$init\n#>Perro.hablar 2 ?\n#<Perro.hablar\n")
        self.assertEqual([child.label for child in root.children], ["Animal.$init()", "Perro.hablar(2, ?)"])

    def test_empty_trace(self) -> None:
        root = build_activation_tree("hola\n")
        self.assertEqual(render_activation_tree(root), "main")
        self.assertEqual(root.depth, 0)
        self.assertTrue(re.fullmatch("hola\n", strip_trace("hola\n")))


if __name__ == "__main__":
    unittest.main()
