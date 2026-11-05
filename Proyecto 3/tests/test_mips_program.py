"""Pruebas del punto de entrada y del área global (``main_program`` y
``data_lines`` de ``mips_functions.py``)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "src"))
sys.path.insert(0, str(PROJECT / "tests"))

from mips_doubles import MemoryRegisters, TinyMips, Translation, format_assembly, run  # noqa: E402
from mips_functions import FunctionTranslator, MipsFunctionError  # noqa: E402
from tac import Const, Name, TACInstruction, TACOp  # noqa: E402

PROGRAM = """
function suma(a: integer, b: integer): integer { return a + b; }
let x: integer = 40;
let listo: boolean = true;
x = suma(x, 2);
print(x);
"""


class MainProgramTests(unittest.TestCase):
    def setUp(self) -> None:
        self.t = Translation(PROGRAM)

    def test_entry_sets_gp_and_fp_and_exit_ends_the_program(self) -> None:
        lines = self.t.translator.main_program(["# cuerpo"])
        self.assertEqual(
            lines,
            [
                "# código global",
                ".globl main",
                "main:",
                "la $gp, globales",
                "move $fp, $sp",
                "# cuerpo",
                "# fin del programa",
                "li $v0, 10",
                "syscall",
            ],
        )

    def test_main_goes_before_the_functions(self) -> None:
        program = self.t.program()
        self.assertLess(program.index(".data"), program.index(".text"))
        self.assertLess(program.index("main:"), program.index("fn_suma:"))
        self.assertEqual(program.count("main:"), 1)

    def test_open_function_or_pending_params(self) -> None:
        translator = FunctionTranslator(self.t.model, MemoryRegisters(self.t.model))
        translator.begin_function(TACInstruction(TACOp.BEGIN_FUNC, None, Name("suma")))
        with self.assertRaises(MipsFunctionError):
            translator.main_program([])
        translator = FunctionTranslator(self.t.model, MemoryRegisters(self.t.model))
        translator.translate_param(TACInstruction(TACOp.PARAM, None, Const(1, "integer")))
        with self.assertRaises(MipsFunctionError):
            translator.main_program([])


class GlobalAreaTests(unittest.TestCase):
    def test_global_area_has_the_size_of_the_global_record(self) -> None:
        t = Translation(PROGRAM)
        size = t.model.global_area.size  # x (4) + listo (1, alineado) + t1 (4)
        self.assertEqual(size, 12)
        self.assertEqual(
            t.translator.data_lines(),
            ["# área global: variables y temporales del código global", ".align 2", "globales: .space 12"],
        )

    def test_empty_global_area_still_reserves_a_word(self) -> None:
        t = Translation("function nada() { }\nnada();")
        self.assertEqual(t.model.global_area.size, 0)
        self.assertIn("globales: .space 4", t.translator.data_lines())

    def test_globals_live_in_the_global_area(self) -> None:
        translation, machine = run(PROGRAM)
        self.assertEqual(machine.output, [42])
        base = machine.data_labels["globales"]
        self.assertEqual(machine.get("$gp"), base)
        self.assertEqual(machine.read(base, 4), 42)  # x en globales+0
        self.assertEqual(machine.read(base + 4, 1), 1)  # listo en globales+4

    def test_stack_and_frame_pointers_start_and_end_at_the_top(self) -> None:
        _, machine = run(PROGRAM)
        self.assertEqual(machine.get("$sp"), TinyMips.STACK_TOP)
        self.assertEqual(machine.get("$fp"), TinyMips.STACK_TOP)


class AssemblyFormatTests(unittest.TestCase):
    def test_labels_and_sections_are_flush_and_instructions_indented(self) -> None:
        text = format_assembly(Translation(PROGRAM).program())
        lines = text.splitlines()
        for flush in (".data", ".text", "main:", "fn_suma:", "fn_suma_fin:", "globales: .space 12"):
            self.assertIn(flush, lines)
        self.assertIn("    la $gp, globales", lines)
        self.assertIn("    jr $ra", lines)


if __name__ == "__main__":
    unittest.main()
