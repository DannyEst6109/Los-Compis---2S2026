"""Persona 3 · Sentencias de control en MIPS (rúbrica: 3 puntos).

Cubre condicionales, ciclos, ``break``/``continue``, estructuras anidadas,
``switch`` y cortocircuito: primero la forma del código (``mips_control``)
y después la ejecución real en MARS.
"""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mips_helpers import EXPECTED, EXAMPLES, MarsTestCase, compile_mips, instructions, needs_mars

from mips_control import ControlFlowTranslator
from mips_frames import FrameModel
from mips_registers import MipsRegisters
from mips_runtime import MipsGenerationError
from tac import Const, Label, TACInstruction, TACOp


def translator_for(source: str):
    result = compile_mips(source)
    registers = MipsRegisters(FrameModel(result.symbol_table))
    variable = next(instruction.result for instruction in result.tac if instruction.op is TACOp.ASSIGN)
    return ControlFlowTranslator(registers), registers, variable


class ControlTranslationTests(unittest.TestCase):
    def test_label_saves_registers_before_and_starts_clean(self) -> None:
        control, registers, x = translator_for("let x: integer = 1;")
        registers.assign_from(x, None, "$v0")  # x queda modificado en un registro
        lines = control.translate(TACInstruction(TACOp.LABEL, Label("L9")), None)
        self.assertEqual(lines, ["sw $t0, 0($gp)", "L9:"])
        # Después de la etiqueta el valor se vuelve a leer de memoria.
        self.assertEqual(registers.value_register(x, None)[0], ["lw $t0, 0($gp)"])

    def test_goto_saves_registers_and_jumps(self) -> None:
        control, registers, x = translator_for("let x: integer = 1;")
        registers.assign_from(x, None, "$v0")
        lines = control.translate(TACInstruction(TACOp.GOTO, Label("L3")), None)
        self.assertEqual(lines, ["sw $t0, 0($gp)", "j L3"])
        self.assertEqual(registers.spill(None), [])

    def test_conditional_branches(self) -> None:
        control, registers, x = translator_for("let x: boolean = true;")
        if_true = control.translate(TACInstruction(TACOp.IF_TRUE, Label("L1"), x), None)
        self.assertEqual(if_true, ["lbu $t0, 0($gp)", "bne $t0, $zero, L1"])
        if_false = control.translate(TACInstruction(TACOp.IF_FALSE, Label("L2"), x), None)
        # El camino que sigue de largo conserva el registro: no se vuelve a cargar.
        self.assertEqual(if_false, ["beq $t0, $zero, L2"])

    def test_branch_spills_modified_values_before_jumping(self) -> None:
        control, registers, x = translator_for("let x: boolean = true;")
        registers.assign_from(x, None, "$v0")
        lines = control.translate(TACInstruction(TACOp.IF_TRUE, Label("L1"), x), None)
        self.assertEqual(lines, ["sb $t0, 0($gp)", "bne $t0, $zero, L1"])

    def test_constant_conditions_are_resolved_at_compile_time(self) -> None:
        control, _registers, _x = translator_for("let x: integer = 1;")
        cases = [
            (TACOp.IF_TRUE, True, ["j L1"]),
            (TACOp.IF_TRUE, False, []),
            (TACOp.IF_FALSE, False, ["j L1"]),
            (TACOp.IF_FALSE, True, []),
        ]
        for op, value, expected in cases:
            with self.subTest(op=op, value=value):
                lines = control.translate(TACInstruction(op, Label("L1"), Const(value, "boolean")), None)
                self.assertEqual(instructions(lines), expected)
        self.assertEqual(control.folded, 4)

    def test_target_must_be_a_label(self) -> None:
        control, _registers, x = translator_for("let x: integer = 1;")
        with self.assertRaises(MipsGenerationError):
            control.translate(TACInstruction(TACOp.GOTO, x), None)

    def test_if_else_uses_tac_labels_and_jumps(self) -> None:
        result = compile_mips(
            "let x: integer = 11; let y: integer = 0;\n"
            "if (x > 10) { y = 1; } else { y = 2; }",
            optimize=False,
        )
        code = instructions(result.mips.lines)
        # if t1 goto L1: la condición quedó en el registro que eligió getReg().
        self.assertTrue(any(re.fullmatch(r"bne \$[ts]\d, \$zero, L1", line) for line in code), code)
        self.assertIn("j L2", code)  # goto L2 (rama else)
        self.assertIn("j L3", code)  # fin del if
        for label in ("L1:", "L2:", "L3:"):
            self.assertIn(label, result.mips.lines)

    def test_nested_loops_have_unique_defined_labels(self) -> None:
        result = compile_mips(
            "for (let i = 0; i < 3; i = i + 1) { let j = 0; while (j < 3) { j = j + 1; "
            "if (j == 2) { continue; } if (i == j) { break; } } }"
        )
        defined = [line[:-1] for line in result.mips.lines if re.fullmatch(r"L\d+:", line)]
        self.assertEqual(len(defined), len(set(defined)))
        targets = re.findall(r"(?:j|beq|bne)\s.*?\b(L\d+)$", "\n".join(result.mips.lines), re.MULTILINE)
        self.assertTrue(set(targets) <= set(defined), set(targets) - set(defined))


@needs_mars
class ControlExecutionTests(MarsTestCase):
    def test_if_else_chain(self) -> None:
        self.assert_runs(
            """
            function signo(n: integer): integer {
              if (n > 0) { return 1; } else { if (n < 0) { return -1; } }
              return 0;
            }
            let x: integer = 15; let y: integer = 0;
            if (x > 10) { y = 1; } else { y = 2; }
            print(y);
            if (x < 10) { y = 1; } else { y = 2; }
            print(y);
            print(signo(-8)); print(signo(0)); print(signo(4));
            """,
            "1\n2\n-1\n0\n1",
        )

    def test_nested_conditions_and_short_circuit(self) -> None:
        self.assert_runs(
            """
            function verdad(n: integer): boolean { print(n); return true; }
            function falso(n: integer): boolean { print(n); return false; }
            if (falso(1) && verdad(2)) { print(0); }
            if (verdad(3) || falso(4)) { print(5); }
            if (!(falso(6) || falso(7)) && verdad(8)) {
              if (verdad(9) && !falso(10)) { print(11); } else { print(0); }
            }
            let m = 4 > 3 ? (2 > 1 ? 12 : 0) : 0;
            print(m);
            """,
            "1\n3\n5\n6\n7\n8\n9\n10\n11\n12",
        )

    def test_while_do_while_and_for(self) -> None:
        self.assert_runs(
            """
            let i = 0; let s = 0;
            while (i < 100) { s = s + i; i = i + 1; }
            print(s);
            do { i = i - 30; } while (i > 0);
            print(i);
            let p = 1;
            for (let k = 0; k < 10; k = k + 1) { p = p * 2; }
            print(p);
            do { print(7); } while (false);
            while (false) { print(0); }
            """,
            "4950\n-20\n1024\n7",
        )

    def test_break_and_continue_in_nested_loops(self) -> None:
        self.assert_runs(
            """
            let cuenta = 0;
            for (let a = 0; a < 10; a = a + 1) {
              if (a == 7) { break; }
              if (a % 2 == 1) { continue; }
              let b = 0;
              while (true) {
                b = b + 1;
                if (b > a) { break; }
                if (b == 2) { continue; }
                cuenta = cuenta + 1;
              }
            }
            print(cuenta);
            """,
            # a = 0, 2, 4, 6 -> b recorre 1..a sin el 2: 0 + 1 + 3 + 5
            "9",
        )

    def test_foreach_with_break_continue_and_nested_arrays(self) -> None:
        self.assert_runs(
            """
            let m: integer[][] = [[1, 2, 3], [4, 5, 6], [7, 8, 9]];
            let s = 0;
            foreach (fila in m) {
              foreach (v in fila) {
                if (v % 2 == 0) { continue; }
                if (v > 7) { break; }
                s = s + v;
              }
            }
            print(s);
            let vacio: integer[] = [];
            foreach (v in vacio) { print(v); }
            """,
            "16",
        )

    def test_switch_fall_through_default_and_no_match(self) -> None:
        self.assert_runs(
            """
            function nombre(n: integer) {
              switch (n) {
                case 1: print("uno");
                case 2: print("dos"); break;
                case 3: print("tres"); break;
                default: print("otro");
              }
            }
            nombre(1); nombre(2); nombre(3); nombre(9);
            switch (5) { case 1: print("nunca"); }
            for (let k = 0; k < 4; k = k + 1) {
              switch (k % 2) { case 0: continue; default: print(k); }
            }
            """,
            "uno\ndos\ndos\ntres\notro\n1\n3",
        )

    def test_many_iterations_keep_the_stack_balanced(self) -> None:
        self.assert_runs(
            """
            function f(n: integer): integer { if (n % 3 == 0) { return n; } return 0; }
            let total = 0;
            for (let i = 0; i < 3000; i = i + 1) { total = total + f(i); }
            print(total);
            """,
            "1498500",
        )

    def test_control_example_file(self) -> None:
        source = (EXAMPLES / "mips_control_flujo.cps").read_text(encoding="utf-8")
        expected = (EXPECTED / "mips_control_flujo.txt").read_text(encoding="utf-8").rstrip("\n")
        self.assert_runs(source, expected)


if __name__ == "__main__":
    unittest.main()
