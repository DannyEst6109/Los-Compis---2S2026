"""Pruebas de ejecución de funciones, parámetros, valores de retorno y
recursividad.

Cada programa se compila a TAC, se traduce a MIPS y se ejecuta en
``TinyMips`` (``mips_doubles.py``). Se compara lo que imprime y se revisa que
``$sp`` y ``$fp`` terminen exactamente como empezaron. Las instrucciones que
no son de Persona 1 (aritmética, comparaciones, saltos, ``print``) las
traduce un doble de prueba mínimo; el código real de Persona 2 y 3 lo
reemplazará, y las pruebas definitivas se harán en MARS."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "src"))
sys.path.insert(0, str(PROJECT / "tests"))

from mips_doubles import SimulationError, TinyMips, run  # noqa: E402


class RuntimeTestCase(unittest.TestCase):
    def assertRuns(self, source: str, expected: list[int]) -> TinyMips:
        """Ejecuta ``source`` y revisa la salida y la restauración de la pila."""
        _, machine = run(source)
        self.assertEqual(machine.output, expected)
        self.assertEqual(machine.get("$sp"), TinyMips.STACK_TOP, "$sp no volvió a su valor inicial")
        self.assertEqual(machine.get("$fp"), TinyMips.STACK_TOP, "$fp no volvió a su valor inicial")
        return machine


class SimpleFunctionTests(RuntimeTestCase):
    def test_function_without_parameters(self) -> None:
        self.assertRuns("function cinco(): integer { return 5; }\nprint(cinco());", [5])

    def test_procedure(self) -> None:
        self.assertRuns(
            "function mostrar(v: integer) { print(v); }\nmostrar(7);\nmostrar(8);",
            [7, 8],
        )

    def test_procedure_with_explicit_return(self) -> None:
        source = """
function primero(a: integer, b: integer) {
  if (a < b) { print(a); return; }
  print(b);
}
primero(1, 2);
primero(9, 3);
"""
        self.assertRuns(source, [1, 3])


class ParameterTests(RuntimeTestCase):
    def test_parameters_and_return_value(self) -> None:
        source = "function suma(a: integer, b: integer): integer { return a + b; }\nprint(suma(2, 3));"
        self.assertRuns(source, [5])

    def test_argument_order(self) -> None:
        source = """
function resta(a: integer, b: integer): integer { return a - b; }
print(resta(10, 3));
print(resta(3, 10));
"""
        self.assertRuns(source, [7, -7])

    def test_more_than_four_parameters(self) -> None:
        source = """
function mezcla(a: integer, b: integer, c: integer, d: integer, e: integer, f: integer): integer {
  return a - b + c - d + e - f;
}
print(mezcla(100, 1, 20, 3, 40, 5));
"""
        self.assertRuns(source, [151])

    def test_boolean_parameters(self) -> None:
        source = """
function elegir(c: boolean, a: integer, d: boolean, b: integer): integer {
  if (c) { return a; }
  if (d) { return b; }
  return 0;
}
print(elegir(true, 1, false, 2));
print(elegir(false, 1, true, 2));
print(elegir(false, 1, false, 2));
"""
        self.assertRuns(source, [1, 2, 0])

    def test_parameters_are_passed_by_value(self) -> None:
        source = """
function cambia(x: integer): integer { x = x + 100; return x; }
let v: integer = 1;
print(cambia(v));
print(v);
"""
        self.assertRuns(source, [101, 1])

    def test_locals_are_private_to_each_call(self) -> None:
        source = """
function cuadrado(n: integer): integer {
  let r: integer = n * n;
  return r;
}
print(cuadrado(3) + cuadrado(4));
"""
        self.assertRuns(source, [25])

    def test_globals_modified_inside_a_function(self) -> None:
        source = """
let g: integer = 0;
function sube(k: integer) { g = g + k; }
sube(2);
sube(5);
print(g);
"""
        self.assertRuns(source, [7])


class CallCombinationTests(RuntimeTestCase):
    def test_consecutive_calls(self) -> None:
        source = """
function suma(a: integer, b: integer): integer { return a + b; }
print(suma(1, 2));
print(suma(3, 4));
let x: integer = suma(10, 20);
let y: integer = suma(x, x);
print(y);
"""
        self.assertRuns(source, [3, 7, 60])

    def test_nested_calls_as_arguments(self) -> None:
        source = """
function doble(x: integer): integer { return x * 2; }
function inc(x: integer): integer { return x + 1; }
function suma(a: integer, b: integer): integer { return a + b; }
print(doble(inc(doble(3))));
print(suma(doble(2), suma(inc(1), doble(5))));
"""
        self.assertRuns(source, [14, 16])

    def test_function_calling_other_functions(self) -> None:
        source = """
function cuadrado(n: integer): integer { return n * n; }
function suma_cuadrados(a: integer, b: integer): integer { return cuadrado(a) + cuadrado(b); }
function hipotenusa2(a: integer, b: integer): integer { return suma_cuadrados(a, b); }
print(hipotenusa2(3, 4));
"""
        self.assertRuns(source, [25])


class RecursionTests(RuntimeTestCase):
    FACTORIAL = """
function factorial(n: integer): integer {
  if (n <= 1) { return 1; }
  return n * factorial(n - 1);
}
"""

    def test_factorial(self) -> None:
        self.assertRuns(self.FACTORIAL + "print(factorial(1));\nprint(factorial(5));\nprint(factorial(10));",
                        [1, 120, 3628800])

    def test_each_call_has_its_own_activation_record(self) -> None:
        """factorial(5) anida 5 activaciones; cada una ocupa su marco completo
        en la pila, sin pisar el de la anterior."""
        translation, machine = run(self.FACTORIAL + "print(factorial(5));")
        frame = translation.model.frame("factorial").size
        self.assertEqual(machine.stack_used, 5 * frame)
        self.assertEqual(machine.output, [120])

    def test_two_recursive_calls(self) -> None:
        source = """
function fib(n: integer): integer {
  if (n < 2) { return n; }
  return fib(n - 1) + fib(n - 2);
}
print(fib(0));
print(fib(1));
print(fib(10));
"""
        machine = self.assertRuns(source, [0, 1, 55])
        self.assertGreater(machine.calls, 170)  # fib(10) solo hace 177 llamadas

    def test_recursion_with_several_parameters(self) -> None:
        source = """
function potencia(b: integer, e: integer): integer {
  if (e == 0) { return 1; }
  return b * potencia(b, e - 1);
}
function ackermann(m: integer, n: integer): integer {
  if (m == 0) { return n + 1; }
  if (n == 0) { return ackermann(m - 1, 1); }
  return ackermann(m - 1, ackermann(m, n - 1));
}
print(potencia(2, 10));
print(potencia(3, 4));
print(ackermann(2, 3));
"""
        self.assertRuns(source, [1024, 81, 9])

    def test_mutual_recursion(self) -> None:
        source = """
function esPar(n: integer): boolean {
  if (n == 0) { return true; }
  return esImpar(n - 1);
}
function esImpar(n: integer): boolean {
  if (n == 0) { return false; }
  return esPar(n - 1);
}
if (esPar(10)) { print(1); } else { print(0); }
if (esPar(7)) { print(1); } else { print(0); }
"""
        self.assertRuns(source, [1, 0])

    def test_recursion_inside_an_expression_keeps_the_caller_values(self) -> None:
        source = """
function suma_hasta(n: integer): integer {
  if (n == 0) { return 0; }
  let antes: integer = n;
  let resto: integer = suma_hasta(n - 1);
  return antes + resto;
}
print(suma_hasta(100));
"""
        self.assertRuns(source, [5050])


class NestedFunctionTests(RuntimeTestCase):
    def test_access_links_reach_outer_variables(self) -> None:
        source = """
function externo(x: integer): integer {
  let y: integer = 1;
  function primero(): integer { return x; }
  function segundo(): integer { return primero() + y; }
  function cuenta(n: integer): integer {
    if (n <= 0) { return 0; }
    return cuenta(n - 1) + 1;
  }
  function medio(): integer {
    function interno(): integer { return segundo() + x; }
    return interno();
  }
  return medio() + cuenta(3) + segundo();
}
print(externo(3));
print(externo(5));
"""
        self.assertRuns(source, [14, 20])  # 3x + 5

    def test_nested_function_modifies_an_outer_variable(self) -> None:
        source = """
function contador(veces: integer): integer {
  let c: integer = 0;
  function inc() { c = c + 1; }
  function repetir(n: integer) {
    if (n == 0) { return; }
    inc();
    repetir(n - 1);
  }
  repetir(veces);
  return c;
}
print(contador(4));
print(contador(0));
"""
        self.assertRuns(source, [4, 0])

    def test_nested_function_sees_the_right_activation(self) -> None:
        """Cada activación recursiva de ``externo`` tiene su propio ``x``; la
        función anidada ve el de la activación que la llamó."""
        source = """
function externo(x: integer): integer {
  function leer(): integer { return x; }
  if (x == 0) { return 0; }
  return leer() + externo(x - 1);
}
print(externo(4));
"""
        self.assertRuns(source, [10])


class StackPointerTests(RuntimeTestCase):
    def test_stack_is_empty_between_calls(self) -> None:
        """Después de cada llamada del código global, $sp vuelve a su valor."""
        source = """
function suma(a: integer, b: integer): integer { return a + b; }
function nada() { }
print(suma(1, 2));
nada();
print(suma(3, 4));
"""
        translation, machine = run(source)
        self.assertEqual(machine.output, [3, 7])
        self.assertEqual(machine.get("$sp"), TinyMips.STACK_TOP)
        # La pila nunca usa más que el marco más grande de una sola llamada.
        largest = max(frame.size for frame in translation.model.frames.values())
        self.assertEqual(machine.stack_used, largest)

    def test_deep_recursion_restores_the_stack(self) -> None:
        source = """
function baja(n: integer): integer {
  if (n == 0) { return 0; }
  return baja(n - 1);
}
print(baja(500));
"""
        machine = self.assertRuns(source, [0])
        self.assertGreater(machine.stack_used, 500 * 12)


class SimulatorSanityTests(unittest.TestCase):
    """El simulador de prueba detecta los errores que debe detectar."""

    def test_reading_unwritten_memory_fails(self) -> None:
        with self.assertRaises(SimulationError):
            TinyMips(["lw $t0, -4($sp)"]).run()

    def test_misaligned_word_fails(self) -> None:
        with self.assertRaises(SimulationError):
            TinyMips(["sw $zero, -3($sp)"]).run()

    def test_unknown_label_fails(self) -> None:
        with self.assertRaises(SimulationError):
            TinyMips(["jal fn_noExiste"]).run()

    def test_falling_out_of_the_code_fails(self) -> None:
        with self.assertRaises(SimulationError):
            TinyMips(["li $t0, 1"]).run()


if __name__ == "__main__":
    unittest.main()
