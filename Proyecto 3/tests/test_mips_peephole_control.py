"""Persona 3 · Optimización por mirilla de control de flujo
(``mips_peephole_control.py``), que complementa las reglas locales de
Persona 2 (rúbrica: al menos 6 transformaciones).

Cada regla se prueba sola, con sus límites (cuándo NO debe aplicarse), y
después se comprueba en MARS que el programa optimizado imprime lo mismo
que el original.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mips_helpers import EXAMPLES, compile_mips, needs_mars  # noqa: E402

from mars_runner import run_mars  # noqa: E402
from mips_generator import format_assembly, peephole_optimize  # noqa: E402
from mips_peephole_control import (  # noqa: E402
    BRANCH_OVER_JUMP,
    BRANCH_TO_NEXT,
    MOVE_BACK,
    REPEATED_LOAD,
    STORE_LOAD,
    THREADING,
    UNREACHABLE,
    UNUSED_LABEL,
    optimize_control_flow,
)


def optimize(code: list[str]) -> tuple[list[str], dict]:
    lines, report = optimize_control_flow([".text", *code])
    return lines[1:], dict(report.counts)


class RuleTests(unittest.TestCase):
    def test_1_jump_to_jump(self) -> None:
        code = ["j L1", "L2:", "li $t0, 1", "L1:", "# comentario", "j L3", "L3:", "li $t1, 2", "bne $t0, $zero, L1"]
        lines, counts = optimize(code)
        self.assertEqual(lines[0], "j L3")
        self.assertEqual(lines[-1], "bne $t0, $zero, L3")
        self.assertEqual(counts[THREADING], 2)

    def test_1_jump_cycles_do_not_loop_forever(self) -> None:
        lines, _ = optimize(["L1:", "j L2", "L2:", "j L1"])
        self.assertIn("j L1", lines)

    def test_2_conditional_branch_over_a_jump_is_inverted(self) -> None:
        lines, counts = optimize(["bne $t0, $zero, L1", "j L2", "L1:", "li $t1, 1", "L2:", "li $t1, 2", "j L1"])
        self.assertEqual(lines[:2], ["beq $t0, $zero, L2", "L1:"])
        self.assertEqual(counts[BRANCH_OVER_JUMP], 1)

    def test_2_needs_the_branch_target_right_after_the_jump(self) -> None:
        code = ["bne $t0, $zero, L1", "j L2", "L3:", "L1:", "li $t1, 1", "j L3", "L2:", "li $t2, 2"]
        lines, counts = optimize(code)
        self.assertNotIn(BRANCH_OVER_JUMP, counts)
        self.assertEqual(lines[1], "j L2")

    def test_3_unreachable_code_after_unconditional_jumps(self) -> None:
        code = ["j L1", "# t1 = x + 1", "addu $t0, $t0, $t1", "sw $t0, 0($gp)", "L1:", "jr $ra",
                "# end_func f", "li $t9, 1", "L2:", "li $t9, 2", "j L2"]
        lines, counts = optimize(code)
        self.assertEqual(lines, ["j L1", "L1:", "jr $ra", "# end_func f", "L2:", "li $t9, 2", "j L2"])
        self.assertEqual(counts[UNREACHABLE], 3)

    def test_4_unused_generated_labels(self) -> None:
        lines, counts = optimize(["L1:", "p2_local_4:", "p3_local_2:", "fn_f:", "main:", "la $t9, L1", "L5:", "j L5"])
        self.assertEqual(lines, ["L1:", "fn_f:", "main:", "la $t9, L1", "L5:", "j L5"])
        self.assertEqual(counts[UNUSED_LABEL], 2)

    def test_4_labels_used_only_in_data_are_kept(self) -> None:
        lines, _ = optimize_control_flow([".data", ".word L7", ".text", "L7:", "li $t0, 1"])
        self.assertIn("L7:", lines)

    def test_5_load_of_what_was_just_stored(self) -> None:
        lines, counts = optimize(["sw $t0, -8($fp)", "# comentario", "lw $t0, -8($fp)", "sw $t1, 4($gp)", "lw $t2, 4($gp)"])
        self.assertEqual(lines, ["sw $t0, -8($fp)", "# comentario", "sw $t1, 4($gp)", "move $t2, $t1"])
        self.assertEqual(counts[STORE_LOAD], 2)

    def test_5_not_across_labels_or_for_bytes(self) -> None:
        code = ["sw $t0, -8($fp)", "L1:", "lw $t0, -8($fp)", "sb $t1, 0($gp)", "lbu $t1, 0($gp)", "j L1"]
        lines, counts = optimize(code)
        self.assertEqual(lines, code)
        self.assertEqual(counts, {})

    def test_6_repeated_load(self) -> None:
        lines, counts = optimize(["lw $t0, 0($gp)", "lw $t0, 0($gp)", "lw $t1, 0($gp)"])
        self.assertEqual(lines, ["lw $t0, 0($gp)", "move $t1, $t0"])
        self.assertEqual(counts[REPEATED_LOAD], 2)

    def test_6_not_when_the_address_uses_the_loaded_register(self) -> None:
        code = ["lw $t0, 0($t0)", "lw $t0, 0($t0)"]
        self.assertEqual(optimize(code)[0], code)

    def test_7_move_back_and_forth(self) -> None:
        lines, counts = optimize(["move $t0, $t1", "move $t1, $t0", "move $t2, $t1"])
        self.assertEqual(lines, ["move $t0, $t1", "move $t2, $t1"])
        self.assertEqual(counts[MOVE_BACK], 1)

    def test_8_conditional_branch_to_the_next_instruction(self) -> None:
        lines, counts = optimize(["beq $t0, $zero, L4", "# comentario", "L3:", "L4:", "li $t0, 1", "j L3"])
        # L4 se queda sin uso y la regla 4 la quita en la misma ronda.
        self.assertEqual(lines, ["# comentario", "L3:", "li $t0, 1", "j L3"])
        self.assertEqual(counts[BRANCH_TO_NEXT], 1)

    def test_data_section_is_never_touched(self) -> None:
        data = [".data", "x: .word 0", "j L1", "L1:", ".text", "li $t0, 1"]
        self.assertEqual(optimize_control_flow(data)[0][:5], data[:5])


class CombinedOptimizationTests(unittest.TestCase):
    def test_rules_of_both_people_are_combined_until_nothing_changes(self) -> None:
        raw = [".text", "main:", "bne $t0, $zero, L1", "j L2", "L1:", "addiu $t1, $t1, 0", "j L3",
               "L2:", "j L3", "L3:", "li $v0, 10", "syscall"]
        lines, report = peephole_optimize(raw)
        # Las dos ramas terminan en L3 sin hacer nada: sólo queda la salida.
        self.assertEqual(lines, [".text", "main:", "li $v0, 10", "syscall"])
        self.assertGreaterEqual(len(report.counts), 4, report.counts)

    def test_examples_use_many_distinct_transformations(self) -> None:
        used = set()
        for path in sorted(EXAMPLES.glob("*.cps")):
            if "errores" in path.name:
                continue
            used |= set(compile_mips(path.read_text(encoding="utf-8")).mips.peephole.counts)
        # Varias reglas de control de flujo y las de Persona 2 aparecen en los ejemplos.
        self.assertGreaterEqual(len(used), 6, used)


@needs_mars
class PeepholePreservesBehaviourTests(unittest.TestCase):
    def test_optimized_and_raw_programs_print_the_same(self) -> None:
        for path in sorted(EXAMPLES.glob("mips_*.cps")):
            with self.subTest(example=path.name):
                program = compile_mips(path.read_text(encoding="utf-8")).mips
                raw, optimized = run_mars(format_assembly(program.raw_lines)), run_mars(program.text)
                self.assertEqual(raw.output, optimized.output)
                self.assertLess(program.instruction_count, program.raw_instruction_count)


if __name__ == "__main__":
    unittest.main()
