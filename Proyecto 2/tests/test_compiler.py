"""Pruebas de integración: código fuente -> diagnósticos o TAC, a través
del mismo pipeline que usa el IDE (``compiler.compile_source``)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "src"))

from compiler import GENERATION_KIND, compile_source  # noqa: E402
from tac import Label, Name, TACOp, Var  # noqa: E402
from tac_generator import TACGenerationError  # noqa: E402

EXAMPLES = PROJECT / "examples"
VALID_EXAMPLES = sorted(
    [*EXAMPLES.glob("valido_*.cps"), *(path for path in EXAMPLES.glob("tac_*.cps") if "errores" not in path.name)]
)
INVALID_EXAMPLES = sorted([*EXAMPLES.glob("errores_*.cps"), *EXAMPLES.glob("tac_*errores*.cps")])


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


class ValidProgramTests(unittest.TestCase):
    def test_examples_are_classified(self) -> None:
        self.assertGreaterEqual(len(VALID_EXAMPLES), 7)
        self.assertGreaterEqual(len(INVALID_EXAMPLES), 10)

    def test_every_valid_example_produces_well_formed_tac(self) -> None:
        for path in VALID_EXAMPLES:
            with self.subTest(example=path.name):
                result = compile_source(read(path))
                self.assertEqual(result.diagnostics, [])
                self.assertTrue(result.succeeded)
                self.assert_well_formed(result)

    def assert_well_formed(self, result) -> None:
        instructions = list(result.tac)
        self.assertGreater(len(instructions), 0)
        table = result.symbol_table

        # Las funciones no se anidan ni se intercalan con el código global.
        open_function = None
        for instruction in instructions:
            if instruction.op is TACOp.BEGIN_FUNC:
                self.assertIsNone(open_function)
                open_function = instruction.arg1
                record = table.record(str(instruction.arg1))
                self.assertIsNotNone(record, instruction)
                self.assertEqual(instruction.arg2.value, record.size)
            elif instruction.op is TACOp.END_FUNC:
                self.assertEqual(instruction.arg1, open_function)
                open_function = None
        self.assertIsNone(open_function)

        # Etiquetas únicas y todo salto apunta a una etiqueta existente.
        labels = [i.result for i in instructions if i.op is TACOp.LABEL]
        self.assertEqual(len(labels), len(set(labels)))
        for instruction in instructions:
            if instruction.op in (TACOp.GOTO, TACOp.IF_TRUE, TACOp.IF_FALSE, TACOp.TRY_BEGIN):
                self.assertIn(instruction.result, labels)

        # Cada call directo apunta a una función con registro de activación.
        for instruction in instructions:
            if instruction.op is TACOp.CALL and isinstance(instruction.arg1, Name):
                self.assertIsNotNone(table.record(str(instruction.arg1)), instruction)

        # Toda variable del programa usada en el TAC tiene una dirección.
        for instruction in instructions:
            for operand in (instruction.result, instruction.arg1, instruction.arg2):
                if isinstance(operand, Var) and operand.symbol is not None:
                    self.assertIsNotNone(operand.symbol.address, operand)

        # Cada instrucción conserva una línea válida del código fuente.
        line_count = result.analysis.line_count
        for instruction in instructions:
            self.assertIsNotNone(instruction.line)
            self.assertTrue(1 <= instruction.line <= line_count, instruction)

    def test_full_example_contains_every_feature(self) -> None:
        result = compile_source(read(EXAMPLES / "valido_completo.cps"))
        lines = result.tac.lines()
        for expected in [
            "begin_func Animal.constructor, 20",
            "begin_func Perro.hablar, 20",
            "t1 = call factorial, 1",
            "begin_func siguiente, 12",
            "t1 = new Perro",
            "call Animal.constructor, 2",
            "t1 = method perro.hablar",
            "try_begin L31",
            "err = exception",
            "t1 = new_array 3",
            "nota = t1[t2]",
        ]:
            self.assertIn(expected, lines)

    def test_temporary_usage_is_reported_per_unit(self) -> None:
        result = compile_source(read(EXAMPLES / "tac_funciones.cps"))
        units = [usage.unit for usage in result.temp_usage]
        self.assertEqual(units[-1], "global")
        self.assertIn("factorial", units)
        self.assertTrue(all(usage.reuses >= 0 and usage.created <= usage.allocations for usage in result.temp_usage))

    def test_render_separates_functions_with_a_blank_line(self) -> None:
        result = compile_source("function f() { print(1); } f();")
        self.assertEqual(result.tac.render(), "begin_func f, 12\n    print 1\nend_func f\n\n    call f, 0")
        rendered = result.tac.rendered_lines()
        self.assertIsNone(rendered[3][1])
        self.assertIs(rendered[4][1].op, TACOp.CALL)

    def test_compiling_twice_gives_the_same_result(self) -> None:
        source = read(EXAMPLES / "tac_clases.cps")
        self.assertEqual(compile_source(source).tac.lines(), compile_source(source).tac.lines())


class InvalidProgramTests(unittest.TestCase):
    def test_no_tac_for_any_invalid_example(self) -> None:
        for path in INVALID_EXAMPLES:
            with self.subTest(example=path.name):
                result = compile_source(read(path))
                self.assertGreater(len(result.diagnostics), 1)
                self.assertIsNone(result.tac)
                self.assertFalse(result.succeeded)

    def test_diagnostics_are_merged_and_sorted(self) -> None:
        result = compile_source("let a: integer = \"x\";\nlet b = @;\nprint(c);")
        kinds = {diagnostic.kind for diagnostic in result.diagnostics}
        self.assertTrue({"Léxico", "Semántico"} <= kinds)
        positions = [(d.line, d.column) for d in result.diagnostics]
        self.assertEqual(positions, sorted(positions))

    def test_generation_failure_is_reported_without_partial_tac(self) -> None:
        def failing_generate(self, program):
            self.emit(TACOp.PRINT, arg1=Label("parcial"))
            raise TACGenerationError(program.statements[0], "fallo simulado")

        with mock.patch("tac_generator.TACGenerator.generate", failing_generate):
            result = compile_source("let x = 1;\nprint(x);")
        self.assertIsNone(result.tac)
        self.assertEqual(len(result.diagnostics), 1)
        diagnostic = result.diagnostics[0]
        self.assertEqual((diagnostic.kind, diagnostic.line, diagnostic.description), (GENERATION_KIND, 1, "fallo simulado"))

    def test_empty_program_compiles_to_empty_tac(self) -> None:
        result = compile_source("// sólo un comentario\n")
        self.assertTrue(result.succeeded)
        self.assertEqual(len(result.tac), 0)


if __name__ == "__main__":
    unittest.main()
