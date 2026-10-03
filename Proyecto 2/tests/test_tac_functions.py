"""Pruebas de la traducción de funciones, parámetros, return, llamadas y
recursión. Inspeccionan el TAC; no ejecutan el programa."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "src"))

import ast_nodes as ast  # noqa: E402
from compiler import compile_source  # noqa: E402
from symbol_table import SymbolTable  # noqa: E402
from tac import TACOp  # noqa: E402
from tac_generator import TACGenerationError, TACGenerator, prepare_generator  # noqa: E402

SPAN = ast.SourceSpan.unknown()


def compile_ok(source: str):
    result = compile_source(source)
    assert result.succeeded, result.diagnostics
    return result


def tac_lines(source: str) -> list[str]:
    return compile_ok(source).tac.lines()


def section(lines: list[str], label: str) -> list[str]:
    """Cuerpo de la función ``label`` (sin begin_func/end_func)."""
    start = next(i for i, line in enumerate(lines) if line.startswith(f"begin_func {label},"))
    end = lines.index(f"end_func {label}")
    return lines[start + 1:end]


def global_code(lines: list[str]) -> list[str]:
    last_end = max((i for i, line in enumerate(lines) if line.startswith("end_func")), default=-1)
    return lines[last_end + 1:]


class FunctionDefinitionTests(unittest.TestCase):
    def test_function_with_parameters_and_return(self) -> None:
        self.assertEqual(
            tac_lines("function suma(a: integer, b: integer): integer { return a + b; }"),
            ["begin_func suma, 24", "t1 = a + b", "return t1", "end_func suma"],
        )

    def test_procedure_without_return_value(self) -> None:
        self.assertEqual(
            tac_lines("function hola() { print(\"hola\"); return; }"),
            ["begin_func hola, 12", 'print "hola"', "return", "end_func hola"],
        )

    def test_local_variables_are_assigned_in_the_body(self) -> None:
        lines = tac_lines("function f(a: integer): integer { let b: integer = a * 2; return b; }")
        self.assertEqual(section(lines, "f"), ["t1 = a * 2", "b = t1", "return b"])

    def test_functions_are_emitted_before_global_code(self) -> None:
        lines = tac_lines("let x = 1; function f(): integer { return 2; } print(f());")
        self.assertEqual(lines[0], "begin_func f, 12")
        self.assertEqual(global_code(lines), ["x = 1", "t1 = call f, 0", "print t1"])

    def test_nested_function_is_a_separate_section_after_its_parent(self) -> None:
        lines = tac_lines(
            "function externo(n: integer): integer {"
            "  function interno(k: integer): integer { return k + n; }"
            "  return interno(n);"
            "}"
        )
        self.assertEqual(
            [line for line in lines if line.startswith(("begin_func", "end_func"))],
            ["begin_func externo, 20", "end_func externo", "begin_func interno, 20", "end_func interno"],
        )
        self.assertEqual(section(lines, "externo"), ["param n", "t1 = call interno, 1", "return t1"])
        # La función anidada lee directamente las variables de su entorno.
        self.assertEqual(section(lines, "interno"), ["t1 = k + n", "return t1"])

    def test_each_function_has_its_own_temporaries(self) -> None:
        result = compile_ok(
            "function f(a: integer): integer { return (a + 1) * (a + 2); }"
            "let x = 1 + f(2) * 3;"
        )
        lines = result.tac.lines()
        self.assertEqual(section(lines, "f"), ["t1 = a + 1", "t2 = a + 2", "t1 = t1 * t2", "return t1"])
        # El temporal t1 del código global sigue vivo durante la llamada:
        # vive en otro registro de activación, así que no hay conflicto.
        self.assertEqual(global_code(lines), ["param 2", "t1 = call f, 1", "t1 = t1 * 3", "t1 = 1 + t1", "x = t1"])
        units = {usage.unit: usage for usage in result.temp_usage}
        self.assertEqual((units["f"].created, units["global"].created), (2, 1))

    def test_labels_are_unique_across_functions(self) -> None:
        lines = tac_lines(
            "function a(x: integer) { if (x > 0) { print(x); } }"
            "function b(x: integer) { while (x > 0) { x = x - 1; } }"
            "if (true) { a(1); }"
        )
        labels = [line for line in lines if line.endswith(":")]
        self.assertEqual(len(labels), len(set(labels)))

    def test_loop_contexts_do_not_leak_into_functions(self) -> None:
        lines = tac_lines(
            "while (true) {"
            "  function f() { while (false) { break; } }"
            "  f();"
            "  break;"
            "}"
        )
        body = section(lines, "f")
        inner_end = body[-1]
        self.assertTrue(inner_end.endswith(":"))
        self.assertIn(f"goto {inner_end[:-1]}", body)
        main = global_code(lines)
        self.assertEqual(main[-1], "L3:")
        self.assertIn("goto L3", main[:-2])  # el break global sale del while global

    def test_instructions_keep_their_source_line(self) -> None:
        result = compile_ok("function f(a: integer): integer {\n  let b = a + 1;\n  return b;\n}")
        lines = {str(instruction): instruction.line for instruction in result.tac}
        self.assertEqual(lines["begin_func f, 24"], 1)
        self.assertEqual(lines["t1 = a + 1"], 2)
        self.assertEqual(lines["return b"], 3)
        self.assertEqual(lines["end_func f"], 4)


class CallTests(unittest.TestCase):
    def test_call_with_result(self) -> None:
        lines = tac_lines("function f(a: integer, b: integer): integer { return a; } let x = f(1, 2);")
        self.assertEqual(global_code(lines), ["param 1", "param 2", "t1 = call f, 2", "x = t1"])

    def test_procedure_call_as_statement_has_no_destination(self) -> None:
        lines = tac_lines("function p() { print(1); } p();")
        self.assertEqual(global_code(lines), ["call p, 0"])

    def test_arguments_are_evaluated_before_the_params(self) -> None:
        lines = tac_lines(
            "function f(a: integer, b: integer): integer { return a; }"
            "function g(c: integer): integer { return c; }"
            "let y = 1; let x = f(y + 1, g(y * 2));"
        )
        self.assertEqual(
            global_code(lines)[1:],
            [
                "t1 = y + 1",
                "t2 = y * 2",
                "param t2",
                "t2 = call g, 1",
                "param t1",
                "param t2",
                "t1 = call f, 2",
                "x = t1",
            ],
        )

    def test_call_inside_condition(self) -> None:
        lines = tac_lines("function esPar(n: integer): boolean { return n % 2 == 0; } if (esPar(4)) { print(1); }")
        self.assertEqual(global_code(lines)[:4], ["param 4", "t1 = call esPar, 1", "if t1 goto L1", "goto L2"])

    def test_call_result_in_print_and_concatenation(self) -> None:
        lines = tac_lines('function n(): string { return "x"; } print("valor: " + n());')
        self.assertEqual(global_code(lines), ["t1 = call n, 0", 't1 = concat "valor: ", t1', "print t1"])

    def test_untyped_parameter_concatenation_uses_concat(self) -> None:
        lines = tac_lines('function saludar(nombre): string { return "Hola " + nombre; }')
        self.assertEqual(section(lines, "saludar"), ['t1 = concat "Hola ", nombre', "return t1"])

    def test_array_argument_and_return(self) -> None:
        lines = tac_lines(
            "function primero(xs: integer[]): integer { return xs[0]; } print(primero([4, 5]));"
        )
        self.assertEqual(section(lines, "primero"), ["t1 = xs[0]", "return t1"])
        self.assertEqual(
            global_code(lines),
            ["t1 = new_array 2", "t1[0] = 4", "t1[1] = 5", "param t1", "t1 = call primero, 1", "print t1"],
        )


class RecursionTests(unittest.TestCase):
    def test_factorial(self) -> None:
        lines = tac_lines(
            "function factorial(n: integer): integer {"
            "  if (n <= 1) { return 1; }"
            "  return n * factorial(n - 1);"
            "}"
            "print(factorial(5));"
        )
        self.assertEqual(
            lines,
            [
                "begin_func factorial, 20",
                "t1 = n <= 1",
                "if t1 goto L1",
                "goto L2",
                "L1:",
                "return 1",
                "L2:",
                "t1 = n - 1",
                "param t1",
                "t1 = call factorial, 1",
                "t1 = n * t1",
                "return t1",
                "end_func factorial",
                "param 5",
                "t1 = call factorial, 1",
                "print t1",
            ],
        )

    def test_two_recursive_calls_keep_the_first_result_alive(self) -> None:
        lines = tac_lines(
            "function fib(n: integer): integer {"
            "  if (n < 2) { return n; }"
            "  return fib(n - 1) + fib(n - 2);"
            "}"
        )
        self.assertEqual(
            section(lines, "fib")[-8:],
            ["t1 = n - 1", "param t1", "t1 = call fib, 1", "t2 = n - 2", "param t2", "t2 = call fib, 1",
             "t1 = t1 + t2", "return t1"],
        )

    def test_mutual_recursion_before_declaration(self) -> None:
        lines = tac_lines(
            "function esPar(n: integer): boolean { if (n == 0) { return true; } return esImpar(n - 1); }"
            "function esImpar(n: integer): boolean { if (n == 0) { return false; } return esPar(n - 1); }"
        )
        self.assertIn("t1 = call esImpar, 1", section(lines, "esPar"))
        self.assertIn("t1 = call esPar, 1", section(lines, "esImpar"))


class InvalidFunctionTests(unittest.TestCase):
    def test_semantic_errors_prevent_generation(self) -> None:
        for source in [
            "function f(a: integer): integer { return a; } f();",
            "function f(a: integer): integer { return a; } f(\"x\");",
            "function f(): string { return 1; }",
            "function f(): integer { return; }",
            "function f() { return 1; }",
            "return 1;",
            "noExiste(1);",
            "let x = 1; x();",
        ]:
            with self.subTest(source=source):
                result = compile_source(source)
                self.assertTrue(result.diagnostics)
                self.assertIsNone(result.tac)

    def test_error_example_reports_every_error(self) -> None:
        source = (PROJECT / "examples" / "tac_funciones_errores.cps").read_text(encoding="utf-8")
        result = compile_source(source)
        self.assertGreaterEqual(len(result.diagnostics), 8)
        self.assertIsNone(result.tac)

    def test_return_outside_function_rejected_when_semantics_is_bypassed(self) -> None:
        program = ast.Program(span=SPAN, statements=(ast.ReturnStatement(span=SPAN, value=None),))
        with self.assertRaisesRegex(TACGenerationError, "return"):
            TACGenerator(SymbolTable()).generate(program)

    def test_state_is_restored_when_a_function_fails(self) -> None:
        source = "while (true) { function f(): integer { return 1; } break; }"
        result = compile_ok(source)
        generator = prepare_generator(result.symbol_table, result.analysis.ast)

        def explode(_node):
            raise TACGenerationError(_node, "falla")

        generator.visit_return_statement = explode
        with self.assertRaises(TACGenerationError):
            generator.generate(result.analysis.ast)
        self.assertIsNone(generator._function)
        self.assertEqual(generator._control_stack, [])
        self.assertEqual(generator.temps.live_count, 0)


class ExampleTests(unittest.TestCase):
    def test_functions_example(self) -> None:
        result = compile_ok((PROJECT / "examples" / "tac_funciones.cps").read_text(encoding="utf-8"))
        lines = result.tac.lines()
        for label in ("suma", "factorial", "fibonacci", "esPar", "esImpar", "imprimirRango", "escalar", "aplicar"):
            self.assertTrue(any(line.startswith(f"begin_func {label},") for line in lines), label)
        self.assertEqual(sum(1 for i in result.tac if i.op is TACOp.BEGIN_FUNC), 8)
        self.assertEqual(
            sum(1 for i in result.tac if i.op is TACOp.BEGIN_FUNC),
            sum(1 for i in result.tac if i.op is TACOp.END_FUNC),
        )


if __name__ == "__main__":
    unittest.main()
